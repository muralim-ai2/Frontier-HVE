"""End-to-end test of hooks/metrics.py on synthetic hook payloads and OTel spans in a temp folder."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
SESSION = "11111111-2222-3333-4444-555555555555"
SUB = "call_sub1"
T0 = 1_800_000_000_000
ISO_MS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00$")


def hrtime(ms: int) -> list[int]:
    """Return an OTel [seconds, nanoseconds] tuple for T0 + ms, with sub-millisecond digits."""
    total = T0 + ms
    return [total // 1000, total % 1000 * 1_000_000 + 456_789]


def chat_span(span_id: str, end_ms: int, model: str, tokens: int, attrs: dict[str, str]) -> dict[str, Any]:
    """Return a Copilot OTel chat span line."""
    return {
        "spanId": span_id, "startTime": hrtime(end_ms - 400), "endTime": hrtime(end_ms), "ended": True,
        "status": {"code": 0}, "resource": {"attributes": {"session.id": "window-1"}},
        "attributes": {"gen_ai.operation.name": "chat", "gen_ai.response.model": model,
                       "gen_ai.usage.input_tokens": tokens, "gen_ai.usage.output_tokens": tokens // 10,
                       "gen_ai.usage.cache_read.input_tokens": 0, "copilot_chat.copilot_usage_nano_aiu": tokens * 1000,
                       "copilot_chat.request.options": json.dumps({"reasoning": {"effort": "high"}}), **attrs},
    }


def tool_span(call: str, end_ms: int, attrs: dict[str, str]) -> dict[str, Any]:
    """Return a Copilot OTel execute_tool span line."""
    return {"spanId": f"t-{call}", "startTime": hrtime(end_ms - 10), "endTime": hrtime(end_ms), "ended": True,
            "status": {"code": 1}, "resource": {"attributes": {"session.id": "window-1"}},
            "attributes": {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.call.id": call, **attrs}}


def fire(root: Path, event: str, ms: int, tool: str | None, call: str | None) -> None:
    """Run the metrics hook with one synthetic VS Code hook payload."""
    payload = {"hook_event_name": event, "session_id": SESSION,
               "timestamp": datetime.fromtimestamp((T0 + ms) / 1000, timezone.utc).isoformat()}
    if tool:
        payload |= {"tool_name": tool, "tool_use_id": f"{call}__vscode-1"}
    else:
        payload["transcript_path"] = str(root / "transcript.jsonl")
    subprocess.run([sys.executable, str(root / "hooks" / "metrics.py")], input=json.dumps(payload), text=True,
                   check=True, env={**os.environ, "HARNESS_MODE": "single"})


def run_session(main_model: str, canceled: bool) -> tuple[subprocess.CompletedProcess[str], list[dict[str, Any]]]:
    """Replay a single-mode session with one sub-agent, optionally with a canceled call, then flush; return the flush result and session rows."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "hooks").mkdir()
        shutil.copy(REPO / "hooks" / "metrics.py", root / "hooks")
        (root / ".github" / "agents").mkdir(parents=True)
        (root / ".github" / "agents" / "single.agent.md").write_text(
            "---\nname: single\nmodel: Claude Opus 5.5 (copilot)\n---\nmodel: not-the-pin\n", encoding="utf-8")
        runs = root / "research" / "runs"
        runs.mkdir(parents=True)
        main = {"copilot_chat.chat_session_id": SESSION}
        sub = {"copilot_chat.chat_session_id": SUB, "copilot_chat.parent_chat_session_id": SESSION}
        spans = [
            {"resource": {}, "scopeMetrics": []},
            chat_span("title", 500, "gpt-4o-mini", 300, {"copilot_chat.parent_chat_session_id": SESSION}),
            chat_span("m1", 1000, main_model, 100, main),
            chat_span("a1", 2000, "gpt-5.6-luna", 50, sub),
            chat_span("a2", 3000, "gpt-5.6-luna", 70, sub),
            chat_span("m2", 4000, main_model, 200, main),
            chat_span("other", 9000, main_model, 999, {"copilot_chat.chat_session_id": "other-session"}),
            tool_span("c1", 1200, main), tool_span("c2", 3200, main), tool_span("c3", 2500, sub), tool_span("c4", 2060, main),
        ]
        if canceled:
            spans.append({"spanId": "m0", "startTime": hrtime(0), "endTime": hrtime(400), "ended": True,
                          "status": {"code": 2, "message": "Canceled"}, "resource": {"attributes": {"session.id": "window-1"}},
                          "attributes": {"gen_ai.operation.name": "chat", **main}})
        (runs / "copilot-otel.jsonl").write_text("".join(json.dumps(s) + "\n" for s in spans), encoding="utf-8")
        for event, ms, tool, call in [
            ("PreToolUse", 1100, "list_dir", "c1"), ("PreToolUse", 1150, "runSubagent", "c2"),
            ("PostToolUse", 1200, "list_dir", "c1"), ("PreToolUse", 2050, "read_file", "c4"),
            ("PostToolUse", 2060, "read_file", "c4"), ("PreToolUse", 2100, "run_in_terminal", "c3"),
            ("PostToolUse", 2500, "run_in_terminal", "c3"), ("Stop", 3100, None, None),
            ("PostToolUse", 3200, "runSubagent", "c2"), ("Stop", 4100, None, None),
        ]:
            fire(root, event, ms, tool, call)
        flush = subprocess.run([sys.executable, str(root / "hooks" / "metrics.py"), "flush"], capture_output=True, text=True)
        rows = [json.loads(line) for line in (runs / f"{SESSION}.jsonl").read_text(encoding="utf-8").splitlines()]
    return flush, rows


def test_pinned_session_with_subagent() -> None:
    """Sub-agent turns become rows with per-conversation context, a parent tool call made while the sub-agent runs stays with the parent, rows are chronological, and flush passes."""
    flush, rows = run_session("claude-opus-5.5", canceled=False)
    assert flush.returncode == 0, flush.stderr
    assert [(r["tool_name"], r["subagent_session"], r["model"], r["context_tokens"], r["latency_ms"]) for r in rows] == [
        ("list_dir", None, "claude-opus-5.5", 100, 100),
        ("runSubagent", None, "claude-opus-5.5", 100, 2050),
        ("read_file", None, "claude-opus-5.5", 100, 10),
        ("run_in_terminal", SUB, "gpt-5.6-luna", 50, 400),
        (None, SUB, "gpt-5.6-luna", 120, 400),
        (None, None, "claude-opus-5.5", 300, 400),
    ]
    stamps = [r["ts"] for r in rows]
    assert [r["cost_nano_aiu"] for r in rows] == [100_000, 100_000, 100_000, 50_000, 70_000, 200_000]
    assert {r["reasoning_effort"] for r in rows} == {"high"} and {r["cache_read_tokens"] for r in rows} == {0}
    assert all(ISO_MS.match(ts) for ts in stamps), stamps
    assert stamps == sorted(stamps), stamps


def test_flush_fails_on_model_pin_mismatch() -> None:
    """Flush exits non-zero when the session's own turns were served by a model other than the pin."""
    flush, _ = run_session("gpt-5.6-sol", canceled=False)
    assert flush.returncode != 0
    assert "served ['gpt-5.6-sol'], but single.agent.md pins 'claude-opus-5.5'" in flush.stderr, flush.stderr


def test_canceled_call_keeps_hook_working_and_fails_flush() -> None:
    """A canceled chat call does not break the hooks or the other rows, but flush marks the session incomplete."""
    flush, rows = run_session("claude-opus-5.5", canceled=True)
    assert len(rows) == 6
    assert flush.returncode != 0
    assert "errored or canceled chat calls ['m0']" in flush.stderr, flush.stderr


if __name__ == "__main__":
    test_pinned_session_with_subagent()
    test_flush_fails_on_model_pin_mismatch()
    test_canceled_call_keeps_hook_working_and_fails_flush()
    print("test_metrics: OK")
