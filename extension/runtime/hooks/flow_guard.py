"""SubagentStop guard for creator-flow stage agents: a stage may not finish until it has moved the flow along one of its edges."""

import json
import os
import sys
from pathlib import Path

from interventions import record


def main() -> None:
    """Block the stage agent's stop once while its flow is running, still at its stage, and not escalated."""
    payload = json.load(sys.stdin)
    if payload["hook_event_name"] not in ("Stop", "SubagentStop"):
        raise ValueError(f"flow_guard.py does not handle hook event {payload['hook_event_name']!r}")
    path = Path.cwd() / os.environ["HARNESS_PROJECT"] / ".harness" / "flow.json"
    # Plugin agents also work outside flows; FLOW_REF ties a plugin stage agent to its own flow.
    if not path.exists():
        return
    state = json.loads(path.read_text(encoding="utf-8"))
    stage = os.environ["FLOW_STAGE"]
    if os.environ.get("FLOW_REF", state["flow"]) != state["flow"]:
        return
    if state["stage"] != stage or state["escalated"] or payload["stop_hook_active"]:
        return
    reason = (f"The {stage} stage is not finished: run `flow.py status`, then `flow.py transition` along one of its edges with the "
              "evidence it needs. If the evidence cannot be met, take the back-edge with a note, or report what blocks you.")
    record(payload["session_id"], "flow_guard", "stage_not_finished", reason)
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
