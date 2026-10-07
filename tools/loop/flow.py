"""State machine of the creator-flow graph workflow: a stage moves on only along a drawn edge, with deterministic evidence, and capped loops."""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools" / "git"), str(ROOT / "hooks")]
from branch_workflow import read_json, write_json  # noqa: E402
from loop import TRIVIAL_VERIFY, run_check  # noqa: E402
from no_fallback import scan_file  # noqa: E402

EDGES = {
    "shape-defined": ("designer", "prototyper"),
    "direction-invalidated": ("prototyper", "designer"),
    "concept-validated": ("prototyper", "builder"),
    "build-complete": ("builder", "architect"),
    "rework-required": ("architect", "builder"),
    "structurally-sound": ("architect", "sweeper"),
    "cleaned-and-optimized": ("sweeper", "grower"),
    "roadmap-aligned": ("grower", "maintainer"),
    "new-opportunity-found": ("maintainer", "grower"),
    "healthy-at-rest": ("maintainer", "done"),
}
BACK_EDGES = ("direction-invalidated", "rework-required", "new-opportunity-found")
BACK_EDGE_CAP = 2
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".scss", ".html", ".vue", ".svelte"}
SKIP_DIRS = {"node_modules", ".next", ".git", ".harness", ".worktrees", "dist", "build", "coverage"}
MAX_FILE_LINES = 500
Profile = Literal["benchmark", "product"]

Json = dict[str, Any]


def flow_file(project: Path) -> Path:
    """Return the flow state path."""
    return project / ".harness" / "flow.json"


def init(project: Path, profile: Profile) -> Json:
    """Start the flow at the designer stage; benchmark runs give Grower one pass (no new-opportunity loop)."""
    if flow_file(project).exists():
        raise FileExistsError(f"{flow_file(project)} exists")
    caps = {e: BACK_EDGE_CAP for e in BACK_EDGES} | ({"new-opportunity-found": 0} if profile == "benchmark" else {})
    state = {"profile": profile, "stage": "designer", "caps": caps, "taken": {e: 0 for e in BACK_EDGES}, "history": [],
             "code_lines_at_sweep": None, "escalated": None, "help": None}
    write_json(flow_file(project), state)
    return state


def code_files(project: Path) -> dict[Path, int]:
    """Return line counts of the project's source files, skipping dependency, build and state folders."""
    counts = {}
    for folder, dirs, names in os.walk(project):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            path = Path(folder) / name
            if path.suffix.lower() in CODE_SUFFIXES:
                counts[path] = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return counts


def design(project: Path) -> Json:
    """Return design.json after checking its fields: screens, acceptance criteria, and non-trivial prototype and lint checks."""
    data = read_json(project / "design.json")
    if not (isinstance(data.get("screens"), list) and data["screens"] and isinstance(data.get("acceptance"), list) and data["acceptance"]):
        raise ValueError("design.json needs non-empty 'screens' and 'acceptance' lists")
    for key in ("prototype_check", "lint_check"):
        if not isinstance(data.get(key), str) or TRIVIAL_VERIFY.match(data[key]):
            raise ValueError(f"design.json needs a real {key!r} command")
    return data


def feature_checks_fail(project: Path) -> list[str]:
    """Return the features that are not marked passing or whose check fails now."""
    state = read_json(project / ".harness" / "state.json")
    features = read_json(project / "feature_list.json")
    return [f["name"] for f in features if not f["passes"] or run_check(state["lock"][f["name"]]["verify"], project)[0] != 0]


def structure_problems(project: Path) -> list[str]:
    """Return files over the size limit and no-fallback (B1) findings in the working tree."""
    problems = []
    for path, lines in code_files(project).items():
        if lines > MAX_FILE_LINES:
            problems.append(f"{path.relative_to(project).as_posix()}: {lines} lines")
        problems += scan_file(path.relative_to(project).as_posix(), path.read_text(encoding="utf-8", errors="replace"))
    return problems


def evidence(project: Path, edge: str, state: Json) -> list[str]:
    """Return what is missing for an edge; an empty list means the edge's evidence holds."""
    if edge == "shape-defined":
        design(project)
        return []
    if edge == "concept-validated":
        code, output = run_check(design(project)["prototype_check"], project)
        return [] if code == 0 else [f"prototype_check exited {code}: {output[-400:]}"]
    if edge == "build-complete":
        if not (project / ".harness" / "state.json").exists():
            return ["the feature loop was never initialized"]
        failing = feature_checks_fail(project)
        return [f"features failing: {failing}"] if failing else []
    if edge == "structurally-sound":
        return structure_problems(project)
    if edge == "cleaned-and-optimized":
        code, output = run_check(design(project)["lint_check"], project)
        missing = [] if code == 0 else [f"lint_check exited {code}: {output[-400:]}"]
        lines = sum(code_files(project).values())
        missing += [f"code grew from {state['code_lines_at_sweep']} to {lines} lines"] if lines > state["code_lines_at_sweep"] else []
        failing = feature_checks_fail(project)
        return missing + ([f"features failing after cleanup: {failing}"] if failing else [])
    if edge == "roadmap-aligned":
        roadmap = read_json(project / "roadmap.json")
        names = {f["name"] for f in read_json(project / "feature_list.json")}
        if not isinstance(roadmap, list):
            return ["roadmap.json must be a list of {opportunity, feature}"]
        return [f"opportunity {r.get('opportunity')!r} is not linked to a feature in feature_list.json" for r in roadmap
                if not isinstance(r, dict) or r.get("feature") not in names]
    if edge == "healthy-at-rest":
        code, output = run_check(design(project)["lint_check"], project)
        failing = feature_checks_fail(project)
        return (([f"lint_check exited {code}"] if code else []) + ([f"features failing: {failing}"] if failing else [])
                + [p for p in structure_problems(project) if "lines" in p])
    return []


def transition(project: Path, edge: str, note: str) -> Json:
    """Move along an edge from the current stage when its evidence holds; a capped back-edge escalates to the human instead."""
    state = read_json(flow_file(project))
    if state["escalated"]:
        raise RuntimeError(f"escalated to the human: {state['help']['question']}")
    if edge not in EDGES or EDGES[edge][0] != state["stage"]:
        allowed = [e for e, (src, _) in EDGES.items() if src == state["stage"]]
        raise ValueError(f"{edge!r} is not an edge from {state['stage']!r}; allowed: {allowed}")
    if edge in BACK_EDGES:
        if not note.strip():
            raise ValueError(f"{edge!r} needs a note saying what was invalid")
        if state["taken"][edge] >= state["caps"][edge]:
            state["escalated"] = state["stage"]
            state["help"] = {"rule": "loop-cap", "edge": edge, "question": f"{edge!r} was already taken {state['taken'][edge]} time(s) "
                             f"(cap {state['caps'][edge]}). Latest reason: {note}. How should the flow proceed?"}
            write_json(flow_file(project), state)
            return {"edge": edge, "moved": False, "escalated": True, "question": state["help"]["question"]}
        state["taken"][edge] += 1
    else:
        missing = evidence(project, edge, state)
        if missing:
            return {"edge": edge, "moved": False, "missing": missing}
    if edge == "structurally-sound":
        state["code_lines_at_sweep"] = sum(code_files(project).values())
    state["history"].append({"edge": edge, "from": state["stage"], "to": EDGES[edge][1], "note": note, "ts_ms": time.time() * 1000})
    state["stage"] = EDGES[edge][1]
    write_json(flow_file(project), state)
    return {"edge": edge, "moved": True, "stage": state["stage"]}


def status(project: Path) -> Json:
    """Return the current stage, its allowed edges, and back-edge use against the caps."""
    state = read_json(flow_file(project))
    return {"stage": state["stage"], "allowed": [e for e, (src, _) in EDGES.items() if src == state["stage"]],
            "taken": state["taken"], "caps": state["caps"], "escalated": state["help"]}


def resume(project: Path, note: str) -> Json:
    """Human-only: record the answer, clear the escalation, and allow one more pass of the capped edge."""
    state = read_json(flow_file(project))
    if not state["escalated"]:
        raise ValueError("the flow is not escalated")
    state["history"].append({"human_note": note, "help": state["help"], "ts_ms": time.time() * 1000})
    edge = state["help"]["edge"]
    state["caps"][edge] = state["taken"][edge] + 1
    state["escalated"], state["help"] = None, None
    write_json(flow_file(project), state)
    return {"resumed": True, "stage": state["stage"]}


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 4 and args[0] == "init" and args[2] == "--profile" and args[3] in ("benchmark", "product"):
        out: Json = init(Path(args[1]).resolve(), args[3])  # type: ignore[arg-type]
    elif len(args) == 2 and args[0] == "status":
        out = status(Path(args[1]).resolve())
    elif len(args) >= 3 and args[0] == "transition":
        out = transition(Path(args[1]).resolve(), args[2], " ".join(args[3:]))
    elif len(args) >= 3 and args[0] == "resume":
        out = resume(Path(args[1]).resolve(), " ".join(args[2:]))
    else:
        raise SystemExit("usage: flow.py init <project> --profile {benchmark|product} | status <project> | "
                         "transition <project> <edge> [note] | resume <project> <note>")
    print(json.dumps(out, indent=2))
    sys.exit(0 if out.get("moved", True) and not out.get("escalated") else 1)
