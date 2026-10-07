"""PostToolUse module-size guard: block when an edited file exceeds 500 lines and ask the agent to propose a split to the human."""

import json
import re
import sys
from pathlib import Path
from typing import Any

from interventions import record

ROOT = Path(__file__).resolve().parent.parent
MAX_LINES = 500
EDIT_TOOLS = {"create_file", "replace_string_in_file", "multi_replace_string_in_file", "insert_edit_into_file", "apply_patch"}
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$", re.M)
EXEMPT = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}


def edited_paths(tool_input: Any) -> list[str]:
    """Return every filePath value and every apply_patch target in a tool input."""
    if isinstance(tool_input, dict):
        own = [tool_input["filePath"]] if isinstance(tool_input.get("filePath"), str) else []
        return own + [p for v in tool_input.values() for p in edited_paths(v)]
    if isinstance(tool_input, list):
        return [p for v in tool_input for p in edited_paths(v)]
    return PATCH_FILE.findall(tool_input) if isinstance(tool_input, str) else []


def oversized(tool_input: Any) -> list[tuple[str, int]]:
    """Return (path, line count) of edited files over the limit; relative paths are resolved against the workspace root."""
    found = []
    for raw in dict.fromkeys(edited_paths(tool_input)):
        path = Path(raw) if Path(raw).is_absolute() else ROOT / raw
        if path.name not in EXEMPT and path.is_file():
            lines = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            if lines > MAX_LINES:
                found.append((raw, lines))
    return found


def main() -> None:
    """Answer PostToolUse for edit tools with a block naming each file over the limit."""
    payload = json.load(sys.stdin)
    if payload["hook_event_name"] != "PostToolUse":
        raise ValueError(f"module_guard.py does not handle hook event {payload['hook_event_name']!r}")
    if payload["tool_name"] not in EDIT_TOOLS:
        return
    found = oversized(payload["tool_input"])
    if not found:
        return
    files = ", ".join(f"{p} ({n} lines)" for p, n in found)
    reason = (f"Module size limit is {MAX_LINES} lines; target 200-300: {files}. Split it now into modules of about 250 lines "
              "with one responsibility each, and list the split in your final summary for the human to review.")
    record(payload["session_id"], "module_guard", "oversized_file", files)
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
