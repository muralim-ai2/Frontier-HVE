"""Hook that joins tool-call hook events with Copilot OTel chat spans into research/runs/<session_id>.jsonl."""

import gzip
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "research" / "runs"
AGENTS_DIR = ROOT / ".github" / "agents"
OTEL_FILE = RUNS_DIR / "copilot-otel.jsonl"
OTEL_ARCHIVE_DIR = RUNS_DIR / "otel"
MODE_AGENTS = {"minimal": "minimal", "single": "single", "harness": "creator", "flow": "creator-flow"}
MODEL_LINE = re.compile(r"^model:\s*(.+)$", re.MULTILINE)
STOP_EVENTS = ("Stop", "SubagentStop")
CACHE_KEYS = ("gen_ai.usage.cache_read.input_tokens", "gen_ai.usage.cache_creation.input_tokens")
STATUS_ERROR = 2
SESSION_ID = re.compile(r"^[\w-]+$")

Json = dict[str, Any]
EventName = Literal["PreToolUse", "PostToolUse", "Stop", "SubagentStop"]


class HookEvent(TypedDict):
    """One hook firing as stored in <session_id>.events.jsonl."""

    event: EventName
    mode: str
    ts_ms: float
    tool_use_id: str | None
    tool_name: str | None
    transcript_path: str | None


class ChatSpan(TypedDict):
    """Token usage of one LLM call read from a Copilot OTel chat span."""

    span_id: str
    window: str
    subagent_session: str | None
    start_ms: float
    end_ms: float
    model: str
    input_tokens: int
    output_tokens: int
    cache_tokens: int | None
    cache_read_tokens: int | None
    cost_nano_aiu: int
    reasoning_effort: str | None


class MetricRecord(TypedDict):
    """One line of research/runs/<session_id>.jsonl."""

    session_id: str
    mode: str
    subagent_session: str | None
    turn_id: str
    ts: str
    model: str
    prompt_tokens: int
    context_tokens: int
    cache_tokens: int | None
    cache_read_tokens: int | None
    completion_tokens: int
    cost_nano_aiu: int
    reasoning_effort: str | None
    tool_name: str | None
    tool_ok: bool | None
    latency_ms: int | None


def iso_to_ms(ts: str) -> float:
    """Return epoch milliseconds for an ISO 8601 timestamp."""
    return datetime.fromisoformat(ts).timestamp() * 1000


def ms_to_iso(ms: float) -> str:
    """Return a millisecond-precision ISO 8601 UTC timestamp for epoch milliseconds."""
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="milliseconds")


def hrtime_to_ms(hr: list[int]) -> float:
    """Return epoch milliseconds for an OTel [seconds, nanoseconds] tuple."""
    return hr[0] * 1000 + hr[1] / 1_000_000


def read_jsonl(path: Path) -> list[Json]:
    """Return the complete lines of an append-only JSONL file, excluding a tail still being written."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n")[:-1] if line]


def to_event(payload: Json, mode: str) -> HookEvent:
    """Return the timing-relevant subset of a hook payload, plus the transcript path on Stop events."""
    name = payload["hook_event_name"]
    if name in ("PreToolUse", "PostToolUse"):
        tool_use_id, tool_name, transcript = payload["tool_use_id"], payload["tool_name"], None
    elif name in STOP_EVENTS:
        tool_use_id = tool_name = None
        transcript = payload["transcript_path"]
    else:
        raise ValueError(f"metrics.py does not handle hook event {name!r}")
    return HookEvent(event=name, mode=mode, ts_ms=iso_to_ms(payload["timestamp"]),
                     tool_use_id=tool_use_id, tool_name=tool_name, transcript_path=transcript)


def request_effort(attrs: Json) -> str | None:
    """Return the reasoning effort Copilot actually requested (OpenAI `reasoning.effort` or Anthropic `output_config.effort`), if any."""
    options = json.loads(attrs["copilot_chat.request.options"])
    for key in ("reasoning", "output_config"):
        if "effort" in options.get(key, {}):
            return options[key]["effort"]
    return None  # models without a reasoning setting


def parse_chat_span(rec: Json, session_id: str) -> ChatSpan:
    """Return token usage and timing of a chat span record of the session or one of its sub-agents."""
    attrs = rec["attributes"]
    cache = [attrs[k] for k in CACHE_KEYS if k in attrs]
    conversation = attrs["copilot_chat.chat_session_id"]
    try:
        return ChatSpan(
            span_id=rec["spanId"],
            window=rec["resource"]["attributes"]["session.id"],
            subagent_session=None if conversation == session_id else conversation,
            start_ms=hrtime_to_ms(rec["startTime"]),
            end_ms=hrtime_to_ms(rec["endTime"]),
            model=attrs["gen_ai.response.model"],
            input_tokens=attrs["gen_ai.usage.input_tokens"],
            output_tokens=attrs["gen_ai.usage.output_tokens"],
            cache_tokens=sum(cache) if cache else None,
            cache_read_tokens=attrs[CACHE_KEYS[0]] if CACHE_KEYS[0] in attrs else None,
            cost_nano_aiu=attrs["copilot_chat.copilot_usage_nano_aiu"],
            reasoning_effort=request_effort(attrs),
        )
    except KeyError as missing:
        raise KeyError(f"chat span {rec['spanId']} in {OTEL_FILE} lacks {missing}") from missing


def belongs(attrs: Json, session_id: str) -> bool:
    """Return True for spans of the session or its sub-agents; utility calls carry no chat_session_id (decision D-006)."""
    return "copilot_chat.chat_session_id" in attrs and session_id in (attrs["copilot_chat.chat_session_id"],
                                                                    attrs.get("copilot_chat.parent_chat_session_id"))


def archive_file(session_id: str) -> Path:
    """Return the gzip archive path of a pruned session's OTel records."""
    return OTEL_ARCHIVE_DIR / f"{session_id}.otel.jsonl.gz"


def otel_records(session_id: str) -> tuple[list[Json], dict[str, float]]:
    """Return the OTel records to read for a session and the per-window export watermark: its archive once pruned, else the live export."""
    archive = archive_file(session_id)
    if archive.exists():
        lines = gzip.decompress(archive.read_bytes()).decode("utf-8").splitlines()
        return [json.loads(line) for line in lines[1:]], json.loads(lines[0])["window_end"]
    if not OTEL_FILE.exists():
        raise FileNotFoundError(f"{OTEL_FILE} missing: add the Copilot OTel file-export settings to VS Code User settings (decision D-005) and reload the window")
    return read_jsonl(OTEL_FILE), {}


def load_chat_spans(session_id: str) -> tuple[list[ChatSpan], list[str], dict[str, str | None], dict[str, float]]:
    """Return the session's and its sub-agents' completed chat spans in end order, ids of its errored or canceled chat spans, the conversation (None = the session itself) of each tool call id, and the latest exported span end per VS Code window."""
    spans: list[ChatSpan] = []
    failed: list[str] = []
    tools: dict[str, str | None] = {}
    records, window_end = otel_records(session_id)
    for rec in records:
        if "ended" not in rec:  # log and metric records share the file with spans
            continue
        window = rec["resource"]["attributes"]["session.id"]
        window_end[window] = max(window_end.get(window, 0.0), hrtime_to_ms(rec["endTime"]))
        attrs = rec["attributes"]
        if not belongs(attrs, session_id):
            continue
        conversation = attrs["copilot_chat.chat_session_id"]
        operation = attrs.get("gen_ai.operation.name")
        if operation == "execute_tool":
            tools[attrs["gen_ai.tool.call.id"]] = None if conversation == session_id else conversation
        elif operation == "chat" and rec["status"]["code"] == STATUS_ERROR:  # errored or canceled calls report no usage (decision D-007)
            failed.append(rec["spanId"])
        elif operation == "chat":
            spans.append(parse_chat_span(rec, session_id))
    return sorted(spans, key=lambda s: s["end_ms"]), failed, tools, window_end


def call_id(event: HookEvent) -> str:
    """Return the model's tool call id inside a hook tool_use_id such as 'call_X__vscode-123'."""
    return str(event["tool_use_id"]).split("__vscode")[0]


def build_records(session_id: str, events: list[HookEvent], spans: list[ChatSpan], tools: dict[str, str | None],
                  watermark: float) -> tuple[list[MetricRecord], list[str]]:
    """Return chronological records, one per tool call and per tool-less turn, from events the OTel export has settled, and the settled tool calls OTel has no execute_tool span for."""
    settled = [e for e in events if e["ts_ms"] <= watermark]  # spans export in end order, so earlier spans are all present
    mode = events[0]["mode"]
    posts = {e["tool_use_id"]: e["ts_ms"] for e in settled if e["event"] == "PostToolUse"}
    stops = [e["ts_ms"] for e in settled if e["event"] in STOP_EVENTS]
    pres = [e for e in settled if e["event"] == "PreToolUse"]
    records: list[MetricRecord] = []
    conversations: defaultdict[str | None, list[ChatSpan]] = defaultdict(list)
    for span in spans:
        conversations[span["subagent_session"]].append(span)
    for conversation, conv_spans in conversations.items():
        context = 0
        conv_pres = [e for e in pres if call_id(e) in tools and tools[call_id(e)] == conversation]
        for i, span in enumerate(conv_spans):
            context += span["input_tokens"]
            next_end = conv_spans[i + 1]["end_ms"] if i + 1 < len(conv_spans) else float("inf")
            closed = i + 1 < len(conv_spans) or any(ts >= span["end_ms"] for ts in stops)
            span_pres = [e for e in conv_pres if span["end_ms"] <= e["ts_ms"] < next_end]
            base = dict(session_id=session_id, mode=mode, subagent_session=conversation, turn_id=span["span_id"],
                        model=span["model"], prompt_tokens=span["input_tokens"], context_tokens=context,
                        cache_tokens=span["cache_tokens"], cache_read_tokens=span["cache_read_tokens"],
                        completion_tokens=span["output_tokens"], cost_nano_aiu=span["cost_nano_aiu"],
                        reasoning_effort=span["reasoning_effort"])
            if not span_pres and closed:
                records.append(MetricRecord(**base, ts=ms_to_iso(span["end_ms"]), tool_name=None, tool_ok=None,
                                            latency_ms=round(span["end_ms"] - span["start_ms"])))
            for pre in span_pres:
                post = posts.get(pre["tool_use_id"])  # PostToolUse fires only on success
                if post is None and not closed:
                    continue
                records.append(MetricRecord(**base, ts=ms_to_iso(pre["ts_ms"]), tool_name=pre["tool_name"],
                                            tool_ok=post is not None,
                                            latency_ms=None if post is None else round(post - pre["ts_ms"])))
    unmatched = [str(e["tool_use_id"]) for e in pres if call_id(e) not in tools]
    return sorted(records, key=lambda r: r["ts"]), unmatched


def compute(events_path: Path) -> tuple[list[MetricRecord], list[str]]:
    """Return the session's metrics records from its hook events and OTel records, and any data-completeness problems."""
    session_id = events_path.name.removesuffix(".events.jsonl")
    events: list[HookEvent] = read_jsonl(events_path)  # type: ignore[assignment]
    spans, failed, tools, window_end = load_chat_spans(session_id)
    records, unmatched = build_records(session_id, events, spans, tools, window_end[spans[-1]["window"]]) if spans else ([], [])
    problems = [f"errored or canceled chat calls {failed} whose tokens OTel does not report"] if failed else []
    if unmatched:
        problems.append(f"tool calls {unmatched} without an OTel execute_tool span, so their conversation is unknown")
    return records, problems


def rebuild(events_path: Path) -> tuple[list[MetricRecord], list[str]]:
    """Rewrite the session's metrics JSONL; return its records and any data-completeness problems."""
    records, problems = compute(events_path)
    out = RUNS_DIR / events_path.name.replace(".events.jsonl", ".jsonl")
    tmp = out.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    os.replace(tmp, out)
    return records, problems


def pinned_model(mode: str) -> str:
    """Return the model id pinned in the agent file of a harness mode."""
    path = AGENTS_DIR / f"{MODE_AGENTS[mode]}.agent.md"
    match = MODEL_LINE.search(path.read_text(encoding="utf-8").split("---", 2)[1])
    if not match:
        raise LookupError(f"{path} frontmatter has no 'model:' line")
    return match.group(1).strip().lower().removesuffix(" (copilot)").replace(" ", "-")


def check_model_pin(records: list[MetricRecord]) -> None:
    """Raise if the session's own (non-sub-agent) turns were served by a model other than its mode's pin."""
    mode = records[0]["mode"]
    pin = pinned_model(mode)
    served = sorted({r["model"] for r in records if r["subagent_session"] is None})
    if served != [pin]:
        raise ValueError(f"session {records[0]['session_id']} (mode={mode}) was served {served}, but {MODE_AGENTS[mode]}.agent.md pins {pin!r}: "
                         "move its .events.jsonl and .jsonl to research/runs/invalid/ and re-run with the pinned model")


def run_hook() -> None:
    """Append the incoming hook event to its session log and rebuild that session's metrics."""
    mode = os.environ["HARNESS_MODE"]
    if mode not in MODE_AGENTS:
        raise ValueError(f"HARNESS_MODE={mode!r}, expected one of {tuple(MODE_AGENTS)}")
    payload: Json = json.load(sys.stdin)
    session_id = payload["session_id"]
    if not SESSION_ID.match(session_id):
        raise ValueError(f"unsafe session_id {session_id!r}")
    event = to_event(payload, mode)
    events_path = RUNS_DIR / f"{session_id}.events.jsonl"
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    if event["event"] != "PreToolUse":
        rebuild(events_path)


def flush() -> None:
    """Rebuild every session after the OTel exporter has settled and fail on sessions with no records, errored or canceled calls, or an unpinned model."""
    sessions = sorted(RUNS_DIR.glob("*.events.jsonl"))
    if not sessions:
        raise FileNotFoundError(f"no hook events in {RUNS_DIR}: the agent hooks have not fired (open enterprise-harness/ as the workspace folder, set Session Target to Local, and run a custom agent)")
    for events_path in sessions:
        records, problems = rebuild(events_path)
        if not records:
            raise LookupError(f"no chat spans in {OTEL_FILE} matched copilot_chat.chat_session_id of {events_path.name}")
        if problems:
            raise RuntimeError(f"session {records[0]['session_id']} is incomplete: {'; '.join(problems)}: "
                               "move its .events.jsonl and .jsonl to research/runs/invalid/ and re-run")
        check_model_pin(records)


if __name__ == "__main__":
    if sys.argv[1:] == ["flush"]:
        flush()
    elif sys.argv[1:]:
        raise SystemExit("usage: metrics.py            (hook, reads payload on stdin)\n       metrics.py flush      (finalize all sessions)")
    else:
        run_hook()
