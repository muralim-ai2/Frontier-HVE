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
from hve_paths import RUNS_DIR

READ_ONLY_TOOLS = {"read_file", "file_search", "grep_search", "list_dir", "semantic_search", "get_errors", "get_terminal_output",
                   "terminal_last_command", "manage_todo_list", "view_image", "vscode_askQuestions", "mcp_graphify_query_graph",
                   "mcp_graphify_get_node", "mcp_graphify_get_neighbors", "mcp_graphify_shortest_path",
                   "github-pull-request_pullRequestStatusChecks", "github-pull-request_currentActivePullRequest"}
PR_TOOL = "github-pull-request_create_pull_request"
PROTECTED = re.compile(r"feature_list\.json|progress\.txt|\.harness[/\\]", re.I)
LOOP_SCRIPT = re.compile(r"^\s*python3?\s+\"?[^\"\s]*tools[/\\](loop[/\\](loop|flow)|git[/\\](parallel_options|branch_workflow))\.py\"?"
                         r"(\s+[\w./\\:-]+)*\s*$", re.I)
HUMAN_ONLY = re.compile(r"loop\.py\s+resume\b|flow\.py\s+resume\b", re.I)
HOOK_BYPASS = re.compile(r"--no-verify|core\.hooksPath|\.git[/\\]hooks", re.I)
GIT_PUSH = re.compile(r"\bgit\s+push\b", re.I)
BRANCH = re.compile(r"feature/[\w-]+")
FORCE = re.compile(r"\s(-f|--force|--force-with-lease)\b|\s\+\S", re.I)

Json = dict[str, Any]


def project() -> Path:
    """Return the agent's project folder: HARNESS_PROJECT (set per agent in its hook env) under the workspace root."""
    return Path.cwd() / os.environ["HARNESS_PROJECT"]


def read(path: Path) -> Any:
    """Return parsed JSON, or None when the file does not exist yet."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def escalation(proj: Path) -> str | None:
    """Return the human question of an escalated loop or flow, if any."""
    for name in ("state.json", "flow.json"):
        state = read(proj / ".harness" / name)
        if state and state["escalated"]:
            return state["help"]["question"]
    return None


def deny(session_id: str, kind: str, reason: str, blindspot: str | None = None, stop: bool = False) -> Json:
    """Record the intervention and return a PreToolUse deny, optionally stopping the agent."""
    record(session_id, "loop_guard", kind, reason, blindspot)
    out: Json = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}
    return out | ({"continue": False, "stopReason": reason} if stop else {})


def log_tool(proj: Path, entry: Json) -> None:
    """Append a tool event to the project's tool log while a feature is being built (input to diagnose.py)."""
    state = read(proj / ".harness" / "state.json")
    if state and state["current"]:
        with (proj / ".harness" / "tool_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry | {"ts_ms": time.time() * 1000, "feature": state["current"]}) + "\n")


def push_gate(session_id: str, proj: Path, branches: list[str], what: str) -> Json | None:
    """Deny a push or PR unless the loop uses GitHub review and the human ticked every branch it names."""
    state = read(proj / ".harness" / "state.json")
    approved = (read(proj / ".harness" / "push_approved.json") or {"branches": []})["branches"]
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
        if LOOP_SCRIPT.match(command) or not PROTECTED.search(command):
            return None
    elif not PROTECTED.search(json.dumps(tool_input)) or (
            not (proj / ".harness" / "state.json").exists() and ".harness" not in json.dumps(tool_input)):
        return None  # before loop init, the agent writes feature_list.json itself
    return deny(session_id, "anti_gaming", "feature_list.json, progress.txt and .harness/ change only through the loop scripts. "
                "Do not edit them.", "B5")


def stop(session_id: str, now_ms: float, stop_hook_active: bool) -> Json | None:
    """Block stopping while features fail or the flow is unfinished, unless escalated, or the budget (or one push) is spent."""
    proj = project()
    if escalation(proj):
        return None
    features = read(proj / "feature_list.json") if (proj / ".harness" / "state.json").exists() else None
    flow = read(proj / ".harness" / "flow.json")
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
