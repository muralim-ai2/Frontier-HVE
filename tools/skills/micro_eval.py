"""Micro paired eval: answer each skill's small tasks with and without the skill in one model call, then blind-judge each pair with another model."""

import hashlib
import json
import math
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
CACHE_DIR = Path.cwd() / ".hve" / "evals" / "micro"
SCORE_MAX = 5
SYSTEM = "You are a senior software engineer. Answer the task directly and concretely in at most 250 words."
JUDGE_SYSTEM = ("You are a strict, impartial evaluator. You see a task, its checks, and two anonymous answers A and B. "
                "Judge only against the checks and overall usefulness; ignore length and style preferences. "
                'Reply with JSON only: {"a": {"checks_met": [<check numbers>], "score": <0-5>}, '
                '"b": {"checks_met": [<check numbers>], "score": <0-5>}, "reason": "<one sentence>"}')

Json = dict[str, Any]


def read_env(env_file: Path) -> dict[str, str]:
    """Return the KEY=VALUE pairs of an env file such as .env.local."""
    lines = env_file.read_text(encoding="utf-8").splitlines()
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


def with_first(task_id: str) -> bool:
    """Return whether the with-skill answer is shown as A, fixed by a hash of the task id (random-like, reproducible)."""
    return int(hashlib.sha256(task_id.encode()).hexdigest(), 16) % 2 == 0


def judge_prompt(task: Json, a: str, b: str) -> str:
    """Return the judge's user prompt: the task, its numbered checks and the two anonymous answers."""
    checks = "\n".join(f"{i}. {c}" for i, c in enumerate(task["checks"], 1))
    return f"Task:\n{task['prompt']}\n\nChecks:\n{checks}\n\nAnswer A:\n{a}\n\nAnswer B:\n{b}"


def unblind(verdict: Json, shown_first: bool) -> Json:
    """Map a judge verdict on A and B back to with-skill and without-skill scores and checks met."""
    first, second = (verdict["a"], verdict["b"]) if shown_first else (verdict["b"], verdict["a"])
    return {"with": float(first["score"]), "without": float(second["score"]), "reason": verdict["reason"],
            "with_checks": sorted(first["checks_met"]), "without_checks": sorted(second["checks_met"]),
            "with_shown_as": "A" if shown_first else "B"}


def sign_test_p(gains: int, losses: int) -> float:
    """Return the one-sided exact sign-test p-value that the skill helps, from checks met only with it (gains) or only without (losses)."""
    n = gains + losses
    return sum(math.comb(n, k) for k in range(gains, n + 1)) / 2 ** n if n else 1.0


def judge(client: Client, model: str, task: Json, with_skill: str, without_skill: str) -> Json:
    """Return the judge's scores for both answers, shown as A and B in an order fixed by the task id (blind, reproducible)."""
    shown_first = with_first(task["id"])
    a, b = (with_skill, without_skill) if shown_first else (without_skill, with_skill)
    messages = [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": judge_prompt(task, a, b)}]
    return unblind(parse_json(client.chat(model, messages)["content"]), shown_first)


def summarize(name: str, rows: list[Json], config: Json, method: str, models: Json) -> Json:
    """Return the eval of one skill from per-task rows: quality lift, wins, losses, worst task and per-call token overhead."""
    added = statistics.mean(r["prompt_delta"] + r["completion_delta"] for r in rows)
    gains = sum(len(set(r["with_checks"]) - set(r["without_checks"])) for r in rows)
    losses = sum(len(set(r["without_checks"]) - set(r["with_checks"])) for r in rows)
    return {"skill": name, "eval_method": method} | models | {
        "quality_lift_pp": round(statistics.mean(r["delta"] for r in rows) / SCORE_MAX * 100, 1),
        "token_overhead_pct": round(added / config["baseline_tokens_per_call"] * 100, 2), "lift_per_aiu": None,
        "wins": sum(r["delta"] > 0 for r in rows), "losses": sum(r["delta"] < 0 for r in rows), "worst_delta": min(r["delta"] for r in rows),
        "check_gains": gains, "check_losses": losses, "check_sign_test_p": round(sign_test_p(gains, losses), 4),
        "runs_with": [r["task"] for r in rows], "runs_without": [r["task"] for r in rows], "per_task": rows}


def report(name: str, tasks: list[Json], answers: dict[tuple[str, bool], Json], verdicts: dict[str, Json], config: Json,
           evals_dir: Path) -> Json:
    """Return and write <evals_dir>/<name>.json from the answers' token usage and the unblinded verdicts."""
    rows = []
    for task in tasks:
        w, wo, v = answers[(task["id"], True)]["usage"], answers[(task["id"], False)]["usage"], verdicts[task["id"]]
        rows.append({"task": task["id"], "with": v["with"], "without": v["without"], "delta": v["with"] - v["without"], "reason": v["reason"],
                     "with_checks": v["with_checks"], "without_checks": v["without_checks"],
                     "prompt_delta": w["prompt_tokens"] - wo["prompt_tokens"], "completion_delta": w["completion_tokens"] - wo["completion_tokens"]})
    result = summarize(name, rows, config, "micro", {"generator": config["generator"], "judge": config["judge"]})
    evals_dir.mkdir(parents=True, exist_ok=True)
    (evals_dir / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def run(suites: dict[str, list[Json]], skills: dict[str, str], env_file: Path, evals_dir: Path) -> list[Json]:
    """Answer every task of each skill in both conditions, judge each pair, and write one eval per skill."""
    config = json.loads((SKILLS_DIR / "categories.json").read_text(encoding="utf-8"))["micro_eval"]
    client = Client(read_env(env_file)["AZURE_OPENAI_ENDPOINT"], access_token(), config["models"])
    names = list(suites)
    jobs = [(n, t, with_skill) for n in names for t in suites[n] for with_skill in (True, False)]
    start = time.time()
    with ThreadPoolExecutor(config["concurrency"]) as pool:
        outputs = list(pool.map(lambda j: answer(client, config["generator"], j[1], skills[j[0]] if j[2] else None), jobs))
        answers = {(j[1]["id"], j[2]): o for j, o in zip(jobs, outputs)}
        pairs = [t for n in names for t in suites[n]]
        judged = list(pool.map(lambda t: judge(client, config["judge"], t, answers[(t["id"], True)]["content"],
                                               answers[(t["id"], False)]["content"]), pairs))
    verdicts = {t["id"]: v for t, v in zip(pairs, judged)}
    results = [report(n, suites[n], answers, verdicts, config, evals_dir) for n in names]
    print(f"{len(jobs)} answers and {len(pairs)} judgements in {time.time() - start:.0f} s; {client.spent:,} tokens spent this run "
          "(cached calls cost nothing)", file=sys.stderr)
    return results


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit("usage: micro_eval.py all | <skill> [<skill> ...]   (run from the repository root)")
    selected = sorted(p.stem for p in TASKS_DIR.glob("*.json")) if args == ["all"] else args
    suite_map = {n: json.loads((TASKS_DIR / f"{n}.json").read_text(encoding="utf-8")) for n in selected}
    skill_map = {n: (SKILLS_DIR / "admitted" / n / "SKILL.md").read_text(encoding="utf-8") for n in selected}
    for r in run(suite_map, skill_map, ROOT / ".env.local", EVALS_DIR):
        print(f"{r['skill']:<22} lift {r['quality_lift_pp']:>6} pp  wins {r['wins']}/{len(r['per_task'])}  worst {r['worst_delta']:+}  "
              f"overhead {r['token_overhead_pct']}%")
