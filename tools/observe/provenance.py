"""Check that the harness components an agent declares left their evidence in a workspace for one chat session."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Literal, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "templates"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "loop"))
from manage import check_session, resolve  # noqa: E402
from ask_report import facts, guard_summary  # noqa: E402
from loop_paths import loop_dir, state_file  # noqa: E402

Status = Literal["verified", "not-exercised", "failed"]
Json = dict[str, Any]
COMPONENTS = {"skills": "skill_loader.py", "profile": "profile_detector.py", "templates": "template_guard.py", "metrics": "metrics.py",
              "loop": "loop/loop.py", "reflection": "evaluation/reflection.py", "contract": "loop/lifecycle.py"}
LAYERS = {"1 contract": "contract.json", "2 rubrics": "rubric-results.json", "3 validation": "validation-results.json",
          "4 council": "council/*.json", "5 decision": "report.json"}


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
    features_file = loop_dir(project) / "feature_list.json"
    if not features_file.is_file():
        return {"status": "not-exercised", "detail": f"no feature_list.json in {loop_dir(project)}"}, False
    if not state_file(project).is_file() or not (loop_dir(project) / "progress.txt").is_file():
        return {"status": "failed", "detail": "feature_list.json exists but loop.py init never ran (loop state or progress.txt missing)"}, False
    features = json.loads(features_file.read_text(encoding="utf-8"))
    passing = sum(1 for f in features if f["passes"])
    return {"status": "verified", "detail": f"{passing}/{len(features)} features pass; progress.txt present"}, passing == len(features)


def _reflection(project: Path, finished: bool) -> Finding:
    """Return the latest output evaluation's five layers and decision, or a failure when a finished loop has none."""
    reports = sorted((project / ".hve" / "evaluations").glob("*/report.json"))
    if reports:
        folder = reports[-1].parent
        report = json.loads(reports[-1].read_text(encoding="utf-8"))
        missing = [layer for layer, pattern in LAYERS.items() if not any(folder.glob(pattern))]
        hooks = ", ".join(f"{h['id']} {'passed' if h['passed'] else 'FAILED'} ({h['detail']})" for h in report["validation"]["hooks"])
        council = ", ".join(f"{c['role']}={c['recommendation']} ({c['requestedModel']})" for c in report["council"])
        unfinished = ["the decision is revise but no revision pass followed"] if report["decision"] == "revise" else []
        return {"status": "failed" if missing or unfinished else "verified",
                "detail": f"{report['runId']}: {report['decision']}, score {report['score']}; layers missing {missing}; validation: {hooks}; "
                          f"council: {council}; {len(report['markers'])} markers" + "".join(f"; {u}" for u in unfinished)}
    return {"status": "failed" if finished else "not-exercised",
            "detail": "every feature passes but no output evaluation ran" if finished else "the feature loop did not finish"}


def _contract(workspace: Path, session: str) -> tuple[Finding, Json | None]:
    """Return whether the active ask's done stages used their expected skills and templates and its plan is in sync, with the facts."""
    if not (workspace / ".hve" / "asks" / "active.json").is_file():
        return {"status": "not-exercised", "detail": "no lifecycle contract in this workspace"}, None
    found = facts(workspace, session)
    stale = [f"{found['plan']['plan']} changed since its last sync"] if found["plan"] and found["plan"]["changed"] else []
    counts = ", ".join(f"{n} {s}" for s, n in sorted(Counter(s["status"] for s in found["stages"]).items()))
    detail = (f"{found['ask']} ({found['lifecycle']}): {counts}; gaps: {'; '.join(found['gaps']) or 'none'}; outside contract: "
              f"{', '.join(found['outside_contract']) or 'none'}; recommended skills unused: "
              f"{', '.join(found['usage']['unused_skills']) or 'none'}" + "".join(f"; {s}" for s in stale))
    return {"status": "failed" if found["gaps"] or stale else "verified", "detail": detail}, found


def _trace(runs: Path, session: str) -> Json | None:
    """Return model calls, tokens, tools and sub-agents from the session's metrics rows, or None when metrics were not collected."""
    path = runs / f"{session}.jsonl"
    if not path.is_file():
        return None
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    calls = list({r["turn_id"]: r for r in rows}.values())
    main = [c["prompt_tokens"] for c in calls if c["subagent_session"] is None]
    sub = [c["prompt_tokens"] for c in calls if c["subagent_session"]]
    tools: dict[str, int] = {}
    for r in rows:
        if r["tool_name"]:
            tools[r["tool_name"]] = tools.get(r["tool_name"], 0) + 1
    return {"model_calls": {"main": len(main), "subagent": len(sub)},
            "subagents": len({c["subagent_session"] for c in calls if c["subagent_session"]}),
            "models": sorted({c["model"] for c in calls}),
            "prompt_tokens": {"main_first": main[0] if main else 0, "main_peak": max(main, default=0),
                              "subagent_peak": max(sub, default=0), "total": sum(main) + sum(sub)},
            "completion_tokens": sum(c["completion_tokens"] for c in calls),
            "cost_aiu": round(sum(c["cost_nano_aiu"] for c in calls) / 1e9, 2),
            "cache_read_ratio": round(sum(c["cache_read_tokens"] or 0 for c in calls) / max(1, sum(main) + sum(sub)), 3),
            "tool_calls": dict(sorted(tools.items(), key=lambda t: -t[1])),
            "failed_tool_calls": sum(1 for r in rows if r["tool_name"] and r["tool_ok"] is False)}


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
    skills_used: list[str] = []
    if found["skills"]["status"] == "verified":
        loadout = json.loads(exists["skills"].read_text(encoding="utf-8"))
        # Loadouts written before `used` existed record only the last prompt's skills.
        skills_used = sorted(Path(s).name for s in loadout.get("used", loadout["skills"]))
        found["skills"]["detail"] = "loaded: " + (", ".join(skills_used) or "none matched the prompt")
    found["loop"], finished = _loop(project)
    found["reflection"] = _reflection(project, finished)
    found["contract"], contract = _contract(workspace, session)
    declared = {name: found[name] for name, marker in COMPONENTS.items() if marker in agent}
    unknown = [name for name in required if name not in declared]
    if unknown:
        raise ValueError(f"{agent_file.name} does not declare required components {unknown}; it declares {sorted(declared)}")
    interventions = runs / f"{session}.interventions.jsonl"
    ok = (all(c["status"] != "failed" for c in declared.values()) and all(declared[name]["status"] == "verified" for name in required))
    trace = _trace(runs, session)
    summary = None if trace is None else {
        "skills_used": skills_used, "subagents": trace["subagents"],
        "tokens": {"prompt": trace["prompt_tokens"]["total"], "completion": trace["completion_tokens"]},
        "cost_aiu": trace["cost_aiu"]}
    report = {"session": session, "agent": agent_file.name, "ok": ok, "summary": summary, "components": declared, "trace": trace,
              "interventions": len(interventions.read_text(encoding="utf-8").splitlines()) if interventions.is_file() else 0,
              "guards": guard_summary(workspace, session), "contract": contract}
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
