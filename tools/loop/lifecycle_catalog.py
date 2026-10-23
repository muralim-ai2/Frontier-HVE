"""Find and pick delivery lifecycles: built-in, repository plugin folders, the workspace's overlays, and expertise packs routed by request."""

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "skills"))
sys.path.insert(0, str(ROOT / "tools" / "plugins"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recommend import stems  # noqa: E402
from stage_evidence import validate_stage  # noqa: E402
import store  # noqa: E402
from route import candidates  # noqa: E402

WORKSPACE = Path.cwd()
SOURCES = [ROOT / "templates" / "lifecycles", *sorted(ROOT.glob("plugins/*/lifecycles")),
           *sorted(p for p in WORKSPACE.glob("plugins/*/lifecycles") if not (p.parent / "hve-plugin.json").is_file()),
           WORKSPACE / ".hve" / "lifecycles"]
STAGE_FIELDS = {"name", "goal", "agent", "skills", "plugin_skills", "templates", "exit", "skip_when"}
OPTIONAL_STAGE_FIELDS = {"evidence", "rework"}

Json = dict[str, Any]


def validate(lifecycle: Json, source: str) -> Json:
    """Return the lifecycle after checking its fields, stages, optional stage evidence and rework steps, or raise naming the source."""
    missing = {"name", "title", "summary", "fits", "stages"} - set(lifecycle)
    if missing or not lifecycle["stages"]:
        raise ValueError(f"{source}: lifecycle needs name, title, summary, fits and non-empty stages; missing {sorted(missing)}")
    earlier: list[str] = []
    for stage in lifecycle["stages"]:
        if not STAGE_FIELDS <= set(stage):
            raise ValueError(f"{source}: stage {stage.get('name')!r} needs {sorted(STAGE_FIELDS - set(stage))}")
        extra = set(stage) - STAGE_FIELDS - OPTIONAL_STAGE_FIELDS
        if extra:
            raise ValueError(f"{source}: stage {stage['name']!r} has unknown fields {sorted(extra)}")
        validate_stage(stage, earlier, source)
        earlier.append(stage["name"])
    return lifecycle | {"source": source}


def catalog() -> dict[str, Json]:
    """Return every lifecycle by name: built-in, plugin folders and workspace overlays (a later one overrides the same name), then the
    lifecycles of every available expertise pack as '<pack>:<name>'."""
    found: dict[str, Json] = {}
    for folder in SOURCES:
        for path in sorted(folder.glob("*.json")):
            lifecycle = validate(json.loads(path.read_text(encoding="utf-8")), path.as_posix())
            found[lifecycle["name"]] = lifecycle | ({"overrides": found[lifecycle["name"]]["source"]} if lifecycle["name"] in found else {})
    for name, entry in store.packs(WORKSPACE).items():
        for lifecycle in entry["manifest"]["lifecycles"].values():
            found[lifecycle["name"]] = lifecycle | {"pack": name}
    return found


def pick(request: str, first: tuple[str, ...] = ()) -> list[Json]:
    """Return lifecycles ranked by the request words they fit (the matched words are the reason); lifecycles of the packs in first lead."""
    words = stems(request)
    ranked = [{"name": c["name"], "title": c["title"], "summary": c["summary"], "source": c["source"], "pack": c.get("pack"),
               "matched": sorted(words & stems(" ".join(c["fits"])))} for c in catalog().values()]
    return sorted(ranked, key=lambda r: (r["pack"] not in first, -len(r["matched"])))


def route(request: str) -> Json:
    """Return the expertise packs for a request (named, named but missing, matched with why) and the lifecycles, matched packs' first."""
    packs = store.packs(WORKSPACE)
    found = candidates(request, WORKSPACE, packs)
    lead = tuple(dict.fromkeys([*found["explicit"], *(m["name"] for m in found["matched"])]))
    return {"packs": found, "lifecycles": pick(request, lead)}
