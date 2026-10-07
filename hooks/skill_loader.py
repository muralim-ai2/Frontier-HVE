"""Task-use gate hook: pick at most N admitted skills for the prompt's categories, announce them, and block reading any other SKILL.md."""

import json
import re
import sys
from pathlib import Path
from typing import Any, TypedDict

from interventions import record
from hve_paths import RUNS_DIR

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
OVERRIDE_FILE = SKILLS_DIR / "eval_override.json"
SESSION_ID = re.compile(r"^[\w-]+$")
SKILL_REF = re.compile(r"([^\s\"'/\\]+)[/\\]+SKILL\.md", re.I)

Json = dict[str, Any]


class Loadout(TypedDict):
    """Skills chosen for one session and whether they were announced to the agent yet."""

    categories: list[str]
    skills: list[str]
    announced: bool


def state_file(session_id: str) -> Path:
    """Return the session's loadout file after validating the session id."""
    if not SESSION_ID.match(session_id):
        raise ValueError(f"unsafe session_id {session_id!r}")
    return RUNS_DIR / f"{session_id}.skills.json"


def choose(prompt: str) -> Loadout:
    """Return the eval override's skills if present, else the top admitted skills by quality lift for the prompt's categories."""
    config = json.loads((SKILLS_DIR / "categories.json").read_text(encoding="utf-8"))
    categories = [name for name, cat in config["categories"].items() if re.search(cat["task_pattern"], prompt, re.I)]
    if OVERRIDE_FILE.exists():
        skills = json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))["skills"]
    else:
        admitted = json.loads((SKILLS_DIR / "registry.json").read_text(encoding="utf-8"))["admitted"]
        matching = sorted((e for e in admitted if set(e["task_categories"]) & set(categories)), key=lambda e: -e["quality_lift_pp"])
        skills = [f"skills/admitted/{e['name']}" for e in matching]
    return Loadout(categories=categories, skills=skills[:config["max_skills_per_session"]], announced=False)


def pre_tool_output(session_id: str, loadout: Loadout, tool_input: Json) -> Json | None:
    """Return a deny for reading a SKILL.md outside the loadout, the one-time loadout announcement, or nothing."""
    allowed = {Path(s).name for s in loadout["skills"]}
    blocked = sorted({m for m in SKILL_REF.findall(json.dumps(tool_input)) if m not in allowed})
    if blocked:
        reason = f"Skill(s) {blocked} are not loaded for this task. Use only: {sorted(allowed) or 'none'}."
        record(session_id, "skill_loader", "skill_denied", reason)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}
    if loadout["announced"] or not loadout["skills"]:
        return None
    loadout["announced"] = True
    paths = ", ".join(f"{s}/SKILL.md" for s in loadout["skills"])
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
            f"Skills loaded for this task: read and follow {paths} before continuing. Do not use any other skill."}}


def main() -> None:
    """Choose the loadout on UserPromptSubmit; enforce and announce it on PreToolUse."""
    payload = json.load(sys.stdin)
    path = state_file(payload["session_id"])
    event = payload["hook_event_name"]
    if event == "UserPromptSubmit":
        path.write_text(json.dumps(choose(payload["prompt"])), encoding="utf-8")
    elif event == "PreToolUse":
        if not path.exists():
            raise FileNotFoundError(f"{path} missing: the UserPromptSubmit skill_loader hook did not run for this session")
        loadout: Loadout = json.loads(path.read_text(encoding="utf-8"))
        output = pre_tool_output(payload["session_id"], loadout, payload["tool_input"])
        path.write_text(json.dumps(loadout), encoding="utf-8")
        if output:
            print(json.dumps(output))
    else:
        raise ValueError(f"skill_loader.py does not handle hook event {event!r}")


if __name__ == "__main__":
    main()
