"""Move each collected benchmark run's OTel records into a small gzip archive, verify them, then empty the live Copilot OTel export."""

import gzip
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hooks"))
from metrics import OTEL_FILE, RUNS_DIR, archive_file, belongs, compute, hrtime_to_ms, read_jsonl  # noqa: E402

LOCK_FILE = RUNS_DIR / "bench.lock"

Json = dict[str, Any]


def scan_live(pending: list[str]) -> tuple[dict[str, list[str]], dict[str, float]]:
    """Stream the live export once; return the raw lines of each pending session and the latest span end per VS Code window."""
    picked: dict[str, list[str]] = {s: [] for s in pending}
    window_end: dict[str, float] = {}
    with OTEL_FILE.open("rb") as f:
        for raw in f:
            if not raw.endswith(b"\n"):
                break  # tail still being written
            if b'"ended"' not in raw:
                continue
            rec = json.loads(raw)
            window = rec["resource"]["attributes"]["session.id"]
            window_end[window] = max(window_end.get(window, 0.0), hrtime_to_ms(rec["endTime"]))
            for session_id in pending:
                if session_id.encode() in raw and belongs(rec["attributes"], session_id):
                    picked[session_id].append(raw.decode("utf-8").rstrip("\r\n"))
    return picked, window_end


def archive(session_id: str, lines: list[str], window_end: dict[str, float]) -> None:
    """Write the session's archive, then check it rebuilds exactly the metrics rows already on disk; remove it and raise if not."""
    path = archive_file(session_id)
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_bytes(gzip.compress("\n".join([json.dumps({"window_end": window_end}), *lines]).encode("utf-8") + b"\n"))
    os.replace(tmp, path)
    rebuilt, _ = compute(RUNS_DIR / f"{session_id}.events.jsonl")
    if [dict(r) for r in rebuilt] != read_jsonl(RUNS_DIR / f"{session_id}.jsonl"):
        path.unlink()
        raise RuntimeError(f"the archive of {session_id} does not rebuild its metrics rows; the live export was left untouched")


def prune() -> Json:
    """Archive and verify every collected session, then empty the live export; refuse while a run is active or uncollected."""
    if LOCK_FILE.exists():
        raise RuntimeError(f"{LOCK_FILE} exists: a bench run is in progress (if none is, the last one crashed; delete the lock file)")
    sessions = [p.name.removesuffix(".events.jsonl") for p in sorted(RUNS_DIR.glob("*.events.jsonl"))]
    uncollected = [s for s in sessions if not (RUNS_DIR / f"{s}.run.json").exists()]
    if uncollected:
        raise RuntimeError(f"uncollected sessions {uncollected} still need the live export: run tools/observe/collect.py or move them "
                           "to research/runs/invalid/ first")
    pending = [s for s in sessions if not archive_file(s).exists()]
    size = OTEL_FILE.stat().st_size
    picked, window_end = scan_live(pending)
    for session_id in pending:
        archive(session_id, picked[session_id], window_end)
    with OTEL_FILE.open("r+b") as f:
        f.truncate(0)
    return {"archived": pending, "freed_mb": round(size / 1e6, 1)}


if __name__ == "__main__":
    if sys.argv[1:]:
        raise SystemExit("usage: otel_prune.py")
    print(json.dumps(prune(), indent=2))
