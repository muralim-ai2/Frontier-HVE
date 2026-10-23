"""Expertise packs of an ask: check the user's pack choice against the routing, record what each pack brings, and measure its context
load in tokens, absolute and relative to the ask's contracted context and to a reference context window."""

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "plugins"))
sys.path.insert(0, str(ROOT / "tools" / "skills"))
import store  # noqa: E402
from recommend import read  # noqa: E402

CHARS_PER_TOKEN = 4
CORE = "core"

Json = dict[str, Any]


def chosen(workspace: Path, routed: Json, names: list[str], lifecycle: Json) -> list[Json]:
    """Return the packs the user chose (@<pack> arguments; @core for none), after checking that named packs exist, that a routed request
    records a choice, and that a pack lifecycle brings its own pack."""
    if routed["missing"]:
        raise LookupError(f"the request names packs that are not available: {routed['missing']}; install or enable them first")
    offered = routed["explicit"] + [m["name"] for m in routed["matched"]]
    if not names and (offered or lifecycle.get("pack")):
        raise ValueError(f"packs {offered or [lifecycle['pack']]} match this ask: ask the user and pass @<pack> for each chosen pack, or @core "
                         "for none")
    if CORE in names and len(names) > 1:
        raise ValueError("@core means no pack; do not combine it with packs")
    picked = [n for n in names if n != CORE]
    if lifecycle.get("pack") and lifecycle["pack"] not in picked:
        raise ValueError(f"lifecycle {lifecycle['name']} belongs to pack {lifecycle['pack']}: choose @{lifecycle['pack']} or another lifecycle")
    return [store.pack(workspace, n) for n in dict.fromkeys(picked)]


def text_tokens(value: object) -> int:
    """Return the estimated tokens of a value as the agent reads it (JSON for structures)."""
    return len(value if isinstance(value, str) else json.dumps(value)) // CHARS_PER_TOKEN


def knowledge_index(pack: Json) -> list[Json]:
    """Return the knowledge index lines an agent reads for a pack (not the documents themselves)."""
    return [{k: d[k] for k in ("id", "title", "kind", "use_when", "stages")} for d in pack["manifest"]["knowledge"]]


def record(pack: Json, routed: Json, lifecycle: Json, stages: list[Json]) -> Json:
    """Return the contract's record of one chosen pack: identity, why it was routed, what the ask uses from it, and its static tokens."""
    name, data = pack["name"], pack["manifest"]
    live = [s for s in stages if s["status"] != "skipped"]
    prefix = f"{name}:"
    agents = sorted({s["agent"][len(prefix):] for s in live if s["agent"].startswith(prefix)})
    templates = sorted({t for s in live for t in s["templates"] if t.startswith(prefix)})
    names = {s["name"] for s in live}
    docs = [d for d in data["knowledge"] if not d["stages"] or names & set(d["stages"])]
    why = next((m["why"] for m in routed["matched"] if m["name"] == name), [])
    own = lifecycle["file"] if lifecycle.get("pack") == name else None
    return {"name": name, "id": pack["id"], "version": pack["version"], "source": pack["source"], "folder": pack["folder"],
            "sha256": pack["sha256"], "routed": ["named in the request"] * (name in routed["explicit"]) + why,
            "lifecycle": lifecycle["name"] if own else None, "agents": agents, "templates": templates,
            "knowledge": [{k: d[k] for k in ("id", "title", "kind", "use_when", "stages", "tokens")} | {"path": f"{pack['folder']}/{d['file']}"}
                          for d in docs],
            "evaluation": f"{pack['folder']}/{data['evaluation']}" if data["evaluation"] else None,
            "tokens": {"index": data["manifest_tokens"], "knowledge_index": text_tokens(knowledge_index(pack)),
                       "lifecycle": data["lifecycles"][lifecycle["name"]]["tokens"] if own else 0,
                       "knowledge": sum(d["tokens"] for d in docs),
                       "agents": sum(a["tokens"] for a in data["agents"] if a["name"] in agents),
                       "templates": sum(t["tokens"] for k, t in data["templates"].items() if f"{prefix}{k}" in templates)}}


def window() -> int:
    """Return the reference context window the shares are measured against (the first of the context-load reference windows)."""
    return read("categories.json")["context_load"]["reference_windows"][0]


def share(part: int, whole: int) -> float:
    """Return part as a percentage of whole, to one decimal."""
    return round(part / whole * 100, 1) if whole else 0.0


def load(data: Json) -> Json:
    """Return each chosen pack's context load: always-loaded tokens (manifest index, knowledge index, its lifecycle, its selected skills)
    and on-demand tokens (knowledge documents, pack agents, pack templates), absolute and as a share of the ask's contracted context
    (all selected skills plus the packs' always-loaded parts) and of the reference window."""
    packs = data.get("packs", [])
    skills = {p["name"]: sum(r["skill_tokens"] for r in data["skills"]["selected"] if r["name"].startswith(f"{p['name']}:")) for p in packs}
    always = {p["name"]: p["tokens"]["index"] + p["tokens"]["knowledge_index"] + p["tokens"]["lifecycle"] + skills[p["name"]] for p in packs}
    context = data["skills"]["tokens"] + sum(always[n] - skills[n] for n in always)
    size = window()
    rows = []
    for p in packs:
        t = p["tokens"]
        demand = t["knowledge"] + t["agents"] + t["templates"]
        rows.append({"name": p["name"], "version": p["version"], "skills": skills[p["name"]], "always": always[p["name"]],
                     "on_demand": demand, "total": always[p["name"]] + demand,
                     "share_of_ask_context_pct": share(always[p["name"]], context), "share_of_window_pct": share(always[p["name"]], size),
                     "on_demand_share_of_window_pct": share(demand, size)} | {k: t[k] for k in ("index", "knowledge_index", "lifecycle",
                                                                                                     "knowledge", "agents", "templates")})
    total = sum(always.values())
    return {"packs": rows, "always": total, "on_demand": sum(r["on_demand"] for r in rows), "ask_context_tokens": context,
            "share_of_ask_context_pct": share(total, context), "window": size, "share_of_window_pct": share(total, size)}


def measured(pack_load: Json, prompt_tokens: Json | None) -> Json:
    """Return the pack load with each pack's always-loaded share of the first and peak measured prompt, when the session was measured."""
    if prompt_tokens is None:
        return pack_load | {"measured": None}
    first, peak = prompt_tokens["first_prompt"], prompt_tokens["peak_prompt"]
    rows = [r | {"share_of_first_prompt_pct": share(r["always"], first), "share_of_peak_prompt_pct": share(r["always"], peak)}
            for r in pack_load["packs"]]
    return pack_load | {"packs": rows, "measured": {"first_prompt": first, "peak_prompt": peak, "source": prompt_tokens["source"],
                                                     "share_of_first_prompt_pct": share(pack_load["always"], first)}}


def brief_lines(data: Json, stage: Json) -> list[str]:
    """Return the brief lines naming the stage's pack agent and the pack knowledge to open when its use-when applies."""
    lines = []
    pack, _, agent = stage["agent"].partition(":")
    folder = next((p["folder"] for p in data.get("packs", []) if p["name"] == pack), None)
    if agent and folder:
        lines.append(f"- Pack agent for this stage: {stage['agent']} (its instructions: {folder}/agents/{agent}.agent.md)")
    docs = [d for p in data.get("packs", []) for d in p["knowledge"] if not d["stages"] or stage["name"] in d["stages"]]
    if docs:
        lines.append("- Pack knowledge (open a document only when its use-when applies): "
                     + "; ".join(f"{d['title']} ({d['kind']}, {d['tokens']:,} tokens) at {d['path']}: use when {d['use_when']}" for d in docs))
    return lines


def report_lines(pack_load: Json) -> list[str]:
    """Return the provenance table of each pack's context load: absolute tokens, share of the ask's context, of the window and, when the
    session was measured, of its first and peak prompt."""
    if not pack_load["packs"]:
        return ["No expertise packs: core only."]
    m = pack_load["measured"]
    rows = ["| Pack | Always loaded (index, knowledge index, lifecycle, skills) | On demand (knowledge, agents, templates) | "
            "Share of ask context | Share of window | Share of first / peak prompt |", "|---|---|---|---|---|---|"]
    for r in pack_load["packs"]:
        prompt = f"{r['share_of_first_prompt_pct']}% / {r['share_of_peak_prompt_pct']}%" if m else "not measured"
        rows.append(f"| {r['name']} {r['version']} | {r['always']:,} ({r['index']:,}, {r['knowledge_index']:,}, {r['lifecycle']:,}, "
                    f"{r['skills']:,}) | {r['on_demand']:,} ({r['knowledge']:,}, {r['agents']:,}, {r['templates']:,}) | "
                    f"{r['share_of_ask_context_pct']}% | {r['share_of_window_pct']}% | {prompt} |")
    rows.append(f"\nAll packs: {pack_load['always']:,} tokens always loaded ({pack_load['share_of_ask_context_pct']}% of the "
                f"{pack_load['ask_context_tokens']:,}-token ask context, {pack_load['share_of_window_pct']}% of a {pack_load['window']:,}-token "
                f"window), {pack_load['on_demand']:,} on demand." + (f" Measured from {m['source']}." if m else ""))
    return rows


def plan_lines(data: Json) -> str:
    """Return the plan.md section listing the ask's packs, why each was routed, what the ask uses from it and its context load."""
    if not data.get("packs"):
        return "Expertise packs: none (core only).\n"
    pack_load = data["pack_load"]
    rows = "\n".join(f"| {r['name']} {r['version']} | {r['always']:,} | {r['share_of_ask_context_pct']}% | {r['share_of_window_pct']}% | "
                     f"{r['on_demand']:,} |" for r in pack_load["packs"])
    detail = "\n".join(f"- {p['name']}: routed by {', '.join(p['routed']) or 'the user'}; lifecycle {p['lifecycle'] or 'none'}; agents "
                       f"{', '.join(p['agents']) or 'none'}; templates {', '.join(p['templates']) or 'none'}; knowledge "
                       f"{', '.join(d['id'] for d in p['knowledge']) or 'none'}" for p in data["packs"])
    return (f"Expertise packs ({pack_load['always']:,} tokens always loaded, {pack_load['share_of_ask_context_pct']}% of this ask's "
            f"{pack_load['ask_context_tokens']:,}-token contracted context, {pack_load['share_of_window_pct']}% of a "
            f"{pack_load['window']:,}-token window):\n\n| Pack | Always loaded | Share of ask context | Share of window | On demand |\n"
            f"|---|---|---|---|---|\n{rows}\n\n{detail}\n")
