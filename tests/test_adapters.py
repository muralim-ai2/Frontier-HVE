"""Tests of the client adapters: export structure for Claude Code, Cursor, Codex and VS Code, and the exported hooks run with each
client's documented hook payloads through agent_compat.py."""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
EXTENSION = REPO / "extension"
EXPORT = EXTENSION / "runtime" / "tools" / "adapters" / "export.py"
PROFILE = {"prompt_style": None, "wants_evidence": None, "verbosity": None, "output_format": None, "build_preference": "pro_code",
           "depth_evidence": 0, "explanation_depth": None, "bloat_triggers": []}

Json = dict[str, Any]


def export(ws: Path, client: str, *extra: str) -> Json:
    """Run the built exporter for a client into ws and return its JSON report."""
    result = subprocess.run([sys.executable, str(EXPORT), client, str(ws), *extra], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def exported_workspace(tmp: str) -> Path:
    """Build the extension and export all three clients plus the Azure DevOps server into a fresh workspace."""
    subprocess.run([sys.executable, str(EXTENSION / "build.py")], check=True, capture_output=True)
    ws = Path(tmp) / "ws"
    ws.mkdir()
    for client in ("claude", "cursor", "codex", "vscode"):
        export(ws, client, "--ado", "contoso")
    (ws / ".hve" / "user_profile.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    return ws


def claude_hooks(ws: Path) -> dict[str, list[list[str]]]:
    """Return the exec-form argument vectors per event from the exported hve-creator subagent, with the project dir filled in."""
    hooks: dict[str, list[list[str]]] = {}
    front = (ws / ".claude" / "agents" / "hve-creator.md").read_text(encoding="utf-8").split("---\n")[1]
    for line in front.splitlines():
        if match := re.match(r"^  (\w+):$", line):
            event = match[1]
            hooks[event] = []
        elif match := re.match(r"^ {10}args: (.+)$", line):
            hooks[event].append([a.replace("${CLAUDE_PROJECT_DIR}", str(ws)) for a in json.loads(match[1])])
    return hooks


def fire(ws: Path, client: str, payload: Json) -> list[Json]:
    """Run every exported hook of the client for the payload's event, the way the client runs them; return the non-empty outputs."""
    event = payload["hook_event_name"]
    env = os.environ | {"CLAUDE_PROJECT_DIR": str(ws), "CURSOR_PROJECT_DIR": str(ws)}
    if client == "claude":
        runs = [dict(args=[sys.executable, *argv], shell=False) for argv in claude_hooks(ws)[event]]
    elif client == "cursor":
        runs = [dict(args=h["command"], shell=True) for h in json.loads((ws / ".cursor" / "hooks.json").read_text())["hooks"][event]]
    else:
        groups = json.loads((ws / ".codex" / "hooks.json").read_text())["hooks"][event]
        runs = [dict(args=h["command"], shell=True) for g in groups for h in g["hooks"]]
    outputs = []
    for run in runs:
        result = subprocess.run(run["args"], shell=run["shell"], cwd=ws, input=json.dumps(payload), capture_output=True, text=True, env=env)
        assert result.returncode == 0, (client, event, run["args"], result.stderr)
        outputs += [json.loads(result.stdout)] if result.stdout.strip() else []
    return outputs


def start_loop(ws: Path, passes: bool = False, escalated: bool = False) -> None:
    """Write the loop state the guards read: one feature and the loop state file."""
    (ws / ".harness").mkdir(exist_ok=True)
    (ws / "feature_list.json").write_text(json.dumps([{"name": "login", "description": "d", "verify": "exit 0", "passes": passes}]))
    state = {"current": None, "review": "local", "escalated": escalated, "help": {"question": "Which database?"}}
    (ws / ".harness" / "state.json").write_text(json.dumps(state), encoding="utf-8")


def test_export_structure() -> None:
    """Each client gets the runtime, skills (minus VS Code-only ones), its agents, hooks naming real scripts, and the ado server."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = exported_workspace(tmp)
        runtime = ws / ".hve" / "runtime"
        assert (runtime / "hooks" / "agent_compat.py").is_file() and (runtime / "skills" / "licenses" / "agentx" / "LICENSE").is_file()
        for skills in (".claude/skills", ".cursor/skills", ".agents/skills"):
            names = {p.parent.name for p in (ws / skills).glob("*/SKILL.md")}
            assert {"delivery-coach", "feature-checklist"} <= names and not {"pr-push", "export-harness"} & names, (skills, names)
            for skill in (ws / skills).glob("*/SKILL.md"):
                assert re.search(rf"^name: \"?{skill.parent.name}\"?$", skill.read_text(encoding="utf-8"), re.M), skill
        agents = {p.stem for p in (ws / ".claude" / "agents").glob("*.md")}
        assert agents == {"hve-creator", "hve-single", "hve-azure-devops"}, agents
        argv = [a for args in claude_hooks(ws).values() for a in args]
        assert {a[2] for a in argv} == {"hooks/profile_detector.py", "hooks/skill_loader.py", "hooks/compaction.py", "hooks/loop_guard.py",
                                        "hooks/module_guard.py", "scripts/choice_recorder.py", "scripts/guardrail.py"}
        assert all((runtime / a[2]).is_file() for a in argv)
        assert any(a[2] == "scripts/guardrail.py" and a[-2:] == ["--", "--hook"] for a in argv), argv
        creator = (ws / ".claude" / "agents" / "hve-creator.md").read_text(encoding="utf-8")
        assert "{{RUNTIME}}" not in creator and ".hve/runtime/tools/loop/loop.py" in creator
        cursor = json.loads((ws / ".cursor" / "hooks.json").read_text())
        assert cursor["version"] == 1 and set(cursor["hooks"]) == {"sessionStart", "beforeSubmitPrompt", "preToolUse", "postToolUse", "stop"}
        assert "disable-model-invocation: true" in (ws / ".cursor" / "skills" / "hve-creator" / "SKILL.md").read_text(encoding="utf-8")
        codex = json.loads((ws / ".codex" / "hooks.json").read_text())
        assert set(codex["hooks"]) == {"SessionStart", "UserPromptSubmit", "SubagentStart", "PreToolUse", "PostToolUse", "Stop"}
        assert "allow_implicit_invocation: false" in (ws / ".agents" / "skills" / "hve-creator" / "agents" / "openai.yaml").read_text()
        for path, key in ((".mcp.json", "mcpServers"), (".cursor/mcp.json", "mcpServers"), (".vscode/mcp.json", "servers")):
            server = json.loads((ws / path).read_text())[key]["ado"]
            assert "@azure-devops/mcp" in server["args"] and server["args"][-5:] == ["core", "work", "work-items", "repositories", "pipelines"]
        assert "[mcp_servers.ado]" in (ws / ".codex" / "config.toml").read_text()


def test_export_refuses_foreign_files_and_bad_organizations() -> None:
    """A hooks file the harness did not write is kept, a re-export is idempotent, and an unsafe organization name is rejected."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = exported_workspace(tmp)
        export(ws, "codex", "--ado", "contoso")
        assert (ws / ".codex" / "config.toml").read_text().count("[mcp_servers.ado]") == 1
        (ws / ".cursor" / "hooks.json").write_text('{"version": 1, "hooks": {"stop": [{"command": "./mine.sh"}]}}')
        result = subprocess.run([sys.executable, str(EXPORT), "cursor", str(ws)], capture_output=True, text=True)
        assert result.returncode != 0 and "not written by Frontier HVE" in result.stderr
        assert "mine.sh" in (ws / ".cursor" / "hooks.json").read_text()
        result = subprocess.run([sys.executable, str(EXPORT), "vscode", str(ws), "--ado", "x; rm -rf /"], capture_output=True, text=True)
        assert result.returncode != 0 and "organization name" in result.stderr


def test_claude_code_hooks() -> None:
    """Claude Code payloads: profile context, skill loadout, guards, module size, ticked check, victory check and escalation stop."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = exported_workspace(tmp)
        base = {"session_id": "c1", "cwd": str(ws), "transcript_path": "t", "permission_mode": "default"}
        start = fire(ws, "claude", base | {"hook_event_name": "SessionStart", "source": "startup"})
        assert any("Delivery" in o["hookSpecificOutput"]["additionalContext"] for o in start), start
        fire(ws, "claude", base | {"hook_event_name": "UserPromptSubmit", "prompt": "Design an accessible signup page UI with clear forms"})
        assert json.loads((ws / ".hve" / "runs" / "c1.skills.json").read_text())["skills"]
        read = {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": str(ws / "README.md")}, "tool_use_id": "t1"}
        notice = fire(ws, "claude", base | read)
        assert any(".hve/skills/" in o["hookSpecificOutput"].get("additionalContext", "") for o in notice), notice
        start_loop(ws)
        write = {"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_use_id": "t2",
                 "tool_input": {"file_path": str(ws / "feature_list.json"), "content": "[]"}}
        denied = fire(ws, "claude", base | write)
        assert denied[0]["hookSpecificOutput"]["permissionDecision"] == "deny" and "loop scripts" in json.dumps(denied), denied
        push = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "t3", "tool_input": {"command": "git push -f origin main"}}
        assert "Force pushes" in fire(ws, "claude", base | push)[0]["hookSpecificOutput"]["permissionDecisionReason"]
        (ws / "big.py").write_text("x = 1\n" * 600)
        post = {"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_use_id": "t4", "tool_input": {"file_path": str(ws / "big.py")},
                "tool_response": {"filePath": str(ws / "big.py"), "type": "create"}}
        assert any(o.get("decision") == "block" and "big.py (600 lines)" in o["reason"] for o in fire(ws, "claude", base | post))
        question = {"question": "Does login work? [project: .]", "header": "check:login", "multiSelect": False,
                    "options": [{"label": "looks right"}, {"label": "needs changes"}]}
        ask = {"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion", "tool_use_id": "t5", "tool_input": {"questions": [question]},
               "tool_response": {"questions": [question], "answers": {question["question"]: "looks right"}}}
        fire(ws, "claude", base | ask)
        assert json.loads((ws / ".harness" / "checks" / "login.json").read_text())["result"] == "looks right"
        stop = fire(ws, "claude", base | {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"})
        assert stop[0]["decision"] == "block" and "login" in stop[0]["reason"] and "hookSpecificOutput" not in stop[0], stop
        start_loop(ws, escalated=True)
        halted = fire(ws, "claude", base | push | {"tool_input": {"command": "ls"}})
        assert halted[0]["continue"] is False and "Which database?" in halted[0]["stopReason"], halted


def test_cursor_hooks() -> None:
    """Cursor native payloads get Cursor native answers: deny with messages, additional_context and followup_message."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = exported_workspace(tmp)
        base = {"conversation_id": "u1", "generation_id": "g1", "model": "m", "cursor_version": "2.4", "workspace_roots": [str(ws)]}
        start = fire(ws, "cursor", base | {"hook_event_name": "sessionStart", "session_id": "u1", "composer_mode": "agent"})
        assert "Delivery" in start[0]["additional_context"], start
        prompt = fire(ws, "cursor", base | {"hook_event_name": "beforeSubmitPrompt", "prompt": "Build a login form", "attachments": []})
        assert prompt == [{"continue": True}] * len(prompt), prompt
        start_loop(ws)
        write = {"hook_event_name": "preToolUse", "tool_name": "Write", "tool_use_id": "t1", "cwd": str(ws),
                 "tool_input": {"file_path": str(ws / "progress.txt"), "content": "done"}}
        denied = fire(ws, "cursor", base | write)
        assert denied[0]["permission"] == "deny" and "loop scripts" in denied[0]["agent_message"], denied
        harmless = fire(ws, "cursor", base | write | {"tool_name": "Read", "tool_input": {"file_path": str(ws / "app.py")}})
        assert all(o.get("permission") != "deny" for o in harmless), harmless
        (ws / "big.py").write_text("x = 1\n" * 600)
        post = {"hook_event_name": "postToolUse", "tool_name": "Write", "tool_use_id": "t2", "cwd": str(ws), "duration": 5,
                "tool_input": {"file_path": str(ws / "big.py")}, "tool_output": "{}"}
        assert any("big.py (600 lines)" in o.get("additional_context", "") for o in fire(ws, "cursor", base | post))
        stop = fire(ws, "cursor", base | {"hook_event_name": "stop", "status": "completed", "loop_count": 0})
        assert "login" in stop[0]["followup_message"], stop
        assert fire(ws, "cursor", base | {"hook_event_name": "stop", "status": "completed", "loop_count": 1}) == []


def test_codex_hooks() -> None:
    """Codex payloads: apply_patch guarded, no unsupported continue on PreToolUse, Stop always answers JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = exported_workspace(tmp)
        base = {"session_id": "x1", "cwd": str(ws), "transcript_path": None, "model": "gpt", "turn_id": "r1", "permission_mode": "default"}
        fire(ws, "codex", base | {"hook_event_name": "UserPromptSubmit", "prompt": "Fix the login check"})
        start_loop(ws, passes=True)
        assert fire(ws, "codex", base | {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": None}) == [{}]
        start_loop(ws, escalated=True)
        patch = "*** Begin Patch\n*** Update File: progress.txt\n@@\n-a\n+b\n*** End Patch\n"
        denied = fire(ws, "codex", base | {"hook_event_name": "PreToolUse", "tool_name": "apply_patch", "tool_use_id": "t1",
                                           "tool_input": {"command": patch}})
        guard = next(o for o in denied if o.get("hookSpecificOutput", {}).get("permissionDecision") == "deny")
        assert "Which database?" in guard["hookSpecificOutput"]["permissionDecisionReason"] and "continue" not in guard, denied
        start_loop(ws)
        stop = fire(ws, "codex", base | {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"})
        assert stop[0]["decision"] == "block" and "login" in stop[0]["reason"], stop
        sub = fire(ws, "codex", base | {"hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "default"})
        assert sub and "additionalContext" in sub[0]["hookSpecificOutput"], sub


if __name__ == "__main__":
    test_export_structure()
    test_export_refuses_foreign_files_and_bad_organizations()
    test_claude_code_hooks()
    test_cursor_hooks()
    test_codex_hooks()
    print("test_adapters: OK")
