"""Hook that enforces a wall-clock budget (HARNESS_BUDGET_MIN minutes) per session: hard stop, or ask the user to continue."""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from interventions import record

RUNS_DIR = Path(__file__).resolve().parent.parent / "research" / "runs"
SESSION_ID = re.compile(r"^[\w-]+$")
WARN_BEFORE_MS = 2 * 60_000
GRACE_MS = 60_000


def budget_file(session_id: str) -> Path:
    """Return the session's budget state file after validating the session id."""
    if not SESSION_ID.match(session_id):
        raise ValueError(f"unsafe session_id {session_id!r}")
    return RUNS_DIR / f"{session_id}.budget.json"


def pre_tool_output(state: dict[str, Any], now_ms: float, tool_use_id: str) -> dict[str, Any] | None:
    """Return the PreToolUse output for the elapsed time: nothing, a wrap-up nudge, then a hard stop or the user's continue prompt."""
    elapsed = now_ms - state["start_ms"]
    budget = state["budget_ms"]
    minutes = budget / 60_000
    if elapsed < budget - WARN_BEFORE_MS:
        return None
    if elapsed < budget:
        left = round((budget - elapsed) / 60_000, 1)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
                f"Time budget: {left} of {minutes:g} minutes left. Finish the smallest complete version, run one final check, then stop."}}
    if state["on_end"] == "ask":
        state["pending_ask"].append(tool_use_id)
        window = state["window_ms"] / 60_000
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "ask",
            "permissionDecisionReason": f"Time budget of {minutes:g} minutes is used. Allow to give the agent {window:g} more minutes; "
                                        "deny to make it stop.",
            "additionalContext": f"The {minutes:g}-minute budget is used. If this call is denied, the user wants you to stop: make no "
                                 "further changes and reply with your final summary."}}
    if elapsed < budget + GRACE_MS:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
                f"Time budget of {minutes:g} minutes is used up. Make no further changes; reply with your final summary now."}}
    state["denied"].append(tool_use_id)
    reason = f"Time budget of {minutes:g} minutes plus {GRACE_MS // 60_000} minute grace exceeded."
    return {"continue": False, "stopReason": reason,
            "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}


def main() -> None:
    """Record the session start; nudge, then stop or ask the user, once the budget is spent; extend it when the user allows."""
    payload = json.load(sys.stdin)
    path = budget_file(payload["session_id"])
    now_ms = datetime.fromisoformat(payload["timestamp"]).timestamp() * 1000
    event = payload["hook_event_name"]
    if event == "SessionStart":
        on_end = os.environ["HARNESS_BUDGET_ON_END"]
        if on_end not in ("stop", "ask"):
            raise ValueError(f"HARNESS_BUDGET_ON_END={on_end!r}, expected 'stop' or 'ask'")
        window = float(os.environ["HARNESS_BUDGET_MIN"]) * 60_000
        state = {"start_ms": now_ms, "budget_ms": window, "window_ms": window, "on_end": on_end, "pending_ask": [], "extensions": 0,
                 "denied": []}
        path.write_text(json.dumps(state), encoding="utf-8")
        return
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: the SessionStart budget hook did not run for this session")
    state = json.loads(path.read_text(encoding="utf-8"))
    output = None
    if event == "PreToolUse":
        output = pre_tool_output(state, now_ms, payload["tool_use_id"])
        if output and output.get("continue") is False:
            record(payload["session_id"], "budget", "budget_stop", output["stopReason"])
    elif event == "PostToolUse":
        if payload["tool_use_id"] in state["pending_ask"]:
            state["budget_ms"] += state["window_ms"]
            state["pending_ask"], state["extensions"] = [], state["extensions"] + 1
            record(payload["session_id"], "budget", "budget_extended", f"user allowed {state['window_ms'] / 60_000:g} more minutes")
    else:
        raise ValueError(f"budget.py does not handle hook event {event!r}")
    path.write_text(json.dumps(state), encoding="utf-8")
    if output:
        print(json.dumps(output))


if __name__ == "__main__":
    main()
