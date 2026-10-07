"""Workspace skill evaluator: static gate, blind with/without pairs judged in chat (or on Foundry), and admission to the workspace library."""

import json
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

import micro_eval
from onboard import NON_PYTHON_SCRIPTS, decide, decide_provisional
from recommend import SKILLS_DIR, stems
from scan import scan
from triage import load_categories, skill_categories

WORKSPACE = Path.cwd()
STATE = WORKSPACE / ".hve"
USER_REGISTRY = STATE / "skills-registry.json"
USER_LIBRARY = STATE / "skill-library"
DUPLICATE_SIMILARITY = 0.5

Json = dict[str, Any]


def eval_dir(name: str) -> Path:
    """Return the workspace folder holding one skill's tasks, answers, judge prompts and verdicts."""
    return STATE / "evals" / name


def read(path: Path) -> Any:
    """Return a parsed JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def registries() -> list[Json]:
    """Return the entries of the harness library registry and the workspace registry."""
    entries = read(SKILLS_DIR / "registry.json")["admitted"]
    return entries + (read(USER_REGISTRY)["admitted"] if USER_REGISTRY.is_file() else [])


def static(skill_dir: Path) -> Json:
    """Return the static report: scan, categories, provisional-gate reasons, overlapping library skills and context cost."""
    config = load_categories()
    report = scan(skill_dir)
    categories = skill_categories(report, config)
    scripts = sorted(p.name for p in skill_dir.rglob("*") if p.suffix.lower() in NON_PYTHON_SCRIPTS)
    own = stems(report["description"])
    overlaps = [{"skill": e["name"], "similarity": round(len(own & stems(e["description"])) / len(own | stems(e["description"])), 2)}
                for e in registries() if e["name"] != report["name"] and own | stems(e["description"])]
    return {"name": report["name"], "ok": report["ok"], "findings": report["findings"], "categories": categories,
            "gate_reasons": decide_provisional(dict(report), categories, config["provisional"], scripts),
            "overlaps": [o for o in overlaps if o["similarity"] >= DUPLICATE_SIMILARITY],
            "cost": {"tokens_per_request_if_in_a_skill_folder": (len(report["name"]) + len(report["description"])) // 4 + 15,
                     "tokens_when_loaded": report["skill_tokens"]},
            "next": f"write 5 tasks to {(eval_dir(report['name']) / 'tasks.json').as_posix()}"}


def blind(name: str) -> list[Json]:
    """Write and return one judge prompt per task with the two answers as anonymous A and B (order fixed by the task id)."""
    folder = eval_dir(name)
    answers = read(folder / "answers.json")
    prompts = []
    for task in read(folder / "tasks.json"):
        pair = answers[task["id"]]
        a, b = (pair["with"], pair["without"]) if micro_eval.with_first(task["id"]) else (pair["without"], pair["with"])
        prompts.append({"task": task["id"], "prompt": f"{micro_eval.JUDGE_SYSTEM}\n\n{micro_eval.judge_prompt(task, a, b)}"})
    (folder / "judge.json").write_text(json.dumps(prompts, indent=2) + "\n", encoding="utf-8")
    return prompts


def admit(skill_dir: Path, evaluation: Json) -> Json:
    """Apply the admission gate to an evaluation, then add the skill to the workspace library or record its rejection."""
    config = load_categories()
    report = scan(skill_dir)
    reasons = decide(dict(report), evaluation, skill_categories(report, config), config["thresholds"])
    entry = {"name": report["name"], "description": report["description"], "source": "workspace", "status": "admitted",
             "task_categories": skill_categories(report, config), "skill_tokens": report["skill_tokens"]}
    entry |= {k: evaluation[k] for k in ("quality_lift_pp", "token_overhead_pct", "eval_method", "wins", "losses", "worst_delta")}
    registry = read(USER_REGISTRY) if USER_REGISTRY.is_file() else {"admitted": [], "rejected": []}
    for status in ("admitted", "rejected"):
        registry[status] = [e for e in registry[status] if e["name"] != report["name"]]
    target = USER_LIBRARY / report["name"]
    if target.exists():
        shutil.rmtree(target)
    if reasons:
        registry["rejected"].append(entry | {"status": "rejected", "reason": "; ".join(reasons), "rejected_date": date.today().isoformat()})
    else:
        shutil.copytree(skill_dir, target)
        registry["admitted"].append(entry | {"admitted_date": date.today().isoformat()})
    USER_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    USER_REGISTRY.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return entry | {"admitted": not reasons, "reasons": reasons}


def record(skill_dir: Path) -> Json:
    """Unblind the judge verdicts saved in chat, score the skill, write its eval and apply the gate."""
    name = scan(skill_dir)["name"]
    folder = eval_dir(name)
    verdicts = read(folder / "verdicts.json")
    body_tokens = scan(skill_dir)["skill_tokens"]
    rows = []
    for task in read(folder / "tasks.json"):
        v = micro_eval.unblind(verdicts[task["id"]], micro_eval.with_first(task["id"]))
        rows.append({"task": task["id"], "with": v["with"], "without": v["without"], "delta": v["with"] - v["without"],
                     "reason": v["reason"], "prompt_delta": body_tokens, "completion_delta": 0})
    config = load_categories()["micro_eval"]
    evaluation = micro_eval.summarize(name, rows, config, "in-chat", {"generator": "chat model (sub-agents)", "judge": "chat model (sub-agent)"})
    (folder / "eval.json").write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")
    return admit(skill_dir, evaluation)


def foundry(skill_dir: Path) -> Json:
    """Run the micro eval on the workspace's Foundry endpoint (.env.local, keyless az login), then apply the gate."""
    name = scan(skill_dir)["name"]
    tasks = read(eval_dir(name) / "tasks.json")
    evaluation = micro_eval.run({name: tasks}, {name: (skill_dir / "SKILL.md").read_text(encoding="utf-8")}, WORKSPACE / ".env.local",
                                eval_dir(name))[0]
    return admit(skill_dir, evaluation)


if __name__ == "__main__":
    args = sys.argv[1:]
    commands = {"static": lambda a: static(Path(a)), "blind": blind, "record": lambda a: record(Path(a)), "foundry": lambda a: foundry(Path(a))}
    if len(args) != 2 or args[0] not in commands:
        raise SystemExit("usage: evaluate.py static <skill_dir> | blind <skill name> | record <skill_dir> | foundry <skill_dir>")
    print(json.dumps(commands[args[0]](args[1]), indent=2))
