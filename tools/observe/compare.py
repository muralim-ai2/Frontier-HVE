"""Compare benchmark runs by mode and model, ranked Quality > Tokens > Latency > Cache, from hook/OTel metrics and blind scores."""

import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "research" / "runs"
BLIND_DIR = ROOT / "research" / "blind"
OUT_FILE = ROOT / "research" / "comparisons" / "comparison.json"
METRICS = ("human_score", "ai_score", "prompt_tokens", "completion_tokens", "cache_ratio", "cost_aiu", "model_calls", "tool_calls",
           "subagent_calls", "wall_clock_s")

Json = dict[str, Any]


class RunSummary(TypedDict):
    """Per-run totals; token and cost sums count each model call once."""

    session_id: str
    mode: str
    model: str
    reasoning_effort: str
    human_score: float | None
    ai_score: float | None
    prompt_tokens: int
    completion_tokens: int
    cache_ratio: float
    cost_aiu: float
    model_calls: int
    tool_calls: int
    subagent_calls: int
    wall_clock_s: float


def blind_scores() -> dict[str, Json]:
    """Return scores by session id from every blind round, joined through each round's key.json."""
    scores: dict[str, Json] = {}
    for key_file in sorted(BLIND_DIR.glob("round-*/key.json")):
        key = json.loads(key_file.read_text(encoding="utf-8"))
        sheet = json.loads((key_file.parent / "scores.json").read_text(encoding="utf-8"))
        for label, entry in key.items():
            scores[entry["session_id"]] = sheet[label]
    return scores


def summarize(manifest: Json, scores: dict[str, Json]) -> RunSummary:
    """Return totals for one collected run."""
    sid = manifest["session_id"]
    rows = [json.loads(line) for line in (RUNS_DIR / f"{sid}.jsonl").read_text(encoding="utf-8").splitlines()]
    turns = list({r["turn_id"]: r for r in rows}.values())
    prompt = sum(t["prompt_tokens"] for t in turns)
    score = scores.get(sid, {})
    tag_file = RUNS_DIR / f"{sid}.skill.json"
    tag = json.loads(tag_file.read_text(encoding="utf-8")) if tag_file.exists() else {"condition": "without"}
    return RunSummary(
        session_id=sid, mode=manifest["mode"] + (f"+{tag['skill']}" if tag["condition"] == "with" else ""),
        model=",".join(sorted({t["model"] for t in turns if t["subagent_session"] is None})),
        reasoning_effort=",".join(sorted({str(t["reasoning_effort"]) for t in turns if t["subagent_session"] is None})),
        human_score=score.get("human_score"), ai_score=score.get("ai_score"),
        prompt_tokens=prompt, completion_tokens=sum(t["completion_tokens"] for t in turns),
        cache_ratio=round(sum(t["cache_read_tokens"] or 0 for t in turns) / prompt, 3),
        cost_aiu=round(sum(t["cost_nano_aiu"] for t in turns) / 1e9, 2),
        model_calls=len(turns), tool_calls=sum(1 for r in rows if r["tool_name"]),
        subagent_calls=sum(1 for t in turns if t["subagent_session"]),
        wall_clock_s=(datetime.fromisoformat(manifest["ended"]) - datetime.fromisoformat(manifest["started"])).total_seconds(),
    )


def aggregate(runs: list[RunSummary]) -> list[Json]:
    """Return one row per (mode, model) with mean and std dev of each metric, ranked Quality > Tokens > Latency > Cache."""
    groups: dict[tuple[str, str, str], list[RunSummary]] = {}
    for run in runs:
        groups.setdefault((run["mode"], run["model"], run["reasoning_effort"]), []).append(run)
    table: list[Json] = []
    for (mode, model, effort), members in groups.items():
        row: Json = {"mode": mode, "model": model, "effort": effort, "runs": len(members)}
        for metric in METRICS:
            values = [m[metric] for m in members if m[metric] is not None]
            row[metric] = round(statistics.mean(values), 2) if values else None
            row[f"{metric}_sd"] = round(statistics.stdev(values), 2) if len(values) > 1 else None
        table.append(row)
    def score(row: Json, metric: str) -> float:
        """Return a quality score for ranking; unscored runs rank below every scored one."""
        return row[metric] if row[metric] is not None else -1.0

    return sorted(table, key=lambda r: (-score(r, "human_score"), -score(r, "ai_score"), r["prompt_tokens"], r["wall_clock_s"], -r["cache_ratio"]))


def render(table: list[Json]) -> str:
    """Return the ranked table as Markdown."""
    head = "| rank | mode | model | effort | runs | " + " | ".join(METRICS) + " |"
    lines = [head, "|" + "---|" * (head.count("|") - 1)]
    for rank, row in enumerate(table, 1):
        cells = [f"{row[m]}" + (f" ±{row[m + '_sd']}" if row[f"{m}_sd"] is not None else "") for m in METRICS]
        lines.append(f"| {rank} | {row['mode']} | {row['model']} | {row['effort']} | {row['runs']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    """Print the ranked comparison and write runs + table to research/comparisons/comparison.json."""
    scores = blind_scores()
    runs = [summarize(json.loads(p.read_text(encoding="utf-8")), scores) for p in sorted(RUNS_DIR.glob("*.run.json"))]
    if not runs:
        raise FileNotFoundError(f"no collected runs (*.run.json) in {RUNS_DIR}")
    table = aggregate(runs)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({"runs": runs, "table": table}, indent=2) + "\n", encoding="utf-8")
    print(render(table))


if __name__ == "__main__":
    main()
