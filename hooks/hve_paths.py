"""Workspace state locations for harness hooks: <workspace>/.hve, since hooks run with the workspace root as working directory."""

from pathlib import Path

STATE_DIR = Path.cwd() / ".hve"
RUNS_DIR = STATE_DIR / "runs"
OUTPUTS_DIR = STATE_DIR / "outputs"
PROFILE_FILE = STATE_DIR / "user_profile.json"
BLINDSPOTS_FILE = STATE_DIR / "blindspots" / "detected_blindspots.jsonl"
