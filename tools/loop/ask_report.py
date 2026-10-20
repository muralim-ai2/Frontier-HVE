"""Compare the active ask's contract with a session's facts and write its provenance report."""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lifecycle import WORKSPACE, active, plan_status  # noqa: E402
from loop_paths import state_dir  # noqa: E402

Json = dict[str, Any]


def guard_summary(workspace: Path, session: str) -> Json:
    """Return the session's guard trips per hook and kind, waiver answers, and guards laid down, from the intervention and waiver logs."""
    runs = workspace / ".hve" / "runs"
    log = runs / f"{session}.interventions.jsonl"
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []
    trips: dict[str, int] = {}
    for e in entries:
        if e["kind"] not in ("waived", "waiver_answer"):
            trips[f"{e['hook']}/{e['kind']}"] = trips.get(f"{e['hook']}/{e['kind']}", 0) + 1
    waivers = runs / f"{session}.waivers.json"
    return {"trips": trips, "waiver_answers": [f"{e['hook']}: {e['detail']}" for e in entries if e["kind"] == "waiver_answer"],
            "waived_calls": sum(e["kind"] == "waived" for e in entries),
            "laid_down": sorted(h for h, v in json.loads(waivers.read_text(encoding="utf-8")).items() if v) if waivers.is_file() else []}


def usage(data: Json, used: set[str], workspace: Path, session: str) -> Json:
    """Return recommended against used for skills, personas, tasks, MCP servers and hooks, naming the evidence for each use."""
    reported: dict[str, set[str]] = {}
    for entry in data["reported"]:
        for skill in entry["skills"]:
            reported.setdefault(skill, set()).add(entry["persona"])
    skills = [{"name": r["name"], "reason": r["reason"], "read": r["name"] in used, "reported_by": sorted(reported.get(r["name"], set()))}
              for r in data["skills"]["selected"]]
    invoked = {d["persona"] for d in data["delegations"]}
    planned = {p["agent"] for p in data["personas"]}
    personas = ([{"agent": p["agent"], "planned": True, "stages": p["stages"], "delegated": p["agent"] in invoked} for p in data["personas"]]
                + [{"agent": a, "planned": False, "stages": [], "delegated": True} for a in sorted(invoked - planned)])
    tasks = [{"name": t["name"], "milestone": t["milestone"], "persona": t["persona"], "passes": t["passes"],
              "skills": {s: any(s in e["skills"] for e in data["reported"] if e["task"] == t["name"]) for s in t["skills"]}}
             for t in data["tasks"]]
    log = state_dir(workspace) / "tool_log.jsonl"
    tools = {json.loads(line)["tool"] for line in log.read_text(encoding="utf-8").splitlines()} if log.is_file() else set()
    servers = sorted({s["name"] for s in data["environment"]["mcp_servers"]})
    mcp = [{"server": s, "called": any(t.startswith((f"mcp_{s}_", f"{s}/")) for t in tools)} for s in servers]
    fired = sorted({key.split("/")[0] for key in guard_summary(workspace, session)["trips"]}
                   | ({"skill_loader"} if (workspace / ".hve" / "runs" / f"{session}.skills.json").is_file() else set()))
    return {"skills": skills, "personas": personas, "tasks": tasks, "mcp": mcp,
            "hooks": {"configured_files": data["environment"]["hook_files"], "fired": fired},
            "unused_skills": [s["name"] for s in skills if not s["read"] and not s["reported_by"]]}


def cache(workspace: Path, session: str) -> Json | None:
    """Return the session's prompt and cache-read tokens from its research telemetry rows, or None when the session was not measured."""
    log = workspace / ".hve" / "runs" / f"{session}.jsonl"
    if not log.is_file():
        return None
    turns = {r["turn_id"]: r for r in map(json.loads, log.read_text(encoding="utf-8").splitlines())}
    if not turns:
        return None
    prompt = sum(r["prompt_tokens"] for r in turns.values())
    cached = sum(r["cache_read_tokens"] or 0 for r in turns.values())
    return {"turns": len(turns), "prompt_tokens": prompt, "cache_read_tokens": cached, "share": round(cached / prompt, 3) if prompt else 0.0}


def facts(workspace: Path, session: str) -> Json:
    """Return the active contract against the session's facts: skills used, templates authored, gaps of done stages, plan sync and guards."""
    path, data = active(workspace)
    runs = workspace / ".hve" / "runs"
    loadout = runs / f"{session}.skills.json"
    used = {Path(s).name for s in json.loads(loadout.read_text(encoding="utf-8"))["used"]} if loadout.is_file() else set()
    deliverables = workspace / ".hve" / "deliverables" / f"{session}.json"
    authored = {d["kind"] for d in json.loads(deliverables.read_text(encoding="utf-8"))["documents"]} if deliverables.is_file() else set()
    observed = used
    used = observed | {s for e in data["reported"] for s in e["skills"]}
    stages = [{"name": s["name"], "status": s["status"], "agent": s["agent"], "note": s["note"],
               "skills": {k: k in used for k in s["skills"]}, "templates": {t: t in authored for t in s["templates"]}} for s in data["stages"]]
    gaps = [f"{s['name']}: {kind} {item} expected but not {verb}" for s in stages if s["status"] == "done"
            for kind, verb in (("skills", "used"), ("templates", "authored")) for item, ok in s[kind].items() if not ok]
    status = plan_status(workspace)
    contracted = {k for s in data["stages"] for k in s["skills"]} | {r["name"] for r in data["skills"]["selected"]}
    return {"ask": data["ask"], "lifecycle": data["lifecycle"], "source": data["source"], "agent": data["agent"], "session": session,
            "evidence": [p.relative_to(workspace).as_posix() for p in (path, loadout, deliverables) if p.is_file()],
            "plan": status, "stages": stages, "gaps": gaps, "outside_contract": sorted(used - contracted),
            "usage": usage(data, observed, workspace, session), "skill_load": data["skills"], "cache": cache(workspace, session),
            "decisions": data["decisions"], "guards": guard_summary(workspace, session)}


def usage_rows(u: Json) -> list[str]:
    """Return the recommended-against-used table rows for skills, personas, tasks, MCP servers and hook files."""
    mark = {True: "✓", False: "✗"}
    rows = ["| Kind | Item | Recommended | Used | Evidence |", "|---|---|---|---|---|"]
    for s in u["skills"]:
        evidence = "; ".join([*(["read (hook)"] if s["read"] else []), *([f"reported by {', '.join(s['reported_by'])}"] if s["reported_by"] else [])])
        rows.append(f"| skill | {s['name']} | {s['reason']} | {mark[s['read'] or bool(s['reported_by'])]} | {evidence or '-'} |")
    for p in u["personas"]:
        rows.append(f"| persona | {p['agent']} | {', '.join(p['stages']) if p['planned'] else 'not planned'} | {mark[p['delegated']]} | "
                    "delegation log |")
    for t in u["tasks"]:
        skills = ", ".join(f"{k} {mark[v]}" for k, v in t["skills"].items()) or "-"
        rows.append(f"| task | {t['name']} | {t['milestone']}, {t['persona']} | {mark[t['passes']]} passes | skills reported: {skills} |")
    for m in u["mcp"]:
        rows.append(f"| MCP server | {m['server']} | available | {mark[m['called']]} | feature-loop tool log |")
    for h in u["hooks"]["configured_files"]:
        rows.append(f"| hook file | {h} | configured | - | hooks seen: {', '.join(u['hooks']['fired']) or 'none'} |")
    return rows


def load_lines(skills: Json, measured: Json | None) -> str:
    """Return the report lines for the ask's skill load against the guideline, the user's choice, and measured prompt caching."""
    budget = skills["budget"]["max_tokens"]
    choice = skills.get("choice")
    chosen = f"; choice: {choice['choice']} ({choice['over_guideline_tokens']:,} tokens over)" if choice else ""
    cached = ("not measured: per-call metrics come from the research arms' metrics hook with Copilot OTel (bench.py)" if measured is None else
              f"{measured['cache_read_tokens']:,} of {measured['prompt_tokens']:,} prompt tokens read from cache ({measured['share']:.0%}) "
              f"over {measured['turns']} turn(s), measured from Copilot OTel")
    return (f"- Skill load: {len(skills['selected'])} skills, {skills['tokens']:,} tokens against a {budget:,}-token guideline "
            f"(suggested set {skills['suggested_tokens']:,} tokens){chosen}.\n- Prompt cache: {cached}.\n")


def report(session: str) -> str:
    """Write <ask>/provenance.md: each stage's expected against used skills and authored templates, recommended against used, skill load
    and caching, plan sync, decisions and guards."""
    path = active()[0]
    f = facts(WORKSPACE, session)
    mark = {True: "✓", False: "✗"}
    rows = ["| Stage | Status | Agent | Skills expected → used | Templates expected → authored | Note |", "|---|---|---|---|---|---|"]
    for s in f["stages"]:
        skills = ", ".join(f"{k} {mark[v]}" for k, v in s["skills"].items()) or "-"
        templates = ", ".join(f"{t} {mark[v]}" for t, v in s["templates"].items()) or "-"
        rows.append(f"| {s['name']} | {s['status']} | {s['agent']} | {skills} | {templates} | {s['note']} |")
    plan = f["plan"]
    plan_line = "no plan.md" if plan is None else f"{plan['revisions']} revision(s), {'CHANGED since last sync' if plan['changed'] else 'in sync'}"
    guards = f["guards"]
    trips = ", ".join(f"{k} ×{n}" for k, n in guards["trips"].items()) or "none"
    text = (f"# Provenance: {f['ask']}\n\nLifecycle `{f['lifecycle']}` ({f['source']}), agent {f['agent']}, session {session}.\n"
            f"Facts from: {', '.join(f['evidence'])}.\n\n" + "\n".join(rows)
            + "\n\n## Recommended against used\n\n" + "\n".join(usage_rows(f["usage"]))
            + f"\n\n- Gaps in done stages: {'; '.join(f['gaps']) or 'none'}.\n"
            f"- Recommended skills not used: {', '.join(f['usage']['unused_skills']) or 'none'}.\n"
            f"- Skills used outside the contract: {', '.join(f['outside_contract']) or 'none'}.\n"
            + load_lines(f["skill_load"], f["cache"]) +
            f"- Plan: {plan_line}.\n"
            f"- Guards: trips {trips}; laid down {', '.join(guards['laid_down']) or 'none'} ({guards['waived_calls']} call(s) let through); "
            f"answers {'; '.join(guards['waiver_answers']) or 'none'}.\n"
            "\n## Decisions\n\n" + "\n".join(f"- {d['ts']} {d['stage']}: {d['choice']} — {d['why']}" for d in f["decisions"]) + "\n")
    (path.parent / "provenance.md").write_text(text, encoding="utf-8")
    return text
