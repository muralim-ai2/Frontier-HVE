"""Plugin evaluation contracts: check them against the core contract, check the agent's core-rubric selection, and combine both."""

from typing import Any

from contract import EvaluationContract, items, mapping, text, validate_contract

ALWAYS = ("evidence-verification", "safety-maintainability")
NOT_APPLICABLE = "not-applicable-output-kind"
COVERED = "covered-by:"
CORE_SHARE = (0.2, 0.5)
PLUGIN_KEYS = {"version", "intent", "coreShare", "validation", "rubrics", "decision"}

Json = dict[str, Any]


def plugin_contract(raw: object, core: EvaluationContract) -> Json:
    """Return {coreShare, contract} for a valid plugin contract; core hooks it references keep their core definition."""
    root = mapping(raw, "plugin contract")
    if set(root) != PLUGIN_KEYS:
        raise ValueError(f"a plugin contract has exactly the keys {sorted(PLUGIN_KEYS)} (council and revision limit come from the core); "
                         f"got {sorted(root)}")
    share = root["coreShare"]
    if isinstance(share, bool) or not isinstance(share, (int, float)) or not CORE_SHARE[0] <= share <= CORE_SHARE[1]:
        raise ValueError(f"coreShare must be a number from {CORE_SHARE[0]} to {CORE_SHARE[1]}")
    core_hooks = {h["id"]: h for h in core["validation"]["hooks"]}
    own = [mapping(h, f"validation.hooks[{i}]") for i, h in enumerate(items(mapping(root["validation"], "validation").get("hooks"),
                                                                                "validation.hooks"))]
    for hook in own:
        if hook.get("type") == "command":
            raise ValueError(f"plugin validation hook {hook.get('id')!r} is a command; plugins may use feature-checks and artifacts only")
        if hook.get("id") in core_hooks:
            raise ValueError(f"plugin validation hook id {hook['id']!r} is a core hook id; reference it from a rubric instead")
    rubrics = [mapping(r, f"rubrics[{i}]") for i, r in enumerate(items(root["rubrics"], "rubrics"))]
    reused = sorted({r.get("id") for r in rubrics} & {r["id"] for r in core["rubrics"]})
    if reused:
        raise ValueError(f"plugin rubric ids {reused} are core rubric ids")
    referenced = sorted({h for r in rubrics for h in items(r.get("validationHooks"), "rubric validationHooks") if h in core_hooks})
    decision = mapping(root["decision"], "decision")
    if set(decision) != {"minimumScore", "councilPasses"}:
        raise ValueError("a plugin contract decision has exactly minimumScore and councilPasses")
    contract = validate_contract({"version": root["version"], "intent": root["intent"], "rubrics": rubrics,
                                  "validation": {"hooks": own + [core_hooks[h] for h in referenced]},
                                  "council": core["council"],
                                  "decision": decision | {"maxRevisionPasses": core["decision"]["maxRevisionPasses"]}})
    for key in ("minimumScore", "councilPasses"):
        if contract["decision"][key] < core["decision"][key]:
            raise ValueError(f"plugin decision.{key} {contract['decision'][key]} is below the core value {core['decision'][key]}")
    return {"coreShare": float(share), "contract": contract}


def selection(raw: object, core: EvaluationContract, plugin: Json, output_kind: str) -> Json:
    """Return the agent's validated choice of core rubrics: each listed once, the always-rubrics included, exclusions justified."""
    root = mapping(raw, "rubric selection")
    if set(root) != {"include", "exclude", "reasons"}:
        raise ValueError("a rubric selection has exactly include, exclude and reasons")
    include = [text(r, "include[]") for r in items(root["include"], "include")]
    exclude = {text(k, "exclude key"): text(v, f"exclude.{k}") for k, v in mapping(root["exclude"], "exclude").items()}
    reasons = {text(k, "reasons key"): text(v, f"reasons.{k}") for k, v in mapping(root["reasons"], "reasons").items()}
    core_ids = [r["id"] for r in core["rubrics"]]
    listed = include + list(exclude)
    if sorted(listed) != sorted(core_ids):
        raise ValueError(f"list every core rubric exactly once in include or exclude: {core_ids}; got {listed}")
    dropped = [r for r in ALWAYS if r in exclude]
    if dropped:
        raise ValueError(f"core rubrics {dropped} always apply and cannot be excluded")
    hooks = {h["id"]: h for h in core["validation"]["hooks"]}
    plugin_ids = {r["id"] for r in plugin["contract"]["rubrics"]}
    for rubric in (r for r in core["rubrics"] if r["id"] in exclude):
        reason = exclude[rubric["id"]]
        if reason == NOT_APPLICABLE:
            if any(output_kind in hooks[h]["outputKinds"] for h in rubric["validationHooks"]):
                raise ValueError(f"{rubric['id']} has validation for output kind {output_kind!r}, so it is applicable")
        elif reason.startswith(COVERED):
            if reason[len(COVERED):] not in plugin_ids:
                raise ValueError(f"{rubric['id']} is {reason}, which is not a plugin rubric {sorted(plugin_ids)}")
            if rubric["id"] not in reasons:
                raise ValueError(f"reasons.{rubric['id']} must say in one sentence how the plugin rubric covers it")
        else:
            raise ValueError(f"exclude.{rubric['id']} must be {NOT_APPLICABLE!r} or '{COVERED}<plugin rubric id>'")
    extra = sorted(set(reasons) - {k for k, v in exclude.items() if v.startswith(COVERED)})
    if extra:
        raise ValueError(f"reasons are only for covered-by exclusions; unexpected {extra}")
    return {"include": include, "exclude": exclude, "reasons": reasons}


def combine(core: EvaluationContract, plugin: Json, chosen: Json) -> EvaluationContract:
    """Return one contract: plugin rubrics weighted to 1 - coreShare, included core rubrics to coreShare, the stricter decision."""
    share = plugin["coreShare"]
    own = plugin["contract"]
    included = [r for r in core["rubrics"] if r["id"] in chosen["include"]]
    core_total = sum(r["weight"] for r in included)
    rubrics = ([r | {"weight": r["weight"] * (1 - share)} for r in own["rubrics"]]
               + [r | {"weight": r["weight"] / core_total * share} for r in included])
    used = {h for r in rubrics for h in r["validationHooks"]}
    hooks = {h["id"]: h for h in own["validation"]["hooks"] + core["validation"]["hooks"] if h["id"] in used}
    return validate_contract({"version": 1, "intent": {"workflow": core["intent"]["workflow"], "description": own["intent"]["description"]},
                              "validation": {"hooks": list(hooks.values())}, "rubrics": rubrics, "council": core["council"],
                              "decision": {"minimumScore": own["decision"]["minimumScore"],
                                           "councilPasses": own["decision"]["councilPasses"],
                                           "maxRevisionPasses": core["decision"]["maxRevisionPasses"]}})
