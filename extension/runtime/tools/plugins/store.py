"""Read-only access to the global plugin registry and to a session's plugin selection."""

import json
import os
import re
from pathlib import Path
from typing import Any

SESSION_ID = re.compile(r"^[\w-]+$")

Json = dict[str, Any]


def home() -> Path:
    """Return the global plugin home: HVE_PLUGIN_HOME when set, else ~/.frontier-hve."""
    value = os.environ.get("HVE_PLUGIN_HOME")
    return Path(value) if value else Path.home() / ".frontier-hve"


def registry_file() -> Path:
    """Return the registry path."""
    return home() / "plugins.json"


def registry() -> Json:
    """Return the registry, or an empty one when no plugin was ever installed."""
    path = registry_file()
    if not path.exists():
        return {"version": 1, "plugins": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("plugins"), dict):
        raise ValueError(f"{path} is not a version 1 plugin registry")
    return data


def enabled() -> dict[str, Json]:
    """Return the enabled plugins' registry entries by short name."""
    return {e["name"]: e for e in registry()["plugins"].values() if e["enabled"]}


def plugin(name: str) -> Json:
    """Return the enabled plugin with this short name, or raise naming the install command."""
    found = enabled().get(name)
    if found is None:
        raise LookupError(f"plugin {name!r} is not installed or is disabled; install it with "
                          f"`python <tools>/plugins/plugin.py install <package>` or enable it with `plugin.py enable {name}`")
    return found


def folder(entry: Json) -> Path:
    """Return the store folder of an installed plugin version."""
    return home() / "plugins" / entry["id"] / entry["version"]


def session_file(workspace: Path, session_id: str) -> Path:
    """Return a session's loadout file after validating the session id."""
    if not SESSION_ID.match(session_id):
        raise ValueError(f"unsafe session_id {session_id!r}")
    return workspace / ".hve" / "runs" / f"{session_id}.skills.json"


def selected(workspace: Path, session_id: str) -> list[str]:
    """Return the plugins selected in a session; none when the session has no loadout yet or a choice is pending."""
    path = session_file(workspace, session_id)
    if not path.exists():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")).get("plugins", []))
