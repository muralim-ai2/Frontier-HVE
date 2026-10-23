"""Decide which expertise packs a request is about: named packs first, then task patterns and keywords, ordered by workspace signals."""

import re
from pathlib import Path
from typing import Any

NAMED = re.compile(r"\b(?:use|with|using)\s+(?:the\s+)?([a-z0-9]+(?:-[a-z0-9]+)*)\s+(?:plugin|pack)\b", re.I)
SKIP_DIRS = {"node_modules", ".git", ".hve", ".harness", "dist", "build", ".venv"}

Json = dict[str, Any]


def signal_hits(workspace: Path, signals: list[str]) -> list[str]:
    """Return the workspace signals that hold: a glob that matches a file, or 'file:text' where the file contains the text."""
    hits = []
    for signal in signals:
        file, sep, needle = signal.partition(":")
        if sep:
            path = workspace / file
            held = path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace")
        else:
            held = any(not SKIP_DIRS & set(p.relative_to(workspace).parts) for p in workspace.glob(signal))
        hits += [signal] if held else []
    return hits


def mentions(prompt: str, entry: Json) -> bool:
    """Return whether the prompt names the pack: @name, '<name>:<asset>', or 'use the <name> pack|plugin' (a word of the name suffices)."""
    name, data = entry["name"], entry["manifest"]
    assets = ({a["name"] for a in data["agents"]} | {s["name"] for s in data["skills"]} | set(data["templates"])
              | {k["id"] for k in data["knowledge"]} | {n.split(":", 1)[1] for n in data["lifecycles"]})
    return (re.search(rf"@{re.escape(name)}\b", prompt) is not None
            or any(re.search(rf"\b{re.escape(name)}:{re.escape(a)}\b", prompt) for a in assets)
            or any(m.lower() == name or m.lower() in name.split("-") for m in NAMED.findall(prompt)))


def reasons(prompt: str, entry: Json) -> list[str]:
    """Return why the pack's routing matches the prompt: its task pattern, and each keyword found."""
    routing = entry["manifest"]["routing"]
    pattern = re.search(routing["task_pattern"], prompt, re.I)
    found = [f"keyword {k!r}" for k in routing["keywords"] if re.search(rf"(?<!\w){re.escape(k)}(?!\w)", prompt, re.I)]
    return ([f"task pattern matched {pattern.group(0)!r}"] if pattern else []) + found


def matches(prompt: str, entry: Json) -> bool:
    """Return whether the pack's task pattern or one of its keywords appears in the prompt."""
    return bool(reasons(prompt, entry))


def candidates(prompt: str, workspace: Path, packs: dict[str, Json]) -> Json:
    """Return named packs, pack names named but not available, and matching packs with why, ordered by workspace signals."""
    explicit = sorted(name for name, entry in packs.items() if mentions(prompt, entry))
    # Only hyphenated names count as missing pack ids, so "use the new plugin" never stops a session.
    missing = sorted({m.lower() for m in NAMED.findall(prompt) if "-" in m} - set(packs))
    matched = []
    for name, entry in packs.items():
        why = reasons(prompt, entry)
        if why:
            signals = signal_hits(workspace, entry["manifest"]["routing"]["workspace_signals"])
            matched.append({"name": name, "why": why + [f"workspace has {s}" for s in signals], "signals": len(signals),
                            "source": entry["source"], "version": entry["version"]})
    matched.sort(key=lambda m: (-m["signals"], m["name"]))
    return {"explicit": explicit, "missing": missing, "matched": matched}
