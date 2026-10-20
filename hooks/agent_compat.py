"""Run a harness hook for Copilot, Claude Code, Cursor or Codex: map the client's payload to the VS Code shape the hooks read, run the hook, map its output back."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Client = Literal["claude", "cursor", "codex", "copilot"]
Json = dict[str, Any]

RUNTIME = Path(__file__).resolve().parents[1]
CLIENTS = ("claude", "cursor", "codex", "copilot")
TOOL_NAMES = {"Bash": "run_in_terminal", "PowerShell": "run_in_terminal", "Shell": "run_in_terminal", "exec_command": "run_in_terminal",
              "Write": "create_file", "Edit": "replace_string_in_file", "MultiEdit": "multi_replace_string_in_file", "Read": "read_file",
              "Grep": "grep_search", "Glob": "file_search", "LS": "list_dir", "TodoWrite": "manage_todo_list",
              "AskUserQuestion": "vscode_askQuestions"}
CURSOR_EVENTS = {"sessionStart": "SessionStart", "beforeSubmitPrompt": "UserPromptSubmit", "preToolUse": "PreToolUse",
                 "postToolUse": "PostToolUse", "stop": "Stop"}
PROJECT_DIR_ENV = {"claude": "CLAUDE_PROJECT_DIR", "cursor": "CURSOR_PROJECT_DIR"}
USAGE = ("usage: agent_compat.py [--ask-only] <claude|cursor|codex|copilot> <script under the runtime> [KEY=VALUE ...] [-- script args]\n"
         "  --ask-only: do nothing unless the project has an open Frontier HVE ask (.hve/asks/active.json), for hook files every session runs")


def ask_answers(tool_input: Json, response: Any) -> Json:
    """Return Claude Code AskUserQuestion answers (question text -> comma-joined labels) keyed by header, as VS Code reports them."""
    answers = (json.loads(response) if isinstance(response, str) else response)["answers"]
    return {"answers": {q["header"]: {"selected": [label.strip() for label in answers[q["question"]].split(",")]}
                        if q["question"] in answers else {"skipped": True} for q in tool_input["questions"]}}


def to_vscode(payload: Json, client: Client) -> Json:
    """Return the payload with VS Code event names, session id, tool names, file path field and Stop fields."""
    event = CURSOR_EVENTS[payload["hook_event_name"]] if client == "cursor" else payload["hook_event_name"]
    out = payload | {"hook_event_name": event, "session_id": payload["conversation_id"] if client == "cursor" else payload["session_id"]}
    if "tool_name" in payload:
        tool_input = payload["tool_input"]
        if isinstance(tool_input, dict) and "file_path" in tool_input:
            tool_input = {k: v for k, v in tool_input.items() if k != "file_path"} | {"filePath": tool_input["file_path"]}
        out |= {"tool_name": TOOL_NAMES.get(payload["tool_name"], payload["tool_name"]), "tool_input": tool_input}
        if client == "copilot":
            # Copilot sends no tool call id; the timestamp identifies the call within the session.
            out["tool_use_id"] = f"copilot-{payload['timestamp']}"
        if event == "PostToolUse":
            if client == "cursor":
                response = payload["tool_output"]
            elif client == "copilot":
                response = payload["tool_result"]["text_result_for_llm"]
            else:
                response = payload["tool_response"]
            out["tool_response"] = ask_answers(tool_input, response) if payload["tool_name"] == "AskUserQuestion" and client == "claude" else response
    if event == "Stop":
        out |= {"timestamp": datetime.now(timezone.utc).isoformat(),
                "stop_hook_active": payload["loop_count"] > 0 if client == "cursor" else payload["stop_hook_active"]}
    return out


def to_cursor(output: Json, event: str) -> Json:
    """Return Cursor's native response for a hook output already in Claude Code form; Cursor has no context channel on prompt submit."""
    specific = output.get("hookSpecificOutput", {})
    if event == "PreToolUse":
        if specific.get("permissionDecision") != "deny":
            return {}
        reason = specific["permissionDecisionReason"]
        return {"permission": "deny", "user_message": reason, "agent_message": reason}
    if event == "Stop":
        return {"followup_message": output["reason"]} if output.get("decision") == "block" else {}
    if event in ("PostToolUse", "SessionStart"):
        context = [output["reason"]] if output.get("decision") == "block" else []
        context += [specific["additionalContext"]] if "additionalContext" in specific else []
        return {"additional_context": "\n".join(context)} if context else {}
    return {"continue": True}


def to_copilot(output: Json, event: str) -> Json:
    """Return Copilot's flat hook output: deny with a reason, context where Copilot reads it, or a Stop block."""
    specific = output.get("hookSpecificOutput", {})
    if event == "PreToolUse":
        if specific.get("permissionDecision") == "deny":
            return {"permissionDecision": "deny", "permissionDecisionReason": specific["permissionDecisionReason"]}
        # Copilot cannot stop the agent from PreToolUse: an escalation stop becomes a deny.
        return {"permissionDecision": "deny", "permissionDecisionReason": output["stopReason"]} if output.get("continue") is False else {}
    if event == "Stop":
        return {"decision": "block", "reason": output["reason"]} if output.get("decision") == "block" else {}
    if event in ("PostToolUse", "SessionStart", "SubagentStart"):
        context = [output["reason"]] if output.get("decision") == "block" else []
        context += [specific["additionalContext"]] if "additionalContext" in specific else []
        return {"additionalContext": "\n".join(context)} if context else {}
    return {}


def from_vscode(output: Json, event: str, client: Client) -> Json:
    """Return a hook's VS Code output in the client's format; an empty dict is no decision."""
    specific = output.get("hookSpecificOutput", {})
    if event == "Stop" and "decision" in specific:
        output = {k: v for k, v in output.items() if k != "hookSpecificOutput"} | {"decision": specific["decision"], "reason": specific["reason"]}
    if client == "codex" and event == "PreToolUse":
        output = {k: v for k, v in output.items() if k not in ("continue", "stopReason")}
    if client == "copilot":
        return to_copilot(output, event)
    return to_cursor(output, event) if client == "cursor" else output


def main() -> None:
    """Translate stdin, run the named runtime hook with the given environment, and print its translated output."""
    args = sys.argv[1:]
    ask_only = args[:1] == ["--ask-only"]
    args = args[1:] if ask_only else args
    if len(args) < 2 or args[0] not in CLIENTS:
        raise SystemExit(USAGE)
    client, script, rest = args[0], (RUNTIME / args[1]).resolve(), args[2:]
    if not script.is_relative_to(RUNTIME) or not script.is_file():
        raise SystemExit(f"{args[1]} is not a script under {RUNTIME}")
    split = rest.index("--") if "--" in rest else len(rest)
    env = {key: value for key, _, value in (pair.partition("=") for pair in rest[:split])}
    payload = json.load(sys.stdin)
    project = Path(os.environ[PROJECT_DIR_ENV[client]]) if client in PROJECT_DIR_ENV else Path(payload["cwd"])
    hook_payload = to_vscode(payload, client)  # type: ignore[arg-type]
    event = hook_payload["hook_event_name"]
    if ask_only and not (project / ".hve" / "asks" / "active.json").is_file():
        if client == "codex" and event == "Stop":
            print("{}")
        return
    result = subprocess.run([sys.executable, str(script), *rest[split + 1:]], input=json.dumps(hook_payload), capture_output=True,
                            text=True, cwd=project, env=os.environ | env)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    output = from_vscode(json.loads(result.stdout) if result.stdout.strip() else {}, event, client)  # type: ignore[arg-type]
    if output or (client == "codex" and event == "Stop"):
        print(json.dumps(output))


if __name__ == "__main__":
    main()
