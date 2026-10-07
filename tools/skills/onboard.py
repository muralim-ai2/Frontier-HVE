"""Onboarding gate: admit a skill to skills/admitted/ only if it passes the scan and its paired eval clears both thresholds."""

import json
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

from scan import scan
from triage import load_categories, skill_categories

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_FILE = ROOT / "skills" / "registry.json"
ADMITTED_DIR = ROOT / "skills" / "admitted"
EVALS_DIR = ROOT / "skills" / "evals"

Json = dict[str, Any]


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
    return reasons


def onboard(skill_dir: Path, source: str) -> Json:
    """Scan, check the eval against the thresholds, then admit (copy + registry entry) or reject (registry entry with reasons)."""
    config = load_categories()
    report = scan(skill_dir)
    eval_file = EVALS_DIR / f"{report['name']}.json"
    evaluation = json.loads(eval_file.read_text(encoding="utf-8")) if report["ok"] and eval_file.exists() else None
    categories = skill_categories(report, config)
    reasons = decide(dict(report), evaluation, categories, config["thresholds"])
    entry: Json = {"name": report["name"], "source": source, "task_categories": categories, "skill_tokens": report["skill_tokens"]}
    if evaluation:
        entry |= {k: evaluation[k] for k in ("quality_lift_pp", "token_overhead_pct", "lift_per_aiu")}
        entry["eval_run_ids"] = evaluation["runs_with"] + evaluation["runs_without"]
    registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    for status in ("admitted", "rejected"):
        registry[status] = [e for e in registry[status] if e["name"] != report["name"]]
    target = ADMITTED_DIR / report["name"]
    if target.exists():
        shutil.rmtree(target)
    if reasons:
        registry["rejected"].append(entry | {"reason": "; ".join(reasons), "rejected_date": date.today().isoformat()})
    else:
        shutil.copytree(skill_dir, target)
        registry["admitted"].append(entry | {"admitted_date": date.today().isoformat()})
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return entry | {"admitted": not reasons, "reasons": reasons}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: onboard.py <skill_dir> <source label>")
    print(json.dumps(onboard(Path(sys.argv[1]), sys.argv[2]), indent=2))
