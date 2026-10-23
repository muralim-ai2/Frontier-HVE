"""Hook that records each sub-agent start and stop with its parent agent, ask and session, and the model when the client reports one."""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from hve_paths import RUNS_DIR

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "loop"))
from loop_paths import ask_folder  # noqa: E402

SESSION_ID = re.compile(r"^[\w-]+$")
EVENTS = {"SubagentStart": "start", "SubagentStop": "stop"}


def main() -> None:
    """Append one row per SubagentStart or SubagentStop to .hve/runs/<session>.agents.jsonl."""
    payload = json.load(sys.stdin)
    event = payload["hook_event_name"]
    if event not in EVENTS:
        raise ValueError(f"agent_ledger.py does not handle hook event {event!r}")
    session = payload["session_id"]
    if not SESSION_ID.match(session):
        raise ValueError(f"unsafe session_id {session!r}")
    ask = ask_folder(Path.cwd())
    contract = json.loads((ask / "contract.json").read_text(encoding="utf-8")) if ask else None
    row = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "session": session,
           "ask": contract["ask"] if contract else None, "agent": contract["agent"] if contract else None, "event": EVENTS[event],
           "agent_id": payload["agent_id"], "subagent": payload["agent_type"],
           "model": payload.get("model")}  # Cursor and Codex send the model; VS Code and Copilot do not
    with (RUNS_DIR / f"{session}.agents.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
