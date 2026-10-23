"""Tests of the persona catalog, the team-delivery lifecycle, Collab's scoped asks with the project stage ledger, and Auto's ticked gates."""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools" / "loop"))
sys.path.insert(0, str(REPO / "tools" / "skills"))

import personas  # noqa: E402
from lifecycle_catalog import catalog  # noqa: E402

NAME = re.compile(r"^name: (.+)$", re.M)


def run(ws: Path, *args: str) -> str:
    """Run lifecycle.py in a workspace and return its output, failing with its error."""
    done = subprocess.run([sys.executable, str(REPO / "tools" / "loop" / "lifecycle.py"), *args], cwd=ws, capture_output=True, text=True,
                          encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_catalog_renders_every_persona_and_lifecycles_name_real_agents() -> None:
    """18 personas (16 rendered, 2 existing) are current in extension/agents with plain descriptions, and every built-in lifecycle stage
    names an agent that exists."""
    found = personas.load()
    assert len(found) == 18 and sum(p["kind"] == "existing" for p in found) == 2
    assert personas.stale() == [], "run extension/build.py (or personas.py render) after editing the catalog"
    agents = {NAME.search(p.read_text(encoding="utf-8"))[1].strip() for p in (REPO / "extension" / "agents").glob("*.agent.md")}
    assert {p["agent"] for p in found} <= agents
    for lifecycle in (c for c in catalog().values() if "pack" not in c):
        for stage in lifecycle["stages"]:
            assert stage["agent"] == "self" or stage["agent"] in agents, (lifecycle["name"], stage["name"], stage["agent"])
    team = catalog()["team-delivery"]["stages"]
    assert [s["name"] for s in team if s.get("loop")] == ["data-build", "build", "ui-build", "test", "devops"]
    assert personas.match("design the oracle database schema and migration")[0]["id"] == "db-architect"
    reviewer = (REPO / "extension" / "agents" / "hve-security-reviewer.agent.md").read_text(encoding="utf-8")
    assert "user-invocable: false" in reviewer and "review.md" in reviewer and "Generated from templates/personas/catalog.json" in reviewer


def test_collab_scoped_asks_pack_stage_and_ledger() -> None:
    """A Collab visit runs only its stages, a pack lifecycle can deliver a stage of team-delivery, briefs name the persona's role, and the
    ledger shows every stage across both asks."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / ".hve" / "runs").mkdir(parents=True)
        shutil.copytree(REPO / "examples" / "plugins" / "oracle-offering", ws / "plugins" / "oracle-offering")
        (ws / "req.md").write_text("Design the data model for the leave portal", encoding="utf-8")
        first = json.loads(run(ws, "contract", "team-delivery", "data-model", "Frontier HVE Collab", "req.md", "only=data-architecture"))
        assert first["scope"] == ["data-architecture"] and first["for_stage"] is None
        assert [s["name"] for s in first["stages"] if s["status"] != "skipped"] == ["data-architecture"]
        assert "Your role: database architect." in run(ws, "brief", "HVE db-architect", "stage=data-architecture")
        run(ws, "stage", "data-architecture", "done", "model accepted")
        (ws / "req.md").write_text("Migrate the Oracle database schema and data for the leave portal", encoding="utf-8")
        second = json.loads(run(ws, "contract", "oracle-offering:oracle-migration", "ora-build", "Frontier HVE Collab", "req.md",
                                "for=team-delivery:data-build", "@oracle-offering"))
        assert second["for_stage"] == "team-delivery:data-build" and [p["name"] for p in second["packs"]] == ["oracle-offering"]
        ledger = json.loads(run(ws, "ledger"))
        assert ledger["latest"]["data-architecture"] == "done" and ledger["latest"]["requirements"] == "not started"
        assert ledger["stages"]["data-build"][0]["via"] == "oracle-offering:oracle-migration" and len(ledger["asks"]) == 2
        assert "data-architecture" not in ledger["open"] and "data-build" in ledger["open"]
        bad = subprocess.run([sys.executable, str(REPO / "tools" / "loop" / "lifecycle.py"), "contract", "team-delivery", "x", "Frontier HVE Collab",
                              "req.md", "only=no-such-stage"], cwd=ws, capture_output=True, text=True)
        assert bad.returncode != 0 and "unknown stages" in bad.stderr


def test_auto_pauses_only_at_ticked_gates() -> None:
    """With gates=ticked the checklist gets a gate per milestone that the user ticks in the form or plan.md; without it there are none."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / ".hve" / "runs").mkdir(parents=True)
        (ws / "req.md").write_text("Build a leave request service", encoding="utf-8")
        data = json.loads(run(ws, "contract", "sdlc", "leave", "Frontier HVE Auto", "req.md", "gates=ticked", "test=feature checks cover it"))
        assert data["gates"] == "ticked" and next(s for s in data["stages"] if s["name"] == "design")["agent"] == "HVE solution-architect"
        items = json.loads(run(ws, "checklist"))["items"]
        assert {"gate:design", "gate:build", "gate:release"} <= set(items) and "gate:test" not in items
        run(ws, "tick", "gate:design", "on", "review the architecture")
        plan = (Path(ws) / data["paths"]["plan"]).read_text(encoding="utf-8")
        assert "- [x] gate:design" in plan and "- [ ] gate:build" in plan and "Pause for my review after" in plan
        (ws / "req.md").write_text("Build a second service", encoding="utf-8")
        plain = json.loads(run(ws, "contract", "sdlc", "second", "Frontier HVE Auto", "req.md"))
        assert plain["gates"] == "all" and not [i for i in json.loads(run(ws, "checklist"))["items"] if i.startswith("gate:")]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
