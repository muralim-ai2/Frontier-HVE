"""Load and validate Frontier HVE evaluation contracts (JSON)."""

import json
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

HookType = Literal["feature-checks", "command", "artifacts"]
HOOK_TYPES = ("feature-checks", "command", "artifacts")
OutputKind = Literal["ui", "cli", "api", "library", "document"]
OUTPUT_KINDS = ("ui", "cli", "api", "library", "document")
Trigger = Literal["always", "below-warning"]
TRIGGERS = ("always", "below-warning")


class RubricSpec(TypedDict):
    """Define one weighted output rubric."""

    id: str
    description: str
    weight: float
    blocking: float
    warning: float
    criteria: list[str]
    validationHooks: list[str]


class ValidationHook(TypedDict, total=False):
    """Define one deterministic evidence hook."""

    id: str
    type: HookType
    required: bool
    trigger: Trigger
    outputKinds: list[OutputKind]
    command: str
    paths: list[str]
    timeoutSeconds: int
    recommendation: str


class CouncilRole(TypedDict):
    """Define one model-council perspective."""

    id: str
    mandate: str
    modelTier: Literal["high"]


class DecisionSpec(TypedDict):
    """Define deterministic reflection decision thresholds."""

    minimumScore: float
    councilPasses: int
    maxRevisionPasses: int


class EvaluationContract(TypedDict):
    """Define the normalized evaluation contract used by the workflow."""

    version: int
    intent: dict[str, str]
    validation: dict[str, list[ValidationHook]]
    rubrics: list[RubricSpec]
    council: dict[str, list[CouncilRole]]
    decision: DecisionSpec


def mapping(value: object, field: str) -> dict[str, Any]:
    """Return value as a JSON object or raise."""
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a JSON object")
    return cast(dict[str, Any], value)


def items(value: object, field: str) -> list[Any]:
    """Return value as a JSON list or raise."""
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a JSON list")
    return cast(list[Any], value)


def text(value: object, field: str) -> str:
    """Return value as a stripped non-empty string or raise."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _number(value: object, field: str) -> float:
    """Return value as a number or raise."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    return float(value)


def _int(value: object, field: str, low: int, high: int) -> int:
    """Return value as an integer within [low, high] or raise."""
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{field} must be an integer from {low} to {high}")
    return value


def _strings(value: object, field: str) -> list[str]:
    """Return value as a list of non-empty strings or raise."""
    return [text(item, f"{field}[{i}]") for i, item in enumerate(items(value, field))]


def _hooks(validation: dict[str, object]) -> list[ValidationHook]:
    """Return validated evidence hooks."""
    hooks: list[ValidationHook] = []
    for i, raw in enumerate(items(validation.get("hooks"), "validation.hooks")):
        item = mapping(raw, f"validation.hooks[{i}]")
        hook_id = text(item.get("id"), f"validation.hooks[{i}].id")
        kind = text(item.get("type"), f"validation hook {hook_id}.type")
        if kind not in HOOK_TYPES:
            raise ValueError(f"validation hook {hook_id} has unsupported type {kind!r}; expected one of {list(HOOK_TYPES)}")
        if not isinstance(item.get("required"), bool):
            raise ValueError(f"validation hook {hook_id}.required must be boolean")
        if item.get("trigger") not in TRIGGERS:
            raise ValueError(f"validation hook {hook_id}.trigger must be one of {list(TRIGGERS)}")
        kinds = _strings(item.get("outputKinds"), f"validation hook {hook_id}.outputKinds")
        if not kinds or set(kinds) - set(OUTPUT_KINDS):
            raise ValueError(f"validation hook {hook_id}.outputKinds must be a non-empty list of {list(OUTPUT_KINDS)}")
        hook: ValidationHook = {"id": hook_id, "type": cast(HookType, kind), "required": cast(bool, item["required"]),
                                "trigger": cast(Trigger, item["trigger"]), "outputKinds": cast(list[OutputKind], kinds),
                                "timeoutSeconds": _int(item.get("timeoutSeconds"), f"validation hook {hook_id}.timeoutSeconds", 1, 1800)}
        if not hook["required"]:
            hook["recommendation"] = text(item.get("recommendation"), f"optional validation hook {hook_id}.recommendation")
        if kind == "command":
            hook["command"] = text(item.get("command"), f"validation hook {hook_id}.command")
        if kind == "artifacts":
            hook["paths"] = _strings(item.get("paths"), f"validation hook {hook_id}.paths")
        hooks.append(hook)
    if len({h["id"] for h in hooks}) != len(hooks):
        raise ValueError("validation hook ids must be unique")
    return hooks


def _rubrics(value: object, hook_ids: set[str]) -> list[RubricSpec]:
    """Return validated rubrics whose weights sum to 1."""
    rubrics: list[RubricSpec] = []
    for i, raw in enumerate(items(value, "rubrics")):
        item = mapping(raw, f"rubrics[{i}]")
        rubric_id = text(item.get("id"), f"rubrics[{i}].id")
        blocking = _number(item.get("blocking"), f"rubric {rubric_id}.blocking")
        warning = _number(item.get("warning"), f"rubric {rubric_id}.warning")
        if not 0 <= blocking <= warning <= 1:
            raise ValueError(f"rubric {rubric_id} thresholds must satisfy 0 <= blocking <= warning <= 1")
        hooks = _strings(item.get("validationHooks"), f"rubric {rubric_id}.validationHooks")
        unknown = sorted(set(hooks) - hook_ids)
        if unknown:
            raise ValueError(f"rubric {rubric_id} references unknown validation hooks {unknown}")
        rubrics.append({"id": rubric_id, "description": text(item.get("description"), f"rubric {rubric_id}.description"),
                        "weight": _number(item.get("weight"), f"rubric {rubric_id}.weight"), "blocking": blocking, "warning": warning,
                        "criteria": _strings(item.get("criteria"), f"rubric {rubric_id}.criteria"), "validationHooks": hooks})
    if len(rubrics) < 3 or len({r["id"] for r in rubrics}) != len(rubrics):
        raise ValueError("rubrics must contain at least three unique ids")
    if any(r["weight"] <= 0 for r in rubrics) or abs(sum(r["weight"] for r in rubrics) - 1) > 1e-6:
        raise ValueError("rubric weights must be positive and sum to 1")
    return rubrics


def _roles(council: dict[str, object]) -> list[CouncilRole]:
    """Return exactly three validated high-tier council roles."""
    roles: list[CouncilRole] = []
    for i, raw in enumerate(items(council.get("roles"), "council.roles")):
        item = mapping(raw, f"council.roles[{i}]")
        role_id = text(item.get("id"), f"council.roles[{i}].id")
        if item.get("modelTier") != "high":
            raise ValueError(f"council role {role_id} must use modelTier high")
        roles.append({"id": role_id, "mandate": text(item.get("mandate"), f"council.roles[{i}].mandate"), "modelTier": "high"})
    if len(roles) != 3 or len({r["id"] for r in roles}) != 3:
        raise ValueError("council.roles must contain exactly three unique roles")
    return roles


def validate_contract(value: object) -> EvaluationContract:
    """Return a normalized contract or raise for an unsafe or inconsistent definition."""
    root = mapping(value, "contract")
    if root.get("version") != 1:
        raise ValueError("version must be 1")
    intent = mapping(root.get("intent"), "intent")
    hooks = _hooks(mapping(root.get("validation"), "validation"))
    rubrics = _rubrics(root.get("rubrics"), {h["id"] for h in hooks})
    unused = sorted({h["id"] for h in hooks} - {hook for r in rubrics for hook in r["validationHooks"]})
    if unused:
        raise ValueError(f"validation hooks {unused} are not used by any rubric")
    roles = _roles(mapping(root.get("council"), "council"))
    decision = mapping(root.get("decision"), "decision")
    minimum = _number(decision.get("minimumScore"), "decision.minimumScore")
    if not 0 <= minimum <= 1:
        raise ValueError("decision.minimumScore must be between 0 and 1")
    return {"version": 1,
            "intent": {"workflow": text(intent.get("workflow"), "intent.workflow"),
                       "description": text(intent.get("description"), "intent.description")},
            "validation": {"hooks": hooks}, "rubrics": rubrics, "council": {"roles": roles},
            "decision": {"minimumScore": minimum,
                         "councilPasses": _int(decision.get("councilPasses"), "decision.councilPasses", 1, len(roles)),
                         "maxRevisionPasses": _int(decision.get("maxRevisionPasses"), "decision.maxRevisionPasses", 0, 3)}}


def load_contract(path: Path) -> EvaluationContract:
    """Load and validate a JSON evaluation contract."""
    if not path.is_file():
        raise FileNotFoundError(f"evaluation contract not found: {path}")
    try:
        return validate_contract(json.loads(path.read_text(encoding="utf-8")))
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error
