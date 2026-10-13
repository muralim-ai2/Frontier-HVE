"""Decide which enabled plugins a prompt is about: explicit mentions first, then task patterns and keywords, ordered by workspace signals."""

import re
from pathlib import Path
from typing import Any

import store

NAMED = re.compile(r"\b(?:use|with|using)\s+(?:the\s+)?([a-z0-9]+(?:-[a-z0-9]+)*)\s+plugin\b", re.I)
SKIP_DIRS = {"node_modules", ".git", ".hve", ".harness", "dist", "build", ".venv"}

Json = dict[str, Any]


def signal_hits(workspace: Path, signals: list[str]) -> int:
    """Return how many workspace signals hold: a glob that matches a file, or 'file:text' where the file contains the text."""
    hits = 0
    for signal in signals:
        file, sep, needle = signal.partition(":")
        if sep:
            path = workspace / file
            hits += path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace")
        else:
            hits += any(not SKIP_DIRS & set(p.relative_to(workspace).parts) for p in workspace.glob(signal))
    return hits


def mentions(prompt: str, entry: Json) -> bool:
    """Return whether the prompt names the plugin: @name, '<name>:<asset>', or 'use the <name> plugin' (a word of the name suffices)."""
    name, data = entry["name"], entry["manifest"]
    assets = {a["name"] for a in data["agents"]} | {s["name"] for s in data["skills"]} | set(data["templates"]) | set(data["flows"])
    return (re.search(rf"@{re.escape(name)}\b", prompt) is not None
            or any(re.search(rf"\b{re.escape(name)}:{re.escape(a)}\b", prompt) for a in assets)
            or any(m.lower() == name or m.lower() in name.split("-") for m in NAMED.findall(prompt)))


def matches(prompt: str, entry: Json) -> bool:
    """Return whether the plugin's task pattern or one of its keywords appears in the prompt."""
    routing = entry["manifest"]["routing"]
    return (re.search(routing["task_pattern"], prompt, re.I) is not None
            or any(re.search(rf"(?<!\w){re.escape(k)}(?!\w)", prompt, re.I) for k in routing["keywords"]))


def candidates(prompt: str, workspace: Path) -> Json:
    """Return explicitly named plugins, plugin ids named but not installed, and matching plugins ordered by workspace signals."""
    plugins = store.enabled()
    explicit = sorted(name for name, entry in plugins.items() if mentions(prompt, entry))
    # Only hyphenated names count as missing plugin ids, so "use the new plugin" never stops a session.
    missing = sorted({m.lower() for m in NAMED.findall(prompt) if "-" in m} - set(plugins))
    matched = sorted((name for name, entry in plugins.items() if matches(prompt, entry)),
                     key=lambda n: (-signal_hits(workspace, plugins[n]["manifest"]["routing"]["workspace_signals"]), n))
    return {"explicit": explicit, "missing": missing, "matched": matched}
