"""Guard waivers: after repeated trips of a waivable guard the agent asks the user to keep it or lay it down for the session; never while an output evaluation runs."""

import json
from pathlib import Path
from typing import Any

from hve_paths import RUNS_DIR, STATE_DIR
from interventions import SESSION_ID, record

ASK_AFTER = 3
WAIVABLE = {("loop_guard", "loop_files"), ("skill_loader", "skill_denied"), ("module_guard", "oversized_file")}
HEADER = "guard-waiver:"
KEEP = "Keep it on"
LAY_DOWN = "Lay down for this session"


def waivers_file(session_id: str) -> Path:
    """Return the session's waiver file after validating the session id."""
    if not SESSION_ID.match(session_id):
        raise ValueError(f"unsafe session_id {session_id!r}")
    return RUNS_DIR / f"{session_id}.waivers.json"


def strict() -> bool:
    """Return True while an output evaluation run is open: prepared (contract.json) but not decided (report.json)."""
    runs = [p for p in (STATE_DIR / "evaluations").glob("*") if (p / "contract.json").is_file()]
    return any(not (p / "report.json").is_file() for p in runs)


def waived(session_id: str, hook: str) -> bool:
    """Return True when the user laid the hook's guard down for this session."""
    path = waivers_file(session_id)
    return path.is_file() and json.loads(path.read_text(encoding="utf-8")).get(hook, False)


def trips(session_id: str, hook: str, kind: str) -> int:
    """Return how often the guard tripped with this kind in the session."""
    log = RUNS_DIR / f"{session_id}.interventions.jsonl"
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []
    return sum(e["hook"] == hook and e["kind"] == kind for e in entries)


def check(session_id: str, hook: str, kind: str, reason: str, blindspot: str | None = None) -> str | None:
    """Record a trip and return the reason to block, asking for a waiver after repeated trips; None when the guard is laid down."""
    waivable = (hook, kind) in WAIVABLE
    if waivable and waived(session_id, hook) and not strict():
        record(session_id, hook, "waived", f"{kind}: {reason}")
        return None
    record(session_id, hook, kind, reason, blindspot)
    if not waivable:
        return reason
    if strict():
        return f"{reason} Guards are strict while the output evaluation runs."
    count = trips(session_id, hook, kind)
    if count < ASK_AFTER:
        return reason
    return (f"{reason} This guard has tripped {count} times this session. Ask the user with the ask-questions tool (header "
            f"`{HEADER}{hook}`, one line on what it protects and why it tripped, options `{KEEP}` and `{LAY_DOWN}`) and follow the answer.")


def record_answers(session_id: str, tool_input: Any, tool_response: Any) -> None:
    """Save the user's keep or lay-down answers to guard-waiver questions."""
    headers = [q["header"] for q in tool_input["questions"] if q["header"].startswith(HEADER)]
    if not headers:
        return
    answers = (json.loads(tool_response) if isinstance(tool_response, str) else tool_response)["answers"]
    path = waivers_file(session_id)
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    for header in headers:
        hook = header.removeprefix(HEADER)
        if hook not in {h for h, _ in WAIVABLE}:
            raise ValueError(f"{header}: no waivable guard named {hook!r}")
        # A skipped or free-text answer leaves the guard on.
        data[hook] = LAY_DOWN in (answers.get(header, {}).get("selected") or [])
        record(session_id, hook, "waiver_answer", LAY_DOWN if data[hook] else KEEP)
    path.write_text(json.dumps(data), encoding="utf-8")
