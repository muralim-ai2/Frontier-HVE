"""Loop guards: protect loop state (anti-gaming), log tool calls for diagnosis, gate pushes to ticked PRs, stop on escalation, victory check."""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from interventions import record
from guard_policy import check, record_answers
from hve_paths import RUNS_DIR
from module_guard import edited_paths

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "loop"))
from loop_paths import LOOP_FILES, ask_folder, loop_dir, project_folder, state_dir, state_file  # noqa: E402

READ_ONLY_TOOLS = {"read_file", "file_search", "grep_search", "list_dir", "semantic_search", "get_errors", "get_terminal_output",
                   "terminal_last_command", "manage_todo_list", "view_image", "vscode_askQuestions", "mcp_graphify_query_graph",
                   "mcp_graphify_get_node", "mcp_graphify_get_neighbors", "mcp_graphify_shortest_path",
                   "github-pull-request_pullRequestStatusChecks", "github-pull-request_currentActivePullRequest"}
PR_TOOL = "github-pull-request_create_pull_request"
ASK_TOOL = "vscode_askQuestions"
LOCKED_FILES = {"feature_list.json", "progress.txt", "tracker.json"}
LOOP_FILE_NAMES = re.compile(r"feature_list\.json|progress\.txt|tracker\.json", re.I)
# Loop state: .harness/, an ask's loop/ folder, or the project folder, other than the loop files themselves.
LOOP_STATE = re.compile(r"\.harness[/\\]|\.hve[/\\](asks[/\\][^/\\\s\"']+[/\\]loop|project)[/\\]"
                        r"(?!(feature_list(\.add)?\.json|progress\.txt|tracker\.json)\b)", re.I)
SHELL_WRITE = re.compile(r"(?<![\d&])>|\b(Set-Content|Add-Content|Out-File|Remove-Item|Move-Item|Copy-Item|Rename-Item|New-Item|rm|mv|cp|del|"
                         r"erase|ren|move|copy|tee|truncate|touch)\b|\bsed\s+-i|\bgit\s+(checkout|restore|rm|mv)\b|\bpython3?\s+-c|\bnode\s+-e",
                         re.I)
LOOP_SCRIPT = re.compile(r"^\s*python3?\s+\"?[^\"\s]*tools[/\\](loop[/\\](loop|flow)|git[/\\](parallel_options|branch_workflow))\.py\"?"
                         r"(\s+[\w./\\:-]+)*\s*$", re.I)
HUMAN_ONLY = re.compile(r"loop\.py\s+resume\b|flow\.py\s+resume\b", re.I)
HOOK_BYPASS = re.compile(r"--no-verify|core\.hooksPath|\.git[/\\]hooks", re.I)
GIT_PUSH = re.compile(r"\bgit\s+push\b", re.I)
BRANCH = re.compile(r"feature/[\w-]+")
FORCE = re.compile(r"\s(-f|--force|--force-with-lease)\b|\s\+\S", re.I)
# Temporary (D-056): "advise" surfaces loop-file, loop-state and victory-check trips to the user instead of blocking them.
MODE = json.loads((Path(__file__).parent / "guard_mode.json").read_text(encoding="utf-8"))["loop_guard"]
if MODE not in ("advise", "enforce"):
    raise ValueError(f"guard_mode.json loop_guard={MODE!r}, expected 'advise' or 'enforce'")
ADVISED = {"anti_gaming": "loop state (.harness/, the ask's loop/ folder or .hve/project/) was changed outside the loop scripts",
           "loop_files": "a loop file (feature_list.json, progress.txt or tracker.json) was changed while features still fail",
           "victory_check": "the agent stopped while features still fail"}
ATTENTION = "Guard Invoked - For your attention"

Json = dict[str, Any]


def project() -> Path:
    """Return the agent's project folder: HARNESS_PROJECT (set per agent in its hook env) under the workspace root."""
    return Path.cwd() / os.environ["HARNESS_PROJECT"]


def read(path: Path) -> Any:
    """Return parsed JSON, or None when the file does not exist yet."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def escalation(proj: Path) -> str | None:
    """Return the human question of an escalated loop or flow, if any."""
    for path in (state_file(proj), state_dir(proj) / "flow.json"):
        state = read(path)
        if state and state["escalated"]:
            return state["help"]["question"]
    return None


def loop_running(proj: Path) -> bool:
    """Return True while an initialized loop still has failing features or a flow has not reached done."""
    flow = read(state_dir(proj) / "flow.json")
    if flow is not None and flow["stage"] != "done":
        return True
    if not state_file(proj).exists():
        return False
    features = json.loads((loop_dir(proj) / "feature_list.json").read_text(encoding="utf-8"))
    return any(not f["passes"] for f in features)


def protected_target(raw: str, proj: Path, running: bool) -> str | None:
    """Return 'state' for a path in loop state (the ask's loop folder, the project folder), 'files' for the locked loop files while the
    loop runs, else None."""
    path = (Path.cwd() / raw).resolve()
    files = loop_dir(proj).resolve()
    if path.parent == files and path.name in LOOP_FILES:
        return "files" if running and path.name in LOCKED_FILES else None
    folders = [state_dir(proj), *([project_folder(proj)] if ask_folder(proj) else [])]
    return "state" if any(path.is_relative_to(f.resolve()) for f in folders) else None


def clip(text: str) -> str:
    """Return text on one line, cut to 160 characters."""
    line = " ".join(text.split())
    return line if len(line) <= 160 else line[:157] + "..."


def describe(tool_name: str, tool_input: Json) -> str:
    """Return what a tool call changes, in one line: the command, or the files with the first replaced or written text."""
    if tool_name == "run_in_terminal":
        return f"terminal command `{clip(tool_input['command'])}`"
    edits = tool_input.get("replacements") or [tool_input]
    target = f"{tool_name} on {', '.join(edited_paths(tool_input))}"
    more = f" (and {len(edits) - 1} more edits)" if len(edits) > 1 else ""
    if "oldString" in edits[0]:
        return f"{target}: `{clip(edits[0]['oldString'])}` replaced by `{clip(edits[0]['newString'])}`{more}"
    if "content" in edits[0]:
        return f"{target}, new content `{clip(edits[0]['content'])}`"
    return target


def advise(session_id: str, kind: str, change: str, reason: str, event: str) -> Json:
    """Record the trip and return a message for the user and the agent instead of a block (awareness mode)."""
    record(session_id, "loop_guard", kind, f"advised: {change}")
    message = (f"{ATTENTION}: during the run {ADVISED[kind]}. The modification was: {change}. Why the guard watches this: {reason} The loop "
               "guard is in awareness mode for now, so it did not block; review the change and tell the agent to undo it if it was not intended.")
    if event == "Stop":
        return {"systemMessage": message}
    return {"systemMessage": message, "hookSpecificOutput": {"hookEventName": event, "additionalContext": (
        f"{message} Show this to the user word for word in your next reply under the heading **{ATTENTION}**, then continue.")}}


def deny(session_id: str, kind: str, reason: str, blindspot: str | None = None, stop: bool = False, change: str = "") -> Json | None:
    """Record the intervention and return a PreToolUse deny (optionally stopping the agent), an awareness message in advise mode, or None
    when the user waived the guard."""
    if MODE == "advise" and kind in ADVISED:
        return advise(session_id, kind, change, reason, "PreToolUse")
    checked = check(session_id, "loop_guard", kind, reason, blindspot)
    if checked is None:
        return None
    out: Json = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": checked}}
    return out | ({"continue": False, "stopReason": checked} if stop else {})


def log_tool(proj: Path, entry: Json) -> None:
    """Append a tool event to the ask's tool log while a feature is being built (input to diagnose.py)."""
    state = read(state_file(proj))
    if state and state["current"]:
        with (state_dir(proj) / "tool_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry | {"ts_ms": time.time() * 1000, "feature": state["current"]}) + "\n")


def push_gate(session_id: str, proj: Path, branches: list[str], what: str) -> Json | None:
    """Deny a push or PR unless the loop uses GitHub review and the human ticked every branch it names."""
    state = read(state_file(proj))
    approved = (read(state_dir(proj) / "push_approved.json") or {"branches": []})["branches"]
    if not state or state["review"] != "github":
        return deny(session_id, "push_blocked", f"{what} is only allowed for GitHub review loops.")
    unticked = sorted(set(branches) - set(approved)) if branches else ["(no feature branch named)"]
    if unticked:
        return deny(session_id, "push_blocked", f"{what} needs the human's tick first for {unticked}. Show the queue with the pr-push skill.")
    return None


def pre_tool(session_id: str, tool_name: str, tool_input: Json, tool_use_id: str) -> Json | None:
    """Return a deny for escalated work, hook bypasses, human-only commands, unticked pushes, and edits to loop state."""
    proj = project()
    question = escalation(proj)
    if question:
        return deny(session_id, "escalated", f"Escalated to the human: {question} Stop and ask exactly this.", stop=True)
    log_tool(proj, {"phase": "pre", "tool": tool_name, "id": tool_use_id,
                    "key": tool_input.get("command", tool_input.get("filePath", ""))})
    if tool_name in READ_ONLY_TOOLS:
        return None
    if tool_name == PR_TOOL:
        return push_gate(session_id, proj, [tool_input["head"]], "Opening a PR")
    if tool_name == "run_in_terminal":
        command = tool_input["command"]
        if HOOK_BYPASS.search(command):
            return deny(session_id, "hook_bypass", "Commits must pass the pre-commit no-fallback scan; do not bypass git hooks.", "B1")
        if HUMAN_ONLY.search(command):
            return deny(session_id, "human_only", "Resuming an escalation is for the human; ask them and stop.")
        if GIT_PUSH.search(command):
            if FORCE.search(command):
                return deny(session_id, "push_blocked", "Force pushes are not allowed.")
            return push_gate(session_id, proj, BRANCH.findall(command), "git push")
        if LOOP_SCRIPT.match(command) or not SHELL_WRITE.search(command):
            return None
        hits = {"state"} if LOOP_STATE.search(command) else {"files"} if LOOP_FILE_NAMES.search(command) and loop_running(proj) else set()
    else:
        running = loop_running(proj)
        hits = {protected_target(p, proj, running) for p in edited_paths(tool_input)}
    if "state" in hits:
        return deny(session_id, "anti_gaming", "Loop state (.harness/, the ask's loop/ folder or .hve/project/) changes only through the loop "
                    "scripts. Do not edit it.", "B5", change=describe(tool_name, tool_input))
    if "files" in hits:
        return deny(session_id, "loop_files", "While features still fail, feature_list.json, progress.txt and tracker.json change only "
                    "through the loop scripts; add features with feature_list.add.json and `loop.py amend`.", "B5",
                    change=describe(tool_name, tool_input))
    return None


def stop(session_id: str, now_ms: float, stop_hook_active: bool) -> Json | None:
    """Block stopping while features fail or the flow is unfinished, unless escalated, or the budget (or one push) is spent."""
    proj = project()
    if escalation(proj):
        return None
    features = read(loop_dir(proj) / "feature_list.json") if state_file(proj).exists() else None
    flow = read(state_dir(proj) / "flow.json")
    remaining = [f["name"] for f in features or [] if not f["passes"]]
    unfinished = flow is not None and flow["stage"] != "done"
    if not remaining and not unfinished:
        return None
    if os.environ["HARNESS_STOP_POLICY"] == "budget":
        budget = json.loads((RUNS_DIR / f"{session_id}.budget.json").read_text(encoding="utf-8"))
        if now_ms - budget["start_ms"] >= budget["budget_ms"]:
            return None
    elif stop_hook_active:
        return None
    reason = (f"Victory check: features still failing: {', '.join(remaining)}. Continue with `loop.py next`." if remaining
              else f"Victory check: the flow is at stage {flow['stage']!r}, not done. Continue with `flow.py status`.")
    if MODE == "advise":
        return advise(session_id, "victory_check", ", ".join(remaining) or f"flow at stage {flow['stage']!r}", reason, "Stop")
    record(session_id, "loop_guard", "victory_check", reason)
    return {"hookSpecificOutput": {"hookEventName": "Stop", "decision": "block", "reason": reason}}


def main() -> None:
    """Dispatch PreToolUse, PostToolUse and Stop events."""
    payload = json.load(sys.stdin)
    event, session_id = payload["hook_event_name"], payload["session_id"]
    output = None
    if event == "PreToolUse":
        output = pre_tool(session_id, payload["tool_name"], payload["tool_input"], payload["tool_use_id"])
    elif event == "PostToolUse":
        response = payload["tool_response"]
        if payload["tool_name"] == ASK_TOOL:
            record_answers(session_id, payload["tool_input"], response)
        log_tool(project(), {"phase": "post", "tool": payload["tool_name"], "id": payload["tool_use_id"],
                             "response": (response if isinstance(response, str) else json.dumps(response))[:500]})
    elif event == "Stop":
        output = stop(session_id, datetime.fromisoformat(payload["timestamp"]).timestamp() * 1000, payload["stop_hook_active"])
    else:
        raise ValueError(f"loop_guard.py does not handle hook event {event!r}")
    if output:
        print(json.dumps(output))


if __name__ == "__main__":
    main()
