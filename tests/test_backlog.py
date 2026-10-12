"""Tests of the local JSON backlog validator: hierarchy, completeness, dependencies and PRD traceability."""

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools" / "backlog"))
import backlog  # noqa: E402

PRD = "# PRD\n\n- FR-1: Employees submit leave requests.\n- FR-2: Managers approve requests.\n- NFR-1: p95 under 2 s.\n"


def item(id_: str, type_: str, parent: str | None, requirements: list[str], dependencies: list[str] | None = None) -> dict[str, Any]:
    """Return one complete backlog item."""
    return {"id": id_, "type": type_, "parent": parent, "title": f"{type_} {id_}", "persona": "Employee",
            "problem": "Leave is requested by email.", "outcome": "Requests are tracked.", "scope": "Web form.",
            "non_goals": ["Payroll changes"], "acceptance": [{"given": "a signed-in employee", "when": "they submit",
                                                              "then": "the request shows as pending"}],
            "verification": "UI test of the submit flow", "dependencies": dependencies or [], "priority": "P0",
            "priority_rationale": "Blocks every other flow", "requirements": requirements}


VALID = {"version": 1, "prd": "docs/product/PRD-leave.md", "items": [
    item("E1", "epic", None, ["FR-1", "FR-2"]),
    item("F1", "feature", "E1", ["FR-1"]),
    item("S1", "story", "F1", ["FR-1", "NFR-1"]),
    item("S2", "story", "F1", ["FR-2"], ["S1"]),
]}


def report_for(data: dict[str, Any], prd: str = PRD) -> backlog.Report:
    """Write data and the PRD into a temp workspace and return the validator's report."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "docs" / "product").mkdir(parents=True)
        (ws / "docs" / "product" / "PRD-leave.md").write_text(prd, encoding="utf-8")
        (ws / "docs" / "product" / "BACKLOG-leave.json").write_text(json.dumps(data), encoding="utf-8")
        return backlog.validate(ws, "docs/product/BACKLOG-leave.json")


def errors_for(data: dict[str, Any]) -> list[str]:
    """Return the validator's errors for data against the default PRD."""
    return report_for(data)["errors"]


def changed(index: int, **fields: Any) -> dict[str, Any]:
    """Return a copy of VALID with fields of one item replaced."""
    data = copy.deepcopy(VALID)
    data["items"][index].update(fields)
    return data


def test_valid_backlog() -> None:
    """A complete epic, feature and two stories traced to PRD ids pass."""
    assert errors_for(VALID) == []


def test_each_rule_fails() -> None:
    """Each broken rule produces an error naming the item."""
    cases = {
        "duplicate id": changed(3, id="S1", dependencies=[]),
        "needs parent type feature": changed(2, parent="E1"),
        "needs parent type None": changed(0, parent="F1"),
        "missing field persona": {**VALID, "items": [{k: v for k, v in VALID["items"][0].items() if k != "persona"}]},
        "unknown field": changed(0, labels=["x"]),
        "acceptance needs": changed(2, acceptance=[{"given": "x", "when": "y"}]),
        "non_goals needs": changed(1, non_goals=[]),
        "priority must be": changed(1, priority="High"),
        "unknown dependency": changed(3, dependencies=["S9"]),
        "is not in the PRD": changed(2, requirements=["FR-9"]),
        "must look like FR-1": changed(2, requirements=["fr1"]),
        "dependency cycle": changed(2, dependencies=["S2"]),
        "backlog must be": {**VALID, "version": 2},
    }
    for needle, data in cases.items():
        errors = errors_for(data)
        assert any(needle in error for error in errors), (needle, errors)


def test_paths_stay_in_workspace() -> None:
    """A PRD path outside the workspace or in harness state is rejected."""
    for prd in ("../PRD.md", ".hve/PRD.md"):
        try:
            errors_for({**VALID, "prd": prd})
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {prd}")


def malformed_cases() -> list[dict[str, Any]]:
    """Return wrong-type payloads including previously accepted references and crashing dependencies."""
    numeric_dependency = changed(2, id="1")
    numeric_dependency["items"][3]["dependencies"] = [1]
    numeric_parent = changed(0, id="1")
    numeric_parent["items"][1]["parent"] = 1
    return [
        numeric_dependency, numeric_parent,
        *[{**VALID, "version": value} for value in (True, 1.0, "1", None)],
        *[{**VALID, "prd": value} for value in (123, None, [], {}, "")],
        changed(0, id=["E1"]), changed(1, parent={}), changed(1, type=None),
        changed(2, dependencies=[{}]), changed(2, dependencies=[None]),
        changed(2, dependencies=[""]), changed(2, dependencies="S1"),
        changed(2, requirements=[1]), changed(2, non_goals=[None]),
        changed(2, acceptance=[None]), changed(2, acceptance=[{"given": 1, "when": "x", "then": "y"}]),
    ]


def test_malformed_types_are_validation_errors() -> None:
    """Malformed fields are rejected before graph construction without runtime type errors."""
    for data in malformed_cases():
        assert errors_for(data), data
    data = changed(2, id="1")
    data["items"][3]["dependencies"] = ["1"]
    assert errors_for(data) == []
    data = changed(0, id="1")
    data["items"][1]["parent"] = "1"
    assert errors_for(data) == []


def test_uncovered_requirements_are_reported_not_errors() -> None:
    """FR/NFR ids in the PRD that no item delivers are listed in document order; AC ids and lookalikes are ignored."""
    prd = PRD + "- FR-3: Export calendar.\n- NFR-10: WCAG 2.2 AA (see FR-1, AC-4, XFR-7).\n- FR-3 is later.\n"
    assert report_for(VALID, prd) == {"errors": [], "uncovered": ["FR-3", "NFR-10"]}
    assert report_for(changed(2, requirements=["FR-9"]), prd)["uncovered"] == []


def test_cli_exit_codes() -> None:
    """The CLI exits 0 for a valid backlog and 1 with JSON errors otherwise."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "docs" / "product").mkdir(parents=True)
        (ws / "docs" / "product" / "PRD-leave.md").write_text(PRD, encoding="utf-8")
        target = ws / "docs" / "product" / "BACKLOG-leave.json"
        base = [sys.executable, str(REPO / "tools" / "backlog" / "backlog.py"), "--workspace", tmp, "validate",
                "docs/product/BACKLOG-leave.json"]
        target.write_text(json.dumps(VALID), encoding="utf-8")
        result = subprocess.run(base, capture_output=True, text=True)
        assert result.returncode == 0 and json.loads(result.stdout) == {"valid": True, "errors": [], "uncovered": []}, result.stdout
        for data in [changed(2, requirements=["FR-9"]), *malformed_cases()]:
            target.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run(base, capture_output=True, text=True)
            assert result.returncode == 1 and json.loads(result.stdout)["valid"] is False, (result.stdout, result.stderr)
            assert not result.stderr, result.stderr


if __name__ == "__main__":
    test_valid_backlog()
    test_each_rule_fails()
    test_paths_stay_in_workspace()
    test_malformed_types_are_validation_errors()
    test_uncovered_requirements_are_reported_not_errors()
    test_cli_exit_codes()
    print("test_backlog: OK")
