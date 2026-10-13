"""Check that the harness components an agent declares left their evidence in a workspace for one chat session."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "templates"))
from manage import check_session, resolve  # noqa: E402

Status = Literal["verified", "not-exercised", "failed"]
Json = dict[str, Any]
COMPONENTS = {"skills": "skill_loader.py", "profile": "profile_detector.py", "templates": "template_guard.py", "metrics": "metrics.py",
              "loop": "loop/loop.py", "reflection": "evaluation/reflection.py"}


class Finding(TypedDict):
    """Evidence status of one harness component."""

    status: Status
    detail: str


def latest_session(workspace: Path) -> str:
    """Return the id of the newest session with a skill loadout or hook event log in the workspace."""
    logs = sorted([*(workspace / ".hve" / "runs").glob("*.skills.json"), *(workspace / ".hve" / "runs").glob("*.events.jsonl")],
                  key=lambda p: p.stat().st_mtime)
    if not logs:
        raise FileNotFoundError(f"no session logs in {workspace / '.hve' / 'runs'}: no harness hook has run in this workspace")
    return logs[-1].name.split(".")[0]


def _templates(workspace: Path, session: str) -> Finding:
    """Return whether requested deliverables were created from their configured templates and validate."""
    registry = workspace / ".hve" / "deliverables" / f"{session}.json"
    if not registry.is_file():
        return {"status": "not-exercised", "detail": "no deliverable was requested in this session"}
    errors = check_session(workspace, session)
    if errors:
        return {"status": "failed", "detail": "; ".join(errors)}
    documents = json.loads(registry.read_text(encoding="utf-8"))["documents"]
    used = [f"{d['kind']}/{d['slug']} from {resolve(workspace, d['kind'])[0]['source']}" for d in documents]
    return {"status": "verified", "detail": "; ".join(used)}


def _loop(project: Path) -> tuple[Finding, bool]:
    """Return whether the feature loop was initialized with how many features pass, and whether every feature passes."""
    features_file = project / "feature_list.json"
    if not features_file.is_file():
        return {"status": "not-exercised", "detail": f"no feature_list.json in {project}"}, False
    if not (project / ".harness").is_dir():
        return {"status": "failed", "detail": "feature_list.json exists but loop.py init never ran (.harness/ missing)"}, False
    features = json.loads(features_file.read_text(encoding="utf-8"))
    passing = sum(1 for f in features if f["passes"])
    return {"status": "verified", "detail": f"{passing}/{len(features)} features pass"}, passing == len(features)


def _reflection(project: Path, finished: bool) -> Finding:
    """Return the latest output evaluation decision, or a failure when a finished loop has none."""
    reports = sorted((project / ".hve" / "evaluations").glob("*/report.json"))
    if reports:
        report = json.loads(reports[-1].read_text(encoding="utf-8"))
        return {"status": "verified", "detail": f"{report['runId']}: {report['decision']} (score {report['score']})"}
    return {"status": "failed" if finished else "not-exercised",
            "detail": "every feature passes but no output evaluation ran" if finished else "the feature loop did not finish"}


def provenance(agent_file: Path, workspace: Path, project: Path, session: str, required: list[str]) -> Json:
    """Return and save to .hve/runs/<session>.provenance.json each declared component's evidence status and whether all is ok."""
    agent = agent_file.read_text(encoding="utf-8")
    runs = workspace / ".hve" / "runs"
    found: dict[str, Finding] = {}
    exists = {"skills": runs / f"{session}.skills.json", "profile": workspace / ".hve" / "user_profile.json",
              "metrics": runs / f"{session}.events.jsonl"}
    for name, path in exists.items():
        relative = path.relative_to(workspace).as_posix()
        found[name] = ({"status": "verified", "detail": relative} if path.is_file()
                       else {"status": "failed", "detail": f"{relative} missing: the {COMPONENTS[name]} hook did not run"})
    found["templates"] = _templates(workspace, session)
    found["loop"], finished = _loop(project)
    found["reflection"] = _reflection(project, finished)
    declared = {name: found[name] for name, marker in COMPONENTS.items() if marker in agent}
    unknown = [name for name in required if name not in declared]
    if unknown:
        raise ValueError(f"{agent_file.name} does not declare required components {unknown}; it declares {sorted(declared)}")
    interventions = runs / f"{session}.interventions.jsonl"
    ok = (all(c["status"] != "failed" for c in declared.values()) and all(declared[name]["status"] == "verified" for name in required))
    report = {"session": session, "agent": agent_file.name, "ok": ok, "components": declared,
              "interventions": len(interventions.read_text(encoding="utf-8").splitlines()) if interventions.is_file() else 0}
    (runs / f"{session}.provenance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    """Print the provenance report of one session and exit 1 unless it is ok."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent_file", type=Path, help="the agent's .agent.md file (rendered or template)")
    parser.add_argument("session", help="chat session id, or 'latest' for the newest session logged in the workspace")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="workspace root where hooks write .hve/ (default: cwd)")
    parser.add_argument("--project", type=Path, help="folder the feature loop ran in (default: the workspace)")
    parser.add_argument("--require", nargs="*", default=[], choices=sorted(COMPONENTS), help="components that must be verified")
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    session = latest_session(workspace) if args.session == "latest" else args.session
    report = provenance(args.agent_file, workspace, (args.project or workspace).resolve(), session, args.require)
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
