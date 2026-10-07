"""Micro paired eval: answer each skill's small tasks with and without the skill in one model call, then blind-judge each pair with another model."""

import hashlib
import json
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "tests" / "skill_tasks"
SKILLS_DIR = ROOT / "skills"
EVALS_DIR = SKILLS_DIR / "evals"
CACHE_DIR = ROOT / ".hve" / "evals" / "micro"
ENV_FILE = ROOT / ".env.local"
SCORE_MAX = 5
SYSTEM = "You are a senior software engineer. Answer the task directly and concretely in at most 250 words."
JUDGE_SYSTEM = ("You are a strict, impartial evaluator. You see a task, its checks, and two anonymous answers A and B. "
                "Judge only against the checks and overall usefulness; ignore length and style preferences. "
                'Reply with JSON only: {"a": {"checks_met": [<check numbers>], "score": <0-5>}, '
                '"b": {"checks_met": [<check numbers>], "score": <0-5>}, "reason": "<one sentence>"}')

Json = dict[str, Any]


def read_env() -> dict[str, str]:
    """Return the KEY=VALUE pairs of .env.local."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if line.strip() and not line.lstrip().startswith("#"))


def access_token() -> str:
    """Return an Entra token for Azure AI services from the signed-in Azure CLI (keyless)."""
    return subprocess.run("az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv",
                          shell=True, capture_output=True, text=True, check=True).stdout.strip()


class Client:
    """Chat-completions client for one Foundry endpoint that caches every response by request hash."""

    def __init__(self, endpoint: str, token: str, models: Json) -> None:
        """Store the endpoint, bearer token and per-model request parameters."""
        self.url = endpoint.rstrip("/") + "/openai/v1/chat/completions"
        self.token = token
        self.models = models
        self.spent = 0

    def chat(self, model: str, messages: list[Json]) -> Json:
        """Return {content, usage} for the request, from the cache when it was made before."""
        body = {"model": model, "messages": messages} | self.models[model]
        path = CACHE_DIR / f"{hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        request = urllib.request.Request(self.url, json.dumps(body).encode(), {"Authorization": f"Bearer {self.token}",
                                                                               "Content-Type": "application/json"})
        try:
            response = json.load(urllib.request.urlopen(request, timeout=120))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{model} returned HTTP {e.code}: {e.read()[:300]!r}; completed calls are cached, re-run to resume") from e
        result = {"content": response["choices"][0]["message"]["content"], "usage": response["usage"]}
        self.spent += response["usage"]["total_tokens"]
        if not result["content"]:
            raise RuntimeError(f"{model} returned no content after {response['usage']['completion_tokens']} completion tokens "
                               f"(finish_reason {response['choices'][0]['finish_reason']}); raise its token limit in skills/categories.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result), encoding="utf-8")
        return result


def answer(client: Client, model: str, task: Json, skill: str | None) -> Json:
    """Return one answer to the task, with the skill appended to the system prompt when given."""
    system = SYSTEM + (f"\n\nFollow this skill:\n{skill}" if skill else "")
    return client.chat(model, [{"role": "system", "content": system}, {"role": "user", "content": task["prompt"]}])


def parse_json(text: str) -> Json:
    """Return the JSON object in a model reply (between its first '{' and last '}')."""
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


def judge(client: Client, model: str, task: Json, with_skill: str, without_skill: str) -> Json:
    """Return the judge's scores for both answers, shown as A and B in an order fixed by the task id (blind, reproducible)."""
    with_first = int(hashlib.sha256(task["id"].encode()).hexdigest(), 16) % 2 == 0
    a, b = (with_skill, without_skill) if with_first else (without_skill, with_skill)
    checks = "\n".join(f"{i}. {c}" for i, c in enumerate(task["checks"], 1))
    prompt = f"Task:\n{task['prompt']}\n\nChecks:\n{checks}\n\nAnswer A:\n{a}\n\nAnswer B:\n{b}"
    verdict = parse_json(client.chat(model, [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": prompt}])["content"])
    first, second = (verdict["a"], verdict["b"]) if with_first else (verdict["b"], verdict["a"])
    return {"with": float(first["score"]), "without": float(second["score"]), "reason": verdict["reason"], "with_shown_as": "A" if with_first else "B"}


def report(name: str, tasks: list[Json], answers: dict[tuple[str, bool], Json], verdicts: dict[str, Json], config: Json) -> Json:
    """Return and write skills/evals/<name>.json: quality lift, wins, worst task, and per-session token overhead."""
    rows = []
    for task in tasks:
        w, wo, v = answers[(task["id"], True)]["usage"], answers[(task["id"], False)]["usage"], verdicts[task["id"]]
        rows.append({"task": task["id"], "with": v["with"], "without": v["without"], "delta": v["with"] - v["without"], "reason": v["reason"],
                     "prompt_delta": w["prompt_tokens"] - wo["prompt_tokens"], "completion_delta": w["completion_tokens"] - wo["completion_tokens"]})
    added = statistics.mean(r["prompt_delta"] + r["completion_delta"] for r in rows)
    result = {"skill": name, "eval_method": "micro", "generator": config["generator"], "judge": config["judge"],
              "quality_lift_pp": round(statistics.mean(r["delta"] for r in rows) / SCORE_MAX * 100, 1),
              "token_overhead_pct": round(added / config["baseline_tokens_per_call"] * 100, 2), "lift_per_aiu": None,
              "wins": sum(r["delta"] > 0 for r in rows), "losses": sum(r["delta"] < 0 for r in rows),
              "worst_delta": min(r["delta"] for r in rows), "runs_with": [r["task"] for r in rows], "runs_without": [r["task"] for r in rows],
              "per_task": rows}
    EVALS_DIR.mkdir(exist_ok=True)
    (EVALS_DIR / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def run(names: list[str]) -> list[Json]:
    """Answer every task of the named skills in both conditions, judge each pair, and write one eval per skill."""
    config = json.loads((SKILLS_DIR / "categories.json").read_text(encoding="utf-8"))["micro_eval"]
    env = read_env()
    client = Client(env["AZURE_OPENAI_ENDPOINT"], access_token(), config["models"])
    suites = {n: json.loads((TASKS_DIR / f"{n}.json").read_text(encoding="utf-8")) for n in names}
    skills = {n: (SKILLS_DIR / "admitted" / n / "SKILL.md").read_text(encoding="utf-8") for n in names}
    jobs = [(n, t, with_skill) for n in names for t in suites[n] for with_skill in (True, False)]
    start = time.time()
    with ThreadPoolExecutor(config["concurrency"]) as pool:
        outputs = list(pool.map(lambda j: answer(client, config["generator"], j[1], skills[j[0]] if j[2] else None), jobs))
        answers = {(j[1]["id"], j[2]): o for j, o in zip(jobs, outputs)}
        pairs = [t for n in names for t in suites[n]]
        judged = list(pool.map(lambda t: judge(client, config["judge"], t, answers[(t["id"], True)]["content"],
                                               answers[(t["id"], False)]["content"]), pairs))
    verdicts = {t["id"]: v for t, v in zip(pairs, judged)}
    results = [report(n, suites[n], answers, verdicts, config) for n in names]
    print(f"{len(jobs)} answers and {len(pairs)} judgements in {time.time() - start:.0f} s; {client.spent:,} tokens spent this run "
          "(cached calls cost nothing)", file=sys.stderr)
    return results


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit("usage: micro_eval.py all | <skill> [<skill> ...]")
    selected = sorted(p.stem for p in TASKS_DIR.glob("*.json")) if args == ["all"] else args
    for r in run(selected):
        print(f"{r['skill']:<22} lift {r['quality_lift_pp']:>6} pp  wins {r['wins']}/{len(r['per_task'])}  worst {r['worst_delta']:+}  "
              f"overhead {r['token_overhead_pct']}%")
