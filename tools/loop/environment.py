"""Detect the agent harness, configured MCP servers and their tool load, Frontier HVE hook files and plugin skills for an ask's contract."""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "skills"))
from context_load import mcp_servers, tool_load, vscode_user_dir  # noqa: E402

HARNESS_VARS = [("HVE_HARNESS", None), ("COPILOT_AGENT_PROMPT", "copilot-cloud"), ("CLAUDECODE", "claude"), ("CURSOR_TRACE_ID", "cursor"),
                ("CODEX_SANDBOX", "codex"), ("CODEX_HOME", "codex"), ("VSCODE_PID", "vscode")]
HVE_HOOK = re.compile(r"agent_compat\.py|skill_loader\.py|loop_guard\.py")

Json = dict[str, Any]


def hook_files(workspace: Path) -> list[str]:
    """Return the hook files that run Frontier HVE hooks, at workspace and user level, for every harness."""
    home = Path.home()
    candidates = [*sorted((workspace / ".github" / "hooks").glob("*.json")), *sorted((home / ".copilot" / "hooks").glob("*.json")),
                  workspace / ".claude" / "settings.json", home / ".claude" / "settings.json",
                  workspace / ".codex" / "hooks.json", home / ".codex" / "hooks.json",
                  workspace / ".cursor" / "hooks.json", home / ".cursor" / "hooks.json"]
    return [p.as_posix() for p in candidates if p.is_file() and HVE_HOOK.search(p.read_text(encoding="utf-8"))]


def plugin_skills() -> list[str]:
    """Return the names of the harness-assist plugin skills shipped with this runtime or repository."""
    folders = [ROOT / "plugins" / "harness-assist" / "skills", ROOT.parent / "skills"]
    return sorted({p.parent.name for folder in folders if folder.is_dir() for p in folder.glob("*/SKILL.md")})


def harness() -> Json:
    """Return the harness this command runs under, from the first environment variable that identifies one."""
    for variable, name in HARNESS_VARS:
        if os.environ.get(variable):
            return {"name": name or os.environ[variable], "evidence": variable}
    return {"name": "unknown", "evidence": None}


def environment(workspace: Path) -> Json:
    """Return the harness, MCP servers with their estimated tool load, Frontier HVE hook files and plugin skills visible from the workspace."""
    servers = mcp_servers(workspace, vscode_user_dir())
    return {"harness": harness(), "mcp_servers": servers, "tool_load": tool_load(servers), "hook_files": hook_files(workspace),
            "plugin_skills": plugin_skills()}


if __name__ == "__main__":
    print(json.dumps(environment(Path.cwd()), indent=2))
