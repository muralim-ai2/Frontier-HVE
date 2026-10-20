"""Locate the loop files: in the open ask's .hve/asks/<ask>/loop/ folder, or in the project itself when no ask is open there (research runs)."""

import json
import re
from pathlib import Path

LOOP_FILES = ("feature_list.json", "progress.txt", "tracker.json", "feature_list.add.json")
ASK_ID = re.compile(r"^\d{8}-\d{4}-[a-z0-9][a-z0-9-]{0,40}$")


def ask_folder(project: Path) -> Path | None:
    """Return the open ask's folder under the project, or None when no ask is open there."""
    active = project / ".hve" / "asks" / "active.json"
    if not active.is_file():
        return None
    ask = json.loads(active.read_text(encoding="utf-8"))["active"]
    if not ASK_ID.match(ask):
        raise ValueError(f"{active}: ask id {ask!r} must match {ASK_ID.pattern} (<YYYYMMDD>-<HHMM>-<slug>)")
    return active.parent / ask


def loop_dir(project: Path) -> Path:
    """Return the folder holding feature_list.json, progress.txt and tracker.json."""
    ask = ask_folder(project)
    return project if ask is None else ask / "loop"


def state_dir(project: Path) -> Path:
    """Return the folder holding the loop state: state.json, attempts, evidence, PR records, choices, checks and the tool log."""
    ask = ask_folder(project)
    return project / ".harness" if ask is None else ask / "loop"


def evidence_dir(project: Path) -> Path:
    """Return the folder feature checks write screenshots and logs to, one subfolder per feature (exported as HVE_EVIDENCE)."""
    return state_dir(project) / "evidence"
