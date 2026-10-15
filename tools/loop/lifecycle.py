"""Find, pick and contract delivery lifecycles (built-in, plugin or workspace overlays) and report expected against actual per stage."""

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "skills"))
from recommend import rank, stems  # noqa: E402

WORKSPACE = Path.cwd()
ASKS = WORKSPACE / ".hve" / "asks"
SOURCES = [ROOT / "templates" / "lifecycles", *sorted(ROOT.glob("plugins/*/lifecycles")), *sorted(WORKSPACE.glob("plugins/*/lifecycles")),
           WORKSPACE / ".hve" / "lifecycles"]
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
STAGE_FIELDS = {"name", "goal", "agent", "skills", "plugin_skills", "templates", "exit", "skip_when"}
Status = Literal["planned", "active", "done", "skipped"]

Json = dict[str, Any]


def validate(lifecycle: Json, source: Path) -> Json:
    """Return the lifecycle after checking its fields and stages, or raise naming the file."""
    missing = {"name", "title", "summary", "fits", "stages"} - set(lifecycle)
    if missing or not lifecycle["stages"]:
        raise ValueError(f"{source}: lifecycle needs name, title, summary, fits and non-empty stages; missing {sorted(missing)}")
    for stage in lifecycle["stages"]:
        if not STAGE_FIELDS <= set(stage):
            raise ValueError(f"{source}: stage {stage.get('name')!r} needs {sorted(STAGE_FIELDS - set(stage))}")
    return lifecycle | {"source": source.as_posix()}


def catalog() -> dict[str, Json]:
    """Return every lifecycle by name; a later source (plugin, then workspace) overrides an earlier one of the same name."""
    found: dict[str, Json] = {}
    for folder in SOURCES:
        for path in sorted(folder.glob("*.json")):
            lifecycle = validate(json.loads(path.read_text(encoding="utf-8")), path)
            found[lifecycle["name"]] = lifecycle | ({"overrides": found[lifecycle["name"]]["source"]} if lifecycle["name"] in found else {})
    return found


def pick(request: str) -> list[Json]:
    """Return lifecycles ranked by the request words they fit, with the matched words as the reason."""
    words = stems(request)
    ranked = [{"name": c["name"], "title": c["title"], "summary": c["summary"], "source": c["source"],
               "matched": sorted(words & stems(" ".join(c["fits"])))} for c in catalog().values()]
    return sorted(ranked, key=lambda r: -len(r["matched"]))


def ask_dir(slug: str) -> Path:
    """Return the folder of an ask after checking its slug."""
    if not SLUG.match(slug):
        raise ValueError(f"slug {slug!r} must match {SLUG.pattern}")
    return ASKS / slug


def active(workspace: Path = WORKSPACE) -> tuple[Path, Json]:
    """Return the active ask's contract path and contract."""
    asks = workspace / ".hve" / "asks"
    slug = json.loads((asks / "active.json").read_text(encoding="utf-8"))["active"]
    if not SLUG.match(slug):
        raise ValueError(f"slug {slug!r} must match {SLUG.pattern}")
    path = asks / slug / "contract.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def contract(name: str, slug: str, agent: str, request: str, skips: dict[str, str]) -> Json:
    """Write the ask's contract from a lifecycle (skipped stages keep their one-line reason) and make it the active ask."""
    lifecycle = catalog()[name]
    unknown = set(skips) - {s["name"] for s in lifecycle["stages"]}
    if unknown:
        raise ValueError(f"cannot skip unknown stages {sorted(unknown)} of lifecycle {name!r}")
    for stage in lifecycle["stages"]:
        if stage["skills"] and stage["name"] not in skips:
            rank(request, "provisional", tuple(stage["skills"]))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stages = [{k: s[k] for k in ("name", "goal", "agent", "skills", "plugin_skills", "templates", "exit")}
              | {"status": "skipped" if s["name"] in skips else "planned", "note": skips.get(s["name"], "")} for s in lifecycle["stages"]]
    data = {"ask": slug, "request": request, "lifecycle": name, "source": lifecycle["source"], "agent": agent, "created": now,
            "current": None, "stages": stages, "plan": {"sha256": None, "revisions": []},
            "decisions": [{"ts": now, "stage": s, "choice": "skipped", "why": why} for s, why in skips.items()]}
    folder = ask_dir(slug)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "contract.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (ASKS / "active.json").write_text(json.dumps({"active": slug}), encoding="utf-8")
    return data


def set_stage(stage: str, status: Status, note: str) -> Json:
    """Record a stage's status with a one-line note in the active contract; an active stage becomes current."""
    path, data = active()
    match = next((s for s in data["stages"] if s["name"] == stage), None)
    if match is None:
        raise ValueError(f"stage {stage!r} is not in the contract: {[s['name'] for s in data['stages']]}")
    match |= {"status": status, "note": note}
    if status == "active":
        data["current"] = stage
    data["decisions"].append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stage": stage, "choice": status, "why": note})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return match


def current_skills() -> list[str]:
    """Return the library skills of the active ask's current stage, or none when no ask or stage is active."""
    if not (ASKS / "active.json").exists():
        return []
    data = active()[1]
    return next((s["skills"] for s in data["stages"] if s["name"] == data["current"]), [])


def plan_hash(contract_path: Path) -> str | None:
    """Return the SHA-256 of the ask's plan.md, or None before the plan is written."""
    plan = contract_path.parent / "plan.md"
    return hashlib.sha256(plan.read_bytes()).hexdigest() if plan.is_file() else None


def plan_sync(note: str) -> Json:
    """Record the current plan.md as a new plan revision with a one-line note of what changed."""
    path, data = active()
    digest = plan_hash(path)
    if digest is None:
        raise FileNotFoundError(f"{path.parent / 'plan.md'} does not exist: write the plan first")
    data["plan"]["sha256"] = digest
    data["plan"]["revisions"].append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sha256": digest, "note": note})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"revision": len(data["plan"]["revisions"]), "note": note}


def plan_status(workspace: Path = WORKSPACE) -> Json | None:
    """Return whether the active ask's plan.md changed since its last sync, or None when there is no active ask or plan."""
    if not (workspace / ".hve" / "asks" / "active.json").is_file():
        return None
    path, data = active(workspace)
    digest = plan_hash(path)
    if digest is None:
        return None
    return {"plan": (path.parent / "plan.md").relative_to(workspace).as_posix(), "changed": digest != data["plan"]["sha256"],
            "revisions": len(data["plan"]["revisions"])}


def guard_summary(workspace: Path, session: str) -> Json:
    """Return the session's guard trips per hook and kind, waiver answers, and guards laid down, from the intervention and waiver logs."""
    runs = workspace / ".hve" / "runs"
    log = runs / f"{session}.interventions.jsonl"
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []
    trips: dict[str, int] = {}
    for e in entries:
        if e["kind"] not in ("waived", "waiver_answer"):
            trips[f"{e['hook']}/{e['kind']}"] = trips.get(f"{e['hook']}/{e['kind']}", 0) + 1
    waivers = runs / f"{session}.waivers.json"
    return {"trips": trips, "waiver_answers": [f"{e['hook']}: {e['detail']}" for e in entries if e["kind"] == "waiver_answer"],
            "waived_calls": sum(e["kind"] == "waived" for e in entries),
            "laid_down": sorted(h for h, v in json.loads(waivers.read_text(encoding="utf-8")).items() if v) if waivers.is_file() else []}


def facts(workspace: Path, session: str) -> Json:
    """Return the active contract against the session's facts: skills used, templates authored, gaps of done stages, plan sync and guards."""
    path, data = active(workspace)
    runs = workspace / ".hve" / "runs"
    loadout = runs / f"{session}.skills.json"
    used = {Path(s).name for s in json.loads(loadout.read_text(encoding="utf-8"))["used"]} if loadout.is_file() else set()
    deliverables = workspace / ".hve" / "deliverables" / f"{session}.json"
    authored = {d["kind"] for d in json.loads(deliverables.read_text(encoding="utf-8"))["documents"]} if deliverables.is_file() else set()
    stages = [{"name": s["name"], "status": s["status"], "agent": s["agent"], "note": s["note"],
               "skills": {k: k in used for k in s["skills"]}, "templates": {t: t in authored for t in s["templates"]}} for s in data["stages"]]
    gaps = [f"{s['name']}: {kind} {item} expected but not {verb}" for s in stages if s["status"] == "done"
            for kind, verb in (("skills", "used"), ("templates", "authored")) for item, ok in s[kind].items() if not ok]
    status = plan_status(workspace)
    return {"ask": data["ask"], "lifecycle": data["lifecycle"], "source": data["source"], "agent": data["agent"], "session": session,
            "evidence": [p.relative_to(workspace).as_posix() for p in (path, loadout, deliverables) if p.is_file()],
            "plan": status, "stages": stages, "gaps": gaps,
            "outside_contract": sorted(used - {k for s in data["stages"] for k in s["skills"]}),
            "decisions": data["decisions"], "guards": guard_summary(workspace, session)}


def report(session: str) -> str:
    """Write <ask>/provenance.md: each stage's expected against used skills and authored templates, plan sync, decisions and guards."""
    path = active()[0]
    f = facts(WORKSPACE, session)
    mark = {True: "✓", False: "✗"}
    rows = ["| Stage | Status | Agent | Skills expected → used | Templates expected → authored | Note |", "|---|---|---|---|---|---|"]
    for s in f["stages"]:
        skills = ", ".join(f"{k} {mark[v]}" for k, v in s["skills"].items()) or "-"
        templates = ", ".join(f"{t} {mark[v]}" for t, v in s["templates"].items()) or "-"
        rows.append(f"| {s['name']} | {s['status']} | {s['agent']} | {skills} | {templates} | {s['note']} |")
    plan = f["plan"]
    plan_line = "no plan.md" if plan is None else f"{plan['revisions']} revision(s), {'CHANGED since last sync' if plan['changed'] else 'in sync'}"
    guards = f["guards"]
    trips = ", ".join(f"{k} ×{n}" for k, n in guards["trips"].items()) or "none"
    text = (f"# Provenance: {f['ask']}\n\nLifecycle `{f['lifecycle']}` ({f['source']}), agent {f['agent']}, session {session}.\n"
            f"Facts from: {', '.join(f['evidence'])}.\n\n" + "\n".join(rows)
            + f"\n\n- Gaps in done stages: {'; '.join(f['gaps']) or 'none'}.\n"
            f"- Skills used outside the contract: {', '.join(f['outside_contract']) or 'none'}.\n"
            f"- Plan: {plan_line}.\n"
            f"- Guards: trips {trips}; laid down {', '.join(guards['laid_down']) or 'none'} ({guards['waived_calls']} call(s) let through); "
            f"answers {'; '.join(guards['waiver_answers']) or 'none'}.\n"
            "\n## Decisions\n\n" + "\n".join(f"- {d['ts']} {d['stage']}: {d['choice']} — {d['why']}" for d in f["decisions"]) + "\n")
    (path.parent / "provenance.md").write_text(text, encoding="utf-8")
    return text


def main() -> None:
    """CLI: list | pick <request> | show <name> | contract <name> <slug> <agent> <request-file> [stage=why ...] | stage <name> <status> <note> | plan-sync <note> | plan-status | report <session>."""
    args = sys.argv[1:]
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # Windows pipes default to cp1252
    if args[:1] == ["list"]:
        out: Any = [{k: c[k] for k in ("name", "title", "summary", "source")} for c in catalog().values()]
    elif args[:1] == ["pick"] and len(args) == 2:
        out = pick(args[1])
    elif args[:1] == ["show"] and len(args) == 2:
        out = catalog()[args[1]]
    elif args[:1] == ["contract"] and len(args) >= 5:
        skips = dict(a.split("=", 1) for a in args[5:])
        out = contract(args[1], args[2], args[3], Path(args[4]).read_text(encoding="utf-8").strip(), skips)
    elif args[:1] == ["stage"] and len(args) == 4 and args[2] in ("planned", "active", "done", "skipped"):
        out = set_stage(args[1], args[2], args[3])  # type: ignore[arg-type]
    elif args[:1] == ["plan-sync"] and len(args) == 2:
        out = plan_sync(args[1])
    elif args[:1] == ["plan-status"] and len(args) == 1:
        out = plan_status()
    elif args[:1] == ["report"] and len(args) == 2:
        print(report(args[1]))
        return
    else:
        raise SystemExit(main.__doc__)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
