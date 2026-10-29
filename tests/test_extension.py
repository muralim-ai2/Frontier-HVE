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


def render(out: Path, version: str = "0.0.0-test", python: str | None = "python") -> list[str]:
    """Build the extension and render its plugin into out with Node for a Python launcher (None: no Python); return the agent file names."""
    subprocess.run([sys.executable, str(EXTENSION / "build.py")], check=True, capture_output=True, text=True)
    script = (f"process.stdout.write(JSON.stringify(require({json.dumps(str(EXTENSION / 'render.js'))})"
              f".renderPlugin({json.dumps(str(EXTENSION))}, {json.dumps(str(out))}, {json.dumps(version)}, {json.dumps(python)})))")
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


def test_uplift_skill_polish_contract() -> None:
    """The uplift skill and read-only judge share ten bounded polish candidates and an honest evidence contract."""
    skill = (EXTENSION / "skills" / "wow-uplift" / "SKILL.md").read_text(encoding="utf-8")
    source = REPO / "plugins" / "harness-assist" / "skills" / "wow-uplift" / "SKILL.md"
    assert skill == source.read_text(encoding="utf-8"), "Rebuild extension skills from the canonical plugin templates"
    judge = (EXTENSION / "agents" / "hve-uplift-judge.agent.md").read_text(encoding="utf-8")
    assert re.match(r"---\nname: wow-uplift\ndescription: .+\n---\n", skill)
    checklist = skill.split("## Ten quick uplift candidates\n", 1)[1].split("\n## ", 1)[0]
    assert re.findall(r"^\| (\d+) \|", checklist, re.M) == [str(number) for number in range(1, 11)]
    for candidate in ("Type hierarchy", "Alignment within elements", "Composition and focal balance", "Material layers",
                      "Focus and highlight borders", "Purposeful icons", "Domain-specific creativity", "Contained theme refinement",
                      "Dark appearance", "Colourblind-safe treatment"):
        assert candidate.lower() in checklist.lower() and candidate.lower() in judge.lower(), candidate
    assert "at most 3 rounds" in skill and "one to three" in skill and "one to three" in judge
    assert "report the pass as blocked" in skill and "only if that reviewer actually ran" in skill
    assert "retained/dropped" in skill and "Automated lint is not proof" in skill
    assert "no new dependencies" in skill and "new settings subsystem" in judge
    assert "about a 10%" not in judge and "do not manufacture work" in skill
    assert "tools: [read/" in judge and "agents: []" in judge and "edit/" not in judge
    assert all(f'"{field}"' in judge for field in ("verdict", "changes", "title", "where", "what", "why", "keep"))


def test_extension_js_parses() -> None:
    """Both extension scripts are valid JavaScript."""
    for name in ("extension.js", "render.js"):
        subprocess.run(["node", "--check", str(EXTENSION / name)], check=True)


def test_rendered_plugin_shape() -> None:
    """The plugin has its manifest, 19 skills, guardrail scripts and 41 HVE agents (16 rendered from the persona catalog, 2 benchmark
    research arms) with every runtime path filled in; only the three
    Frontier agents are user-invocable and they, with the uplift judge, pin top models."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "plugin"
        agents = render(out)
        assert len(agents) == 41, agents
        assert json.loads((out / "plugin.json").read_text(encoding="utf-8"))["name"] == "frontier-hve"
        assert len(list((out / "skills").glob("*/SKILL.md"))) == 19
        assert (EXTENSION / "runtime" / "tools" / "map" / "explorer" / "app.js").is_file()
        assert (out / "skills" / "deliverable-templates" / "SKILL.md").is_file()
        assert (EXTENSION / "runtime" / "tools" / "templates" / "manage.py").is_file()
        assert (EXTENSION / "runtime" / "templates" / "deliverables" / "prd-v1.md").is_file()
        assert (EXTENSION / "runtime" / "evaluation" / "frontier.eval.json").is_file()
        reviewer = (out / "com.github.copilot" / "agents" / "hve-evaluation-reviewer.agent.md").read_text(encoding="utf-8")
        assert re.search(r"^user-invocable: false", reviewer, re.M) and "edit/" not in reviewer
        assert not (out / "skills" / "ux-flows").exists() and (EXTENSION / "runtime" / "skills" / "admitted" / "ux-flows" / "SKILL.md").is_file()
        assert (out / "scripts" / "guardrail.py").exists()
        restricted = {"council", "evaluation-reviewer", "minimal", "flow-architect", "flow-maintainer", "skill-judge", "skill-worker",
                      "uplift-judge", "research-minimal", "research-single"}
        visible, pinned = {"e2e", "agile", "prototype", "creator"}, {"e2e", "agile", "prototype", "creator", "uplift-judge"}
        for name in agents:
            text = (out / "com.github.copilot" / "agents" / name).read_text(encoding="utf-8")
            short = name.removeprefix("hve-").removesuffix(".agent.md")
            assert "{{RUNTIME}}" not in text and re.search(r"^name: (HVE |Frontier )", text, re.M), name
            assert bool(re.search(r"^user-invocable: false", text, re.M)) == (short not in visible), f"{name}: only the Frontier agents show"
            assert bool(re.search(r"^model: \[.*'GPT-6 Astra \(copilot\)'", text, re.M)) == (short in pinned), f"{name}: model pin"
            assert not re.search(r"budget\.py|HARNESS_BUDGET", text), f"{name}: product agents have no time budget"
            assert bool(re.search(r"^tools:", text, re.M)) == (short in restricted), \
                f"{name}: only read-only, blind and baseline agents keep a fixed tool list"
            for script in re.findall(r'python "([^"]+\.py)"', text):
                assert Path(script).is_file(), (name, script)
        for name in ("creator", "creator-flow", "creator-github", "single", "product-manager", "e2e", "agile"):
            text = (out / "com.github.copilot" / "agents" / f"hve-{name}.agent.md").read_text(encoding="utf-8")
            assert "lifecycle.py" in text and "contract" in text and "lifecycle.py report" in text, name
            assert name == "single" or "lifecycle.py brief" in text, name


def test_render_for_python_launcher_and_fresh_workspace() -> None:
    """Without Python, hooked agents lose their hooks and warn; python3 replaces python; hooks run in a workspace that was never set up."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "plugin"
        folder = out / "com.github.copilot" / "agents"
        render(out, python=None)
        creator = (folder / "hve-creator.agent.md").read_text(encoding="utf-8")
        assert "hooks:" not in creator and "Python not found" in creator and "description: (Needs Python)" in creator
        assert "Python not found" not in (folder / "hve-minimal.agent.md").read_text(encoding="utf-8")
        render(out, python="python3")
        creator = (folder / "hve-creator.agent.md").read_text(encoding="utf-8")
        assert 'python "' not in creator and 'python3 "' in creator and "Session Target **Local**" in creator
        assert "Session Target **Local**" not in (folder / "hve-flow-designer.agent.md").read_text(encoding="utf-8")
        render(out)
        creator = (folder / "hve-creator.agent.md").read_text(encoding="utf-8")
        assert "Python on this machine" not in creator
        ws = Path(tmp) / "fresh"
        ws.mkdir()
        run(hook(creator, "profile_detector.py"), ws, {"hook_event_name": "SessionStart"})
        run(hook(creator, "skill_loader.py"), ws, {"hook_event_name": "UserPromptSubmit", "prompt": "Build a palette app"},
            HARNESS_SKILLS_MIN_STATUS="provisional")
        assert (ws / ".hve" / "user_profile.json").is_file() and (ws / ".hve" / "runs" / "s1.skills.json").is_file()


def test_rerender_updates_in_place() -> None:
    """Rendering over an existing plugin (held open by VS Code) updates the version and agents and removes stale files."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "plugin"
        render(out, "0.1.0")
        stale = out / "com.github.copilot" / "agents" / "old.agent.md"
        stale.write_text("old", encoding="utf-8")
        (out / "skills" / "old-skill").mkdir()
        assert len(render(out, "0.1.1")) == 41
        assert json.loads((out / "plugin.json").read_text(encoding="utf-8"))["version"] == "0.1.1"
        assert not stale.exists() and not (out / "skills" / "old-skill").exists()


def test_packaged_template_guard() -> None:
    """The packaged manager and guard enforce all authoring agents, but not minimal."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "plugin"
        render(out)
        ws = workspace(tmp)
        folder = out / "com.github.copilot" / "agents"
        for name in ("creator", "creator-flow", "creator-github", "single", "product-manager"):
            text = (folder / f"hve-{name}.agent.md").read_text(encoding="utf-8")
            assert text.count("/hooks/template_guard.py") == 3, name
        assert "template_guard.py" not in (folder / "hve-minimal.agent.md").read_text(encoding="utf-8")
        creator = (folder / "hve-creator.agent.md").read_text(encoding="utf-8")
        command = hook(creator, "template_guard.py")
        start = run(command, ws, {"hook_event_name": "SessionStart"})
        assert start and "deliverable-templates" in json.dumps(start)
        run(command, ws, {"hook_event_name": "UserPromptSubmit", "prompt": "Create a PRD"})
        blocked = run(command, ws, {"hook_event_name": "Stop", "stop_hook_active": False})
        assert blocked and blocked["hookSpecificOutput"]["decision"] == "block"
        manager = EXTENSION / "runtime" / "tools" / "templates" / "manage.py"
        initialized = subprocess.run([sys.executable, str(manager), "init", "prd", "--slug", "sample", "--session", "s1"],
                                     cwd=ws, capture_output=True, text=True)
        assert initialized.returncode == 0, initialized.stderr
        assert (ws / "docs" / "product" / "PRD-sample.md").is_file()


def test_product_manager_agent() -> None:
    """The product manager registers only PRDs, names no fixed template, and its backlog validator runs from the runtime."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "plugin"
        render(out)
        ws = workspace(tmp)
        folder = out / "com.github.copilot" / "agents"
        pm = (folder / "hve-product-manager.agent.md").read_text(encoding="utf-8")
        assert pm.count("HVE_TEMPLATE_TYPES: prd") == 3, pm
        assert "HARNESS_REQUIRED_SKILLS: prd" in pm
        assert "`search_issues`" in pm and "scoped to that repository" in pm and "contract direct <slug> \"HVE product-manager\"" in pm
        assert "+prd" in pm and "The council gets no brief" in pm
        assert "host-selected; actual model unconfirmed" in pm and 'label it "session model"' not in pm
        assert "read `.hve/skills/prd/SKILL.md`" in pm and "skills/admitted/prd/SKILL.md" not in pm
        assert "register prd --slug" in pm and "Create parents and dependencies before" in pm and "`uncovered`" in pm
        ado = (folder / "hve-azure-devops.agent.md").read_text(encoding="utf-8")
        assert "Epic / Issue / Task (Basic" in ado and "Create parents and dependencies before" in ado
        loader = hook(pm, "skill_loader.py")
        for prompt, minimum in (("Create a PRD for an employee leave portal", 1), ("Revise the PRD to clarify goals", 1),
                                ("Create a PRD for a search app", 2)):
            run(loader, ws, {"hook_event_name": "UserPromptSubmit", "prompt": prompt},
                HARNESS_SKILLS_MIN_STATUS="provisional", HARNESS_REQUIRED_SKILLS="prd")
            loadout = json.loads((ws / ".hve" / "runs" / "s1.skills.json").read_text(encoding="utf-8"))
            assert loadout["skills"][0] == "skills/admitted/prd" and len(loadout["skills"]) >= minimum, loadout
            registry = json.loads((EXTENSION / "runtime" / "skills" / "registry.json").read_text(encoding="utf-8"))
            tokens = {entry["name"]: entry["skill_tokens"] for entry in registry["admitted"]}
            budget = json.loads((EXTENSION / "runtime" / "skills" / "categories.json").read_text(encoding="utf-8"))["loadout"]
            total = sum(tokens[Path(skill).name] for skill in loadout["skills"])
            assert loadout["tokens"] == total and loadout["over_budget"] == (total > budget["max_tokens"] or len(loadout["skills"]) > budget["max_skills"])
            skill_path = ws / ".hve" / "skills" / "prd" / "SKILL.md"
            assert skill_path.is_file()
            for path in (skill_path, EXTENSION / "runtime" / "skills" / "admitted" / "prd" / "SKILL.md"):
                read = run(loader, ws, {"hook_event_name": "PreToolUse", "tool_input": {"filePath": str(path)}})
                assert read is None or "permissionDecision" not in read["hookSpecificOutput"], read
        residue = [s for s in ("PRD-TEMPLATE", "12 sections", "12-section", "docs/artifacts", "Research Summary") if s in pm]
        assert not residue, residue
        assert re.search(r"^user-invocable: false", (folder / "hve-council.agent.md").read_text(encoding="utf-8"), re.M)
        guard = hook(pm, "template_guard.py")
        run(guard, ws, {"hook_event_name": "UserPromptSubmit", "prompt": "Write a PRD and a technical design specification"},
            HVE_TEMPLATE_TYPES="prd")
        blocked = run(guard, ws, {"hook_event_name": "Stop", "stop_hook_active": False}, HVE_TEMPLATE_TYPES="prd")
        assert blocked and "prd" in blocked["hookSpecificOutput"]["reason"] and "technicalDesign" not in blocked["hookSpecificOutput"]["reason"]
        backlog_py = re.search(r'python "([^"]+/tools/backlog/backlog\.py)"', pm)[1]  # type: ignore[index]
        (ws / "docs" / "product").mkdir(parents=True)
        (ws / "docs" / "product" / "BACKLOG-x.json").write_text(json.dumps({"version": 1, "prd": "docs/product/PRD-x.md", "items": []}),
                                                                 encoding="utf-8")
        (ws / "docs" / "product" / "PRD-x.md").write_text("FR-1\n", encoding="utf-8")
        result = subprocess.run([sys.executable, backlog_py, "validate", "docs/product/BACKLOG-x.json"], cwd=ws, capture_output=True, text=True)
        assert result.returncode == 1 and "non-empty list" in result.stdout, (result.stdout, result.stderr)


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


def test_delivery_agents_and_lifecycles() -> None:
    """Prototype keeps only the safety guard, engineer is a hidden persona, and e2e/agile contract a packaged lifecycle."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "plugin"
        render(out)
        folder = out / "com.github.copilot" / "agents"
        prototype = (folder / "hve-prototype.agent.md").read_text(encoding="utf-8")
        assert set(re.findall(r"/hooks/(\w+\.py)", prototype)) == {"loop_guard.py", "error_guard.py"}, prototype
        assert re.search(r"^user-invocable: false", (folder / "hve-engineer.agent.md").read_text(encoding="utf-8"), re.M)
        ws = workspace(tmp)
        for name, overlay in (("e2e", "sdlc"), ("agile", "agile-scrum")):
            text = (folder / f"hve-{name}.agent.md").read_text(encoding="utf-8")
            lifecycle_py = re.search(r'python "([^"]+/tools/loop/lifecycle\.py)"', text)[1]  # type: ignore[index]
            (ws / "req.md").write_text("Build a leave portal", encoding="utf-8")
            made = subprocess.run([sys.executable, lifecycle_py, "contract", overlay, f"ask-{name}", f"HVE {name}", "req.md"],
                                  cwd=ws, capture_output=True, text=True)
            assert made.returncode == 0, made.stderr
            active = json.loads((ws / ".hve" / "asks" / "active.json").read_text(encoding="utf-8"))["active"]
            assert active == json.loads(made.stdout)["ask"] and re.fullmatch(rf"\d{{8}}-\d{{4}}-ask-{name}", active), active


if __name__ == "__main__":
    test_extension_js_parses()
    test_rendered_plugin_shape()
    test_render_for_python_launcher_and_fresh_workspace()
    test_rerender_updates_in_place()
    test_packaged_template_guard()
    test_product_manager_agent()
    test_rendered_hooks_run_in_a_workspace()
    test_rendered_flow_and_loop_tools_run()
    test_delivery_agents_and_lifecycles()
    print("test_extension: OK")
