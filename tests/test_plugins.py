"""Tests of expertise packs: manifest validation, install lifecycle, archives and index, routing into the ask contract with its token
load, stage evidence and rework, pack skills and templates, rubric composition, rendering and the author kit."""

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
LIFECYCLE = REPO / "tools" / "loop" / "lifecycle.py"
LOADER = REPO / "hooks" / "skill_loader.py"
MANAGE = REPO / "tools" / "templates" / "manage.py"
sys.path[:0] = [str(REPO / "tools" / p) for p in ("plugins", "loop", "templates", "evaluation")]
import compose  # noqa: E402
import manifest  # noqa: E402
import plugin  # noqa: E402
import store  # noqa: E402
import workflow  # noqa: E402
from contract import load_contract  # noqa: E402

CORE = load_contract(REPO / "evaluation" / "frontier.eval.json")
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
    """Point the pack home at an empty folder inside tmp."""
    home = Path(tmp) / "home"
    os.environ["HVE_PLUGIN_HOME"] = str(home)
    store.packs.cache_clear()
    return home


def copy_sample(tmp: str, name: str, change: Callable[[Path], None] | None = None) -> Path:
    """Return a copy of the sample pack, optionally changed."""
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
    """Turn a sample copy into a second pack, postgres-offering, by another publisher."""
    def change(data: Json) -> None:
        data.update(name="postgres-offering", publisher="contoso-pg")
        data["routing"].update(keywords=["postgres", "postgresql"], task_pattern="\\bpostgres(ql)?\\b")
    edit_json(folder / "hve-plugin.json", change)
    path = folder / "lifecycles" / "oracle-migration.json"
    path.write_text(path.read_text(encoding="utf-8").replace("oracle-offering:", "postgres-offering:"), encoding="utf-8")


def install(folder: Path) -> Json:
    """Install a pack folder after confirming the hash inspect shows."""
    result = plugin.install(str(folder), None, plugin.inspect(str(folder), None)["sha256"], "user")
    store.packs.cache_clear()
    return result


def lifecycle(ws: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run lifecycle.py in a workspace."""
    return subprocess.run([sys.executable, str(LIFECYCLE), *args], cwd=ws, capture_output=True, text=True, encoding="utf-8", env=os.environ)


def ok(result: subprocess.CompletedProcess[str]) -> Any:
    """Return the JSON a successful command printed."""
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_manifest_validation() -> None:
    """The sample is valid and measured; scripts, hooks, foreign tools and references, bad evidence, rework and knowledge, and weak
    rubric contracts are rejected."""
    data = manifest.load(SAMPLE)
    assert data["id"] == "contoso-oracle-practice.oracle-offering" and set(data["lifecycles"]) == {"oracle-offering:oracle-migration"}
    assert [k["id"] for k in data["knowledge"]] == ["migration-process-map", "common-fixes"] and data["manifest_tokens"] > 0
    assert all(k["tokens"] > 0 for k in data["knowledge"]) and all(a["tokens"] > 0 for a in data["agents"])
    assert {s["status"] for s in data["skills"]} == {"admitted"} and all(s["quality_lift_pp"] is None for s in data["skills"])
    life = Path("lifecycles") / "oracle-migration.json"
    rubric = Path("evaluation") / "oracle-offering.eval.json"
    cases: list[tuple[str, Callable[[Path], None]]] = [
        ("Markdown and JSON only", lambda f: (f / "agents" / "helper.py").write_text("x = 1\n", encoding="utf-8")),
        ("cannot ship hooks", lambda f: (f / "hooks").mkdir()),
        ("nested frontmatter", lambda f: (f / "agents" / "oracle-engineer.agent.md").write_text(
            (SAMPLE / "agents" / "oracle-engineer.agent.md").read_text(encoding="utf-8").replace(
                "tools:", "hooks:\n  Stop:\n    - type: command\ntools:", 1), encoding="utf-8")),
        ("not in the manifest tools", lambda f: edit_json(f / "hve-plugin.json", lambda d: d["tools"].remove("execute/getTerminalOutput"))),
        ("reserved", lambda f: edit_json(f / "hve-plugin.json", lambda d: d.update(name="core"))),
        ("plugin needs Frontier HVE", lambda f: edit_json(f / "hve-plugin.json", lambda d: d["harness"].update(frontierHve=">=9.0.0"))),
        ("undeclared assets", lambda f: (f / "knowledge" / "extra.md").write_text("x", encoding="utf-8")),
        ("is not a agent of pack", lambda f: edit_json(f / life, lambda d: d["stages"][0].update(agent="other-pack:architect"))),
        ("is not a skill of pack", lambda f: edit_json(f / life, lambda d: d["stages"][0].update(skills=["oracle-offering:ghost"]))),
        ("rework needs exactly", lambda f: edit_json(f / life, lambda d: d["stages"][3]["rework"].update(to="release"))),
        ("rework cap must be", lambda f: edit_json(f / life, lambda d: d["stages"][3]["rework"].update(cap=4))),
        ("must be an object whose type", lambda f: edit_json(f / life, lambda d: d["stages"][0]["evidence"].append({"type": "vibes"}))),
        ("knowledge[0] needs exactly", lambda f: edit_json(f / "hve-plugin.json", lambda d: d["knowledge"][0].pop("stages"))),
        ("is a command", lambda f: edit_json(f / rubric, lambda d: d["validation"]["hooks"][0].update(type="command", command="x"))),
        ("below the core value", lambda f: edit_json(f / rubric, lambda d: d["decision"].update(minimumScore=0.5))),
        ("core rubric ids", lambda f: edit_json(f / rubric, lambda d: d["rubrics"][0].update(id="task-completion"))),
        ("coreShare", lambda f: edit_json(f / rubric, lambda d: d.update(coreShare=0.9))),
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
        entry = store.enabled()["oracle-offering"]
        assert store.folder(entry).is_dir() and entry["manifest"]["skills"][0]["skill_tokens"] > 0
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
        assert "oracle-offering" not in store.enabled() and "not available" in raises(LookupError, store.pack, Path(tmp), "oracle-offering")
        plugin.set_enabled("oracle-offering", True, None)
        (store.folder(store.enabled()["oracle-offering"]) / "README.md").write_text("tampered\n", encoding="utf-8")
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


def hook(ws: Path, payload: Json) -> Json | None:
    """Run the skill loader hook in a workspace; return its JSON output or None."""
    result = subprocess.run([sys.executable, str(LOADER)], input=json.dumps({"session_id": "s1"} | payload), capture_output=True,
                            text=True, cwd=ws, env={**os.environ, "HARNESS_SKILLS_MIN_STATUS": "provisional"})
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def fill(path: Path) -> None:
    """Replace every placeholder of a generated document with content."""
    path.write_text(FILL.sub("Filled from workspace evidence.", path.read_text(encoding="utf-8")), encoding="utf-8")


def test_routing_contract_and_load() -> None:
    """A routed request needs a recorded pack choice; the contract, plan, brief and provenance carry the packs and their token load;
    pack skills load and other packs' skills are denied; pack templates, stage evidence and capped rework hold."""
    with tempfile.TemporaryDirectory() as tmp:
        fresh_home(tmp)
        install(copy_sample(tmp, "pg", as_postgres))
        ws = Path(tmp) / "ws"
        (ws / "plugins").mkdir(parents=True)
        shutil.copytree(SAMPLE, ws / "plugins" / "oracle-offering")
        (ws / "req.md").write_text("Use the mysql-offering plugin to migrate", encoding="utf-8")
        assert ok(lifecycle(ws, "route", "req.md"))["packs"]["missing"] == ["mysql-offering"]
        (ws / "req.md").write_text("Migrate our Oracle PL/SQL estate to Postgres", encoding="utf-8")
        routed = ok(lifecycle(ws, "route", "req.md"))
        assert [m["name"] for m in routed["packs"]["matched"]] == ["oracle-offering", "postgres-offering"], routed["packs"]
        assert routed["lifecycles"][0]["pack"] in ("oracle-offering", "postgres-offering")
        assert "oracle-migration" not in [r["name"] for r in routed["lifecycles"]], "a pack's lifecycles folder is not a plain overlay"
        refused = lifecycle(ws, "contract", "oracle-offering:oracle-migration", "ora", "Frontier BYOW", "req.md")
        assert refused.returncode != 0 and "pass @<pack>" in refused.stderr
        mixed = lifecycle(ws, "contract", "oracle-offering:oracle-migration", "ora", "Frontier BYOW", "req.md", "@core")
        assert mixed.returncode != 0 and "belongs to pack oracle-offering" in mixed.stderr
        data = ok(lifecycle(ws, "contract", "oracle-offering:oracle-migration", "ora", "Frontier BYOW", "req.md", "@oracle-offering"))
        pack = data["packs"][0]
        assert pack["name"] == "oracle-offering" and pack["source"] == "workspace" and pack["lifecycle"] == "oracle-offering:oracle-migration"
        assert any("task pattern" in w for w in pack["routed"]) and pack["agents"] == ["oracle-db-architect", "oracle-engineer"]
        assert [d["id"] for d in pack["knowledge"]] == ["migration-process-map", "common-fixes"]
        load = data["pack_load"]["packs"][0]
        assert load["always"] == load["index"] + load["knowledge_index"] + load["lifecycle"] + load["skills"] and load["skills"] > 0
        assert load["on_demand"] == load["knowledge"] + load["agents"] + load["templates"] > 0
        assert 0 < load["share_of_ask_context_pct"] <= 100 and 0 < load["share_of_window_pct"] < 100
        assert data["decisions"][0]["stage"] == "packs" and "oracle-offering" in data["decisions"][0]["choice"]
        plan = (ws / data["paths"]["plan"]).read_text(encoding="utf-8")
        assert "Expertise packs (" in plan and "| oracle-offering 1.0.0 |" in plan
        assert (ws / ".hve" / "skills" / "oracle-offering__oracle-schema-design" / "SKILL.md").is_file()
        brief = lifecycle(ws, "brief", "oracle-offering:oracle-db-architect", "stage=assess")
        assert brief.returncode == 0, brief.stderr
        assert ".hve/skills/oracle-offering__oracle-schema-design/SKILL.md" in brief.stdout and "Pack agent for this stage" in brief.stdout
        assert "Oracle migration process map" in brief.stdout and "Common Oracle migration fixes" not in brief.stdout
        hook(ws, {"hook_event_name": "UserPromptSubmit", "prompt": "Start the assessment"})
        read = {"hook_event_name": "PreToolUse", "tool_name": "read_file"}
        allowed = hook(ws, read | {"tool_input": {"filePath": ".hve/skills/oracle-offering__oracle-schema-design/SKILL.md"}})
        assert allowed is None or allowed["hookSpecificOutput"].get("permissionDecision") != "deny", allowed
        other = store.folder(store.enabled()["postgres-offering"]) / "skills" / "oracle-schema-design" / "SKILL.md"
        denied = hook(ws, read | {"tool_input": {"filePath": other.as_posix()}})
        assert denied and denied["hookSpecificOutput"]["permissionDecision"] == "deny", "a pack the ask did not choose stays closed"
        missing = lifecycle(ws, "stage", "assess", "done", "assessed")
        assert missing.returncode != 0 and "no valid oracle-offering:assessment document" in missing.stderr
        sys.path.insert(0, str(MANAGE.parent))
        import manage
        store.packs.cache_clear()
        fill(manage.initialize(ws, "oracle-offering:assessment", "estate", "s1"))
        assert ok(lifecycle(ws, "stage", "assess", "done", "assessed"))["status"] == "done"
        for _ in range(2):
            assert ok(lifecycle(ws, "rework", "validate", "row counts differ"))["current"] == "build"
        capped = lifecycle(ws, "rework", "validate", "still differ")
        assert capped.returncode != 0 and "rework cap of 2" in capped.stderr
        report = lifecycle(ws, "report", "s1")
        assert report.returncode == 0, report.stderr
        assert "## Expertise packs" in report.stdout and "| oracle-offering 1.0.0 |" in report.stdout


def write_input(project: Path, name: str, value: object) -> Path:
    """Write an agent input file and return its path."""
    path = project / ".hve" / "evaluations" / "input" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_rubric_composition() -> None:
    """Pack rubrics combine with the selected core rubrics; unsound selections are rejected before scoring."""
    pack = compose.plugin_contract(json.loads((SAMPLE / "evaluation" / "oracle-offering.eval.json").read_text(encoding="utf-8")), CORE)
    core_ids = [r["id"] for r in CORE["rubrics"]]
    exclude = {"task-completion": "covered-by:migration-completeness"}
    good = {"include": [r for r in core_ids if r not in exclude], "exclude": exclude,
            "reasons": {"task-completion": "migration-completeness scores every requested object and workflow end to end."}}
    chosen = compose.selection(good, CORE, pack, "cli")
    bad = [
        ("exactly once", good | {"include": good["include"][:2]}),
        ("cannot be excluded", good | {"include": [r for r in good["include"] if r != "evidence-verification"],
                                       "exclude": exclude | {"evidence-verification": "not-applicable-output-kind"}}),
        ("not a plugin rubric", good | {"exclude": {"task-completion": "covered-by:ghost"}}),
        ("must say in one sentence", good | {"reasons": {}}),
    ]
    for expected, value in bad:
        assert expected in raises(ValueError, compose.selection, value, CORE, pack, "cli"), expected
    combined = compose.combine(CORE, pack, chosen)
    weights = {r["id"]: r["weight"] for r in combined["rubrics"]}
    assert abs(sum(weights.values()) - 1) < 1e-9 and abs(weights["migration-completeness"] - 0.28) < 1e-9
    assert abs(sum(weights[r] for r in good["include"]) - 0.3) < 1e-9 and "task-completion" not in weights
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


def test_render_packs() -> None:
    """Available packs render as their own Agent Plugins folders with core hooks; packs no longer available are removed."""
    with tempfile.TemporaryDirectory() as tmp:
        fresh_home(tmp)
        install(SAMPLE)
        subprocess.run([sys.executable, str(REPO / "extension" / "build.py")], check=True, capture_output=True)
        packs = json.loads(subprocess.run([sys.executable, str(REPO / "tools" / "plugins" / "plugin.py"), "packs", tmp], capture_output=True,
                                          text=True, check=True, env=os.environ).stdout)
        root = Path(tmp) / "rendered"
        render = json.dumps(str(REPO / "extension" / "render.js"))
        script = (f"const r = require({render}); const packs = JSON.parse(require('fs').readFileSync(0, 'utf8')); process.stdout.write("
                  f"JSON.stringify(r.renderPacks({json.dumps(str(REPO / 'extension'))}, 'python', {json.dumps(str(root))}, packs)));")
        run = lambda value: json.loads(subprocess.run(["node", "-e", script], input=json.dumps(value), capture_output=True, text=True,
                                                      check=True).stdout)
        out = root / "contoso-oracle-practice.oracle-offering"
        assert [Path(f) for f in run(packs)] == [out]
        assert json.loads((out / "plugin.json").read_text(encoding="utf-8"))["name"] == "oracle-offering"
        architect = (out / "com.github.copilot" / "agents" / "oracle-db-architect.agent.md").read_text(encoding="utf-8")
        assert "name: oracle-offering:oracle-db-architect" in architect and "skill_loader.py" in architect and "{{RUNTIME}}" not in architect
        for command in re.findall(r'python "([^"]+\.py)"', architect):
            assert Path(command).is_file(), command
        assert run([]) == [] and not out.exists()


def test_author_kit_and_requirements() -> None:
    """init scaffolds a valid, tested pack repository; test runs routing cases; the schema matches the validator; requirements report."""
    with tempfile.TemporaryDirectory() as tmp:
        fresh_home(tmp)
        repo = Path(tmp) / "repo"
        created = plugin.author.init(repo, "sap-offering", "contoso-sap", "SAP Offering")
        assert created["id"] == "contoso-sap.sap-offering" and (repo / ".github" / "workflows" / "release-plugin.yml").is_file()
        assert plugin.author.test(repo / "plugin")["passed"] is True and plugin.author.test(SAMPLE)["passed"] is True
        cases = repo / "plugin" / "tests" / "routing.json"
        cases.write_text(json.dumps({"cases": [{"prompt": "Fix the button color", "routes": True}]}), encoding="utf-8")
        assert plugin.author.test(repo / "plugin")["failed"][0]["prompt"] == "Fix the button color"
        assert "is not empty" in raises(FileExistsError, plugin.author.init, repo, "x", "y", "Z")
        schema = json.loads((REPO / "schemas" / "hve-plugin.schema.json").read_text(encoding="utf-8"))
        assert set(schema["properties"]) == manifest.MANIFEST_KEYS and set(schema["required"]) == manifest.REQUIRED_KEYS
        ws = Path(tmp) / "ws"
        ws.mkdir()
        (ws / "frontier-hve.plugins.json").write_text(json.dumps({"version": 1, "plugins": [
            {"name": "oracle-offering", "range": ">=1.0.0 <2.0.0", "source": str(SAMPLE)}]}), encoding="utf-8")
        assert [m["name"] for m in plugin.requirements(ws)["missing"]] == ["oracle-offering"]
        install(SAMPLE)
        assert [m["name"] for m in plugin.requirements(ws)["ok"]] == ["oracle-offering"]


if __name__ == "__main__":
    for test in (test_manifest_validation, test_install_lifecycle, test_archive_and_index, test_routing_contract_and_load,
                 test_rubric_composition, test_render_packs, test_author_kit_and_requirements):
        test()
    print("test_plugins: OK")
