"""Tests of the plugin architecture: package validation, install lifecycle, archives and index, routing, templates, flows and rubrics."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / "examples" / "plugins" / "oracle-offering"
sys.path[:0] = [str(REPO / "tools" / p) for p in ("plugins", "loop", "templates", "evaluation")]
import compose  # noqa: E402
import flow  # noqa: E402
import manage  # noqa: E402
import manifest  # noqa: E402
import plugin  # noqa: E402
import store  # noqa: E402
import workflow  # noqa: E402
from contract import load_contract  # noqa: E402

CORE = load_contract(REPO / "evaluation" / "frontier.eval.json")
LOADER = REPO / "hooks" / "skill_loader.py"
FILL = re.compile(r"\{\{\s*FILL:[^{}]*\}\}")

Json = dict[str, Any]


def raises(error: type[Exception], fn: Callable[..., Any], *args: Any) -> str:
    """Return the message of the error fn(*args) raises; fail if it does not."""
    try:
        fn(*args)
    except error as e:
        return str(e)
    raise AssertionError(f"{fn.__name__}{args} did not raise {error.__name__}")


def fresh_home(tmp: str) -> Path:
    """Point the plugin home at an empty folder inside tmp."""
    home = Path(tmp) / "home"
    os.environ["HVE_PLUGIN_HOME"] = str(home)
    return home


def copy_sample(tmp: str, name: str, change: Callable[[Path], None] | None = None) -> Path:
    """Return a copy of the sample plugin, optionally changed."""
    folder = Path(tmp) / name
    shutil.copytree(SAMPLE, folder)
    if change:
        change(folder)
    return folder


def edit_json(path: Path, change: Callable[[Json], None]) -> None:
    """Apply change to a JSON file in place."""
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def as_postgres(folder: Path) -> None:
    """Turn a sample copy into a second plugin, postgres-offering, by another publisher."""
    def change(data: Json) -> None:
        data.update(name="postgres-offering", publisher="contoso-pg")
        data["routing"].update(keywords=["postgres", "postgresql"], task_pattern="\\bpostgres(ql)?\\b")
    edit_json(folder / "hve-plugin.json", change)
    flow_path = folder / "flows" / "oracle-migration.flow.json"
    flow_path.write_text(flow_path.read_text(encoding="utf-8").replace("oracle-offering:", "postgres-offering:"), encoding="utf-8")


def install(folder: Path) -> Json:
    """Install a plugin folder after confirming the hash inspect shows."""
    return plugin.install(str(folder), None, plugin.inspect(str(folder), None)["sha256"], "user")


def test_manifest_validation() -> None:
    """The sample is valid; scripts, hooks, foreign tools, reserved names, bad flows and weak contracts are rejected."""
    data = manifest.load(SAMPLE)
    assert data["id"] == "contoso-oracle-practice.oracle-offering" and set(data["flows"]) == {"oracle-migration"}
    assert {s["status"] for s in data["skills"]} == {"admitted"} and all(s["quality_lift_pp"] is None for s in data["skills"])
    flow_file = Path("flows") / "oracle-migration.flow.json"
    contract_file = Path("evaluation") / "oracle-offering.eval.json"
    cases: list[tuple[str, Callable[[Path], None]]] = [
        ("Markdown and JSON only", lambda f: (f / "agents" / "helper.py").write_text("x = 1\n", encoding="utf-8")),
        ("cannot ship hooks", lambda f: (f / "hooks").mkdir()),
        ("nested frontmatter", lambda f: (f / "agents" / "oracle-engineer.agent.md").write_text(
            (SAMPLE / "agents" / "oracle-engineer.agent.md").read_text(encoding="utf-8").replace(
                "tools:", "hooks:\n  Stop:\n    - type: command\ntools:", 1), encoding="utf-8")),
        ("not in the manifest tools", lambda f: edit_json(f / "hve-plugin.json", lambda d: d["tools"].remove("execute/getTerminalOutput"))),
        ("reserved", lambda f: edit_json(f / "hve-plugin.json", lambda d: d.update(name="core"))),
        ("plugin needs Frontier HVE", lambda f: edit_json(f / "hve-plugin.json", lambda d: d["harness"].update(frontierHve=">=9.0.0"))),
        ("undeclared assets", lambda f: (f / "templates" / "extra.md").write_text("x", encoding="utf-8")),
        ("form a cycle", lambda f: edit_json(f / flow_file, lambda d: d["edges"].update(
            back={"from": "design", "to": "assess", "evidence": [{"type": "feature-checks"}]}))),
        ("cap must be", lambda f: edit_json(f / flow_file, lambda d: d["edges"]["rework-required"].update(cap=4))),
        ("agent must be", lambda f: edit_json(f / flow_file, lambda d: d["stages"]["assess"].update(agent="HVE flow-designer"))),
        ("lockChecks", lambda f: edit_json(f / flow_file, lambda d: d.update(lockChecks=False))),
        ("kebab-case", lambda f: edit_json(f / flow_file, lambda d: d["edges"].update(
            {"x\nhooks:": {"from": "assess", "to": "design", "evidence": [{"type": "feature-checks"}]}}))),
        ("is a command", lambda f: edit_json(f / contract_file, lambda d: d["validation"]["hooks"][0].update(type="command", command="x"))),
        ("below the core value", lambda f: edit_json(f / contract_file, lambda d: d["decision"].update(minimumScore=0.5))),
        ("core rubric ids", lambda f: edit_json(f / contract_file, lambda d: d["rubrics"][0].update(id="task-completion"))),
        ("coreShare", lambda f: edit_json(f / contract_file, lambda d: d.update(coreShare=0.9))),
    ]
    for expected, change in cases:
        with tempfile.TemporaryDirectory() as tmp:
            message = raises(ValueError, manifest.load, copy_sample(tmp, "p", change))
            assert expected in message, (expected, message)


def test_install_lifecycle() -> None:
    """Install needs confirmation, is idempotent, rejects clashes and changed content, upgrades, disables, reconciles and uninstalls."""
    with tempfile.TemporaryDirectory() as tmp:
        home = fresh_home(tmp)
        assert "--confirm <sha256>" in raises(PermissionError, plugin.install, str(SAMPLE), None, None, "user")
        assert install(SAMPLE)["installed"] is True
        assert plugin.install(str(SAMPLE), None, None, "user")["unchanged"] is True
        entry = store.plugin("oracle-offering")
        assert store.folder(entry).is_dir() and entry["owner"] == "user" and entry["manifest"]["skills"][0]["skill_tokens"] > 0
        clash = copy_sample(tmp, "clash", lambda f: edit_json(f / "hve-plugin.json", lambda d: d.update(publisher="other")))
        assert "already used by" in raises(ValueError, install, clash)
        changed = copy_sample(tmp, "changed", lambda f: (f / "README.md").write_text("changed\n", encoding="utf-8"))
        assert "different content" in raises(ValueError, install, changed)
        broken = copy_sample(tmp, "broken", lambda f: edit_json(f / "hve-plugin.json", lambda d: d.update(version="1.0.1", tools=[])))
        before = store.registry_file().read_text(encoding="utf-8")
        raises(ValueError, plugin.install, str(broken), None, None, "user")
        assert store.registry_file().read_text(encoding="utf-8") == before and not list((home / "staging").glob("*"))
        (home / "plugins.lock").write_text("", encoding="utf-8")
        assert "another Frontier HVE window" in raises(RuntimeError, install, SAMPLE)
        (home / "plugins.lock").unlink()
        upgrade = copy_sample(tmp, "upgrade", lambda f: edit_json(f / "hve-plugin.json", lambda d: d.update(version="1.0.1")))
        assert install(upgrade)["previous"] == "1.0.0"
        assert plugin.reconcile(None)["removed"] == ["contoso-oracle-practice.oracle-offering/1.0.0"]
        plugin.set_enabled("oracle-offering", False, "test")
        assert "is not installed or is disabled" in raises(LookupError, store.plugin, "oracle-offering")
        plugin.set_enabled("oracle-offering", True, None)
        (store.folder(store.plugin("oracle-offering")) / "README.md").write_text("tampered\n", encoding="utf-8")
        assert plugin.reconcile(None)["disabled"][0]["reason"] == "store content changed since install"
        plugin.uninstall("oracle-offering")
        assert not (home / "plugins" / "contoso-oracle-practice.oracle-offering").exists() and store.registry()["plugins"] == {}


def test_archive_and_index() -> None:
    """Packing is reproducible; archives and index entries install; unsafe, tampered and revoked packages are refused."""
    with tempfile.TemporaryDirectory() as tmp:
        fresh_home(tmp)
        first = plugin.pack(SAMPLE, Path(tmp) / "a")
        assert plugin.pack(SAMPLE, Path(tmp) / "b")["sha256"] == first["sha256"]
        index = Path(tmp) / "index.json"
        entry = {"name": "oracle-offering", "version": "1.0.0", "url": first["package"], "sha256": first["sha256"]}
        index.write_text(json.dumps({"version": 1, "plugins": [entry]}), encoding="utf-8")
        info = plugin.inspect("index:oracle-offering@1.0.0", str(index))
        assert info["verifiedByIndex"] is True and info["needsConfirmation"] is True
        plugin.install("index:oracle-offering@1.0.0", str(index), info["sha256"], "user")
        index.write_text(json.dumps({"version": 1, "plugins": [entry | {"revoked": True}]}), encoding="utf-8")
        assert plugin.reconcile(str(index))["disabled"][0]["reason"] == "revoked in the organization index"
        assert "revoked" in raises(PermissionError, plugin.inspect, "index:oracle-offering@1.0.0", str(index))
        index.write_text(json.dumps({"version": 1, "plugins": [entry | {"sha256": "0" * 64}]}), encoding="utf-8")
        assert "does not match the index" in raises(ValueError, plugin.inspect, "index:oracle-offering@1.0.0", str(index))
        evil = Path(tmp) / "evil.hveplugin"
        with zipfile.ZipFile(evil, "w") as package:
            package.writestr("../evil.md", "x")
        assert "unsafe entry" in raises(ValueError, plugin.inspect, str(evil), None)


def hook(ws: Path, payload: Json, **env: str) -> Json | None:
    """Run the skill loader hook in a workspace; return its JSON output or None."""
    result = subprocess.run([sys.executable, str(LOADER)], input=json.dumps({"session_id": "s1"} | payload), capture_output=True,
                            text=True, cwd=ws, env={**os.environ, "HARNESS_SKILLS_MIN_STATUS": "provisional", **env})
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def session(ws: Path) -> Json:
    """Return the session loadout written by the hook."""
    return json.loads((ws / ".hve" / "runs" / "s1.skills.json").read_text(encoding="utf-8"))


def context(ws: Path) -> str:
    """Return the announcement the first PreToolUse adds."""
    out = hook(ws, {"hook_event_name": "PreToolUse", "tool_name": "read_file", "tool_input": {"filePath": "app.py"}})
    assert out is not None
    return out["hookSpecificOutput"]["additionalContext"]


def test_routing() -> None:
    """One match selects; two matches ask and block plugin assets until answered; follow-ups keep the answer; names override."""
    with tempfile.TemporaryDirectory() as tmp:
        fresh_home(tmp)
        install(SAMPLE)
        install(copy_sample(tmp, "pg", as_postgres))
        ws = Path(tmp) / "ws"
        (ws / ".hve" / "runs").mkdir(parents=True)
        hook(ws, {"hook_event_name": "UserPromptSubmit", "prompt": "Plan the Oracle schema migration"})
        state = session(ws)
        assert state["plugins"] == ["oracle-offering"] and state["pending"] == []
        assert any("oracle-schema-design" in s for s in state["skills"] + state["recommended"]), state
        assert "Plugin oracle-offering 1.0.0: agents oracle-offering:oracle-db-architect" in context(ws)
        hook(ws, {"hook_event_name": "UserPromptSubmit", "prompt": "Migrate Oracle to Postgres"})
        state = session(ws)
        assert state["plugins"] == [] and state["pending"] == ["oracle-offering", "postgres-offering"]
        assert "header `select-plugin`" in context(ws)
        denied = hook(ws, {"hook_event_name": "PreToolUse", "tool_name": "read_file",
                           "tool_input": {"filePath": ".hve/skills/oracle-offering__oracle-schema-design/SKILL.md"}})
        assert denied and denied["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "not selected in this session" in raises(ValueError, manage.request, ws, "s1", ["oracle-offering:assessment"])
        hook(ws, {"hook_event_name": "PostToolUse", "tool_name": "vscode_askQuestions",
                  "tool_input": {"questions": [{"header": "select-plugin"}]},
                  "tool_response": {"answers": {"select-plugin": {"selected": ["oracle-offering"]}}}})
        assert session(ws)["plugins"] == ["oracle-offering"] and session(ws)["pending"] == []
        assert manage.request(ws, "s1", ["oracle-offering:assessment"])["requested"] == ["oracle-offering:assessment"]
        hook(ws, {"hook_event_name": "UserPromptSubmit", "prompt": "Now add the rollback steps"})
        assert session(ws)["plugins"] == ["oracle-offering"]
        hook(ws, {"hook_event_name": "UserPromptSubmit", "prompt": "Also cover the Postgres side"})
        assert session(ws)["plugins"] == ["oracle-offering"] and session(ws)["pending"] == [], "a declined candidate is not asked again"
        hook(ws, {"hook_event_name": "UserPromptSubmit", "prompt": "Use the postgres plugin for this"})
        assert session(ws)["plugins"] == ["postgres-offering"]
        hook(ws, {"hook_event_name": "UserPromptSubmit", "prompt": "Use the mysql-offering plugin here"})
        assert "not installed or are disabled" in context(ws)
        hook(ws, {"hook_event_name": "UserPromptSubmit", "prompt": "Review this"}, HARNESS_PLUGIN="oracle-offering")
        assert session(ws)["plugins"] == ["oracle-offering"]


def fill(path: Path) -> None:
    """Replace every placeholder of a generated document with content."""
    path.write_text(FILL.sub("Filled from workspace evidence.", path.read_text(encoding="utf-8")), encoding="utf-8")


def test_plugin_flow() -> None:
    """A plugin flow runs from its snapshot with template, locked-check and artifact evidence, and stops when the plugin changes."""
    with tempfile.TemporaryDirectory() as tmp:
        fresh_home(tmp)
        install(SAMPLE)
        project = Path(tmp) / "proj"
        (project / ".hve" / "runs").mkdir(parents=True)
        (project / ".hve" / "runs" / "s1.skills.json").write_text(json.dumps({"plugins": ["oracle-offering"]}), encoding="utf-8")
        assert "benchmark runs use the core flow" in raises(ValueError, flow.init, project, "benchmark", "oracle-offering:oracle-migration")
        flow.init(project, "product", "oracle-offering:oracle-migration")
        status = flow.status(project)
        assert status["agent"] == "oracle-offering:oracle-db-architect" and Path(status["instructions"]).is_file()
        assert status["evaluation"].endswith("evaluation/oracle-offering.eval.json") and status["allowed"] == ["assessed"]
        assert "no valid oracle-offering:assessment document" in flow.transition(project, "assessed", "")["missing"][0]
        fill(manage.initialize(project, "oracle-offering:assessment", "estate", "s1"))
        assert flow.transition(project, "assessed", "")["stage"] == "design"
        fill(manage.initialize(project, "technicalDesign", "target", "s1"))
        (project / "design.json").write_text(json.dumps({"acceptance": []}), encoding="utf-8")
        missing = flow.transition(project, "design-approved", "")["missing"]
        assert "needs a non-empty 'acceptance' list" in missing[0] and "needs a real 'validation_check' command" in missing[1]
        (project / "check.py").write_text("print('rows match')\n", encoding="utf-8")
        design = {"acceptance": ["row counts match"], "validation_check": "python check.py"}
        (project / "design.json").write_text(json.dumps(design), encoding="utf-8")
        assert flow.transition(project, "design-approved", "")["stage"] == "build"
        state = json.loads(flow.flow_file(project).read_text(encoding="utf-8")) | {"stage": "validate"}
        flow.flow_file(project).write_text(json.dumps(state), encoding="utf-8")
        (project / "feature_list.json").write_text(json.dumps([{"name": "rows", "passes": True}]), encoding="utf-8")
        (project / ".harness" / "state.json").write_text(json.dumps({"lock": {"rows": {"verify": "python check.py"}}}), encoding="utf-8")
        (project / "design.json").write_text(json.dumps(design | {"validation_check": "python -c \"print(1)\""}), encoding="utf-8")
        missing = flow.transition(project, "cutover-ready", "")["missing"]
        assert any("changed after it was approved" in m for m in missing), missing
        assert any("no valid oracle-offering:migrationRunbook" in m for m in missing) and any(".log was written" in m for m in missing)
        (project / "design.json").write_text(json.dumps(design), encoding="utf-8")
        fill(manage.initialize(project, "oracle-offering:migrationRunbook", "cutover", "s1"))
        (project / ".harness" / "evidence" / "rows").mkdir(parents=True)
        (project / ".harness" / "evidence" / "rows" / "check.log").write_text("rows match\n", encoding="utf-8")
        assert flow.transition(project, "cutover-ready", "")["stage"] == "done"
        install(copy_sample(tmp, "up", lambda f: edit_json(f / "hve-plugin.json", lambda d: d.update(version="1.0.1"))))
        assert "--restart" in raises(RuntimeError, flow.status, project)
        assert flow.init(project, "product", "oracle-offering:oracle-migration", True)["stage"] == "assess"


def write_input(project: Path, name: str, value: object) -> Path:
    """Write an agent input file and return its path."""
    path = project / ".hve" / "evaluations" / "input" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_rubric_composition() -> None:
    """Plugin rubrics combine with the selected core rubrics; unsound selections are rejected before scoring."""
    plugin_data = compose.plugin_contract(json.loads((SAMPLE / "evaluation" / "oracle-offering.eval.json").read_text(encoding="utf-8")), CORE)
    good = {"include": ["evidence-verification", "safety-maintainability", "constraint-adherence"],
            "exclude": {"task-completion": "covered-by:migration-completeness", "usability-accessibility": "not-applicable-output-kind"},
            "reasons": {"task-completion": "migration-completeness scores every requested object and workflow end to end."}}
    chosen = compose.selection(good, CORE, plugin_data, "cli")
    bad = [
        ("exactly once", good | {"include": good["include"][:2]}),
        ("cannot be excluded", good | {"include": ["safety-maintainability", "constraint-adherence"],
                                       "exclude": good["exclude"] | {"evidence-verification": "not-applicable-output-kind"}}),
        ("not a plugin rubric", good | {"exclude": good["exclude"] | {"task-completion": "covered-by:ghost"}}),
        ("must say in one sentence", good | {"reasons": {}}),
    ]
    for expected, value in bad:
        assert expected in raises(ValueError, compose.selection, value, CORE, plugin_data, "cli"), expected
    assert "is applicable" in raises(ValueError, compose.selection, good, CORE, plugin_data, "ui")
    combined = compose.combine(CORE, plugin_data, chosen)
    weights = {r["id"]: r["weight"] for r in combined["rubrics"]}
    assert abs(sum(weights.values()) - 1) < 1e-9 and abs(weights["migration-completeness"] - 0.28) < 1e-9
    assert abs(sum(weights[r] for r in good["include"]) - 0.3) < 1e-9 and "task-completion" not in weights
    assert {h["id"] for h in combined["validation"]["hooks"]} == {"validation-logs", "locked-feature-checks", "runtime-logs"}
    assert combined["decision"]["minimumScore"] == 0.85 and combined["council"] == CORE["council"]
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "project"
        project.mkdir()
        (project / "app.py").write_text("print('migrated')\n", encoding="utf-8")
        (project / "request.md").write_text("Migrate the Oracle schema.\n", encoding="utf-8")
        contract_path = SAMPLE / "evaluation" / "oracle-offering.eval.json"
        core_path = REPO / "evaluation" / "frontier.eval.json"
        assert "needs --rubric-selection" in raises(ValueError, workflow.prepare, project, core_path, project / "request.md", "cli", 0,
                                                    contract_path)
        assert "needs --plugin-contract" in raises(ValueError, workflow.prepare, project, core_path, project / "request.md", "cli", 0,
                                                   None, write_input(project, "sel.json", good))
        run = workflow.prepare(project, core_path, project / "request.md", "cli", 0, contract_path, write_input(project, "sel.json", good))
        folder = project / ".hve" / "evaluations" / run["runId"]
        snapshot = json.loads((folder / "contract.json").read_text(encoding="utf-8"))
        assert [r["id"] for r in snapshot["rubrics"]][:3] == ["migration-completeness", "data-integrity", "rollback-readiness"]
        assert json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["rubricSelection"] == chosen


def test_render_plugins() -> None:
    """Enabled plugins render as their own Agent Plugins folders with core hooks; creator-flow may delegate to flow stage agents."""
    with tempfile.TemporaryDirectory() as tmp:
        home = fresh_home(tmp)
        install(SAMPLE)
        subprocess.run([sys.executable, str(REPO / "extension" / "build.py")], check=True, capture_output=True)
        render = json.dumps(str(REPO / "extension" / "render.js"))
        extension = json.dumps(str(REPO / "extension"))
        script = (f"const r = require({render}); process.stdout.write(JSON.stringify(r.renderPlugins({extension}, 'python'))); "
                  f"r.renderPlugin({extension}, {json.dumps(str(Path(tmp) / 'core'))}, '0.0.0-test', 'python');")
        folders = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, env=os.environ).stdout)
        out = home / "rendered" / "contoso-oracle-practice.oracle-offering"
        assert [Path(f) for f in folders] == [out]
        assert json.loads((out / "plugin.json").read_text(encoding="utf-8"))["name"] == "oracle-offering"
        agents = out / "com.github.copilot" / "agents"
        architect = (agents / "oracle-db-architect.agent.md").read_text(encoding="utf-8")
        engineer = (agents / "oracle-engineer.agent.md").read_text(encoding="utf-8")
        assert "name: oracle-offering:oracle-db-architect" in architect and "HARNESS_PLUGIN: oracle-offering" in architect
        assert "{{RUNTIME}}" not in architect and "flow_guard.py" not in architect, "an agent of two stages gets no stage guard"
        assert "FLOW_STAGE: validate" in engineer and "FLOW_REF: oracle-offering:oracle-migration" in engineer
        for command in re.findall(r'python "([^"]+\.py)"', architect + engineer):
            assert Path(command).is_file(), command
        creator_flow = (Path(tmp) / "core" / "com.github.copilot" / "agents" / "hve-creator-flow.agent.md").read_text(encoding="utf-8")
        assert "HVE flow-maintainer, oracle-offering:oracle-db-architect, oracle-offering:oracle-engineer]" in creator_flow
        plugin.set_enabled("oracle-offering", False, "test")
        assert json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, env=os.environ).stdout) == []
        assert not out.exists()


def test_author_kit_and_requirements() -> None:
    """init scaffolds a valid, tested plugin repository; test runs routing cases; the schema matches the validator; requirements report."""
    with tempfile.TemporaryDirectory() as tmp:
        fresh_home(tmp)
        repo = Path(tmp) / "repo"
        created = plugin.author.init(repo, "sap-offering", "contoso-sap", "SAP Offering")
        assert created["id"] == "contoso-sap.sap-offering" and (repo / ".github" / "workflows" / "release-plugin.yml").is_file()
        assert plugin.author.test(repo / "plugin")["passed"] is True
        assert plugin.author.test(SAMPLE)["passed"] is True
        cases = repo / "plugin" / "tests" / "routing.json"
        cases.write_text(json.dumps({"cases": [{"prompt": "Fix the button color", "routes": True}]}), encoding="utf-8")
        assert plugin.author.test(repo / "plugin")["failed"][0]["prompt"] == "Fix the button color"
        assert "is not empty" in raises(FileExistsError, plugin.author.init, repo, "x", "y", "Z")
        schema = json.loads((REPO / "schemas" / "hve-plugin.schema.json").read_text(encoding="utf-8"))
        assert set(schema["properties"]) == manifest.MANIFEST_KEYS and set(schema["required"]) == manifest.REQUIRED_KEYS
        ws = Path(tmp) / "ws"
        ws.mkdir()
        assert plugin.requirements(ws)["file"] is None
        install(SAMPLE)
        need = [{"name": "oracle-offering", "range": ">=1.0.0 <2.0.0", "source": str(SAMPLE)},
                {"name": "sap-offering", "range": ">=0.1.0", "source": str(repo / "plugin")},
                {"name": "oracle-offering", "range": ">=2.0.0", "source": str(SAMPLE)}]
        (ws / plugin.REQUIREMENTS).write_text(json.dumps({"version": 1, "plugins": need}), encoding="utf-8")
        report = plugin.requirements(ws)
        assert [r["name"] for r in report["ok"]] == ["oracle-offering"] and [r["name"] for r in report["missing"]] == ["sap-offering"]
        assert report["conflicts"][0]["installed"] == "1.0.0"


def test_export_plugin_agents() -> None:
    """Enabled plugins' agents export to Claude Code and Codex with the plugin-limited loader; disabled ones are removed on re-export."""
    with tempfile.TemporaryDirectory() as tmp:
        fresh_home(tmp)
        install(SAMPLE)
        subprocess.run([sys.executable, str(REPO / "extension" / "build.py")], check=True, capture_output=True)
        exporter = REPO / "extension" / "runtime" / "tools" / "adapters" / "export.py"
        ws = Path(tmp) / "ws"
        ws.mkdir()
        for client in ("claude", "codex"):
            subprocess.run([sys.executable, str(exporter), client, str(ws)], check=True, capture_output=True, env=os.environ)
        claude = (ws / ".claude" / "agents" / "oracle-offering-oracle-engineer.md").read_text(encoding="utf-8")
        assert "HARNESS_PLUGIN=oracle-offering" in claude and ".hve/runtime/tools/loop/flow.py" in claude and "{{RUNTIME}}" not in claude
        assert (ws / ".agents" / "skills" / "oracle-offering-oracle-db-architect" / "SKILL.md").is_file()
        plugin.set_enabled("oracle-offering", False, "test")
        for client in ("claude", "codex"):
            subprocess.run([sys.executable, str(exporter), client, str(ws)], check=True, capture_output=True, env=os.environ)
        assert not (ws / ".claude" / "agents" / "oracle-offering-oracle-engineer.md").exists()
        assert not (ws / ".agents" / "skills" / "oracle-offering-oracle-db-architect").exists()
        assert (ws / ".claude" / "agents" / "hve-creator.md").is_file()


if __name__ == "__main__":
    test_manifest_validation()
    test_install_lifecycle()
    test_archive_and_index()
    test_routing()
    test_plugin_flow()
    test_rubric_composition()
    test_render_plugins()
    test_author_kit_and_requirements()
    test_export_plugin_agents()
    print("test_plugins: OK")
