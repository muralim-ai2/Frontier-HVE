"""Validate a local JSON product backlog against the PRD it delivers."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TypeGuard, TypedDict, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "templates"))
from manage import safe_path  # noqa: E402

PARENT = {"epic": None, "feature": "epic", "story": "feature"}
PRIORITIES = ("P0", "P1", "P2")
TEXT_FIELDS = ("id", "type", "title", "persona", "problem", "outcome", "scope", "verification", "priority", "priority_rationale")
LIST_FIELDS = ("non_goals", "acceptance", "dependencies", "requirements")
FIELDS = {*TEXT_FIELDS, *LIST_FIELDS, "parent"}
REQUIREMENT_ID = re.compile(r"[A-Z][A-Z0-9]*-\d+\Z")


class Criterion(TypedDict):
    """One Given/When/Then acceptance criterion."""

    given: str
    when: str
    then: str


class Item(TypedDict):
    """One epic, feature or story in the backlog."""

    id: str
    type: str
    parent: str | None
    title: str
    persona: str
    problem: str
    outcome: str
    scope: str
    non_goals: list[str]
    acceptance: list[Criterion]
    verification: str
    dependencies: list[str]
    priority: str
    priority_rationale: str
    requirements: list[str]


class Report(TypedDict):
    """Validation errors and the PRD requirement ids no item delivers."""

    errors: list[str]
    uncovered: list[str]


def filled(value: object) -> TypeGuard[str]:
    """Return whether value is non-blank text."""
    return isinstance(value, str) and bool(value.strip())


def schema_errors(item: dict[str, object]) -> list[str]:
    """Return item shape errors before references are used as graph keys."""
    name = str(item.get("id", "?"))
    errors = [f"{name}: unknown field {key}" for key in sorted(set(item) - FIELDS)]
    errors += [f"{name}: missing field {key}" for key in sorted(FIELDS - set(item))]
    if errors:
        return errors
    errors += [f"{name}: {key} must be non-empty text" for key in TEXT_FIELDS if not filled(item[key])]
    errors += [f"{name}: {key} must be a list" for key in LIST_FIELDS if not isinstance(item[key], list)]
    if item["parent"] is not None and not filled(item["parent"]):
        errors.append(f"{name}: parent must be null or non-empty text")
    if errors:
        return errors
    for key in ("non_goals", "dependencies", "requirements"):
        values = item[key]
        if isinstance(values, list) and not all(filled(value) for value in values):
            errors.append(f"{name}: {key} must contain only non-empty text")
    return errors


def item_errors(item: Item, types: dict[str, str], prd_text: str) -> list[str]:
    """Return the hierarchy, acceptance and traceability errors of one validated item."""
    name = item["id"]
    errors: list[str] = []
    if item["type"] not in PARENT:
        errors.append(f"{name}: type must be one of {list(PARENT)}")
    else:
        parent = item["parent"]
        parent_type = None if parent is None else types.get(parent, "missing")
        if parent_type != PARENT[item["type"]]:
            errors.append(f"{name}: a {item['type']} needs parent type {PARENT[item['type']]}, got {parent_type}")
    if item["priority"] not in PRIORITIES:
        errors.append(f"{name}: priority must be one of {list(PRIORITIES)}")
    if not item["non_goals"] or not all(filled(goal) for goal in item["non_goals"]):
        errors.append(f"{name}: non_goals needs at least one non-empty entry")
    if not item["acceptance"] or not all(isinstance(c, dict) and set(c) == {"given", "when", "then"}
                                         and all(filled(v) for v in c.values()) for c in item["acceptance"]):
        errors.append(f"{name}: acceptance needs at least one complete given/when/then criterion")
    errors += [f"{name}: unknown dependency {dep}" for dep in item["dependencies"] if dep not in types or dep == name]
    if not item["requirements"]:
        errors.append(f"{name}: requirements must list the PRD ids it delivers")
    for req in item["requirements"]:
        if not isinstance(req, str) or not REQUIREMENT_ID.match(req):
            errors.append(f"{name}: requirement id {req!r} must look like FR-1")
        elif not re.search(rf"(?<![\w-]){re.escape(req)}(?![\w-])", prd_text):
            errors.append(f"{name}: requirement {req} is not in the PRD")
    return errors


def cycle(graph: dict[str, list[str]]) -> list[str]:
    """Return one dependency cycle as a list of ids, or an empty list."""
    visiting: list[str] = []
    done: set[str] = set()

    def visit(node: str) -> list[str]:
        if node in visiting:
            return visiting[visiting.index(node):] + [node]
        if node in done:
            return []
        visiting.append(node)
        for dep in graph[node]:
            found = visit(dep)
            if found:
                return found
        visiting.pop()
        done.add(node)
        return []

    for node in graph:
        found = visit(node)
        if found:
            return found
    return []


def uncovered(prd_text: str, items: list[Item]) -> list[str]:
    """Return the PRD's FR/NFR ids that no backlog item delivers, in document order."""
    delivered = {req for item in items for req in item["requirements"]}
    found = re.findall(r"(?<![\w-])(?:FR|NFR)-\d+(?![\w-])", prd_text)
    return [req for req in dict.fromkeys(found) if req not in delivered]


def validate(workspace: Path, relative: str) -> Report:
    """Return every error in the backlog file at a workspace-relative path and, if valid, the PRD ids it leaves uncovered."""
    data: object = json.loads(safe_path(workspace, relative).read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or set(data) != {"version", "prd", "items"}
            or type(data["version"]) is not int or data["version"] != 1):
        return Report(errors=['backlog must be {"version": 1, "prd": "<workspace-relative PRD path>", "items": [...]}'], uncovered=[])
    if not filled(data["prd"]):
        return Report(errors=["prd must be a non-empty workspace-relative path string"], uncovered=[])
    prd_text = safe_path(workspace, data["prd"]).read_text(encoding="utf-8")
    raw_items = data["items"]
    if not isinstance(raw_items, list) or not raw_items or not all(isinstance(item, dict) for item in raw_items):
        return Report(errors=["items must be a non-empty list of objects"], uncovered=[])
    errors = [error for item in raw_items for error in schema_errors(item)]
    if errors:
        return Report(errors=errors, uncovered=[])
    items = [cast(Item, item) for item in raw_items]
    ids = [item["id"] for item in items]
    errors = [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    types = {item["id"]: item["type"] for item in items}
    for item in items:
        errors += item_errors(item, types, prd_text)
    if not errors:
        found = cycle({item["id"]: item["dependencies"] for item in items})
        if found:
            errors.append("dependency cycle: " + " -> ".join(found))
    return Report(errors=errors, uncovered=[] if errors else uncovered(prd_text, items))


def main() -> None:
    """Validate one backlog file and print the result as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate").add_argument("backlog", help="workspace-relative path, e.g. docs/product/BACKLOG-<slug>.json")
    args = parser.parse_args()
    report = validate(args.workspace.resolve(strict=True), args.backlog)
    print(json.dumps({"valid": not report["errors"], **report}, indent=2))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
