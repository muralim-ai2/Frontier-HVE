"""Verify exact-ask, revision-guarded UI reviews against the existing lifecycle CLI."""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "tools" / "loop" / "lifecycle.py"


def invoke(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the existing lifecycle CLI in the supplied test workspace."""
    return subprocess.run([sys.executable, "-B", str(CLI), *args], cwd=workspace, capture_output=True, text=True, encoding="utf-8")


def run(workspace: Path, *args: str) -> dict[str, object]:
    """Return a successful lifecycle CLI response."""
    result = invoke(workspace, *args)
    assert result.returncode == 0, result.stderr
    value: dict[str, object] = json.loads(result.stdout)
    return value


def create(workspace: Path, slug: str) -> str:
    """Create a real ask in the disposable workspace."""
    request = workspace / "request.txt"
    request.write_text("Build an onboarding policy checker", encoding="utf-8")
    data = run(workspace, "contract", "direct", slug, "Frontier Lite", str(request))
    ask = data["ask"]
    assert isinstance(ask, str)
    return ask


def read_contract(workspace: Path, ask: str) -> dict[str, object]:
    """Read the selected ask's contract."""
    value: dict[str, object] = json.loads((workspace / ".hve" / "asks" / ask / "contract.json").read_text(encoding="utf-8"))
    return value


def test_review_ticket_is_read_only_and_valid_review_is_persistent(tmp_path: Path) -> None:
    """Read-only tickets authorize persistent reviews of exactly their selected ask."""
    ask = create(tmp_path, "first")
    folder = tmp_path / ".hve" / "asks" / ask
    before = {name: (folder / name).read_bytes() for name in ("contract.json", "plan.md")}
    ticket = run(tmp_path, "review-status", ask)
    assert {name: (folder / name).read_bytes() for name in before} == before
    result = run(tmp_path, "tick-for", ask, str(ticket["revision"]), "stage:deliver", "accepted", "Human inspected the evidence")
    assert result["ask"] == ask and result["value"] == "accepted"
    checklist = read_contract(tmp_path, ask)["checklist"]
    assert isinstance(checklist, dict) and checklist["stage:deliver"]["value"] == "accepted"
    assert "- [x] stage:deliver" in (folder / "plan.md").read_text(encoding="utf-8")


def test_changed_active_ask_does_not_receive_a_stale_review(tmp_path: Path) -> None:
    """Switching asks refuses the old ticket without changing either contract."""
    first = create(tmp_path, "first")
    ticket = run(tmp_path, "review-status", first)
    second = create(tmp_path, "second")
    before = {ask: read_contract(tmp_path, ask) for ask in (first, second)}
    result = invoke(tmp_path, "tick-for", first, str(ticket["revision"]), "stage:deliver", "accepted", "Reviewed first ask")
    assert result.returncode != 0 and "changed" in result.stderr
    assert {ask: read_contract(tmp_path, ask) for ask in before} == before
    assert invoke(tmp_path, "review-status", first).returncode != 0


def test_plan_edit_invalidates_review_and_does_not_reconcile_ticks(tmp_path: Path) -> None:
    """An edited plan rejects an earlier ticket without writing the plan or contract."""
    ask = create(tmp_path, "first")
    ticket = run(tmp_path, "review-status", ask)
    plan = tmp_path / ".hve" / "asks" / ask / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace("- [ ] stage:deliver", "- [x] stage:deliver"), encoding="utf-8")
    before = read_contract(tmp_path, ask)
    text = plan.read_bytes()
    result = invoke(tmp_path, "tick-for", ask, str(ticket["revision"]), "stage:deliver", "accepted", "Old review")
    assert result.returncode != 0 and "changed" in result.stderr
    assert read_contract(tmp_path, ask) == before and plan.read_bytes() == text


def test_guarded_reviews_reject_nonreview_actions_and_preserve_legacy_tick(tmp_path: Path) -> None:
    """The UI route cannot toggle telemetry, while the existing tick route retains its behavior."""
    ask = create(tmp_path, "first")
    ticket = run(tmp_path, "review-status", ask)
    bad = invoke(tmp_path, "tick-for", ask, str(ticket["revision"]), "opt:evaluation", "on", "Not a review")
    assert bad.returncode != 0 and "guarded review needs" in bad.stderr
    assert read_contract(tmp_path, ask)["checklist"] == {}
    legacy = run(tmp_path, "tick", "stage:deliver", "changes", "Legacy form requested changes")
    assert legacy["value"] == "changes"


def test_new_recorded_evidence_invalidates_ticket(tmp_path: Path) -> None:
    """A changed deterministic check record invalidates an outstanding review ticket."""
    ask = create(tmp_path, "first")
    ticket = run(tmp_path, "review-status", ask)
    records = tmp_path / ".hve" / "asks" / ask / "loop" / "prs"
    records.mkdir()
    (records / "policy.json").write_text('{"verify": {"exit_code": 1}}', encoding="utf-8")
    result = invoke(tmp_path, "tick-for", ask, str(ticket["revision"]), "stage:deliver", "accepted", "Old review")
    assert result.returncode != 0 and "changed" in result.stderr
    assert read_contract(tmp_path, ask)["checklist"] == {}
