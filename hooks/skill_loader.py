"""Task-use gate hook: load the best library skills for the prompt within the loadout budget, offer the rest, and block other library skills."""

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, TypedDict

from interventions import record
from hve_paths import RUNS_DIR, STATE_DIR

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
OVERRIDE_FILE = SKILLS_DIR / "eval_override.json"
SESSION_ID = re.compile(r"^[\w-]+$")
SKILL_REF = re.compile(r"([^\s\"'/\\]+)[/\\]+SKILL\.md", re.I)
ASK_TOOL = "vscode_askQuestions"
LOAD_HEADER = "load-skills"
sys.path.insert(0, str(ROOT / "tools" / "skills"))
from recommend import rank  # noqa: E402

Json = dict[str, Any]


class Loadout(TypedDict):
    """Skills chosen for one session, ranked skills over budget that the user may add, and whether the loadout was announced."""

    categories: list[str]
    skills: list[str]
    recommended: list[str]
    announced: bool


def state_file(session_id: str) -> Path:
    """Return the session's loadout file after validating the session id."""
    if not SESSION_ID.match(session_id):
        raise ValueError(f"unsafe session_id {session_id!r}")
    return RUNS_DIR / f"{session_id}.skills.json"


def library() -> set[str]:
    """Return the names of all admitted and candidate library skills."""
    return {p.name for folder in ("admitted", "candidates") if (SKILLS_DIR / folder).is_dir()
            for p in (SKILLS_DIR / folder).iterdir() if p.is_dir()}


def install(sources: list[str]) -> None:
    """Copy library skills into <workspace>/.hve/skills/<name>/ so the agent reads them inside the workspace."""
    for source in sources:
        shutil.copytree(ROOT / source, STATE_DIR / "skills" / Path(source).name, dirs_exist_ok=True)


def choose(prompt: str) -> Loadout:
    """Return the eval override's skills if present, else the ranked skills that fit the loadout budget and the ranked rest."""
    if OVERRIDE_FILE.exists():
        return Loadout(categories=[], skills=json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))["skills"], recommended=[],
                       announced=False)
    ranked = rank(prompt, os.environ["HARNESS_SKILLS_MIN_STATUS"])  # type: ignore[arg-type]
    return Loadout(categories=ranked["categories"], skills=[r["path"] for r in ranked["load"]],
                   recommended=[r["path"] for r in ranked["recommend"]], announced=False)


def announcement(loadout: Loadout) -> str:
    """Return the instruction naming the loaded skills and, if any, the ranked skills over budget to offer the user."""
    text = ""
    if loadout["skills"]:
        paths = ", ".join(f".hve/skills/{Path(s).name}/SKILL.md" for s in loadout["skills"])
        text = f"Skills loaded for this task: read and follow {paths} before continuing. Do not use other library skills."
    if loadout["recommended"]:
        names = ", ".join(Path(s).name for s in loadout["recommended"])
        text += (f" Also relevant but over the loadout budget (ranked): {names}. Tell the user and ask with the ask-questions tool "
                 f"(header `{LOAD_HEADER}`, multi-select, labels = skill names) which to add; only ticked skills load.")
    return text.strip()


def pre_tool_output(session_id: str, loadout: Loadout, tool_input: Json) -> Json | None:
    """Return a deny for reading a library SKILL.md outside the loadout, the one-time loadout announcement, or nothing."""
    allowed = {Path(s).name for s in loadout["skills"]}
    blocked = sorted({m for m in SKILL_REF.findall(json.dumps(tool_input)) if m in library() and m not in allowed})
    if blocked:
        reason = f"Skill(s) {blocked} are not loaded for this task. Use only: {sorted(allowed) or 'none'}."
        record(session_id, "skill_loader", "skill_denied", reason)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}
    if loadout["announced"] or not (loadout["skills"] or loadout["recommended"]):
        return None
    loadout["announced"] = True
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": announcement(loadout)}}


def add_ticked(loadout: Loadout, tool_input: Json, tool_response: Any) -> list[str]:
    """Move the skills the user ticked under the load-skills question from recommended into the loadout; return them."""
    if not any(q["header"] == LOAD_HEADER for q in tool_input["questions"]):
        return []
    answer = (json.loads(tool_response) if isinstance(tool_response, str) else tool_response)["answers"][LOAD_HEADER]
    ticked = [s for s in loadout["recommended"] if Path(s).name in (answer.get("selected") or [])]
    loadout["skills"] += ticked
    loadout["recommended"] = [s for s in loadout["recommended"] if s not in ticked]
    loadout["announced"] = loadout["announced"] and not ticked
    return ticked


def main() -> None:
    """Choose and install the loadout on UserPromptSubmit; enforce and announce it on PreToolUse; add ticked skills on PostToolUse."""
    payload = json.load(sys.stdin)
    path = state_file(payload["session_id"])
    event = payload["hook_event_name"]
    if event == "UserPromptSubmit":
        loadout = choose(payload["prompt"])
        install(loadout["skills"])
        path.write_text(json.dumps(loadout), encoding="utf-8")
        return
    if event not in ("PreToolUse", "PostToolUse"):
        raise ValueError(f"skill_loader.py does not handle hook event {event!r}")
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: the UserPromptSubmit skill_loader hook did not run for this session")
    loadout = json.loads(path.read_text(encoding="utf-8"))
    output = None
    if event == "PreToolUse":
        output = pre_tool_output(payload["session_id"], loadout, payload["tool_input"])
    elif payload["tool_name"] == ASK_TOOL:
        install(add_ticked(loadout, payload["tool_input"], payload["tool_response"]))
    path.write_text(json.dumps(loadout), encoding="utf-8")
    if output:
        print(json.dumps(output))


if __name__ == "__main__":
    main()
