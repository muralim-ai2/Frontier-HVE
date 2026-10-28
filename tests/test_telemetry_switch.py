"""Research telemetry is a switch, not a question: plans, ticks, agent prompts and the report no longer ask about it."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "tools" / "loop" / "lifecycle.py"
sys.path.insert(0, str(REPO / "tools" / "loop"))
import ask_report  # noqa: E402

REMINDER = "Turn off research telemetry"
PROMPTS = [*(REPO / "extension" / "agents").glob("*.agent.md"), *(REPO / ".github" / "agents").glob("*.agent.md"),
           *(REPO / "templates" / "personas").rglob("*.md")]


def invoke(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the lifecycle CLI in a scratch workspace."""
    return subprocess.run([sys.executable, "-B", str(CLI), *args], cwd=workspace, capture_output=True, text=True, encoding="utf-8")


def new_ask(workspace: Path) -> dict[str, Any]:
    """Create a direct ask in the workspace and return its contract."""
    (workspace / "request.txt").write_text("Build an onboarding policy checker", encoding="utf-8")
    made = invoke(workspace, "contract", "direct", "policy", "HVE creator", "request.txt")
    assert made.returncode == 0, made.stderr
    ask = json.loads(made.stdout)["ask"]
    contract: dict[str, Any] = json.loads((workspace / ".hve" / "asks" / ask / "contract.json").read_text(encoding="utf-8"))
    return contract


def test_plans_and_ticks_have_no_telemetry_option() -> None:
    """A new ask's plan lists only the evaluation option, and ticking a telemetry option is refused."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        contract = new_ask(workspace)
        plan = (workspace / contract["paths"]["plan"]).read_text(encoding="utf-8")
        assert "- [ ] opt:evaluation" in plan and "opt:telemetry" not in plan, plan
        assert "opt:telemetry" not in contract["checklist_rendered"], contract["checklist_rendered"]
        refused = invoke(workspace, "tick", "opt:telemetry", "on")
        assert refused.returncode != 0 and "not on the ask's checklist" in refused.stderr, refused.stderr


def test_agent_prompts_do_not_ask_about_telemetry() -> None:
    """No agent or persona prompt asks the user about research telemetry or records a telemetry option."""
    assert len(PROMPTS) > 40, PROMPTS
    asking = [p.name for p in PROMPTS if "opt:telemetry" in (text := p.read_text(encoding="utf-8")) or "research telemetry for this ask" in text]
    assert not asking, asking


def test_report_reminds_only_when_telemetry_recorded_the_ask() -> None:
    """The provenance report reminds the user to switch telemetry off only when it measured the ask."""
    with tempfile.TemporaryDirectory() as tmp:
        contract = new_ask(Path(tmp))
        unmeasured = "\n".join(ask_report.checklist_lines(contract, None))
        assert REMINDER not in unmeasured and "opt:evaluation: open" in unmeasured, unmeasured
        measured = {"cache_read_tokens": 900, "prompt_tokens": 1000, "share": 0.9, "turns": 2, "source": "copilot-otel.jsonl"}
        assert REMINDER in "\n".join(ask_report.checklist_lines(contract, measured))
        assert "research telemetry was off" in ask_report.load_lines(contract["skills"], None)


if __name__ == "__main__":
    test_plans_and_ticks_have_no_telemetry_option()
    test_agent_prompts_do_not_ask_about_telemetry()
    test_report_reminds_only_when_telemetry_recorded_the_ask()
    print("test_telemetry_switch: OK")
