"""The workspace's project across asks: its record, what it is about, topic shifts, and the stage ledger of what every ask did."""

import json
import re
from pathlib import Path
from typing import Any

from loop_paths import project_folder
from lifecycle_catalog import catalog, pick
from recommend import stems

WORKSPACE = Path.cwd()
CREATE = re.compile(r"^\s*(?:please\s+|(?:can|could|would)\s+you\s+)?(build|creat\w*|develop\w*|make|writ\w*|draft\w*|design\w*|"
                    r"generat\w*|prepar\w*|start\w*)\b", re.I)
SHIFT_MIN_WORDS = 3
SHIFT_OVERLAP = 0.2
SCOPE_NOTE = "outside this ask's scope"

Json = dict[str, Any]


def deliverable(text: str) -> str | None:
    """Return the lifecycle (kind of deliverable) whose fit words the text matches most, or None when none match."""
    ranked = [p for p in pick(text) if p["matched"] and p["name"] != "direct"]
    return ranked[0]["name"] if ranked else None


def subject(text: str) -> set[str]:
    """Return the text's word stems without creation verbs and lifecycle fit words (app, report, deck), leaving what the work is about."""
    generic = stems(" ".join(f for c in catalog().values() for f in c["fits"]) + " build create develop make write draft design generate "
                    "prepare start formal new simple")
    return stems(text) - generic


def overlap(previous: str, prompt: str) -> float:
    """Return the share of the prompt's subject words that also appear in the previous text (1.0 for a prompt without subject words)."""
    new = subject(prompt)
    return len(new & subject(previous)) / len(new) if new else 1.0


def topic_shift(previous: str, prompt: str) -> Json | None:
    """Return a new-workspace recommendation when a prompt starts a different project from the workspace's one (a different kind of
    deliverable, or new work sharing little with it); None for work on the same project."""
    share = overlap(previous, prompt)
    kinds = (deliverable(previous), deliverable(prompt))
    if None not in kinds and kinds[0] != kinds[1] and share < SHIFT_OVERLAP:
        return {"recommend": "new-workspace", "overlap": round(share, 2), "kinds": list(kinds),
                "reason": f"this is {kinds[1]} work and this workspace's project is {kinds[0]} work: their files, skills and checks belong apart"}
    if CREATE.match(prompt) and len(subject(prompt)) >= SHIFT_MIN_WORDS and share < SHIFT_OVERLAP:
        return {"recommend": "new-workspace", "overlap": round(share, 2), "kinds": list(kinds),
                "reason": "this starts a different project from the one in this workspace; one workspace holds one project"}
    return None


def shift_message(shift: Json, ask: str) -> str:
    """Return the one-line recommendation to show the user for a prompt that starts a different project."""
    return (f"Frontier HVE: this looks like a different project from this workspace's (open ask {ask}); {shift['reason']}. Recommended: "
            "open another folder (or a git worktree) in a new window. You can also stay: the agent then opens a new ask here and records it.")


def project_status(workspace: Path = WORKSPACE) -> Json | None:
    """Return the workspace's project (name, goal, asks) with its feature count, passing count and whether the loop needs init or amend."""
    folder = project_folder(workspace)
    if not (folder / "project.json").is_file():
        return None
    features = json.loads((folder / "feature_list.json").read_text(encoding="utf-8")) if (folder / "feature_list.json").is_file() else []
    return json.loads((folder / "project.json").read_text(encoding="utf-8")) | {
        "feature_list": (folder / "feature_list.json").relative_to(workspace).as_posix(), "features": len(features),
        "passing": sum(f["passes"] for f in features), "loop": "amend" if (folder / "state.json").is_file() else "init"}


def project_text(workspace: Path = WORKSPACE) -> str:
    """Return what the workspace's project is about: its goal, every ask's request and its feature names."""
    project = project_status(workspace)
    if project is None:
        raise FileNotFoundError(f"{project_folder(workspace) / 'project.json'} missing: no ask has opened a project in this workspace")
    requests = [json.loads((workspace / ".hve" / "asks" / a / "contract.json").read_text(encoding="utf-8"))["request"] for a in project["asks"]]
    folder = project_folder(workspace)
    names = [f["name"] for f in json.loads((folder / "feature_list.json").read_text(encoding="utf-8"))] \
        if (folder / "feature_list.json").is_file() else []
    return " ".join([project["goal"], *requests, *names])


def record_project(slug: str, request: str, ask: str, now: str, workspace: Path = WORKSPACE) -> None:
    """Add the ask to the workspace's project, starting the project from the first ask's request."""
    path = project_folder(workspace) / "project.json"
    project = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
        "name": slug, "goal": request, "kind": deliverable(request), "created": now, "asks": []}
    project["asks"].append(ask)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project, indent=2), encoding="utf-8")


def ledger(lifecycle: str, workspace: Path = WORKSPACE) -> Json:
    """Return the project's stage ledger for a lifecycle: per stage, every ask that worked on it (directly, or through another lifecycle
    run for that stage) with its status, persona and note, plus the stages no ask has done yet."""
    stages = [s["name"] for s in catalog()[lifecycle]["stages"]]
    project = project_status(workspace)
    rows: dict[str, list[Json]] = {s: [] for s in stages}
    asks = []
    for ask in project["asks"] if project else []:
        data = json.loads((workspace / ".hve" / "asks" / ask / "contract.json").read_text(encoding="utf-8"))
        asks.append({k: data.get(k) for k in ("ask", "lifecycle", "agent", "created", "scope", "for_stage")})
        target = data.get("for_stage")
        if target and target.split(":", 1)[0] == lifecycle:
            worked = [s for s in data["stages"] if s["status"] != "skipped"]
            status = "done" if worked and all(s["status"] == "done" for s in worked) else "active" if any(
                s["status"] in ("active", "done") for s in worked) else "planned"
            rows[target.split(":", 1)[1]].append({"ask": data["ask"], "status": status, "via": data["lifecycle"], "persona": data["agent"],
                                                  "note": f"{len(worked)} stages of {data['lifecycle']}", "created": data["created"]})
        elif data["lifecycle"] == lifecycle:
            for s in data["stages"]:
                if s["status"] != "skipped" or not s["note"].startswith(SCOPE_NOTE):
                    rows[s["name"]].append({"ask": data["ask"], "status": s["status"], "persona": s["agent"], "note": s["note"],
                                            "created": data["created"]})
    latest = {s: (r[-1]["status"] if r else "not started") for s, r in rows.items()}
    return {"project": project["name"] if project else None, "lifecycle": lifecycle, "asks": asks, "stages": rows, "latest": latest,
            "open": [s for s in stages if latest[s] not in ("done", "skipped")]}
