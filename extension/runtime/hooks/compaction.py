"""Hook that tells every sub-agent to return a short summary, so raw tool output stays out of the parent's context."""

import json
import sys

SUBAGENT_CONTEXT = ("Return only what the parent agent needs, under 2,000 tokens: findings, decisions, file paths with line ranges, "
                    "and command exit codes. Summarize tool output; never paste it raw. "
                    "Work in exactly one role (frontend, backend, data, or infra), the one your task names; if the task spans "
                    "several roles, do only your role's part and name the rest in your reply.")


def main() -> None:
    """Answer a SubagentStart event with the return-size instruction."""
    event = json.load(sys.stdin)["hook_event_name"]
    if event != "SubagentStart":
        raise ValueError(f"compaction.py does not handle hook event {event!r}")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": SUBAGENT_CONTEXT}}))


if __name__ == "__main__":
    main()
