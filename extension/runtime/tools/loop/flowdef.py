"""Load and validate SDLC flow definitions: the core graph and plugin flows, both plain JSON."""

import json
import re
from pathlib import Path
from typing import Any

CORE_FLOW = Path(__file__).resolve().parents[2] / "evaluation" / "flows" / "core.flow.json"
BUILDER = "core:builder"
DONE = "done"
MAX_CAP = 3
# Flow, stage and edge names are rendered into agent frontmatter, so they stay plain kebab-case.
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EVIDENCE_FIELDS: dict[str, dict[str, type]] = {
    "json-fields": {"file": str, "lists": list, "checks": list},
    "check": {"file": str, "key": str},
    "feature-checks": {},
    "structure": {"scope": str},
    "no-code-growth": {"since": str},
    "linked-list": {"file": str, "key": str},
    "template-valid": {"kind": str},
    "artifacts": {"paths": list},
}
STRUCTURE_SCOPES = ("all", "size")

Json = dict[str, Any]


def project_path(value: object, field: str) -> str:
    """Return a project-relative path without traversal, or raise."""
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/") or ":" in value \
            or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError(f"{field} must be a project-relative path without '..': {value!r}")
    return value


def evidence_item(raw: object, field: str, kinds: set[str], edges: set[str]) -> Json:
    """Return one validated evidence entry."""
    if not isinstance(raw, dict) or raw.get("type") not in EVIDENCE_FIELDS:
        raise ValueError(f"{field} must be an object whose type is one of {sorted(EVIDENCE_FIELDS)}")
    fields = EVIDENCE_FIELDS[raw["type"]]
    if set(raw) - {"type"} != set(fields):
        raise ValueError(f"{field} ({raw['type']}) needs exactly the fields {sorted(fields)}")
    for key, kind in fields.items():
        if not isinstance(raw[key], kind) or not raw[key]:
            raise ValueError(f"{field}.{key} must be a non-empty {kind.__name__}")
    if raw["type"] in ("json-fields", "check", "linked-list"):
        project_path(raw["file"], f"{field}.file")
    if raw["type"] == "artifacts":
        for i, glob in enumerate(raw["paths"]):
            project_path(glob, f"{field}.paths[{i}]")
    if raw["type"] == "json-fields" and not all(isinstance(v, str) and v for v in raw["lists"] + raw["checks"]):
        raise ValueError(f"{field} lists and checks must be non-empty strings")
    if raw["type"] == "structure" and raw["scope"] not in STRUCTURE_SCOPES:
        raise ValueError(f"{field}.scope must be one of {list(STRUCTURE_SCOPES)}")
    if raw["type"] == "no-code-growth" and raw["since"] not in edges:
        raise ValueError(f"{field}.since must name an edge of this flow, got {raw['since']!r}")
    if raw["type"] == "template-valid" and raw["kind"] not in kinds:
        raise ValueError(f"{field}.kind {raw['kind']!r} is not a known template kind {sorted(kinds)}")
    return dict(raw)


def reachable(start: str, edges: list[tuple[str, str]]) -> set[str]:
    """Return the nodes reachable from start along the edges."""
    seen, todo = {start}, [start]
    while todo:
        node = todo.pop()
        for src, dst in edges:
            if src == node and dst not in seen:
                seen.add(dst)
                todo.append(dst)
    return seen


def acyclic(edges: list[tuple[str, str]]) -> bool:
    """Return whether the directed edges contain no cycle."""
    remaining = list(edges)
    while remaining:
        targets = {dst for _, dst in remaining}
        sources = {src for src, _ in remaining if src not in targets}
        if not sources:
            return False
        remaining = [e for e in remaining if e[0] not in sources]
    return True


def validate(raw: object, plugin: str | None, agents: set[str], kinds: set[str], base: Path | None) -> Json:
    """Return a validated flow; plugin flows (plugin set) lock their checks and use only core:builder or their own agents."""
    if not isinstance(raw, dict):
        raise ValueError("a flow definition must be a JSON object")
    allowed = {"id", "description", "start", "lockChecks", "stages", "edges", "evaluation"}
    if set(raw) - allowed or not {"id", "description", "start", "lockChecks", "stages", "edges"} <= set(raw):
        raise ValueError(f"flow keys must be {sorted(allowed)} (evaluation optional); got {sorted(raw)}")
    flow_id = raw["id"]
    if not isinstance(flow_id, str) or not flow_id or not isinstance(raw["description"], str) or not raw["description"]:
        raise ValueError("flow id and description must be non-empty strings")
    if not isinstance(raw["lockChecks"], bool) or (plugin is not None and not raw["lockChecks"]):
        raise ValueError(f"flow {flow_id}: lockChecks must be boolean, and true for plugin flows")
    stages, edges = raw["stages"], raw["edges"]
    if not isinstance(stages, dict) or not stages or DONE in stages or raw["start"] not in stages:
        raise ValueError(f"flow {flow_id}: stages must be a non-empty object without {DONE!r} that contains start")
    if not isinstance(edges, dict) or not edges:
        raise ValueError(f"flow {flow_id}: edges must be a non-empty object")
    bad = [n for n in [flow_id, *stages, *edges] if not NAME.fullmatch(n)]
    if bad:
        raise ValueError(f"flow {flow_id!r}: flow, stage and edge names must be lowercase kebab-case; got {bad}")
    for name, stage in stages.items():
        if not isinstance(stage, dict) or set(stage) - {"agent", "instructions"} or not isinstance(stage.get("agent"), str):
            raise ValueError(f"flow {flow_id}: stage {name} needs an 'agent' and optional 'instructions'")
        if plugin is not None:
            if stage["agent"] != BUILDER and stage["agent"] not in {f"{plugin}:{a}" for a in agents}:
                raise ValueError(f"flow {flow_id}: stage {name} agent must be {BUILDER} or an agent of {plugin}, got {stage['agent']!r}")
            if stage["agent"] != BUILDER and "instructions" not in stage:
                raise ValueError(f"flow {flow_id}: stage {name} needs instructions for its plugin agent")
        if "instructions" in stage:
            if base is None or not (base / project_path(stage["instructions"], f"stage {name}.instructions")).is_file():
                raise ValueError(f"flow {flow_id}: stage {name} instructions file not found: {stage['instructions']}")
    pairs: list[tuple[str, str]] = []
    forward: list[tuple[str, str]] = []
    normalized: Json = {}
    for name, edge in edges.items():
        field = f"flow {flow_id}: edge {name}"
        if not isinstance(edge, dict) or edge.get("from") not in stages or (edge.get("to") not in stages and edge.get("to") != DONE):
            raise ValueError(f"{field} must go from a stage to a stage or {DONE!r}")
        if edge.get("back"):
            if set(edge) != {"from", "to", "back", "cap"} or edge["back"] is not True or edge["to"] == DONE:
                raise ValueError(f"{field}: a back-edge has exactly from, to, back: true and cap, and does not end the flow")
            if isinstance(edge["cap"], bool) or not isinstance(edge["cap"], int) or not 1 <= edge["cap"] <= MAX_CAP:
                raise ValueError(f"{field}: cap must be an integer from 1 to {MAX_CAP}")
            normalized[name] = {"from": edge["from"], "to": edge["to"], "back": True, "cap": edge["cap"]}
        else:
            if set(edge) != {"from", "to", "evidence"} or not isinstance(edge["evidence"], list) or not edge["evidence"]:
                raise ValueError(f"{field}: a forward edge has exactly from, to and a non-empty evidence list")
            evidence = [evidence_item(e, f"{field}.evidence[{i}]", kinds, set(edges)) for i, e in enumerate(edge["evidence"])]
            normalized[name] = {"from": edge["from"], "to": edge["to"], "back": False, "evidence": evidence}
            forward.append((edge["from"], edge["to"]))
        pairs.append((edge["from"], edge["to"]))
    if not acyclic(forward):
        raise ValueError(f"flow {flow_id}: forward edges form a cycle; only capped back-edges may loop")
    unreachable = set(stages) - reachable(raw["start"], pairs)
    if unreachable:
        raise ValueError(f"flow {flow_id}: stages {sorted(unreachable)} are unreachable from {raw['start']!r}")
    stuck = [s for s in stages if DONE not in reachable(s, pairs)]
    if stuck:
        raise ValueError(f"flow {flow_id}: stages {sorted(stuck)} cannot reach {DONE!r}")
    flow = {"id": flow_id, "description": raw["description"], "start": raw["start"], "lockChecks": raw["lockChecks"],
            "stages": {n: dict(s) for n, s in stages.items()}, "edges": normalized}
    if "evaluation" in raw:
        flow["evaluation"] = project_path(raw["evaluation"], f"flow {flow_id}.evaluation")
    return flow


def core() -> Json:
    """Return the validated core flow."""
    return validate(json.loads(CORE_FLOW.read_text(encoding="utf-8")), None, set(), set(), None)
