"""Compare the active ask's contract with a session's facts and write its provenance report."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))
from lifecycle import WORKSPACE, active, plan_status  # noqa: E402
from loop_paths import loop_dir, state_dir, state_file  # noqa: E402
from ask_plan import OPTIONS, items, refresh, ticked  # noqa: E402
import ask_packs  # noqa: E402

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


def otel_spans(workspace: Path, session: str) -> list[Json] | None:
    """Return the session's and its sub-agents' chat spans from the Copilot OTel export, or None when research telemetry wrote no export."""
    export = workspace / ".hve" / "runs" / "copilot-otel.jsonl"
    if not export.is_file():
        return None
    import metrics  # imported only when the export exists: its hve_paths resolves .hve/ from the working directory
    if metrics.OTEL_FILE.resolve() != export.resolve():
        raise ValueError(f"run the report from the workspace root {workspace}: the OTel export is read from the working directory")
    return metrics.load_chat_spans(session)[0]


def measures(workspace: Path, session: str) -> Json | None:
    """Return the session's model calls, tokens, cost, cache reads and wall clock from its metrics rows (research arms) or from the
    Copilot OTel export (research telemetry on), or None when the session was not measured."""
    rows = workspace / ".hve" / "runs" / f"{session}.jsonl"
    spans = None if rows.is_file() else otel_spans(workspace, session)
    if rows.is_file():
        calls = list({r["turn_id"]: r for r in map(json.loads, rows.read_text(encoding="utf-8").splitlines())}.values())
        times = [datetime.fromisoformat(r["ts"]).timestamp() * 1000 for r in calls]
        source = "metrics rows (research arm)"
        usage_rows = [(r["prompt_tokens"], r["completion_tokens"], r["cost_nano_aiu"], r["cache_read_tokens"] or 0) for r in calls]
    elif spans is not None:
        times = [t for s in spans for t in (s["start_ms"], s["end_ms"])]
        source = "Copilot OTel export (research telemetry)"
        usage_rows = [(s["input_tokens"], s["output_tokens"], s["cost_nano_aiu"], s["cache_read_tokens"] or 0) for s in spans]
    else:
        return None
    if not usage_rows:
        return None
    prompts = [u[0] for u in usage_rows]
    prompt = sum(prompts)
    cached = sum(u[3] for u in usage_rows)
    return {"source": source, "turns": len(usage_rows), "prompt_tokens": prompt, "first_prompt": prompts[0], "peak_prompt": max(prompts),
            "completion_tokens": sum(u[1] for u in usage_rows), "cost_aiu": round(sum(u[2] for u in usage_rows) / 1e9, 2),
            "cache_read_tokens": cached, "share": round(cached / prompt, 3) if prompt else 0.0,
            "wall_clock_s": round((max(times) - min(times)) / 1000)}


def ms(ts: str) -> float:
    """Return epoch milliseconds of an ISO 8601 timestamp."""
    return datetime.fromisoformat(ts).timestamp() * 1000


def agent_runs(workspace: Path, data: Json) -> list[Json]:
    """Return the ask's sub-agent runs from every session's agent ledger, each matched to the brief logged just before it (by time), the
    skills its role reported, and its models (from the client, or from OTel spans of sub-agents inside its start-stop window)."""
    rows = [r for p in sorted((workspace / ".hve" / "runs").glob("*.agents.jsonl"))
            for r in map(json.loads, p.read_text(encoding="utf-8").splitlines()) if r["ask"] == data["ask"]]
    stops = {r["agent_id"]: r for r in rows if r["event"] == "stop"}
    briefs = sorted(data["delegations"], key=lambda d: d["ts"])
    spans = {s: otel_spans(workspace, s) for s in {r["session"] for r in rows}}
    runs, used = [], set()
    for start in sorted((r for r in rows if r["event"] == "start"), key=lambda r: r["ts"]):
        earlier = [i for i, b in enumerate(briefs) if i not in used and ms(b["ts"]) <= ms(start["ts"]) + 1000]
        brief = briefs[earlier[-1]] if earlier else None
        used |= {earlier[-1]} if earlier else set()
        stop = stops.get(start["agent_id"])
        reported = [e["skills"] for e in data["reported"] if brief and e["persona"] == brief["persona"] and e["task"] == brief["task"]]
        window = (ms(start["ts"]), ms(stop["ts"]) if stop else float("inf"))
        traced = sorted({s["model"] for s in spans[start["session"]] or [] if s["subagent_session"] and window[0] <= s["start_ms"] <= window[1]})
        model = start["model"] or (stop or {}).get("model")
        runs.append({"agent": start["agent"], "subagent": start["subagent"], "agent_id": start["agent_id"], "session": start["session"],
                     "started": start["ts"], "seconds": round((window[1] - window[0]) / 1000) if stop else None, "brief": brief,
                     "reported": reported[-1] if reported else None,
                     "model": model or (", ".join(traced) + " (OTel)" if traced else None)})
    return runs


def agent_lines(runs: list[Json]) -> list[str]:
    """Return the Agents table: who ran each sub-agent, its brief and skills, reported skills, run time and model."""
    if not runs:
        return ["No sub-agent runs recorded for this ask (the agent ledger hook records them from 0.14.0)."]
    rows = ["| Agent | Sub-agent | Id | Session | Started | Seconds | Brief: role, skills | Reported skills | Model |",
            "|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        brief = f"{r['brief']['persona']}: {', '.join(r['brief']['skills']) or 'none'}" if r["brief"] else "no brief"
        reported = "-" if r["reported"] is None else ", ".join(r["reported"]) or "none"
        rows.append(f"| {r['agent'] or '-'} | {r['subagent']} | {r['agent_id']} | {r['session']} | {r['started'][11:19]} | "
                    f"{'-' if r['seconds'] is None else r['seconds']} | {brief} | {reported} | {r['model'] or 'not measured'} |")
    return rows


def quality(workspace: Path, data: Json) -> Json:
    """Return the ask's quality facts: its feature checks passing, milestones and tasks signed off, and the latest output evaluation since it opened."""
    features_file = loop_dir(workspace) / "feature_list.json"
    features = json.loads(features_file.read_text(encoding="utf-8")) if features_file.is_file() else []
    lock = json.loads(state_file(workspace).read_text(encoding="utf-8"))["lock"] if state_file(workspace).is_file() else None
    features = [f for f in features if lock is None or lock[f["name"]].get("ask") == data["ask"]]
    created = datetime.fromisoformat(data["created"]).timestamp()
    reports = sorted((p for p in (workspace / ".hve" / "evaluations").glob("*/report.json") if p.stat().st_mtime >= created),
                     key=lambda p: p.stat().st_mtime)
    report = json.loads(reports[-1].read_text(encoding="utf-8")) if reports else None
    signable = [i for i in items(data) if not i.startswith("opt:")]
    return {"features": (sum(f["passes"] for f in features), len(features)), "signed_off": (sum(ticked(data, i) for i in signable), len(signable)),
            "evaluation": f"{report['decision']}, score {report['score']} ({report['runId']})" if report else None}


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
    cache = measures(workspace, session)
    return {"ask": data["ask"], "lifecycle": data["lifecycle"], "source": data["source"], "agent": data["agent"], "session": session,
            "evidence": [p.relative_to(workspace).as_posix() for p in (path, loadout, deliverables) if p.is_file()],
            "plan": status, "stages": stages, "gaps": gaps, "outside_contract": sorted(used - contracted),
            "usage": usage(data, observed, workspace, session), "skill_load": data["skills"], "cache": cache,
            "packs": [{k: p[k] for k in ("name", "id", "version", "source", "sha256", "routed", "lifecycle", "agents", "templates")}
                      | {"knowledge": [d["id"] for d in p["knowledge"]]} for p in data["packs"]],
            "pack_load": ask_packs.measured(ask_packs.load(data), cache),
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
    cached = ("not measured: research telemetry was off (turn it on in Mission Control before the chat)" if measured is None else
              f"{measured['cache_read_tokens']:,} of {measured['prompt_tokens']:,} prompt tokens read from cache ({measured['share']:.0%}) "
              f"over {measured['turns']} turn(s), from {measured['source']}")
    return (f"- Skill load: {len(skills['selected'])} skills, {skills['tokens']:,} tokens against a {budget:,}-token guideline "
            f"(suggested set {skills['suggested_tokens']:,} tokens){chosen}.\n- Prompt cache: {cached}.\n")


def pillar_rows(q: Json, m: Json | None, skills: Json, created: str) -> list[str]:
    """Return the five-pillar table rows: quality from checks, sign-offs and evaluation; cost, tokens, latency and cache when measured."""
    off = "not measured (research telemetry off)"
    opened = round((datetime.now(timezone.utc) - datetime.fromisoformat(created)).total_seconds() / 60)
    passed, total = q["features"]
    signed, signable = q["signed_off"]
    checks = f"{passed}/{total} feature checks pass" if total else "no feature loop"
    source = "-" if m is None else m["source"]
    if m is None:
        cost, tokens, latency, cache = off, off, "", off
    else:
        cost = f"{m['cost_aiu']} AI units"
        tokens = (f"{m['prompt_tokens']:,} prompt tokens (first {m['first_prompt']:,}, peak {m['peak_prompt']:,}), "
                  f"{m['completion_tokens']:,} completion, {m['turns']} model calls")
        latency = f"{m['wall_clock_s']} s of model calls; "
        cache = f"{m['share']:.0%} of prompt tokens read from cache"
    return ["| Pillar | This ask | Source |", "|---|---|---|",
            f"| Quality | {checks}; {signed}/{signable} milestones and tasks signed off; evaluation: {q['evaluation'] or 'not run'} | "
            "loop, checklist, `.hve/evaluations/` |",
            f"| Cost | {cost} | {source} |",
            f"| Token efficiency | {tokens}; skill load {skills['tokens']:,} tokens | {source}, contract |",
            f"| Latency | {latency}ask open {opened} min | {source}, contract |",
            f"| Cache efficiency | {cache} | {source} |"]


def checklist_lines(data: Json, measured: Json | None) -> list[str]:
    """Return one line per checklist item with its sign-off, and a switch-off reminder when research telemetry recorded the ask."""
    lines = []
    for i in items(data):
        entry = data["checklist"].get(i)
        detail = f"{entry['value']} ({entry['by']}{': ' + entry['note'] if entry['note'] else ''})" if entry else "open"
        lines.append(f"- [{'x' if ticked(data, i) else ' '}] {i}: {detail}")
    if measured is not None:
        lines.append("\n**Research telemetry recorded this ask, with full chat content.** Turn it off when you are done: the switch in Mission "
                     "Control, or **Frontier HVE: Turn off research telemetry**.")
    return lines


def report(session: str) -> str:
    """Write <ask>/provenance.md: the five pillars, each stage's expected against used skills and authored templates, the sign-off checklist,
    recommended against used, skill load and caching, plan sync, decisions and guards."""
    path, data = active()
    refresh(path.parent, data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
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
            f"Facts from: {', '.join(f['evidence'])}.\n\n## Pillars\n\n"
            + "\n".join(pillar_rows(quality(WORKSPACE, data), f["cache"], data["skills"], data["created"]))
            + "\n\n## Stages\n\n" + "\n".join(rows)
            + "\n\n## Expertise packs\n\n" + "\n".join(ask_packs.report_lines(f["pack_load"]))
            + "\n\n## Sign-off checklist\n\n" + "\n".join(checklist_lines(data, f["cache"]))
            + "\n\n## Recommended against used\n\n" + "\n".join(usage_rows(f["usage"]))
            + f"\n\n- Gaps in done stages: {'; '.join(f['gaps']) or 'none'}.\n"
            f"- Recommended skills not used: {', '.join(f['usage']['unused_skills']) or 'none'}.\n"
            f"- Skills used outside the contract: {', '.join(f['outside_contract']) or 'none'}.\n"
            + load_lines(f["skill_load"], f["cache"]) +
            f"- Plan: {plan_line}.\n"
            f"- Guards: trips {trips}; laid down {', '.join(guards['laid_down']) or 'none'} ({guards['waived_calls']} call(s) let through); "
            f"answers {'; '.join(guards['waiver_answers']) or 'none'}.\n"
            "\n## Agents\n\n" + "\n".join(agent_lines(agent_runs(WORKSPACE, data))) + "\n"
            "\n## Decisions\n\n" + "\n".join(f"- {d['ts']} {d['stage']}: {d['choice']} — {d['why']}" for d in f["decisions"]) + "\n")
    (path.parent / "provenance.md").write_text(text, encoding="utf-8")
    return text
