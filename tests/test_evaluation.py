"""Tests of the output reflection loop: contract validation, grounded scores, triggered validation, council markers and decisions."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools" / "evaluation"))
import workflow  # noqa: E402
from contract import load_contract, validate_contract  # noqa: E402

CONTRACT = REPO / "evaluation" / "frontier.eval.json"
CLI = REPO / "tools" / "evaluation" / "reflection.py"
ROLES = ("critical", "balanced", "constructive-coach")


def raises(error: type[Exception], fn: Any, *args: Any) -> str:
    """Return the message of the error fn(*args) raises; fail if it does not."""
    try:
        fn(*args)
    except error as e:
        return str(e)
    raise AssertionError(f"{fn.__name__}{args} did not raise {error.__name__}")


def make_project(tmp: str, check_passes: bool = True, screenshot: bool = True) -> Path:
    """Return a delivered project with one locked feature check, a source file, the request and optional screenshot evidence."""
    project = Path(tmp) / "project"
    project.mkdir()
    (project / "app.py").write_text("print('palette')\n", encoding="utf-8")
    (project / "check.py").write_text(f"import sys\nprint('HARNESS_CHECKS 3/3')\nsys.exit({0 if check_passes else 1})\n", encoding="utf-8")
    (project / "feature_list.json").write_text(json.dumps([{"name": "core", "verify": "python check.py", "passes": True}]), encoding="utf-8")
    (project / "request.md").write_text("Build a color palette generator.\n", encoding="utf-8")
    if screenshot:
        (project / ".harness" / "evidence" / "core").mkdir(parents=True)
        (project / ".harness" / "evidence" / "core" / "page.png").write_bytes(b"png")
    return project


def write(project: Path, name: str, value: object) -> Path:
    """Write an agent input JSON file and return its path."""
    path = project / ".hve" / "evaluations" / "input" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def scores(project: Path, **overrides: float) -> Path:
    """Write rubric scores (0.9 unless overridden) citing app.py."""
    rubrics = [{"id": r["id"], "score": overrides.get(r["id"].replace("-", "_"), 0.9), "rationale": "seen in app.py",
                "evidence": ["app.py:1"]} for r in load_contract(CONTRACT)["rubrics"]]
    return write(project, "scores.json", {"rubrics": rubrics})


def verdict(role: str, recommendation: str, *markers: dict[str, Any]) -> dict[str, Any]:
    """Return a council verdict."""
    return {"role": role, "recommendation": recommendation, "summary": f"{role} view", "markers": list(markers)}


def run_to_council(project: Path, revision_pass: int = 0, kind: str = "ui", **overrides: float) -> str:
    """Prepare, score and validate one run; return its id."""
    run_id = workflow.prepare(project, CONTRACT, project / "request.md", kind, revision_pass)["runId"]
    workflow.record_scores(project, run_id, scores(project, **overrides))
    workflow.validate_run(project, run_id)
    workflow.council_prompts(project, run_id)
    return run_id


def council(project: Path, run_id: str, *recommendations: str) -> dict[str, Any]:
    """Record one verdict per role and finalize the run."""
    for role, rec in zip(ROLES, recommendations):
        workflow.record_council(project, run_id, role, write(project, f"{role}.json", verdict(role, rec)), f"model-{role}")
    return workflow.finalize(project, run_id)


def test_contract_loads_and_rejects_unsafe_definitions() -> None:
    """The shipped JSON contract loads; weights, tiers, hook references, triggers, kinds and recommendations are enforced."""
    contract = load_contract(CONTRACT)
    assert [r["id"] for r in contract["rubrics"]][0] == "task-completion" and len(contract["council"]["roles"]) == 3
    edits: list[tuple[Any, str]] = [
        (lambda c: c["rubrics"][0].update(weight=0.5), "sum to 1"),
        (lambda c: c["council"]["roles"][0].update(modelTier="low"), "modelTier high"),
        (lambda c: c["rubrics"][0].update(validationHooks=["ghost"]), "unknown validation hooks"),
        (lambda c: c["rubrics"][3].update(validationHooks=["locked-feature-checks"]), "not used by any rubric"),
        (lambda c: c["validation"]["hooks"][0].update(trigger="sometimes"), "trigger must be one of"),
        (lambda c: c["validation"]["hooks"][1].update(outputKinds=["desktop"]), "outputKinds must be"),
        (lambda c: c["validation"]["hooks"][2].pop("recommendation"), "recommendation must be a non-empty string")]
    for edit, message in edits:
        raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
        edit(raw)
        assert message in raises(ValueError, validate_contract, raw), message


def test_scores_must_be_grounded_and_ordered() -> None:
    """Scores need contract order, a 0-1 range and existing project files as evidence; stages cannot be skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(tmp)
        run_id = workflow.prepare(project, CONTRACT, project / "request.md", "ui", 0)["runId"]
        prompt = json.loads((project / ".hve" / "evaluations" / run_id / "rubric-prompt.json").read_text(encoding="utf-8"))
        assert "app.py" in prompt["inventory"] and not any(p.startswith(".hve/") for p in prompt["inventory"])
        assert "expected 'awaiting-validation'" in raises(ValueError, workflow.validate_run, project, run_id)
        good = json.loads(scores(project).read_text(encoding="utf-8"))
        assert "contract order" in raises(ValueError, workflow.record_scores, project, run_id,
                                          write(project, "bad.json", {"rubrics": good["rubrics"][::-1]}))
        for bad_evidence in (["missing.py"], ["../outside.py"], []):
            good["rubrics"][0]["evidence"] = bad_evidence
            raises(ValueError, workflow.record_scores, project, run_id, write(project, "bad.json", good))
        good["rubrics"][0] |= {"evidence": ["app.py"], "score": 1.5}
        assert "between 0 and 1" in raises(ValueError, workflow.record_scores, project, run_id, write(project, "bad.json", good))
        assert workflow.record_scores(project, run_id, scores(project))["status"] == "awaiting-validation"


def test_validation_follows_trigger_and_output_kind() -> None:
    """Locked checks always run; screenshots only for low UI scores; CLI logs are optional and become a recommendation."""
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(tmp, check_passes=False)
        run_id = run_to_council(project)
        validation = json.loads((project / ".hve" / "evaluations" / run_id / "validation-results.json").read_text(encoding="utf-8"))
        assert [h["id"] for h in validation["hooks"]] == ["locked-feature-checks"] and validation["passed"] is False, validation
        assert validation["notApplicable"] == ["runtime-logs"] and validation["triggeredBy"] == [], validation
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(tmp, check_passes=False)
        run_id = workflow.prepare(project, CONTRACT, project / "request.md", "ui", 0)["runId"]
        workflow.record_scores(project, run_id, scores(project, usability_accessibility=0.7, task_completion=0.5))
        result = workflow.validate_run(project, run_id)
        assert result["passed"] is False and set(result["hooks"]) == {"locked-feature-checks", "visual-evidence"}, result
        folder = project / ".hve" / "evaluations" / run_id
        hooks = {h["id"]: h for h in json.loads((folder / "validation-results.json").read_text(encoding="utf-8"))["hooks"]}
        assert hooks["locked-feature-checks"]["runs"][0]["checks"] == "3/3" and not hooks["locked-feature-checks"]["passed"]
        assert hooks["visual-evidence"]["artifacts"][0]["path"] == ".harness/evidence/core/page.png"
        workflow.council_prompts(project, run_id)
        prompts = json.loads((folder / "council-prompts.json").read_text(encoding="utf-8"))["prompts"]
        assert [p["role"] for p in prompts] == list(ROLES) and all(p["modelTier"] == "high" for p in prompts)
        report = council(project, run_id, "pass", "pass", "pass")
        synthetic = [m for m in report["markers"] if m["source"] in ("rubrics", "validation")]
        assert {m["evidence"][0] for m in synthetic} == {"rubric:task-completion", "validation:locked-feature-checks"}, synthetic
        assert report["decision"] == "revise", report
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(tmp, screenshot=False)
        report = council(project, run_to_council(project, kind="cli"), "pass", "pass", "pass")
        assert report["decision"] == "pass" and report["validation"]["hooks"][1]["id"] == "runtime-logs", report
        assert len(report["recommendations"]) == 1 and report["recommendations"][0].startswith("runtime-logs: collected 0"), report


def test_council_markers_are_traceable() -> None:
    """Verdicts need a known role, recommendation, rubric, severity and real evidence, and each role records once."""
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(tmp)
        run_id = run_to_council(project)
        marker = {"kind": "questionable-design", "severity": "medium", "rubric": "usability-accessibility",
                  "summary": "lock state is color only", "evidence": ["file:app.py", "rubric:usability-accessibility"]}
        assert "unknown council role" in raises(ValueError, workflow.record_council, project, run_id, "ghost",
                                                write(project, "v.json", verdict("ghost", "pass")), "m")
        for bad in ({**marker, "severity": "urgent"}, {**marker, "rubric": "ghost"}, {**marker, "evidence": ["file:nope.py"]},
                    {**marker, "evidence": ["validation:ghost"]}, {**marker, "evidence": []}):
            raises(ValueError, workflow.record_council, project, run_id, "critical", write(project, "v.json", verdict("critical", "pass", bad)), "m")
        assert "must be a non-empty string" in raises(ValueError, workflow.record_council, project, run_id, "critical",
                                                       write(project, "v.json", verdict("critical", "pass")), " ")
        assert workflow.record_council(project, run_id, "critical", write(project, "v.json", verdict("critical", "revise", marker)),
                                       "model-a")["remainingRoles"] == ["balanced", "constructive-coach"]
        assert "already recorded" in raises(FileExistsError, workflow.record_council, project, run_id, "critical",
                                            write(project, "v.json", verdict("critical", "pass")), "m")
        assert "missing" in raises(ValueError, workflow.finalize, project, run_id)


def test_decisions_pass_revise_and_human_review() -> None:
    """Consensus passes; unchanged output is not re-evaluated; a critical marker forces revision; the human verdict is recorded."""
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(tmp)
        assert workflow.check(project)["status"] == "missing"
        assert council(project, run_to_council(project), "pass", "pass", "revise")["decision"] == "pass"
        assert workflow.check(project)["status"] == "pass"
        assert "needs a completed pass 0 whose decision is revise" in raises(ValueError, workflow.prepare, project, CONTRACT,
                                                                             project / "request.md", "ui", 1)
        assert "nothing changed" in raises(ValueError, workflow.prepare, project, CONTRACT, project / "request.md", "ui", 0)
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(tmp)
        run_id = run_to_council(project)
        critical = {"kind": "miss", "severity": "critical", "rubric": "task-completion", "summary": "export missing",
                    "evidence": ["rubric:task-completion"]}
        workflow.record_council(project, run_id, "critical", write(project, "c.json", verdict("critical", "revise", critical)), "m1")
        for role in ROLES[1:]:
            workflow.record_council(project, run_id, role, write(project, f"{role}.json", verdict(role, "pass")), "m2")
        first = workflow.finalize(project, run_id)
        assert first["decision"] == "revise" and first["markers"][0]["severity"] == "critical", first
        cli = subprocess.run([sys.executable, str(CLI), "check", str(project)], capture_output=True, text=True)
        assert cli.returncode == 1 and json.loads(cli.stdout)["status"] == "revise", cli
        (project / "app.py").write_text("print('palette with export')\n", encoding="utf-8")
        second_id = run_to_council(project, 1)
        hooks = json.loads((project / ".hve" / "evaluations" / second_id / "validation-results.json").read_text(encoding="utf-8"))["hooks"]
        assert {h["id"] for h in hooks} == {"locked-feature-checks", "visual-evidence"}, "revision passes re-run every hook"
        assert council(project, second_id, "revise", "pass", "human-review")["decision"] == "human-review"
        cli = subprocess.run([sys.executable, str(CLI), "check", str(project)], capture_output=True, text=True)
        assert cli.returncode == 0 and json.loads(cli.stdout)["status"] == "human-review", cli
        assert "between 0 and 1" in raises(ValueError, workflow.prepare, project, CONTRACT, project / "request.md", "ui", 2)
        bad = write(project, "human.json", {"decision": "revise", "summary": "export still missing", "disagree": [99]})
        assert "unique marker indexes" in raises(ValueError, workflow.record_human, project, second_id, bad)
        human = write(project, "human.json", {"decision": "revise", "summary": "export still missing", "disagree": []})
        assert workflow.record_human(project, second_id, human)["disagreed"] == 0
        assert "already recorded" in raises(FileExistsError, workflow.record_human, project, second_id, human)
        cli = subprocess.run([sys.executable, str(CLI), "check", str(project)], capture_output=True, text=True)
        assert cli.returncode == 1 and json.loads(cli.stdout)["human"] == "revise", cli


def test_output_without_feature_loop_is_evaluated() -> None:
    """A document or prototype with no feature loop is still scored and judged; the locked checks are marked not applicable with a reason."""
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(tmp, screenshot=False)
        (project / "feature_list.json").unlink()
        run_id = run_to_council(project, kind="document")
        validation = json.loads((project / ".hve" / "evaluations" / run_id / "validation-results.json").read_text(encoding="utf-8"))
        assert validation["hooks"] == [] and "locked-feature-checks" in validation["notApplicable"], validation
        assert "no feature loop" in validation["notApplicableWhy"]["locked-feature-checks"] and validation["passed"] is True, validation
        assert council(project, run_id, "pass", "pass", "pass")["decision"] == "pass"


if __name__ == "__main__":
    test_contract_loads_and_rejects_unsafe_definitions()
    test_scores_must_be_grounded_and_ordered()
    test_validation_follows_trigger_and_output_kind()
    test_council_markers_are_traceable()
    test_decisions_pass_revise_and_human_review()
    test_output_without_feature_loop_is_evaluated()
    print("test_evaluation: OK")
