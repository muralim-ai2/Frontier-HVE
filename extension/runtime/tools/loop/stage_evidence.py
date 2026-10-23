"""Optional lifecycle stage evidence and rework: validate the declarations, check the evidence before a stage is signed off, and step
back to an earlier stage within a cap."""

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "templates"))

MAX_REWORK = 3
EVIDENCE_FIELDS: dict[str, dict[str, type]] = {
    "template-valid": {"kind": str},
    "json-fields": {"file": str, "lists": list, "checks": list},
    "check": {"file": str, "key": str},
    "feature-checks": {},
    "artifacts": {"paths": list},
}

Json = dict[str, Any]


def project_path(value: object, field: str) -> str:
    """Return a workspace-relative path without traversal ('{ask}' stands for the ask folder), or raise."""
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/") or ":" in value \
            or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError(f"{field} must be a relative path without '..': {value!r}")
    return value


def validate_item(raw: object, field: str) -> Json:
    """Return one validated evidence entry."""
    if not isinstance(raw, dict) or raw.get("type") not in EVIDENCE_FIELDS:
        raise ValueError(f"{field} must be an object whose type is one of {sorted(EVIDENCE_FIELDS)}")
    fields = EVIDENCE_FIELDS[raw["type"]]
    if set(raw) - {"type"} != set(fields):
        raise ValueError(f"{field} ({raw['type']}) needs exactly the fields {sorted(fields)}")
    for key, kind in fields.items():
        if not isinstance(raw[key], kind) or not raw[key]:
            raise ValueError(f"{field}.{key} must be a non-empty {kind.__name__}")
    for path in [raw["file"]] if "file" in raw else raw.get("paths", []):
        project_path(path, f"{field} path")
    if raw["type"] == "json-fields" and not all(isinstance(v, str) and v for v in raw["lists"] + raw["checks"]):
        raise ValueError(f"{field} lists and checks must be non-empty strings")
    return dict(raw)


def validate_stage(stage: Json, earlier: list[str], source: str) -> None:
    """Raise unless the stage's optional evidence list and rework step ({to: an earlier stage, cap: 1-3}) are well formed."""
    for i, item in enumerate(stage.get("evidence", [])):
        validate_item(item, f"{source}: stage {stage['name']} evidence[{i}]")
    rework = stage.get("rework")
    if rework is None:
        return
    if not isinstance(rework, dict) or set(rework) != {"to", "cap"} or rework["to"] not in earlier:
        raise ValueError(f"{source}: stage {stage['name']} rework needs exactly to (an earlier stage {earlier}) and cap")
    if isinstance(rework["cap"], bool) or not isinstance(rework["cap"], int) or not 1 <= rework["cap"] <= MAX_REWORK:
        raise ValueError(f"{source}: stage {stage['name']} rework cap must be an integer from 1 to {MAX_REWORK}")


def resolve_path(workspace: Path, ask: str, value: str) -> Path:
    """Return the workspace path of an evidence path, with '{ask}' replaced by the ask folder."""
    return workspace / value.replace("{ask}", ask)


def template_problems(workspace: Path, kind: str) -> list[str]:
    """Return why no valid document of the template kind exists in the workspace."""
    from manage import configuration_entry, validate

    entry = configuration_entry(workspace, kind)
    prefix, _, suffix = entry["output"].partition("{slug}")
    slugs = [p.as_posix()[len((workspace / prefix).as_posix()):-len(suffix) or None]
             for p in workspace.glob(entry["output"].replace("{slug}", "*"))]
    if any(not validate(workspace, kind, slug) for slug in slugs):
        return []
    return [f"no valid {kind} document" + (f"; {len(slugs)} found, none valid" if slugs else f" at {entry['output']}")]


def problems(workspace: Path, ask: str, item: Json) -> list[str]:
    """Return what is missing for one evidence entry; an empty list means it holds."""
    from loop import TRIVIAL_VERIFY, load, run_check

    kind = item["type"]
    if kind == "template-valid":
        return template_problems(workspace, item["kind"])
    if kind in ("json-fields", "check"):
        path = resolve_path(workspace, ask, item["file"])
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        if not isinstance(data, dict):
            return [f"{item['file']} is missing or not a JSON object"]
        if kind == "json-fields":
            return ([f"{item['file']} needs a non-empty {k!r} list" for k in item["lists"] if not (isinstance(data.get(k), list) and data[k])]
                    + [f"{item['file']} needs a real {k!r} command" for k in item["checks"]
                       if not isinstance(data.get(k), str) or TRIVIAL_VERIFY.match(data[k])])
        command = data.get(item["key"])
        if not isinstance(command, str) or TRIVIAL_VERIFY.match(command):
            return [f"{item['file']} needs a real {item['key']!r} command"]
        code, output = run_check(command, workspace)
        return [] if code == 0 else [f"{item['key']} exited {code}: {output[-400:]}"]
    if kind == "feature-checks":
        _, features = load(workspace)
        return [f"feature {f['name']} is not passing" for f in features if not f["passes"]]
    return [f"no file matches {glob}" for glob in item["paths"] if not any(p.is_file() for p in workspace.glob(glob.replace("{ask}", ask)))]


def check(workspace: Path, ask: str, stage: Json) -> list[str]:
    """Return every missing piece of the stage's evidence (none when it declares no evidence)."""
    return [p for item in stage.get("evidence", []) for p in problems(workspace, ask, item)]


def rework(data: Json, row: Json, why: str, now: str) -> Json:
    """Step an ask back from the stage to its rework target: the target becomes current, it and every stage up to this one lose their
    sign-off, and the step is recorded; raise past the cap so the user decides."""
    if "rework" not in row:
        raise ValueError(f"stage {row['name']} declares no rework step")
    target, cap = row["rework"]["to"], row["rework"]["cap"]
    taken = sum(1 for d in data["decisions"] if d["stage"] == row["name"] and d["choice"] == f"rework to {target}")
    if taken >= cap:
        raise RuntimeError(f"stage {row['name']} reached its rework cap of {cap}: ask the user how to proceed")
    names = [s["name"] for s in data["stages"]]
    for s in data["stages"][names.index(target):names.index(row["name"]) + 1]:
        s["status"] = "skipped" if s["status"] == "skipped" else "planned"
        data["checklist"].pop(f"stage:{s['name']}", None)
    data["current"] = target
    data["decisions"].append({"ts": now, "stage": row["name"], "choice": f"rework to {target}", "why": why})
    return {"current": target, "rework": taken + 1, "cap": cap}
