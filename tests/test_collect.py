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
        (ws / ".harness" / "state.json").write_text("{}", encoding="utf-8")
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
        ask = json.loads(lifecycle("contract", "agile-scrum", "leave", "HVE agile", "req.md", "sprint-design=No UI change"))["paths"]["ask"]
        nxt = {"hook_event_name": "PreToolUse", "tool_name": "run_in_terminal", "tool_input": {"command": 'python "x/tools/loop/loop.py" next .'}}
        assert hook(nxt) == ""
        plan = ws / ask / "plan.md"
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


def test_direct_contract_tracks_skills_tasks_briefs_and_reports() -> None:
    """A direct ask records ranked skills, persona, environment and a generated plan block; tasks, briefs and reported skills join it."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / ".hve" / "runs").mkdir(parents=True)
        (ws / ".vscode").mkdir()
        (ws / ".vscode" / "mcp.json").write_text('{\n  // team servers\n  "servers": {"graphify": {"command": "g"},},\n}\n', encoding="utf-8")

        def lifecycle(*args: str) -> subprocess.CompletedProcess[str]:
            """Run lifecycle.py in the workspace."""
            return subprocess.run([sys.executable, str(REPO / "tools" / "loop" / "lifecycle.py"), *args], cwd=ws, capture_output=True,
                                  text=True, encoding="utf-8")

        (ws / "req.md").write_text("Build a color palette page with Next.js", encoding="utf-8")
        created = lifecycle("contract", "direct", "palette", "HVE creator", "req.md")
        assert created.returncode == 0, created.stderr
        paths = json.loads(created.stdout)["paths"]
        assert re.fullmatch(r"\.hve/asks/\d{8}-\d{4}-palette", paths["ask"]) and paths["feature_list"] == f"{paths['ask']}/loop/feature_list.json"
        assert (ws / paths["ask"] / "request.md").read_text(encoding="utf-8").strip() == "Build a color palette page with Next.js"
        path = ws / paths["ask"] / "contract.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        names = [r["name"] for r in data["skills"]["selected"]]
        assert names and data["skills"]["tokens"] == sum(r["skill_tokens"] for r in data["skills"]["selected"]), data["skills"]
        assert set(data["skills"]["suggested"]) <= set(names) and data["skills"]["suggested_tokens"] <= data["skills"]["tokens"], data["skills"]
        assert data["personas"] == [{"agent": "HVE creator", "stages": ["deliver"]}] and data["tasks"] == [], data
        assert "graphify" in {s["name"] for s in data["environment"]["mcp_servers"]}, data["environment"]
        assert "graphify" in data["environment"]["tool_load"]["harnesses"]["vscode"]["servers"], data["environment"]
        assert (ws / ".hve" / "skills" / names[0] / "SKILL.md").is_file()
        plan = ws / paths["ask"] / "plan.md"
        assert "<!-- hve:skills -->" in plan.read_text(encoding="utf-8") and lifecycle("plan-status").stdout.strip() == "null"
        assert "MCP servers per harness:\n- vscode: " in plan.read_text(encoding="utf-8")
        if data["skills"]["over_budget"]:
            assert "Over the loadout guideline" in plan.read_text(encoding="utf-8") and "Suggested set" in plan.read_text(encoding="utf-8")
        (ws / paths["feature_list"]).write_text(json.dumps([{"name": "core", "passes": False}]), encoding="utf-8")
        tasks = json.loads(lifecycle("tasks-sync").stdout)
        assert tasks == [{"name": "core", "milestone": "deliver", "persona": "HVE creator", "skills": names, "passes": False}], tasks
        text = lifecycle("brief", "frontend sub-agent", "task=core").stdout
        assert f".hve/skills/{names[0]}/SKILL.md" in text and "graphify" in text and "SKILLS-USED" in text, text
        assert "not in the contract" in lifecycle("brief", "x", "task=ghost").stderr
        lifecycle("used", "frontend sub-agent", "core", f"{names[0]}, made-up")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["delegations"][0]["persona"] == "frontend sub-agent" and data["reported"][0]["skills"] == [names[0], "made-up"], data
        plan.write_text("# Plan\n- Build it\n", encoding="utf-8")
        assert lifecycle("plan-sync", "first plan").returncode == 0
        assert plan.read_text(encoding="utf-8").startswith("# Plan") and "<!-- hve:skills -->" in plan.read_text(encoding="utf-8")
        assert json.loads(lifecycle("plan-status").stdout)["changed"] is False
        text = lifecycle("report", "none").stdout
        assert "## Recommended against used" in text and f"| skill | {names[0]} |" in text and "reported by frontend sub-agent" in text, text
        assert "| persona | frontend sub-agent | not planned | ✓ |" in text and "| persona | HVE creator | deliver | ✗ |" in text, text
        assert "| task | core | deliver, HVE creator | ✗ passes |" in text and "| MCP server | graphify | available | ✗ |" in text, text
        assert "made-up" in text.split("outside the contract: ")[1].splitlines()[0], text
        assert "- Prompt cache: not measured" in text and f"- Skill load: {len(names)} skills" in text, text
        rows = [{"turn_id": "t1", "prompt_tokens": 1000, "cache_read_tokens": 600}, {"turn_id": "t1", "prompt_tokens": 1000, "cache_read_tokens": 600},
                {"turn_id": "t2", "prompt_tokens": 1000, "cache_read_tokens": None}]
        (ws / ".hve" / "runs" / "m1.jsonl").write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
        assert "600 of 2,000 prompt tokens read from cache (30%) over 2 turn(s)" in lifecycle("report", "m1").stdout
        chosen = json.loads(lifecycle("skills", names[0]).stdout)
        assert chosen["skills"] == [names[0]] and chosen["over_guideline_tokens"] == 0, chosen
        assert "Choice: " + names[0] in plan.read_text(encoding="utf-8")
        assert "not in the ask's skills" in lifecycle("skills", "made-up").stderr
        (ws / "req.md").write_text("Create a formal presentation on revenue forecasting for the board", encoding="utf-8")
        shifted = json.loads(lifecycle("contract", "document", "revenue", "HVE creator", "req.md").stdout)
        assert shifted["previous_ask"]["recommend"] == "new-workspace" and shifted["previous_ask"]["ask"] == data["ask"], shifted
        assert json.loads(lifecycle("shift", "Fix the revenue forecasting chart colours").stdout) is None


if __name__ == "__main__":
    test_collects_minimal_reply_and_single_folder()
    test_rejects_unsafe_path_in_reply()
    test_rejects_non_benchmark_and_ambiguous_sessions()
    test_provenance_reports_component_evidence()
    test_contract_plan_check_and_provenance()
    test_direct_contract_tracks_skills_tasks_briefs_and_reports()
    print("test_collect: OK")
