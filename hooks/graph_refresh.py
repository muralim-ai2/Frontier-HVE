"""Hook that keeps creator's Graphify code graph in step with its project folder."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from hve_paths import OUTPUTS_DIR

PROJECT = OUTPUTS_DIR / "harness" / "current"
GRAPH_DIR = OUTPUTS_DIR / "harness" / "graph"
GRAPH_FILE = GRAPH_DIR / "graph.json"
STAGING_DIR = GRAPH_DIR / "staging"
FINGERPRINT_FILE = GRAPH_DIR / "fingerprint.txt"
CODE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py"}
SKIP_DIRS = {"node_modules", ".next"}
EMPTY_GRAPH = {"directed": False, "multigraph": False, "graph": {}, "nodes": [], "links": []}


def project_files() -> list[tuple[str, int, int]]:
    """Return (relative path, mtime ns, size) of every project file outside dependency and build folders."""
    files: list[tuple[str, int, int]] = []
    for folder, dirs, names in os.walk(PROJECT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            path = Path(folder) / name
            stat = path.stat()
            files.append((path.relative_to(PROJECT).as_posix(), stat.st_mtime_ns, stat.st_size))
    return sorted(files)


def write_atomic(path: Path, text: str) -> None:
    """Replace path with text in one step, so the MCP server's hot reload never reads a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def refresh() -> None:
    """Rebuild the graph when the project's files changed; write an empty graph while it has no code."""
    files = project_files()
    fingerprint = hashlib.sha256(json.dumps(files).encode("utf-8")).hexdigest()
    if GRAPH_FILE.exists() and FINGERPRINT_FILE.exists() and FINGERPRINT_FILE.read_text(encoding="utf-8") == fingerprint:
        return
    if any(Path(name).suffix in CODE_SUFFIXES for name, _, _ in files):
        graphify = shutil.which("graphify")
        if graphify is None:
            raise FileNotFoundError('graphify not on PATH: run `uv tool install "graphifyy[mcp]==0.9.71"` and `uv tool update-shell`, then restart VS Code (decision D-016)')
        result = subprocess.run([graphify, "extract", str(PROJECT), "--code-only", "--out", str(STAGING_DIR), "--no-viz", "--force"],
                                capture_output=True, text=True, env={**os.environ, "GRAPHIFY_QUERY_LOG_DISABLE": "1"})
        if result.returncode != 0:
            raise RuntimeError(f"graphify extract failed ({result.returncode}): {result.stderr.strip()}")
        os.replace(STAGING_DIR / "graphify-out" / "graph.json", GRAPH_FILE)
    else:
        write_atomic(GRAPH_FILE, json.dumps(EMPTY_GRAPH))
    write_atomic(FINGERPRINT_FILE, fingerprint)


def main() -> None:
    """Refresh the graph at session start and after every tool call."""
    event = json.load(sys.stdin)["hook_event_name"]
    if event not in ("SessionStart", "PostToolUse"):
        raise ValueError(f"graph_refresh.py does not handle hook event {event!r}")
    refresh()


if __name__ == "__main__":
    main()
