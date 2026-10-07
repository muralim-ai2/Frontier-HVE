"""Onboarding gate: admit a skill to skills/admitted/ as provisional (static gate) or admitted (paired eval clears both thresholds)."""

import json
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any, Literal

from scan import scan
from triage import load_categories, skill_categories

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_FILE = ROOT / "skills" / "registry.json"
ADMITTED_DIR = ROOT / "skills" / "admitted"
EVALS_DIR = ROOT / "skills" / "evals"
NON_PYTHON_SCRIPTS = {".ps1", ".sh", ".bat", ".cmd"}
Mode = Literal["provisional", "eval", "untested"]

Json = dict[str, Any]


def decide_provisional(report: Json, categories: list[str], limits: Json, scripts: list[str]) -> list[str]:
    """Return the reasons a skill fails the static gate (scan, category, size, description, Python-only scripts)."""
    if not report["ok"]:
        return [f"scan: {f['rule']} in {f['file']}:{f['line']}" for f in report["findings"]]
    reasons = []
    if not categories:
        reasons.append("matches no harness category in skills/categories.json, so the loader would never use it")
    if report["skill_tokens"] > limits["max_skill_tokens"]:
        reasons.append(f"{report['skill_tokens']} tokens over the {limits['max_skill_tokens']}-token provisional limit")
    if len(report["description"]) > limits["max_description_chars"]:
        reasons.append(f"description {len(report['description'])} characters over {limits['max_description_chars']}")
    if scripts:
        reasons.append(f"non-Python scripts {scripts}: the runtime ships Python only")
    return reasons


def decide(report: Json, evaluation: Json | None, categories: list[str], thresholds: Json) -> list[str]:
    """Return the reasons to reject the skill; an empty list admits it."""
    if not report["ok"]:
        return [f"scan: {f['rule']} in {f['file']}:{f['line']}" for f in report["findings"]]
    if evaluation is None:
        raise FileNotFoundError(f"no paired eval for {report['name']!r}: run tools/skills/eval_skill.py run/report first")
    reasons = []
    if not categories:
        reasons.append("matches no harness category in skills/categories.json, so the loader would never use it")
    if evaluation["quality_lift_pp"] < thresholds["min_quality_lift_pp"]:
        reasons.append(f"quality lift {evaluation['quality_lift_pp']} pp below {thresholds['min_quality_lift_pp']} pp")
    if evaluation["token_overhead_pct"] >= thresholds["max_token_overhead_pct"]:
        reasons.append(f"token overhead {evaluation['token_overhead_pct']}% not under {thresholds['max_token_overhead_pct']}%")
    if evaluation["eval_method"] == "micro-strict":
        if evaluation["wins"] < len(evaluation["per_task"]):
            reasons.append(f"won {evaluation['wins']} of {len(evaluation['per_task'])} tasks; imported skills must win every task")
        if evaluation["check_sign_test_p"] >= thresholds["strict_alpha"]:
            reasons.append(f"check-level sign test p={evaluation['check_sign_test_p']} not below {thresholds['strict_alpha']} "
                           f"({evaluation['check_gains']} checks gained, {evaluation['check_losses']} lost)")
    if evaluation["eval_method"] == "micro":
        held = len(evaluation["per_task"]) - evaluation["losses"]
        if held < thresholds["micro_min_wins_or_ties"]:
            reasons.append(f"won or tied {held} of {len(evaluation['per_task'])} tasks, needs {thresholds['micro_min_wins_or_ties']}")
        if evaluation["worst_delta"] < -thresholds["micro_max_task_loss"]:
            reasons.append(f"lost a task by {-evaluation['worst_delta']} points, more than {thresholds['micro_max_task_loss']}")
    return reasons


def onboard(skill_dir: Path, source: str, mode: Mode) -> Json:
    """Run the static gate (provisional), the eval gate (eval) or scan and category only (untested), then admit or reject."""
    config = load_categories()
    report = scan(skill_dir)
    categories = skill_categories(report, config)
    evaluation = None
    if mode == "provisional":
        scripts = sorted(p.name for p in skill_dir.rglob("*") if p.suffix.lower() in NON_PYTHON_SCRIPTS)
        reasons = decide_provisional(dict(report), categories, config["provisional"], scripts)
    elif mode == "untested":
        reasons = [f"scan: {f['rule']} in {f['file']}:{f['line']}" for f in report["findings"]]
        reasons += [] if categories else ["matches no harness category in skills/categories.json"]
    else:
        eval_file = EVALS_DIR / f"{report['name']}.json"
        evaluation = json.loads(eval_file.read_text(encoding="utf-8")) if report["ok"] and eval_file.exists() else None
        reasons = decide(dict(report), evaluation, categories, config["thresholds"])
    entry: Json = {"name": report["name"], "description": report["description"], "source": source,
                   "status": "admitted" if mode == "eval" else "provisional", "task_categories": categories,
                   "skill_tokens": report["skill_tokens"], "quality_lift_pp": None}
    if mode == "untested":
        entry["evaluation"] = "pending"
    if evaluation:
        entry |= {k: evaluation[k] for k in ("quality_lift_pp", "token_overhead_pct", "lift_per_aiu", "eval_method")}
        entry["eval_run_ids"] = evaluation["runs_with"] + evaluation["runs_without"]
    registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    for status in ("admitted", "rejected"):
        registry[status] = [e for e in registry[status] if e["name"] != report["name"]]
    target = ADMITTED_DIR / report["name"]
    if target.exists():
        shutil.rmtree(target)
    if reasons:
        registry["rejected"].append(entry | {"status": "rejected", "reason": "; ".join(reasons), "rejected_date": date.today().isoformat()})
    else:
        shutil.copytree(skill_dir, target)
        registry["admitted"].append(entry | {"admitted_date": date.today().isoformat()})
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return entry | {"admitted": not reasons, "reasons": reasons}


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) != 3 or args[2] not in ("provisional", "eval", "untested"):
        raise SystemExit("usage: onboard.py <skill_dir> <source label> provisional|eval|untested")
    print(json.dumps(onboard(Path(args[0]), args[1], args[2]), indent=2))  # type: ignore[arg-type]
