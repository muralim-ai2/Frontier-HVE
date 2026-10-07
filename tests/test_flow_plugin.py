"""Tests of the creator-flow state machine, its stage guard, the harness-assist plugin hooks, and technical-level profiling."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "harness-assist"
sys.path[:0] = [str(REPO / "tools" / "loop"), str(REPO / "tools" / "skills"), str(PLUGIN / "scripts")]
import flow  # noqa: E402
from guardrail import scan as guardrail_scan  # noqa: E402
from scan import scan as skill_scan  # noqa: E402

DESIGN = {"screens": [{"name": "home"}], "acceptance": ["shows 5 colors"], "prototype_check": "python proto.py", "lint_check": "python lint.py"}


def make_flow(tmp: str) -> Path:
    """Return a project with a valid design, passing lint, and a prototype check that passes once proto_ok exists."""
    project = Path(tmp) / "proj"
    project.mkdir()
    (project / "design.json").write_text(json.dumps(DESIGN), encoding="utf-8")
    (project / "proto.py").write_text("import pathlib, sys\nsys.exit(0 if pathlib.Path('proto_ok').exists() else 1)\n", encoding="utf-8")
    (project / "lint.py").write_text("print('ok')\n", encoding="utf-8")
    flow.init(project, "benchmark")
    return project


def test_flow_edges_need_evidence() -> None:
    """Only drawn edges move the flow; concept-validated needs the prototype check; structure blocks a 600-line file."""
    with tempfile.TemporaryDirectory() as tmp:
        project = make_flow(tmp)
        try:
            flow.transition(project, "concept-validated", "")
        except ValueError as e:
            assert "not an edge from 'designer'" in str(e), e
        else:
            raise AssertionError("an edge from another stage must fail")
        assert flow.transition(project, "shape-defined", "")["stage"] == "prototyper"
        assert flow.transition(project, "concept-validated", "")["moved"] is False
        (project / "proto_ok").write_text("", encoding="utf-8")
        assert flow.transition(project, "concept-validated", "")["stage"] == "builder"
        assert "never initialized" in flow.transition(project, "build-complete", "")["missing"][0]
        state = json.loads(flow.flow_file(project).read_text(encoding="utf-8")) | {"stage": "architect"}
        flow.flow_file(project).write_text(json.dumps(state), encoding="utf-8")
        (project / "big.ts").write_text("x\n" * 600, encoding="utf-8")
        assert "big.ts: 600 lines" in flow.transition(project, "structurally-sound", "")["missing"][0]


def test_flow_back_edges_are_capped() -> None:
    """rework-required may be taken twice, the third time asks the human; benchmark Grower gets no second pass."""
    with tempfile.TemporaryDirectory() as tmp:
        project = make_flow(tmp)
        for _ in range(2):
            state = json.loads(flow.flow_file(project).read_text(encoding="utf-8")) | {"stage": "architect"}
            flow.flow_file(project).write_text(json.dumps(state), encoding="utf-8")
            assert flow.transition(project, "rework-required", "split app.ts")["stage"] == "builder"
        state = json.loads(flow.flow_file(project).read_text(encoding="utf-8")) | {"stage": "architect"}
        flow.flow_file(project).write_text(json.dumps(state), encoding="utf-8")
        third = flow.transition(project, "rework-required", "still too big")
        assert third["escalated"] is True and "cap 2" in third["question"], third
        assert flow.resume(project, "accept as is")["resumed"] is True
        state = json.loads(flow.flow_file(project).read_text(encoding="utf-8")) | {"stage": "maintainer"}
        flow.flow_file(project).write_text(json.dumps(state), encoding="utf-8")
        assert flow.transition(project, "new-opportunity-found", "dark mode")["escalated"] is True


def run_hook(script: Path, payload: dict[str, Any], cwd: Path, **env: str) -> dict[str, Any] | None:
    """Run a hook script with a payload in a working folder; return its JSON output or None."""
    result = subprocess.run([sys.executable, str(script)] + (["--hook"] if script.name == "guardrail.py" else []),
                            input=json.dumps({"session_id": "s1", **payload}), capture_output=True, text=True, cwd=cwd,
                            env={**os.environ, **env})
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def test_flow_guard_blocks_unfinished_stage() -> None:
    """A stage agent that stops without a transition is sent back once; other stages and a second stop pass."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "hooks").mkdir()
        (root / ".hve" / "runs").mkdir(parents=True)
        for hook in ("flow_guard.py", "interventions.py", "hve_paths.py"):
            shutil.copy(REPO / "hooks" / hook, root / "hooks")
        project = make_flow(tmp)
        payload = {"hook_event_name": "SubagentStop", "agent_id": "a", "agent_type": "flow-designer", "stop_hook_active": False}
        assert run_hook(root / "hooks" / "flow_guard.py", payload, root, HARNESS_PROJECT=project.name, FLOW_STAGE="designer")["decision"] == "block"  # type: ignore[index]
        assert run_hook(root / "hooks" / "flow_guard.py", payload, root, HARNESS_PROJECT=project.name, FLOW_STAGE="sweeper") is None
        assert run_hook(root / "hooks" / "flow_guard.py", payload | {"stop_hook_active": True}, root, HARNESS_PROJECT=project.name,
                        FLOW_STAGE="designer") is None


def test_choice_recorder() -> None:
    """Tagged answers become the option choice, a cumulative push approval, and the profile's technical level."""
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        (cwd / "proj" / ".harness").mkdir(parents=True)
        (cwd / ".hve").mkdir()
        (cwd / ".hve" / "user_profile.json").write_text(json.dumps({"technical_level": None}), encoding="utf-8")

        def answer(header: str, question: str, selected: list[str]) -> None:
            """Fire the recorder for one answered question."""
            run_hook(PLUGIN / "scripts" / "choice_recorder.py", {
                "hook_event_name": "PostToolUse", "tool_name": "vscode_askQuestions", "tool_use_id": "t",
                "tool_input": {"questions": [{"header": header, "question": question}]},
                "tool_response": json.dumps({"answers": {header: {"selected": selected, "freeText": None, "skipped": False}}})}, cwd)

        answer("choose:palette", "Which option? [project: proj]", ["two"])
        answer("push", "Push which? [project: proj]", ["feature/a"])
        answer("push", "Push which? [project: proj]", ["feature/b", "not-a-branch"])
        answer("technical-level", "How technical? [profile: .hve/user_profile.json]", ["executive"])
        assert json.loads((cwd / "proj" / ".harness" / "choices" / "palette.json").read_text())["approach"] == "two"
        assert json.loads((cwd / "proj" / ".harness" / "push_approved.json").read_text())["branches"] == ["feature/a", "feature/b"]
        assert json.loads((cwd / ".hve" / "user_profile.json").read_text())["technical_level"] == "executive"


def test_guardrail_flags_non_enterprise_prototype() -> None:
    """Over 5,000 lines, FalkorDB, Tesseract, SQLite and a Dockerfile give a review verdict naming a solution architect; the hook warns once."""
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        project = cwd / ".hve" / "outputs" / "flow" / "current"
        (project / ".harness").mkdir(parents=True)
        (project / "package.json").write_text(json.dumps({"dependencies": {"falkordb": "1", "tesseract.js": "5", "better-sqlite3": "9",
                                                                           "react": "19"}}), encoding="utf-8")
        (project / "Dockerfile").write_text("FROM node:20\n", encoding="utf-8")
        (project / "app.ts").write_text("x\n" * 5001, encoding="utf-8")
        report = guardrail_scan(project)
        assert report["verdict"] == "review" and len(report["flagged"]) == 3 and report["infrastructure_files"] == ["Dockerfile"], report
        assert "solution architect" in report["experts"] and "AI engineer" in report["experts"], report["experts"]
        payload = {"hook_event_name": "PostToolUse", "tool_name": "create_file", "tool_input": {}, "tool_use_id": "t", "tool_response": ""}
        first = run_hook(PLUGIN / "scripts" / "guardrail.py", payload, cwd)
        assert first and "Azure AI Document Intelligence" in first["systemMessage"], first
        assert run_hook(PLUGIN / "scripts" / "guardrail.py", payload, cwd) is None


def test_plugin_skills_pass_the_scan() -> None:
    """Every harness-assist skill passes the Phase 9 structure and security scan."""
    reports = [skill_scan(p.parent) for p in sorted((PLUGIN / "skills").glob("*/SKILL.md"))]
    assert len(reports) == 7 and all(r["ok"] for r in reports), [(r["name"], r["findings"]) for r in reports if not r["ok"]]


if __name__ == "__main__":
    test_flow_edges_need_evidence()
    test_flow_back_edges_are_capped()
    test_flow_guard_blocks_unfinished_stage()
    test_choice_recorder()
    test_guardrail_flags_non_enterprise_prototype()
    test_plugin_skills_pass_the_scan()
    print("test_flow_plugin: OK")
