"""Plan check: when the active ask's plan.md changed since its last sync, tell the agent on each prompt and hold loop and stage runs until it reconciles."""

import json
import re
import sys
from pathlib import Path

from guard_policy import check

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "loop"))
from lifecycle import plan_status  # noqa: E402

RUN_COMMAND = re.compile(r"loop\.py\"?\s+(init|next|amend)\b|lifecycle\.py\"?\s+stage\b", re.I)


def reconcile(plan: str, revisions: int) -> str:
    """Return the instruction to reconcile a changed plan."""
    return (f"{plan} changed since its last sync (revision {revisions}), by the user or by you. Before more work: compare it with the "
            "contract's stages and feature_list.json, tell the user in one line per change what will change (stages to redo or skip, "
            "features to add through feature_list.add.json and `loop.py amend`), apply it, then run `lifecycle.py plan-sync \"<one-line note>\"`.")


def main() -> None:
    """Add reconcile context on UserPromptSubmit; deny loop and stage runs on PreToolUse while the plan is out of sync."""
    payload = json.load(sys.stdin)
    event = payload["hook_event_name"]
    if event not in ("UserPromptSubmit", "PreToolUse"):
        raise ValueError(f"plan_check.py does not handle hook event {event!r}")
    status = plan_status()
    if status is None or not status["changed"]:
        return
    text = reconcile(status["plan"], status["revisions"])
    if event == "UserPromptSubmit":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))
    elif payload["tool_name"] == "run_in_terminal" and RUN_COMMAND.search(payload["tool_input"]["command"]):
        reason = check(payload["session_id"], "plan_check", "plan_changed", text)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "permissionDecision": "deny", "permissionDecisionReason": reason}}))


if __name__ == "__main__":
    main()
