"""Paired with/without-skill benchmark runs of the creator agent, and the lift report computed from their metrics and blind scores."""

import json
import shutil
import statistics
import sys
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "observe"))
import bench  # noqa: E402
from compare import RunSummary, blind_scores, summarize  # noqa: E402
from scan import scan  # noqa: E402

CANDIDATES_DIR = ROOT / "skills" / "candidates"
EVALS_DIR = ROOT / "skills" / "evals"
OVERRIDE_FILE = ROOT / "skills" / "eval_override.json"
RUNS_DIR = ROOT / "research" / "runs"
SCORE_MAX = 5
Condition = Literal["with", "without"]
Json = dict[str, Any]


def stage(skill_dir: Path) -> str:
    """Copy a skill that passes the scan into skills/candidates/<name>/ and return its name."""
    report = scan(skill_dir)
    if not report["ok"]:
        raise ValueError(f"{skill_dir} fails the scan; fix or reject it first: {json.dumps(report['findings'], indent=2)}")
    target = CANDIDATES_DIR / report["name"]
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(skill_dir, target)
    return report["name"]


def run_pair(skill_dir: Path, runs: int) -> None:
    """Run the creator benchmark `runs` times per condition, alternating which condition goes first, and tag each session."""
    name = stage(skill_dir)
    for i in range(runs):
        order: list[Condition] = ["without", "with"] if i % 2 == 0 else ["with", "without"]
        for condition in order:
            skills = [(CANDIDATES_DIR / name).relative_to(ROOT).as_posix()] if condition == "with" else []
            OVERRIDE_FILE.write_text(json.dumps({"skills": skills}), encoding="utf-8")
            try:
                session_id = bench.run("creator")
            finally:
                OVERRIDE_FILE.unlink()
            (RUNS_DIR / f"{session_id}.skill.json").write_text(json.dumps({"skill": name, "condition": condition}), encoding="utf-8")


def mean(runs: list[RunSummary], key: str) -> float:
    """Return the mean of one metric over runs."""
    return statistics.mean(float(r[key]) for r in runs)  # type: ignore[literal-required]


def report(name: str, score: Literal["human", "ai"]) -> Json:
    """Return and write skills/evals/<name>.json: quality lift (pp of the 0-5 score), token overhead, latency and cost deltas."""
    scores = blind_scores()
    groups: dict[Condition, list[RunSummary]] = {"with": [], "without": []}
    for tag_file in sorted(RUNS_DIR.glob("*.skill.json")):
        tag = json.loads(tag_file.read_text(encoding="utf-8"))
        if tag["skill"] != name:
            continue
        session_id = tag_file.name.removesuffix(".skill.json")
        summary = summarize(json.loads((RUNS_DIR / f"{session_id}.run.json").read_text(encoding="utf-8")), scores)
        if summary[f"{score}_score"] is None:  # type: ignore[literal-required]
            raise ValueError(f"session {session_id} has no {score}_score: run `python tools/observe/blind.py prepare` and score it")
        groups[tag["condition"]].append(summary)
    if not groups["with"] or not groups["without"]:
        raise ValueError(f"skill {name!r} needs at least one tagged run per condition; have "
                         f"{len(groups['with'])} with, {len(groups['without'])} without")
    w, wo = groups["with"], groups["without"]
    tokens_w = mean(w, "prompt_tokens") + mean(w, "completion_tokens")
    tokens_wo = mean(wo, "prompt_tokens") + mean(wo, "completion_tokens")
    lift = (mean(w, f"{score}_score") - mean(wo, f"{score}_score")) / SCORE_MAX * 100
    result: Json = {
        "skill": name, "score": score, "runs_with": [r["session_id"] for r in w], "runs_without": [r["session_id"] for r in wo],
        "quality_lift_pp": round(lift, 1),
        "token_overhead_pct": round((tokens_w / tokens_wo - 1) * 100, 1),
        "latency_delta_pct": round((mean(w, "wall_clock_s") / mean(wo, "wall_clock_s") - 1) * 100, 1),
        "cost_delta_aiu": round(mean(w, "cost_aiu") - mean(wo, "cost_aiu"), 2),
        "lift_per_aiu": round(lift / mean(w, "cost_aiu"), 3),
    }
    EVALS_DIR.mkdir(exist_ok=True)
    (EVALS_DIR / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 4 and args[0] == "run" and args[2] == "--runs" and args[3].isdigit():
        run_pair(Path(args[1]), int(args[3]))
    elif len(args) == 4 and args[0] == "report" and args[2] == "--score" and args[3] in ("human", "ai"):
        print(json.dumps(report(args[1], args[3]), indent=2))  # type: ignore[arg-type]
    else:
        raise SystemExit("usage: eval_skill.py run <skill_dir> --runs N | eval_skill.py report <skill_name> --score {human|ai}")
