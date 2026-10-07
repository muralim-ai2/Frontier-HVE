"""Append hook interventions (denies, blocks, stops) to the session log and blindspot-coded ones to research/blindspots/."""

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "research" / "runs"
BLINDSPOTS_FILE = ROOT / "research" / "blindspots" / "detected_blindspots.jsonl"
SESSION_ID = re.compile(r"^[\w-]+$")


def record(session_id: str, hook: str, kind: str, detail: str, blindspot: str | None = None) -> None:
    """Append one intervention to research/runs/<session_id>.interventions.jsonl, and to the blindspot log when coded."""
    if not SESSION_ID.match(session_id):
        raise ValueError(f"unsafe session_id {session_id!r}")
    entry = {"ts_ms": time.time() * 1000, "session_id": session_id, "hook": hook, "kind": kind, "detail": detail, "blindspot": blindspot}
    line = json.dumps(entry) + "\n"
    with (RUNS_DIR / f"{session_id}.interventions.jsonl").open("a", encoding="utf-8") as f:
        f.write(line)
    if blindspot:
        BLINDSPOTS_FILE.parent.mkdir(exist_ok=True)
        with BLINDSPOTS_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
