"""State machine of the creator-flow graph workflow: a stage moves on only along a drawn edge, with deterministic evidence, and capped loops.

The graph comes from a validated flow definition: the core flow, or a plugin flow snapshotted when the flow starts."""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools" / "git"), str(ROOT / "hooks"), str(ROOT / "tools" / "plugins"), str(ROOT / "tools" / "templates")]
import store  # noqa: E402
from branch_workflow import read_json, write_json  # noqa: E402
from flowdef import DONE, core  # noqa: E402
from loop import TRIVIAL_VERIFY, run_check  # noqa: E402
from manage import slugs, validate as validate_document  # noqa: E402
from no_fallback import scan_file  # noqa: E402

BENCHMARK_CAPS = {"new-opportunity-found": 0}
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".scss", ".html", ".vue", ".svelte"}
SKIP_DIRS = {"node_modules", ".next", ".git", ".harness", ".hve", "dist", "build", "coverage"}
MAX_FILE_LINES = 500
Profile = Literal["benchmark", "product"]

Json = dict[str, Any]


def flow_file(project: Path) -> Path:
    """Return the flow state path."""
    return project / ".harness" / "flow.json"


def definition_file(project: Path) -> Path:
    """Return the path of the flow definition snapshot taken at init."""
    return project / ".harness" / "flow-definition.json"


def sha256(value: object) -> str:
    """Return the SHA-256 of a JSON value in canonical form."""
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def load_definition(ref: str) -> Json:
    """Return the snapshot record of the flow 'core' or '<plugin>:<flow>'."""
    if ref == "core":
        flow = core()
        return {"ref": ref, "plugin": None, "version": None, "sha256": sha256(flow), "flow": flow}
    name, sep, flow_id = ref.partition(":")
    if not sep:
        raise ValueError(f"--flow must be 'core' or '<plugin>:<flow>', got {ref!r}")
    entry = store.plugin(name)
    flows = entry["manifest"]["flows"]
    if flow_id not in flows:
        raise LookupError(f"plugin {name} has no flow {flow_id!r}; its flows are {sorted(flows)}")
    return {"ref": ref, "plugin": name, "version": entry["version"], "sha256": sha256(flows[flow_id]), "flow": flows[flow_id]}


def init(project: Path, profile: Profile, ref: str = "core", restart: bool = False) -> Json:
    """Start a flow at its start stage; benchmark runs use the core flow and give Grower one pass (no new-opportunity loop)."""
    if profile == "benchmark" and ref != "core":
        raise ValueError("benchmark runs use the core flow so results stay comparable")
    if flow_file(project).exists() and not restart:
        raise FileExistsError(f"{flow_file(project)} exists")
    if restart and not flow_file(project).exists():
        raise FileNotFoundError(f"{flow_file(project)} does not exist; there is no flow to restart")
    snapshot = load_definition(ref)
    flow = snapshot["flow"]
    back = {name: edge["cap"] for name, edge in flow["edges"].items() if edge["back"]}
    caps = back | ({k: v for k, v in BENCHMARK_CAPS.items() if k in back} if profile == "benchmark" else {})
    state = {"profile": profile, "flow": ref, "stage": flow["start"], "caps": caps, "taken": {e: 0 for e in back}, "history": [],
             "started_ms": time.time() * 1000, "lines_at": {}, "check_hashes": {}, "escalated": None, "help": None}
    write_json(definition_file(project), snapshot)
    write_json(flow_file(project), state)
    return state


def definition(project: Path) -> Json:
    """Return the flow snapshot; a plugin flow stops when the installed plugin version differs from the one it started on."""
    if not definition_file(project).exists():
        raise FileNotFoundError(f"{definition_file(project)} is missing; start the flow with `flow.py init`")
    snapshot = read_json(definition_file(project))
    if snapshot["plugin"] is not None:
        installed = store.plugin(snapshot["plugin"])["version"]
        if installed != snapshot["version"]:
            raise RuntimeError(f"plugin {snapshot['plugin']} is now {installed}, but this flow started on {snapshot['version']}: "
                               f"reinstall {snapshot['version']} to finish it, or restart it with "
                               f"`flow.py init <project> --profile product --flow {snapshot['ref']} --restart`")
    return snapshot


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


def project_json(project: Path, name: str) -> Any:
    """Return a project JSON file, or None when it does not exist."""
    path = project / name
    return read_json(path) if path.exists() else None


def feature_checks_fail(project: Path) -> list[str]:
    """Return the features that are not marked passing or whose check fails now."""
    state = read_json(project / ".harness" / "state.json")
    features = read_json(project / "feature_list.json")
    return [f["name"] for f in features if not f["passes"] or run_check(state["lock"][f["name"]]["verify"], project)[0] != 0]


def size_problems(project: Path) -> list[str]:
    """Return the source files over the size limit."""
    return [f"{path.relative_to(project).as_posix()}: {lines} lines" for path, lines in code_files(project).items() if lines > MAX_FILE_LINES]


def structure_problems(project: Path) -> list[str]:
    """Return files over the size limit and no-fallback (B1) findings in the working tree."""
    problems = size_problems(project)
    for path in code_files(project):
        problems += scan_file(path.relative_to(project).as_posix(), path.read_text(encoding="utf-8", errors="replace"))
    return problems


def check_evidence(project: Path, item: Json, state: Json, lock: bool) -> list[str]:
    """Return what is missing for a check: a real command (approved and unchanged when the flow locks checks) that exits 0."""
    file, key = item["file"], item["key"]
    data = project_json(project, file)
    command = data.get(key) if isinstance(data, dict) else None
    if not isinstance(command, str) or TRIVIAL_VERIFY.match(command):
        return [f"{file} needs a real {key!r} command"]
    if lock:
        approved = state["check_hashes"].get(f"{file}#{key}")
        if approved is None:
            return [f"{key} in {file} was never approved by a json-fields edge"]
        if approved != sha256(command):
            return [f"{key} in {file} changed after it was approved; restore it or take the back-edge to the stage that approves it"]
    code, output = run_check(command, project)
    return [] if code == 0 else [f"{key} exited {code}: {output[-400:]}"]


def evidence(project: Path, item: Json, state: Json, lock: bool) -> list[str]:
    """Return what is missing for one evidence entry; an empty list means it holds."""
    kind = item["type"]
    if kind == "json-fields":
        data = project_json(project, item["file"])
        if not isinstance(data, dict):
            return [f"{item['file']} is missing or not a JSON object"]
        return ([f"{item['file']} needs a non-empty {k!r} list" for k in item["lists"] if not (isinstance(data.get(k), list) and data[k])]
                + [f"{item['file']} needs a real {k!r} command" for k in item["checks"]
                   if not isinstance(data.get(k), str) or TRIVIAL_VERIFY.match(data[k])])
    if kind == "check":
        return check_evidence(project, item, state, lock)
    if kind == "feature-checks":
        if not (project / ".harness" / "state.json").exists():
            return ["the feature loop was never initialized"]
        failing = feature_checks_fail(project)
        return [f"features failing: {failing}"] if failing else []
    if kind == "structure":
        return structure_problems(project) if item["scope"] == "all" else size_problems(project)
    if kind == "no-code-growth":
        before = state["lines_at"].get(item["since"])
        if before is None:
            return [f"edge {item['since']!r} was never taken, so there is no line count to compare"]
        lines = sum(code_files(project).values())
        return [f"code grew from {before} to {lines} lines"] if lines > before else []
    if kind == "linked-list":
        data = project_json(project, item["file"])
        if not isinstance(data, list):
            return [f"{item['file']} must be a list of objects with a {item['key']!r} field"]
        names = {f["name"] for f in read_json(project / "feature_list.json")}
        return [f"{item['file']} entry {i} is not linked to a feature in feature_list.json" for i, entry in enumerate(data)
                if not isinstance(entry, dict) or entry.get(item["key"]) not in names]
    if kind == "template-valid":
        found = slugs(project, item["kind"])
        if any(not validate_document(project, item["kind"], slug) for slug in found):
            return []
        return [f"no valid {item['kind']} document" + (f"; {len(found)} found, none valid" if found else "")]
    return [f"no file matching {glob} was written after the flow started" for glob in item["paths"]
            if not any(p.is_file() and p.stat().st_mtime * 1000 >= state["started_ms"] for p in project.glob(glob))]


def allowed(flow: Json, stage: str) -> list[str]:
    """Return the edges leaving a stage."""
    return [name for name, edge in flow["edges"].items() if edge["from"] == stage]


def transition(project: Path, edge: str, note: str) -> Json:
    """Move along an edge from the current stage when its evidence holds; a capped back-edge escalates to the human instead."""
    flow = definition(project)["flow"]
    state = read_json(flow_file(project))
    if state["escalated"]:
        raise RuntimeError(f"escalated to the human: {state['help']['question']}")
    spec = flow["edges"].get(edge)
    if spec is None or spec["from"] != state["stage"]:
        raise ValueError(f"{edge!r} is not an edge from {state['stage']!r}; allowed: {allowed(flow, state['stage'])}")
    if spec["back"]:
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
        missing = [m for item in spec["evidence"] for m in evidence(project, item, state, flow["lockChecks"])]
        if missing:
            return {"edge": edge, "moved": False, "missing": missing}
        for item in (i for i in spec["evidence"] if i["type"] == "json-fields"):
            data = read_json(project / item["file"])
            state["check_hashes"] |= {f"{item['file']}#{key}": sha256(data[key]) for key in item["checks"]}
        if any(i["type"] == "no-code-growth" and i["since"] == edge for e in flow["edges"].values() if not e["back"] for i in e["evidence"]):
            state["lines_at"][edge] = sum(code_files(project).values())
    state["history"].append({"edge": edge, "from": state["stage"], "to": spec["to"], "note": note, "ts_ms": time.time() * 1000})
    state["stage"] = spec["to"]
    write_json(flow_file(project), state)
    return {"edge": edge, "moved": True, "stage": state["stage"]}


def status(project: Path) -> Json:
    """Return the flow, current stage with its agent and instructions, allowed edges, and back-edge use against the caps."""
    snapshot = definition(project)
    flow = snapshot["flow"]
    state = read_json(flow_file(project))
    result = {"flow": snapshot["ref"], "stage": state["stage"], "allowed": allowed(flow, state["stage"]),
              "taken": state["taken"], "caps": state["caps"], "escalated": state["help"]}
    base = store.folder(store.plugin(snapshot["plugin"])) if snapshot["plugin"] else None
    if state["stage"] != DONE:
        stage = flow["stages"][state["stage"]]
        result["agent"] = stage["agent"]
        if base is not None and "instructions" in stage:
            result["instructions"] = (base / stage["instructions"]).as_posix()
    if base is not None and "evaluation" in flow:
        result["evaluation"] = (base / flow["evaluation"]).as_posix()
    return result


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
    parser = argparse.ArgumentParser(description="Creator-flow state machine.")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("init")
    start.add_argument("project", type=Path)
    start.add_argument("--profile", required=True, choices=("benchmark", "product"))
    start.add_argument("--flow", default="core", help="core (default) or <plugin>:<flow>")
    start.add_argument("--restart", action="store_true", help="replace a running flow, for example after a plugin upgrade")
    commands.add_parser("status").add_argument("project", type=Path)
    for name in ("transition", "resume"):
        command = commands.add_parser(name)
        command.add_argument("project", type=Path)
        if name == "transition":
            command.add_argument("edge")
        command.add_argument("note", nargs="*")
    args = parser.parse_args()
    project = args.project.resolve()
    if args.command == "init":
        out: Json = init(project, args.profile, args.flow, args.restart)
    elif args.command == "status":
        out = status(project)
    elif args.command == "transition":
        out = transition(project, args.edge, " ".join(args.note))
    else:
        if not args.note:
            raise SystemExit("resume needs a note")
        out = resume(project, " ".join(args.note))
    print(json.dumps(out, indent=2))
    sys.exit(0 if out.get("moved", True) and not out.get("escalated") else 1)
