"""Prepare a blind scoring round: shuffle collected runs behind random labels, with folders for screenshots and a score sheet."""

import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "research" / "runs"
BLIND_DIR = ROOT / "research" / "blind"
RUBRIC_FILE = ROOT / "tests" / "prompts" / "color-palette.rubric.json"
LABELS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def app_root(output_dir: Path) -> Path:
    """Return the folder holding the run's package.json (the output itself or one sub-folder of it)."""
    roots = [p.parent for p in output_dir.rglob("package.json") if not {"node_modules", ".next"} & set(p.relative_to(output_dir).parts)]
    if len(roots) != 1:
        raise LookupError(f"{output_dir} has {len(roots)} package.json files outside node_modules/.next; expected 1")
    return roots[0]


def prepare() -> Path:
    """Create research/blind/<round>/ with key.json (operator only), scores.json (scorers), and one screenshot folder per label."""
    manifests = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RUNS_DIR.glob("*.run.json"))]
    if len(manifests) > len(LABELS):
        raise ValueError(f"{len(manifests)} runs exceed the {len(LABELS)} available labels")
    secrets.SystemRandom().shuffle(manifests)
    round_dir = BLIND_DIR / datetime.now(timezone.utc).strftime("round-%Y%m%dT%H%M%SZ")
    round_dir.mkdir(parents=True)
    key: dict[str, dict[str, str]] = {}
    for label, manifest in zip(LABELS, manifests):
        key[label] = {"session_id": manifest["session_id"], "mode": manifest["mode"],
                      "app_dir": app_root(ROOT / manifest["output_dir"]).relative_to(ROOT).as_posix()}
        (round_dir / label).mkdir()
    rubric = json.loads(RUBRIC_FILE.read_text(encoding="utf-8"))
    scores = {label: {"human_score": None, "human_notes": "", "ai_score": None, "ai_checks": {c["id"]: None for c in rubric["checks"]},
                      "ai_notes": ""} for label in key}
    (round_dir / "key.json").write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    (round_dir / "scores.json").write_text(json.dumps(scores, indent=2) + "\n", encoding="utf-8")
    return round_dir


if __name__ == "__main__":
    if sys.argv[1:] != ["prepare"]:
        raise SystemExit("usage: blind.py prepare")
    print(prepare().relative_to(ROOT).as_posix())
