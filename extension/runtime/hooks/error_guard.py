"""Error-streak guard: after repeated failed commands in a row, pause the agent and make it ask the user for direction instead of retrying."""

import json
import re
import sys
from pathlib import Path
from typing import Any

from hve_paths import RUNS_DIR
from interventions import SESSION_ID, record

STREAK_LIMIT = 3
TERMINAL_TOOLS = {"run_in_terminal"}
# Copilot CLI tool names (view, grep, glob, ask_user) arrive unmapped.
READ_ONLY_TOOLS = {"read_file", "file_search", "grep_search", "list_dir", "semantic_search", "get_errors", "get_terminal_output", "view_image",
                   "manage_todo_list", "view", "grep", "glob"}
ASK_TOOLS = {"vscode_askQuestions", "ask_user"}
FAILED = re.compile(r"exit(?:ed with)? code:? -?[1-9]\d*|^ERROR while calling tool", re.I | re.M)
# The feature loop's own checks fail by design; its retry rules and escalation handle them.
LOOP_SCRIPT = re.compile(r"tools[/\\](loop[/\\](loop|flow)|git[/\\](parallel_options|branch_workflow))\.py", re.I)
TITLE = "Error guard - paused for your attention"

Json = dict[str, Any]


def streak_file(session_id: str) -> Path:
    """Return the session's error-streak file after validating the session id."""
    if not SESSION_ID.match(session_id):
        raise ValueError(f"unsafe session_id {session_id!r}")
    return RUNS_DIR / f"{session_id}.errors.json"


def load(session_id: str) -> Json:
    """Return the session's error streak: the failed commands in a row and whether the agent is paused."""
    path = streak_file(session_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"failures": [], "paused": False}


def save(session_id: str, state: Json) -> None:
    """Write the session's error streak."""
    streak_file(session_id).write_text(json.dumps(state), encoding="utf-8")


def clip(text: str, limit: int) -> str:
    """Return text on one line, cut to limit characters."""
    line = " ".join(text.split())
    return line if len(line) <= limit else line[:limit - 3] + "..."


def message(failures: list[Json]) -> str:
    """Return the pause message listing the failed commands and their last output, and telling the agent to ask the user for direction."""
    listed = "; ".join(f"{i}) `{clip(f['command'], 120)}` -> {clip(f['output'], 160)}" for i, f in enumerate(failures, start=1))
    return (f"{TITLE}: the last {len(failures)} commands failed in a row, so the agent paused instead of retrying again. {listed}. "
            "Ask the user for direction now with the ask-questions tool: show the failures and your best guess at the cause, and offer to "
            "fix the environment (a missing tool, package or permission), change the approach, or skip this step. "
            "Only reading and asking are allowed until the user answers.")


def post_tool(session_id: str, tool_name: str, tool_input: Json, response: Any) -> Json | None:
    """Count a failed terminal command (a success resets the streak), pause at the limit, and resume once the user answers the question."""
    if tool_name in ASK_TOOLS:
        if load(session_id)["paused"]:
            save(session_id, {"failures": [], "paused": False})
        return None
    if tool_name not in TERMINAL_TOOLS or LOOP_SCRIPT.search(tool_input["command"]):
        return None
    text = response if isinstance(response, str) else json.dumps(response)
    if not FAILED.search(text):
        save(session_id, {"failures": [], "paused": False})
        return None
    state = load(session_id)
    state["failures"] = [*state["failures"], {"command": tool_input["command"], "output": text[-400:]}][-STREAK_LIMIT:]
    state["paused"] = len(state["failures"]) >= STREAK_LIMIT
    save(session_id, state)
    if not state["paused"]:
        return None
    reason = message(state["failures"])
    record(session_id, "error_guard", "error_streak", reason)
    return {"decision": "block", "reason": reason, "systemMessage": reason}


def pre_tool(session_id: str, tool_name: str) -> Json | None:
    """While paused, deny every tool except reading and asking the user, until the user answers."""
    state = load(session_id)
    if not state["paused"] or tool_name in READ_ONLY_TOOLS | ASK_TOOLS:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": message(state["failures"])}}


def main() -> None:
    """Dispatch PostToolUse (count failures, resume on an answer), PreToolUse (hold while paused) and UserPromptSubmit (the user answered: reset)."""
    payload = json.load(sys.stdin)
    event, session_id = payload["hook_event_name"], payload["session_id"]
    if event == "PostToolUse":
        output = post_tool(session_id, payload["tool_name"], payload["tool_input"], payload["tool_response"])
    elif event == "PreToolUse":
        output = pre_tool(session_id, payload["tool_name"])
    elif event == "UserPromptSubmit":
        streak_file(session_id).unlink(missing_ok=True)
        output = None
    else:
        raise ValueError(f"error_guard.py does not handle hook event {event!r}")
    if output:
        print(json.dumps(output))


if __name__ == "__main__":
    main()
