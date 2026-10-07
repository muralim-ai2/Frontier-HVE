"""Guide one benchmark run of one agent in a new chat, log its progress live, flush and collect, then prune the OTel export."""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hooks"))
from metrics import request_effort  # noqa: E402
from otel_prune import LOCK_FILE, prune  # noqa: E402

RUNS_DIR = ROOT / ".hve" / "runs"
OTEL_FILE = RUNS_DIR / "copilot-otel.jsonl"
LOG_FILE = RUNS_DIR / "bench.log"
PROMPT_FILE = ROOT / "tests" / "prompts" / "color-palette.md"
AGENT_MODES = {"minimal": "minimal", "single": "single", "creator": "harness", "creator-flow": "flow"}
POLL_S = 5
HEARTBEAT_S = 30
QUIET_S = 30
START_TIMEOUT_S = 5 * 60
RUN_TIMEOUT_S = 50 * 60

Json = dict[str, Any]


def pinned_effort(agent: str) -> str:
    """Return the `reasoning-effort` value from the agent file's frontmatter."""
    path = ROOT / ".github" / "agents" / f"{agent}.agent.md"
    for line in path.read_text(encoding="utf-8").split("---")[1].splitlines():
        if line.startswith("reasoning-effort:"):
            return line.split(":", 1)[1].strip()
    raise ValueError(f"{path} has no reasoning-effort in its frontmatter")


class Bench:
    """Live log and file tails for one benchmark run."""

    def __init__(self, agent: str, otel_offset: int) -> None:
        """Start the run clock and read the OTel export from otel_offset onwards."""
        self.agent = agent
        self.effort = pinned_effort(agent)
        self.t0 = time.monotonic()
        self.otel_offset = otel_offset
        self.otel_tail = b""
        self.events_seen = 0
        self.calls = 0
        self.last_pre_ms = 0.0
        self.last_stop_ms = 0.0
        self.agent_end_ms = 0.0
        self.last_activity = time.monotonic()

    def log(self, message: str) -> None:
        """Print a timestamped line and append it to .hve/runs/bench.log."""
        elapsed = int(time.monotonic() - self.t0)
        line = f"{datetime.now():%H:%M:%S} +{elapsed // 60:02d}:{elapsed % 60:02d} [{self.agent}] {message}"
        print(line, flush=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def new_otel_records(self, session_id: str) -> list[Json]:
        """Return the OTel records mentioning the session that were appended since the last call."""
        with OTEL_FILE.open("rb") as f:
            f.seek(self.otel_offset)
            data = self.otel_tail + f.read()
            self.otel_offset = f.tell()
        *lines, self.otel_tail = data.split(b"\n")
        key = session_id.encode()
        return [json.loads(line) for line in lines if key in line]

    def new_events(self, session_id: str) -> list[Json]:
        """Return the hook events appended to the session's events file since the last call."""
        path = RUNS_DIR / f"{session_id}.events.jsonl"
        if not path.exists():  # created by the first tool or Stop hook
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        new = [json.loads(line) for line in lines[self.events_seen:]]
        self.events_seen = len(lines)
        return new

    def report(self, session_id: str) -> bool:
        """Log new tool events and model calls; return True once the session's Stop hook follows its last tool call, a top-level
        agent span ended after that Stop, and nothing new happened for QUIET_S (Copilot can start a new agent span mid-run)."""
        events = self.new_events(session_id)
        for e in events:
            if e["event"] == "PreToolUse":
                self.last_pre_ms = e["ts_ms"]
                self.log(f"tool {e['tool_name']} started")
            elif e["event"] == "PostToolUse":
                self.log(f"tool {e['tool_name']} finished")
            else:
                self.last_stop_ms = e["ts_ms"] if e["event"] == "Stop" else self.last_stop_ms
                self.log(f"{e['event']} hook fired")
        records = self.new_otel_records(session_id)
        if events or records:
            self.last_activity = time.monotonic()
        for rec in records:
            attrs = rec.get("attributes", {})
            if "ended" not in rec or "copilot_chat.chat_session_id" not in attrs:
                continue  # logs, metrics, and utility calls (title, categorization)
            if session_id not in (attrs["copilot_chat.chat_session_id"], attrs.get("copilot_chat.parent_chat_session_id")):
                continue
            operation = attrs.get("gen_ai.operation.name")
            if operation == "chat" and rec["status"]["code"] == 2:
                raise RuntimeError(f"a model call of session {session_id} ended with '{rec['status'].get('message')}': the run is invalid. "
                                   "Keep the benchmark chat open and in view until it finishes (switching the Chat view to another chat can "
                                   f"cancel it), move .hve/runs/{session_id}.* to .hve/runs/invalid/, and run again")
            if operation == "chat" and "gen_ai.usage.input_tokens" in attrs:
                self.calls += 1
                who = "main" if attrs["copilot_chat.chat_session_id"] == session_id else "sub-agent"
                effort = request_effort(attrs)
                self.log(f"model call {self.calls} ({who}, {attrs['gen_ai.response.model']}, effort {effort}): "
                         f"{attrs['gen_ai.usage.input_tokens']:,} prompt / {attrs['gen_ai.usage.output_tokens']:,} completion tokens")
                if who == "main" and effort != self.effort:
                    raise RuntimeError(f"the chat ran at reasoning effort {effort!r} but {self.agent}.agent.md pins {self.effort!r}; VS Code "
                                       "ignores the agent file's reasoning-effort (D-020). Stop the chat, set the effort in the model picker "
                                       f"to {self.effort!r}, move .hve/runs/{session_id}.* to .hve/runs/invalid/, and run again")
            elif operation == "invoke_agent" and attrs["copilot_chat.chat_session_id"] == session_id:
                self.agent_end_ms = max(self.agent_end_ms, rec["endTime"][0] * 1000 + rec["endTime"][1] / 1e6)
        return (self.last_stop_ms > self.last_pre_ms and self.agent_end_ms >= self.last_stop_ms
                and time.monotonic() - self.last_activity >= QUIET_S)


def session_ids() -> set[str]:
    """Return the ids of sessions whose SessionStart budget hook has run."""
    return {p.name.removesuffix(".budget.json") for p in RUNS_DIR.glob("*.budget.json")}


def run(agent: str) -> str:
    """Run one benchmark under the bench lock, then prune the OTel export; return the session id."""
    return guarded(lambda: watch(agent))


def guarded(work: Callable[[], str]) -> str:
    """Hold the bench lock while work runs (otel_prune refuses meanwhile), then archive collected runs and empty the live export."""
    if LOCK_FILE.exists():
        raise FileExistsError(f"{LOCK_FILE} exists: another bench run is active (if none is, the last one crashed; delete the lock file)")
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    try:
        session_id = work()
    finally:
        LOCK_FILE.unlink()
    pruned = prune()
    print(f"OTel export pruned: archived {pruned['archived']}, freed {pruned['freed_mb']} MB", flush=True)
    return session_id


def watch(agent: str) -> str:
    """Put the prompt on the clipboard, wait for the user to start a new chat with the agent, follow it live, flush and collect; return the session id."""
    current = ROOT / ".hve" / "outputs" / AGENT_MODES[agent] / "current"
    if current.exists():
        raise FileExistsError(f"{current} exists from an earlier run: run `python tools/observe/collect.py` or move it before a new run")
    bench = Bench(agent, OTEL_FILE.stat().st_size)
    before = session_ids()
    subprocess.run(["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value (Get-Content -Raw -Encoding UTF8 '{PROMPT_FILE}')"],
                   check=True)
    bench.log(f"{PROMPT_FILE.name} is on the clipboard. In VS Code: 1) Chat view > New Chat (+)  2) Session Target = Local, "
              f"agent = {agent}  3) paste (Ctrl+V) and send. Waiting up to {START_TIMEOUT_S // 60} min for the chat to start.")
    last_beat = time.monotonic()
    while not (new := session_ids() - before):
        if time.monotonic() - bench.t0 > START_TIMEOUT_S:
            raise TimeoutError(f"no SessionStart hook within {START_TIMEOUT_S // 60} min. Agent hooks only run on the Local harness with the "
                               f"'{agent}' agent selected in a new chat; check both and run this command again")
        if time.monotonic() - last_beat >= HEARTBEAT_S:
            bench.log(f"still waiting for a new Local chat with agent '{agent}'")
            last_beat = time.monotonic()
        time.sleep(POLL_S)
    if len(new) > 1:
        raise RuntimeError(f"several new sessions appeared at once ({sorted(new)}): run one chat at a time")
    session_id = new.pop()
    bench.log(f"session {session_id} detected; following it live")
    follow(bench, session_id)
    return session_id


def follow(bench: Bench, session_id: str) -> None:
    """Log the session until its request ends, then flush metrics, collect the output, and log a summary."""
    last_beat = time.monotonic()
    while not bench.report(session_id):
        if time.monotonic() - bench.t0 > RUN_TIMEOUT_S:
            raise TimeoutError(f"session {session_id} still running after {RUN_TIMEOUT_S // 60} minutes")
        if time.monotonic() - last_beat >= HEARTBEAT_S:
            bench.log(f"working ({bench.calls} model calls so far)")
            last_beat = time.monotonic()
        time.sleep(POLL_S)
    bench.log("chat finished; flushing metrics and collecting output")
    subprocess.run([sys.executable, str(ROOT / "hooks" / "metrics.py"), "flush"], check=True)
    subprocess.run([sys.executable, str(ROOT / "tools" / "observe" / "collect.py")], check=True)
    rows = [json.loads(line) for line in (RUNS_DIR / f"{session_id}.jsonl").read_text(encoding="utf-8").splitlines()]
    turns = {r["turn_id"]: r for r in rows}.values()
    manifest = json.loads((RUNS_DIR / f"{session_id}.run.json").read_text(encoding="utf-8"))
    bench.log(f"done: {len(turns)} model calls, {sum(t['prompt_tokens'] for t in turns):,} prompt / "
              f"{sum(t['completion_tokens'] for t in turns):,} completion tokens, cost {sum(t['cost_nano_aiu'] for t in turns) / 1e9:.2f} AI units, "
              f"{sum(1 for r in rows if r['tool_name'])} tool calls, {len(manifest['files'])} files in {manifest['output_dir']}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 1 and args[0] in AGENT_MODES:
        run(args[0])
    elif len(args) == 3 and args[0] in AGENT_MODES and args[1] == "--resume" and (RUNS_DIR / f"{args[2]}.budget.json").exists():
        resumed = Bench(args[0], 0)
        resumed.log(f"resuming session {args[2]}; replaying its log so far")

        def resume() -> str:
            """Follow the started session to the end and return its id."""
            follow(resumed, args[2])
            return args[2]

        guarded(resume)
    else:
        raise SystemExit(f"usage: bench.py {{{'|'.join(AGENT_MODES)}}} [--resume <session_id of a started run>]")
