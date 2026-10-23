"""Task-use gate hook: load every relevant library skill for the prompt and the active ask, flag loads over the guideline, and block other library skills."""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, TypedDict

from guard_policy import check, record_answers
from hve_paths import RUNS_DIR, STATE_DIR

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
OVERRIDE_FILE = SKILLS_DIR / "eval_override.json"
SESSION_ID = re.compile(r"^[\w-]+$")
SKILL_REF = re.compile(r"([^\s\"'/\\]+)[/\\]+SKILL\.md", re.I)
OPENS_ASK = re.compile(r"lifecycle\.py\"?\s+(contract|open)\b")
ASK_TOOL = "vscode_askQuestions"
sys.path.insert(0, str(ROOT / "tools" / "skills"))
sys.path.insert(0, str(ROOT / "tools" / "loop"))
sys.path.insert(0, str(ROOT / "tools" / "plugins"))
from recommend import rank, skill_dir  # noqa: E402
from lifecycle import active, current_skills, install, project_status, project_text, shift_message, topic_shift  # noqa: E402
import store  # noqa: E402

Json = dict[str, Any]


class Loadout(TypedDict):
    """Skills chosen for one session, their token total, whether that exceeds the loadout guideline, and whether the loadout was announced."""

    categories: list[str]
    skills: list[str]
    tokens: int
    over_budget: bool
    budget: dict[str, int]
    announced: bool
    used: list[str]
    shift_noted: str | None
    ask: str | None
    displaced_noted: str | None


def state_file(session_id: str) -> Path:
    """Return the session's loadout file after validating the session id."""
    if not SESSION_ID.match(session_id):
        raise ValueError(f"unsafe session_id {session_id!r}")
    return RUNS_DIR / f"{session_id}.skills.json"


def ask_packs() -> tuple[Json, ...]:
    """Return the expertise packs the active ask chose (none without an open ask)."""
    if not (STATE_DIR / "asks" / "active.json").is_file():
        return ()
    return tuple(store.pack(STATE_DIR.parent, p["name"]) for p in active()[1]["packs"])


def library() -> set[str]:
    """Return the names of all admitted and candidate library skills, the workspace's own library, and, with an ask open, the skills of
    packs the ask did not choose."""
    folders = [SKILLS_DIR / "admitted", SKILLS_DIR / "candidates", STATE_DIR / "skill-library"]
    names = {p.name for folder in folders if folder.is_dir() for p in folder.iterdir() if p.is_dir()}
    if (STATE_DIR / "asks" / "active.json").is_file():
        chosen = {p["name"] for p in active()[1]["packs"]}
        names |= {s["name"] for n, p in store.packs(STATE_DIR.parent).items() if n not in chosen for s in p["manifest"]["skills"]}
    return names


def choose(prompt: str) -> tuple[Loadout, list[Json]]:
    """Return the eval override's skills if present, else the required and active ask's skills (with its packs' skills) plus every skill
    ranked for the prompt (none once the user has chosen the ask's skills), and the skills to install."""
    if OVERRIDE_FILE.exists():
        skills = json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))["skills"]
        return (Loadout(categories=[], skills=skills, tokens=0, over_budget=False, budget={}, announced=False, used=list(skills),
                        shift_noted=None, ask=None, displaced_noted=None), [{"name": Path(s).name, "path": s} for s in skills])
    value = os.environ.get("HARNESS_REQUIRED_SKILLS")
    required = tuple(name.strip() for name in value.split(",")) if value is not None else ()
    required += tuple(s for s in current_skills() if s not in required)
    chosen = (STATE_DIR / "asks" / "active.json").is_file() and active()[1]["skills"]["choice"] is not None
    ranked = rank("" if chosen else prompt, os.environ["HARNESS_SKILLS_MIN_STATUS"], required, ask_packs())  # type: ignore[arg-type]
    skills = [f".hve/skills/{skill_dir(r['name'])}" if ":" in r["name"] else r["path"] for r in ranked["load"]]
    return (Loadout(categories=ranked["categories"], skills=skills, tokens=ranked["load_tokens"], over_budget=ranked["over_budget"],
                    budget=ranked["budget"], announced=False, used=list(skills), shift_noted=None, ask=None, displaced_noted=None),
            ranked["load"])


def announcement(loadout: Loadout) -> str:
    """Return the instruction naming the loaded skills and, when the load exceeds the guideline, telling the agent to surface it."""
    if not loadout["skills"]:
        return ""
    paths = ", ".join(f".hve/skills/{Path(s).name}/SKILL.md" for s in loadout["skills"])
    text = (f"Skills loaded for this task ({len(loadout['skills'])}, {loadout['tokens']:,} tokens): read and follow {paths} before "
            "continuing. Do not use other library skills.")
    if loadout["over_budget"]:
        text += (f" This is over the loadout guideline ({loadout['budget']['max_skills']} skills, {loadout['budget']['max_tokens']:,} "
                 "tokens): score every shortlisted skill 0-10 for this ask and run `lifecycle.py skills score <file>`, then show the user "
                 "the suggested top skills with their scores and ask once: suggested, all, or named; then run `lifecycle.py skills "
                 "suggested|all|<a,b>`; the ask's plan.md lists the skills and the suggested set.")
    return text


def prompt_output(loadout: Loadout, prompt: str) -> Json | None:
    """Return the open ask's paths for every prompt (so the agent never searches for plan.md), and once per ask a new-workspace
    recommendation when the prompt starts a different project."""
    if not (STATE_DIR / "asks" / "active.json").is_file():
        return None
    data = active()[1]
    p = data["paths"]
    context = (f"Frontier HVE open ask {data['ask']}: plan {p['plan']}, evidence {p['evidence']}, project feature list "
               f"{p['feature_list']}. Use these paths; never search the workspace for plan.md or feature_list.json.")
    shift = topic_shift(project_text(), prompt) if project_status() else None
    if shift is None or loadout["shift_noted"] == data["ask"]:
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}
    loadout["shift_noted"] = data["ask"]
    message = shift_message(shift, data["ask"])
    return {"systemMessage": message, "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext":
            f"{context} {message} Relay this recommendation to the user in one line before starting; if they stay, open a new ask with "
            "lifecycle.py contract."}}


def displaced_context(loadout: Loadout) -> str | None:
    """Return a once-per-switch note when another chat opened a different ask in this workspace after this chat opened its own."""
    if loadout["ask"] is None or not (STATE_DIR / "asks" / "active.json").is_file():
        return None
    current = active()[1]["ask"]
    if current == loadout["ask"] or loadout["displaced_noted"] == current:
        return None
    loadout["displaced_noted"] = current
    return (f"Another chat opened ask {current} in this workspace, so lifecycle.py and loop.py now act on it, not on this chat's ask "
            f"{loadout['ask']}. Before your next lifecycle.py or loop.py command run `lifecycle.py open {loadout['ask']}`, and tell the user "
            "in one line: both asks keep their own folders, but parallel builds share one git checkout, so run them in separate folders or "
            "git worktrees, one window each.")


def pre_tool_output(session_id: str, loadout: Loadout, tool_input: Json) -> Json | None:
    """Return a deny for reading a library SKILL.md outside the loadout and the active lifecycle stage, the one-time announcement, or nothing."""
    stage = {skill_dir(s) for s in current_skills()}
    allowed = {Path(s).name for s in loadout["skills"]} | stage
    reads = set(SKILL_REF.findall(json.dumps(tool_input)))
    loadout["used"] = sorted({*loadout["used"], *(f"skills/admitted/{m}" for m in reads & stage)})
    blocked = sorted({m for m in reads if m in library() and m not in allowed})
    if blocked:
        reason = check(session_id, "skill_loader", "skill_denied",
                       f"Skill(s) {blocked} are not loaded for this task. Use only: {sorted(allowed) or 'none'}.")
        if reason is not None:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}
        loadout["used"] = sorted({*loadout["used"], *(f"skills/admitted/{m}" for m in blocked)})
    if loadout["announced"] or not loadout["skills"]:
        return None
    loadout["announced"] = True
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": announcement(loadout)}}


def main() -> None:
    """Choose and install the loadout on UserPromptSubmit; enforce and announce it on PreToolUse; record guard-waiver answers on PostToolUse."""
    payload = json.load(sys.stdin)
    path = state_file(payload["session_id"])
    event = payload["hook_event_name"]
    if event == "UserPromptSubmit":
        loadout, rows = choose(payload["prompt"])
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8"))
            # Loadouts written before `used` existed carry only their current skills.
            loadout["used"] = sorted({*previous.get("used", previous["skills"]), *loadout["used"]})
            loadout["shift_noted"] = previous.get("shift_noted")
            loadout["ask"] = previous.get("ask")
            loadout["displaced_noted"] = previous.get("displaced_noted")
        output = prompt_output(loadout, payload["prompt"])
        install(rows)
        path.write_text(json.dumps(loadout), encoding="utf-8")
        if output:
            print(json.dumps(output))
        return
    if event not in ("PreToolUse", "PostToolUse"):
        raise ValueError(f"skill_loader.py does not handle hook event {event!r}")
    if not path.exists():
        if not (STATE_DIR / "asks" / "active.json").is_file():
            raise FileNotFoundError(f"{path} missing: the UserPromptSubmit skill_loader hook did not run for this session and no ask is active")
        # Harnesses whose prompt hook carries no prompt or ran before the ask existed: load the active ask's skills for its request.
        loadout, rows = choose(active()[1]["request"])
        install(rows)
    else:
        loadout = json.loads(path.read_text(encoding="utf-8"))
    # Loadouts written before 0.14.0 do not track the chat's ask.
    loadout.setdefault("ask", None)
    loadout.setdefault("displaced_noted", None)
    output = None
    if event == "PreToolUse":
        output = pre_tool_output(payload["session_id"], loadout, payload["tool_input"])
        note = displaced_context(loadout)
        denied = output is not None and output["hookSpecificOutput"].get("permissionDecision") == "deny"
        if note and not denied:
            context = " ".join(filter(None, [output["hookSpecificOutput"]["additionalContext"] if output else "", note]))
            output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": context}}
    elif payload["tool_name"] == ASK_TOOL:
        record_answers(payload["session_id"], payload["tool_input"], payload["tool_response"])
    elif (payload["tool_name"] == "run_in_terminal" and OPENS_ASK.search(payload["tool_input"]["command"])
          and (STATE_DIR / "asks" / "active.json").is_file()):
        loadout["ask"] = active()[1]["ask"]
    path.write_text(json.dumps(loadout), encoding="utf-8")
    if output:
        print(json.dumps(output))


if __name__ == "__main__":
    main()
