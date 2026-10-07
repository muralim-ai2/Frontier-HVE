"""Tests of the Frontier HVE extension: build, plugin rendering, and the rendered agents' hook commands run from a temp workspace."""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXTENSION = REPO / "extension"
COMMAND = re.compile(r"command: '(.+)'")
EMPTY_PROFILE = {"prompt_style": None, "wants_evidence": None, "verbosity": None, "output_format": None, "build_preference": None,
                 "depth_evidence": 0, "explanation_depth": None, "bloat_triggers": []}


def render(out: Path, version: str = "0.0.0-test") -> list[str]:
    """Build the extension and render its plugin into out with Node; return the rendered agent file names."""
    subprocess.run([sys.executable, str(EXTENSION / "build.py")], check=True, capture_output=True, text=True)
    script = (f"process.stdout.write(JSON.stringify(require({json.dumps(str(EXTENSION / 'render.js'))})"
              f".renderPlugin({json.dumps(str(EXTENSION))}, {json.dumps(str(out))}, {json.dumps(version)})))")
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def workspace(tmp: str) -> Path:
    """Return a temp workspace set up the way the extension's setup command leaves it."""
    ws = Path(tmp) / "ws"
    (ws / ".hve" / "runs").mkdir(parents=True)
    (ws / ".hve" / "user_profile.json").write_text(json.dumps(EMPTY_PROFILE | {"build_preference": "low_code"}), encoding="utf-8")
    return ws


def hook(agent_text: str, needle: str) -> str:
    """Return the first rendered hook command of an agent that mentions needle."""
    return next(c for c in COMMAND.findall(agent_text) if needle in c)


def run(command: str, ws: Path, payload: dict[str, object], **env: str) -> dict[str, object] | None:
    """Run a rendered hook command through the shell in the workspace; return its JSON output or None."""
    result = subprocess.run(command, shell=True, cwd=ws, input=json.dumps({"session_id": "s1", **payload}), capture_output=True,
                            text=True, env={**os.environ, **env})
    assert result.returncode == 0, (command, result.stderr)
    return json.loads(result.stdout) if result.stdout.strip() else None


def test_extension_js_parses() -> None:
    """Both extension scripts are valid JavaScript."""
    for name in ("extension.js", "render.js"):
        subprocess.run(["node", "--check", str(EXTENSION / name)], check=True)


def test_rendered_plugin_shape() -> None:
    """The plugin has its manifest, 7 skills, guardrail scripts and 11 HVE agents with every runtime path filled in."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "plugin"
        agents = render(out)
        assert len(agents) == 15, agents
        assert json.loads((out / "plugin.json").read_text(encoding="utf-8"))["name"] == "frontier-hve"
        assert len(list((out / "skills").glob("*/SKILL.md"))) == 11
        assert not (out / "skills" / "ux-flows").exists() and (EXTENSION / "runtime" / "skills" / "admitted" / "ux-flows" / "SKILL.md").is_file()
        assert (out / "scripts" / "guardrail.py").exists()
        for name in agents:
            text = (out / "com.github.copilot" / "agents" / name).read_text(encoding="utf-8")
            assert "{{RUNTIME}}" not in text and re.search(r"^name: HVE ", text, re.M), name
            assert not re.search(r"^(model|reasoning-effort):|budget\.py|HARNESS_BUDGET", text, re.M), \
                f"{name}: product agents use the picked model, no time budget"
            for script in re.findall(r'python "([^"]+\.py)"', text):
                assert Path(script).is_file(), (name, script)


def test_rerender_updates_in_place() -> None:
    """Rendering over an existing plugin (held open by VS Code) updates the version and agents and removes stale files."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "plugin"
        render(out, "0.1.0")
        stale = out / "com.github.copilot" / "agents" / "old.agent.md"
        stale.write_text("old", encoding="utf-8")
        (out / "skills" / "old-skill").mkdir()
        assert len(render(out, "0.1.1")) == 15
        assert json.loads((out / "plugin.json").read_text(encoding="utf-8"))["version"] == "0.1.1"
        assert not stale.exists() and not (out / "skills" / "old-skill").exists()


def test_rendered_hooks_run_in_a_workspace() -> None:
    """The creator agent's rendered hooks run from a workspace: profile at start, guard, module and guardrail after tools."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "plugin"
        render(out)
        ws = workspace(tmp)
        creator = (out / "com.github.copilot" / "agents" / "hve-creator.agent.md").read_text(encoding="utf-8")
        start = {"hook_event_name": "SessionStart", "timestamp": "2026-10-06T08:00:00+00:00", "source": "new"}
        context = run(hook(creator, "profile_detector.py"), ws, start)
        assert context and "Explanation depth: balanced" in json.dumps(context), context
        prompt = start | {"hook_event_name": "UserPromptSubmit", "prompt": "Design the screens and states of a signup page."}
        assert run(hook(creator, "skill_loader.py"), ws, prompt, HARNESS_SKILLS_MIN_STATUS="provisional") is None
        assert (ws / ".hve" / "skills" / "ux-flows" / "SKILL.md").is_file(), list((ws / ".hve").rglob("SKILL.md"))
        isolated = {**os.environ, "APPDATA": str(ws / "appdata"), "USERPROFILE": str(ws / "home"), "HOME": str(ws / "home")}
        load = subprocess.run([sys.executable, str(EXTENSION / "runtime" / "tools" / "skills" / "context_load.py")], cwd=ws,
                              capture_output=True, text=True, env=isolated)
        assert load.returncode == 0 and json.loads(load.stdout)["total_tokens"] >= 0, load.stderr
        pre = {"hook_event_name": "PreToolUse", "timestamp": "2026-10-06T08:01:00+00:00", "tool_name": "read_file",
               "tool_input": {"filePath": "x"}, "tool_use_id": "t1"}
        assert run(hook(creator, "loop_guard.py"), ws, pre, HARNESS_PROJECT=".", HARNESS_STOP_POLICY="once") is None
        post = pre | {"hook_event_name": "PostToolUse", "tool_name": "create_file", "tool_response": "ok"}
        assert run(hook(creator, "module_guard.py"), ws, post) is None
        assert run(hook(creator, "guardrail.py"), ws, post) is None


def test_rendered_flow_and_loop_tools_run() -> None:
    """From a workspace that is already a git repo, flow.py starts the flow, the stage guard sends an unfinished stage back, and loop.py inits."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "plugin"
        render(out)
        ws = workspace(tmp)
        subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
        subprocess.run(["git", "config", "user.name", "dev"], cwd=ws, check=True)
        subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=ws, check=True)
        designer = (out / "com.github.copilot" / "agents" / "hve-flow-designer.agent.md").read_text(encoding="utf-8")
        flow_py = re.search(r'python "([^"]+/tools/loop/flow\.py)"', designer)[1]  # type: ignore[index]
        subprocess.run([sys.executable, flow_py, "init", ".", "--profile", "product"], cwd=ws, check=True, capture_output=True)
        stop = {"hook_event_name": "SubagentStop", "agent_id": "a", "agent_type": "HVE flow-designer", "stop_hook_active": False}
        blocked = run(hook(designer, "flow_guard.py"), ws, stop, HARNESS_PROJECT=".", FLOW_STAGE="designer")
        assert blocked and blocked["decision"] == "block", blocked
        (ws / "check.py").write_text("import pathlib, sys\nsys.exit(0 if pathlib.Path(sys.argv[1]).exists() else 1)\n", encoding="utf-8")
        features = [{"name": n, "description": f"create {n}", "verify": f"python check.py {n}.txt", "passes": False} for n in "abc"]
        (ws / "feature_list.json").write_text(json.dumps(features), encoding="utf-8")
        loop_py = flow_py.replace("flow.py", "loop.py")
        init = subprocess.run([sys.executable, loop_py, "init", ".", "--review", "local"], cwd=ws, capture_output=True, text=True)
        assert init.returncode == 0, init.stderr
        nxt = subprocess.run([sys.executable, loop_py, "next", "."], cwd=ws, capture_output=True, text=True)
        assert json.loads(nxt.stdout)["name"] == "a", nxt.stdout


if __name__ == "__main__":
    test_extension_js_parses()
    test_rendered_plugin_shape()
    test_rerender_updates_in_place()
    test_rendered_hooks_run_in_a_workspace()
    test_rendered_flow_and_loop_tools_run()
    print("test_extension: OK")
