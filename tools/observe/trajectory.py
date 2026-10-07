"""Trajectory view of one session (timeline, hook interventions, features, context-rot check) and per-run context growth."""

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "research" / "runs"
ROT_WINDOW = 10
ROT_DROP = 0.2
BAR_TOKENS = 5000
TOOL_STATUS = {True: "", False: " (FAILED)", None: " (unsettled)"}

Json = dict[str, Any]


def read_rows(session_id: str) -> list[Json]:
    """Return the session's metrics rows in time order."""
    path = RUNS_DIR / f"{session_id}.jsonl"
    return sorted((json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()), key=lambda r: r["ts"])


def context_rot(rows: list[Json]) -> Json:
    """Return the first tool call whose sliding-window success rate fell more than 20 points below the first window's rate."""
    outcomes = [r["tool_ok"] for r in rows if r["tool_name"] and r["tool_ok"] is not None]
    if len(outcomes) < 2 * ROT_WINDOW:
        return {"checked": False, "reason": f"{len(outcomes)} settled tool calls; need {2 * ROT_WINDOW}"}
    rates = [sum(outcomes[i:i + ROT_WINDOW]) / ROT_WINDOW for i in range(len(outcomes) - ROT_WINDOW + 1)]
    for i, rate in enumerate(rates):
        if rate < rates[0] - ROT_DROP:
            return {"checked": True, "rot": True, "from_tool_call": i + ROT_WINDOW, "baseline": rates[0], "rate": rate}
    return {"checked": True, "rot": False, "baseline": rates[0], "min_rate": min(rates)}


def growth(rows: list[Json]) -> Json:
    """Return the main conversation's prompt size per model call (the context actually sent) and its last/first ratio."""
    sizes = [r["prompt_tokens"] for r in {r["turn_id"]: r for r in rows if r["subagent_session"] is None}.values()]
    return {"calls": len(sizes), "first": sizes[0], "last": sizes[-1], "peak": max(sizes), "ratio": round(sizes[-1] / sizes[0], 2),
            "sizes": sizes}


def interventions(session_id: str) -> list[Json]:
    """Return the hook interventions recorded for the session."""
    path = RUNS_DIR / f"{session_id}.interventions.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def features(session_id: str) -> list[Json] | None:
    """Return the collected project's feature_list.json, or None when the run did not use the loop."""
    manifest = RUNS_DIR / f"{session_id}.run.json"
    if not manifest.exists():
        return None
    path = ROOT / json.loads(manifest.read_text(encoding="utf-8"))["output_dir"] / "feature_list.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def render(session_id: str) -> str:
    """Return the session timeline: per model call its tokens and tools, then interventions, features, rot, and growth."""
    rows = read_rows(session_id)
    lines = [f"session {session_id} ({rows[0]['mode']})", "call | time | who | model/effort | prompt | cache_read | completion | tools"]
    for n, turn_id in enumerate(dict.fromkeys(r["turn_id"] for r in rows), 1):
        turn = [r for r in rows if r["turn_id"] == turn_id]
        first = turn[0]
        tools = ", ".join(f"{r['tool_name']}{TOOL_STATUS[r['tool_ok']]}" for r in turn if r["tool_name"])
        who = "main" if first["subagent_session"] is None else f"sub:{first['subagent_session'][:8]}"
        lines.append(f"{n:>3} | {first['ts'][11:19]} | {who} | {first['model']}/{first['reasoning_effort']} | {first['prompt_tokens']:,} "
                     f"{'#' * (first['prompt_tokens'] // BAR_TOKENS)} | {first['cache_read_tokens']} | {first['completion_tokens']:,} | {tools}")
    for i in interventions(session_id):
        lines.append(f"intervention: {i['hook']} {i['kind']}{' [' + i['blindspot'] + ']' if i['blindspot'] else ''}: {i['detail'][:200]}")
    feats = features(session_id)
    if feats is not None:
        lines.append("features: " + ", ".join(f"{f['name']}={'pass' if f['passes'] else 'FAIL'}" for f in feats))
    lines.append(f"context rot: {json.dumps(context_rot(rows))}")
    g = growth(rows)
    lines.append(f"context growth: {g['first']:,} -> {g['last']:,} tokens over {g['calls']} calls (x{g['ratio']}, peak {g['peak']:,})")
    return "\n".join(lines)


def growth_table() -> str:
    """Return one context-growth line per collected run, for comparing modes."""
    lines = ["session | mode | calls | first | last | peak | last/first"]
    for manifest in sorted(RUNS_DIR.glob("*.run.json")):
        run = json.loads(manifest.read_text(encoding="utf-8"))
        g = growth(read_rows(run["session_id"]))
        lines.append(f"{run['session_id'][:8]} | {run['mode']} | {g['calls']} | {g['first']:,} | {g['last']:,} | {g['peak']:,} | {g['ratio']}")
    return "\n".join(lines)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--growth"]:
        print(growth_table())
    elif len(args) == 1:
        print(render(args[0]))
    else:
        raise SystemExit("usage: trajectory.py <session_id> | --growth")
