"""SubagentStop guard for creator-flow stage agents: a stage may not finish until it has moved the flow along one of its edges."""

import json
import os
import sys
from pathlib import Path

from interventions import record

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    """Block the stage agent's stop once while the flow is still at its stage and not escalated."""
    payload = json.load(sys.stdin)
    if payload["hook_event_name"] not in ("Stop", "SubagentStop"):
        raise ValueError(f"flow_guard.py does not handle hook event {payload['hook_event_name']!r}")
    state = json.loads((ROOT / os.environ["HARNESS_PROJECT"] / ".harness" / "flow.json").read_text(encoding="utf-8"))
    stage = os.environ["FLOW_STAGE"]
    if state["stage"] != stage or state["escalated"] or payload["stop_hook_active"]:
        return
    reason = (f"The {stage} stage is not finished: run `flow.py status`, then `flow.py transition` along one of its edges with the "
              "evidence it needs. If the evidence cannot be met, take the back-edge with a note, or report what blocks you.")
    record(payload["session_id"], "flow_guard", "stage_not_finished", reason)
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
