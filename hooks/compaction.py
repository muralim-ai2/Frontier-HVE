"""Hook that tells every sub-agent to return a short summary and, inside an ask, which skills to follow and report."""

import json
import sys
from pathlib import Path

SUBAGENT_CONTEXT = ("Return only what the parent agent needs, under 2,000 tokens: findings, decisions, file paths with line ranges, "
                    "and command exit codes. Summarize tool output; never paste it raw. "
                    "Work in exactly one role (frontend, backend, data, or infra), the one your task names; if the task spans "
                    "several roles, do only your role's part and name the rest in your reply.")


def ask_context(workspace: Path) -> str:
    """Return the active ask's skill paths and the SKILLS-USED reply rule, or nothing when no ask is active."""
    active = workspace / ".hve" / "asks" / "active.json"
    if not active.is_file():
        return ""
    slug = json.loads(active.read_text(encoding="utf-8"))["active"]
    contract = json.loads((active.parent / slug / "contract.json").read_text(encoding="utf-8"))
    paths = ", ".join(f".hve/skills/{r['name']}/SKILL.md" for r in contract["skills"]["selected"]) or "none"
    return (f" Frontier HVE ask {slug}: unless your brief lists other skills, follow {paths}. "
            "End your reply with one line: SKILLS-USED: <the skills you actually followed, or none>.")


def main() -> None:
    """Answer a SubagentStart event with the return-size instruction and the active ask's skills."""
    event = json.load(sys.stdin)["hook_event_name"]
    if event != "SubagentStart":
        raise ValueError(f"compaction.py does not handle hook event {event!r}")
    context = SUBAGENT_CONTEXT + ask_context(Path.cwd())
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": context}}))


if __name__ == "__main__":
    main()
