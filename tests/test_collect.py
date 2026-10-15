"""End-to-end test of tools/observe/collect.py on synthetic sessions in a temp folder."""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROMPT = "Build a color palette site.\r\nUse Next.js.\r\n"
MIN_ID = "aaaaaaaa-0000-0000-0000-000000000001"
SINGLE_ID = "bbbbbbbb-0000-0000-0000-000000000002"
REPLY = "Here it is.\n\n**index.html**\n```html\n<h1>Palette</h1>\n```\n\n`src/app.js`:\n```js\nconsole.log(1);\n```\n"


def add_session(root: Path, session_id: str, mode: str, user_text: str, reply: str, pasted: str | None = None) -> None:
    """Write a finished session's hook events, transcript, and VS Code chat session store (with the pasted attachment, if any)."""
    workspace = root / "workspaceStorage" / "ws1"
    transcript = workspace / "GitHub.copilot-chat" / "transcripts" / f"{session_id}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    store = workspace / "chatSessions" / f"{session_id}.jsonl"
    store.parent.mkdir(parents=True, exist_ok=True)
    variables = [{"id": "paste", "name": "Pasted text #1", "value": pasted}] if pasted else []
    store.write_text(json.dumps({"kind": 2, "k": ["requests"], "v": [{"variableData": {"variables": variables}}]}) + "\n", encoding="utf-8")
    records = [
        {"type": "session.start", "timestamp": "2026-10-06T08:00:00.000Z", "data": {}},
        {"type": "user.message", "timestamp": "2026-10-06T08:00:00.001Z", "data": {"content": user_text}},
        {"type": "user.message", "timestamp": "2026-10-06T08:00:03.000Z",
         "data": {"content": "[Terminal 5bf42ad4-e4d4 notification: command completed. The terminal has been cleaned up.]\nTerminal output: ok"}},
        {"type": "assistant.message", "timestamp": "2026-10-06T08:00:05.000Z", "data": {"content": ""}},
        {"type": "assistant.message", "timestamp": "2026-10-06T08:01:00.000Z", "data": {"content": reply}},
    ]
    transcript.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    event = {"event": "Stop", "mode": mode, "ts_ms": 0, "tool_use_id": None, "tool_name": None, "transcript_path": str(transcript)}
    (root / ".hve" / "runs" / f"{session_id}.events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")


def make_root(tmp: str) -> Path:
    """Return a temp harness root with collect.py and the benchmark prompt."""
    root = Path(tmp)
    (root / "tools" / "observe").mkdir(parents=True)
    shutil.copy(REPO / "tools" / "observe" / "collect.py", root / "tools" / "observe")
    (root / "tests" / "prompts").mkdir(parents=True)
    (root / "tests" / "prompts" / "color-palette.md").write_bytes(PROMPT.encode("utf-8"))
    (root / ".hve" / "runs").mkdir(parents=True)
    return root


def run_collect(root: Path) -> subprocess.CompletedProcess[str]:
    """Run collect.py inside the temp root."""
    return subprocess.run([sys.executable, str(root / "tools" / "observe" / "collect.py")], capture_output=True, text=True)


def test_collects_minimal_reply_and_single_folder() -> None:
    """minimal code blocks become files; single's current/ folder moves to its session folder without node_modules in the manifest."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        add_session(root, MIN_ID, "minimal", "#attachment:Pasted text #1 ", REPLY, pasted=PROMPT)
        add_session(root, SINGLE_ID, "single", PROMPT, "Done.")
        current = root / ".hve" / "outputs" / "single" / "current"
        (current / "node_modules" / "x").mkdir(parents=True)
        (current / "node_modules" / "x" / "i.js").write_text("", encoding="utf-8")
        (current / "app").mkdir()
        (current / "app" / "page.tsx").write_text("export {}\n", encoding="utf-8")
        result = run_collect(root)
        assert result.returncode == 0, result.stderr
        minimal_out = root / ".hve" / "outputs" / "minimal" / MIN_ID
        assert (minimal_out / "index.html").read_text(encoding="utf-8") == "<h1>Palette</h1>\n"
        assert (minimal_out / "src" / "app.js").read_text(encoding="utf-8") == "console.log(1);\n"
        assert (minimal_out / "response.md").exists()
        assert not current.exists()
        manifest = json.loads((root / ".hve" / "runs" / f"{SINGLE_ID}.run.json").read_text(encoding="utf-8"))
        assert manifest["files"] == ["app/page.tsx"], manifest
        assert manifest["output_dir"] == f".hve/outputs/single/{SINGLE_ID}"
        assert (manifest["started"], manifest["ended"]) == ("2026-10-06T08:00:00.000Z", "2026-10-06T08:01:00.000Z")
        assert run_collect(root).returncode == 0  # already collected sessions are skipped


def test_rejects_unsafe_path_in_reply() -> None:
    """A code block labelled with a path outside the output folder stops collection."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        add_session(root, MIN_ID, "minimal", PROMPT, "../../evil.js\n```js\nx\n```\n")
        result = run_collect(root)
        assert result.returncode != 0 and "unsafe file path '../../evil.js'" in result.stderr, result.stderr
        assert not (root / "tests" / "evil.js").exists()


def test_rejects_non_benchmark_and_ambiguous_sessions() -> None:
    """A session whose prompt differs, or two uncollected sessions of one mode, stop collection."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        add_session(root, MIN_ID, "minimal", "List the files.", "ok")
        result = run_collect(root)
        assert result.returncode != 0 and "is not a benchmark run" in result.stderr, result.stderr
        add_session(root, MIN_ID, "minimal", "#attachment:Pasted text #1", "ok", pasted="Build something else.")
        result = run_collect(root)
        assert result.returncode != 0 and "is not a benchmark run" in result.stderr, result.stderr
        add_session(root, SINGLE_ID, "minimal", PROMPT, "ok")
        result = run_collect(root)
        assert result.returncode != 0 and "more than one uncollected session for mode(s) ['minimal']" in result.stderr, result.stderr


def test_provenance_reports_component_evidence() -> None:
    """A template-built PRD verifies `templates`; a finished loop without evaluation fails `reflection`; a missing loadout fails `skills`."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        agent = ws / "pm.agent.md"
        agent.write_text('hooks: skill_loader.py template_guard.py\nRun "tools/loop/loop.py" then "tools/evaluation/reflection.py".\n',
                         encoding="utf-8")
        (ws / ".hve" / "runs").mkdir(parents=True)
        (ws / ".hve" / "runs" / "s1.skills.json").write_text(json.dumps({"skills": ["skills/admitted/prd"]}), encoding="utf-8")
        cli = [sys.executable, str(REPO / "tools" / "observe" / "provenance.py"), str(agent), "latest", "--workspace", str(ws)]
        result = subprocess.run([*cli, "--require", "templates"], capture_output=True, text=True)
        report = json.loads(result.stdout)
        assert result.returncode == 1 and report["components"]["templates"]["status"] == "not-exercised", report
        assert set(report["components"]) == {"skills", "templates", "loop", "reflection"}, report
        manager = REPO / "tools" / "templates" / "manage.py"
        subprocess.run([sys.executable, str(manager), "--workspace", str(ws), "init", "prd", "--slug", "leave", "--session", "s1"],
                       check=True, capture_output=True)
        prd = ws / "docs" / "product" / "PRD-leave.md"
        assert json.loads(subprocess.run([*cli, "--require", "templates"], capture_output=True, text=True).stdout)[
            "components"]["templates"]["status"] == "failed", "placeholders left in the PRD"
        prd.write_text(re.sub(r"\{\{\s*FILL:[^{}]*\}\}", "Filled.", prd.read_text(encoding="utf-8")), encoding="utf-8")
        (ws / "feature_list.json").write_text(json.dumps([{"name": "a", "passes": True}]), encoding="utf-8")
        (ws / ".harness").mkdir()
        (ws / "progress.txt").write_text("a: pass\n", encoding="utf-8")
        result = subprocess.run([*cli, "--require", "templates"], capture_output=True, text=True)
        report = json.loads(result.stdout)
        assert report["components"]["skills"]["detail"] == "loaded: prd" and report["trace"] is None, report
        assert report["components"]["templates"] == {"status": "verified", "detail": "prd/leave from builtin:prd@1"}, report
        assert report["components"]["reflection"]["status"] == "failed" and result.returncode == 1, report
        assert (ws / ".hve" / "runs" / "s1.provenance.json").is_file()
        (ws / ".hve" / "runs" / "s1.skills.json").unlink()
        (ws / ".hve" / "runs" / "s2.events.jsonl").write_text("", encoding="utf-8")
        report = json.loads(subprocess.run(cli, capture_output=True, text=True).stdout)
        assert report["session"] == "s2" and report["components"]["skills"]["status"] == "failed", report


def test_contract_plan_check_and_provenance() -> None:
    """A lifecycle contract reports expected vs used per done stage; an unsynced plan.md adds context, holds loop runs and fails provenance."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / ".hve" / "runs").mkdir(parents=True)

        def lifecycle(*args: str) -> str:
            """Run lifecycle.py in the workspace and return its output."""
            done = subprocess.run([sys.executable, str(REPO / "tools" / "loop" / "lifecycle.py"), *args], cwd=ws, capture_output=True, text=True,
                                  encoding="utf-8")
            assert done.returncode == 0, done.stderr
            return done.stdout

        def hook(payload: dict[str, object]) -> str:
            """Run plan_check.py in the workspace and return its output."""
            return subprocess.run([sys.executable, str(REPO / "hooks" / "plan_check.py")], input=json.dumps({"session_id": "s1", **payload}),
                                  cwd=ws, capture_output=True, text=True, check=True).stdout

        (ws / "req.md").write_text("Build a leave portal in sprints", encoding="utf-8")
        lifecycle("contract", "agile-scrum", "leave", "HVE agile", "req.md", "sprint-design=No UI change")
        nxt = {"hook_event_name": "PreToolUse", "tool_name": "run_in_terminal", "tool_input": {"command": 'python "x/tools/loop/loop.py" next .'}}
        assert hook(nxt) == ""
        plan = ws / ".hve" / "asks" / "leave" / "plan.md"
        plan.write_text("# Plan\n- Sprint 1: request leave\n", encoding="utf-8")
        assert "plan-sync" in hook({"hook_event_name": "UserPromptSubmit", "prompt": "go"})
        assert json.loads(hook(nxt))["hookSpecificOutput"]["permissionDecision"] == "deny"
        lifecycle("plan-sync", "first plan")
        assert hook(nxt) == ""
        lifecycle("stage", "backlog", "active", "PM writes the PRD")
        lifecycle("stage", "backlog", "done", "PRD and backlog agreed")
        (ws / ".hve" / "runs" / "s1.skills.json").write_text(json.dumps({"skills": [], "used": ["skills/admitted/prd", "skills/admitted/scrub"]}),
                                                             encoding="utf-8")
        agent = ws / "agile.agent.md"
        agent.write_text('Run "tools/loop/lifecycle.py".\n', encoding="utf-8")
        cli = [sys.executable, str(REPO / "tools" / "observe" / "provenance.py"), str(agent), "s1", "--workspace", str(ws)]
        report = json.loads(subprocess.run(cli, capture_output=True, text=True).stdout)
        contract = report["contract"]
        assert contract["gaps"] == ["backlog: templates prd expected but not authored"] and contract["outside_contract"] == ["scrub"], contract
        assert report["components"]["contract"]["status"] == "failed" and report["guards"]["trips"] == {"plan_check/plan_changed": 1}, report
        plan.write_text("# Plan\n- Sprint 1: request and approve leave\n", encoding="utf-8")
        report = json.loads(subprocess.run(cli, capture_output=True, text=True).stdout)
        assert "changed since its last sync" in report["components"]["contract"]["detail"], report
        assert "| backlog | done | HVE product-manager | prd ✓ | prd ✗ |" in lifecycle("report", "s1")


if __name__ == "__main__":
    test_collects_minimal_reply_and_single_folder()
    test_rejects_unsafe_path_in_reply()
    test_rejects_non_benchmark_and_ambiguous_sessions()
    test_provenance_reports_component_evidence()
    test_contract_plan_check_and_provenance()
    print("test_collect: OK")
