"""Trim the Copilot OTel export so it never silently fills the disk: keep the last days of records under a size cap, and make git ignore it."""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

KEEP_DAYS = 3
MAX_BYTES = 200 * 1024 * 1024
EXPORT = ".hve/runs/copilot-otel.jsonl"
LOCK = ".hve/runs/bench.lock"
IGNORED_BY = {".hve/", "/.hve/", ".hve", ".hve/runs/", EXPORT}

Json = dict[str, Any]


def stamp_ms(raw: bytes) -> float | None:
    """Return a record's end time (else start time) in epoch milliseconds, or None for a record that carries neither."""
    record = json.loads(raw)
    hrtime = record.get("endTime") or record.get("startTime")
    return hrtime[0] * 1000 + hrtime[1] / 1e6 if hrtime else None


def ensure_ignored(workspace: Path) -> bool:
    """Add the export to the workspace's .gitignore unless .hve/ or the export is already ignored; return True when a line was added."""
    gitignore = workspace / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.is_file() else []
    if IGNORED_BY & {line.strip() for line in lines}:
        return False
    with gitignore.open("a", encoding="utf-8") as f:
        f.write(("\n" if lines and lines[-1] else "") + f"# Copilot telemetry export: full chat content, large\n{EXPORT}\n")
    return True


def trim(workspace: Path, now_ms: float) -> Json:
    """Keep the export's records from the last KEEP_DAYS days (and undated ones), newest first under MAX_BYTES, rewriting it in place."""
    export = workspace / EXPORT
    ignored = ensure_ignored(workspace)
    if not export.is_file():
        return {"export": None, "gitignore_added": ignored}
    if (workspace / LOCK).exists():
        raise RuntimeError(f"{workspace / LOCK} exists: a benchmark run is reading the export; trim it after the run")
    before = export.stat().st_size
    cutoff = now_ms - KEEP_DAYS * 86_400_000
    kept = export.with_suffix(f".{os.getpid()}.tmp")
    with export.open("rb") as source, kept.open("wb") as out:
        for raw in source:
            if not raw.endswith(b"\n") or (stamp_ms(raw) or now_ms) >= cutoff:
                out.write(raw)
    with kept.open("rb") as f:
        f.seek(max(0, kept.stat().st_size - MAX_BYTES))
        if f.tell():
            f.readline()
        data = f.read()
    kept.unlink()
    # Rewrite in place: the Copilot exporter keeps its append handle on this file.
    with export.open("r+b") as f:
        f.truncate(0)
        f.write(data)
    return {"export": EXPORT, "before_mb": round(before / 1e6, 1), "after_mb": round(len(data) / 1e6, 1), "keep_days": KEEP_DAYS,
            "cap_mb": MAX_BYTES // (1024 * 1024), "gitignore_added": ignored}


if __name__ == "__main__":
    if sys.argv[1:]:
        raise SystemExit("usage: otel_trim.py (run from the workspace root)")
    print(json.dumps(trim(Path.cwd(), time.time() * 1000), indent=2))
