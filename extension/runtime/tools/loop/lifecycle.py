"""Find, pick and contract delivery lifecycles (built-in, plugin or workspace overlays) and report expected against actual per stage."""

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


def active() -> tuple[Path, Json]:
    """Return the active ask's contract path and contract."""
    slug = json.loads((ASKS / "active.json").read_text(encoding="utf-8"))["active"]
    path = ask_dir(slug) / "contract.json"
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
            "current": None, "stages": stages, "decisions": [{"ts": now, "stage": s, "choice": "skipped", "why": why} for s, why in skips.items()]}
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


def report(session: str) -> str:
    """Write <ask>/provenance.md comparing each stage's expected skills and templates with what the session loaded; return it."""
    path, data = active()
    runs = WORKSPACE / ".hve" / "runs"
    loadout = runs / f"{session}.skills.json"
    used = {Path(s).name for s in json.loads(loadout.read_text(encoding="utf-8"))["used"]} if loadout.exists() else set()
    deliverables = WORKSPACE / ".hve" / "deliverables" / f"{session}.json"
    authored = {d["kind"] for d in json.loads(deliverables.read_text(encoding="utf-8"))["documents"]} if deliverables.exists() else set()
    rows = ["| Stage | Status | Agent | Skills expected → used | Templates expected → authored | Note |", "|---|---|---|---|---|---|"]
    for s in data["stages"]:
        skills = ", ".join(f"{k} {'✓' if k in used else '✗'}" for k in s["skills"]) or "-"
        templates = ", ".join(f"{t} {'✓' if t in authored else '✗'}" for t in s["templates"]) or "-"
        rows.append(f"| {s['name']} | {s['status']} | {s['agent']} | {skills} | {templates} | {s['note']} |")
    extra = sorted(used - {k for s in data["stages"] for k in s["skills"]})
    text = (f"# Provenance: {data['ask']}\n\nLifecycle `{data['lifecycle']}` ({data['source']}), agent {data['agent']}, session {session}.\n"
            f"Facts from `{loadout.as_posix()}` and `{deliverables.as_posix()}`.\n\n" + "\n".join(rows)
            + f"\n\nSkills used outside the contract: {', '.join(extra) or 'none'}.\n")
    (path.parent / "provenance.md").write_text(text, encoding="utf-8")
    return text


def main() -> None:
    """CLI: list | pick <request> | show <name> | contract <name> <slug> <agent> <request-file> [stage=why ...] | stage <name> <status> <note> | report <session>."""
    args = sys.argv[1:]
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
    elif args[:1] == ["report"] and len(args) == 2:
        print(report(args[1]))
        return
    else:
        raise SystemExit(main.__doc__)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
