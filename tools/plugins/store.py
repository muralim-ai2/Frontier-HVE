"""Read the global plugin registry and list the expertise packs available to a workspace: enabled installed packs and workspace packs."""

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

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


def folder(entry: Json) -> Path:
    """Return the store folder of an installed plugin version."""
    return home() / "plugins" / entry["id"] / entry["version"]


def file_sha256(path: Path) -> str:
    """Return the SHA-256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_sha256(package: Path) -> str:
    """Return the SHA-256 over a package's relative paths and file contents."""
    digest = hashlib.sha256()
    for path in sorted(p for p in package.rglob("*") if p.is_file()):
        digest.update(f"{path.relative_to(package).as_posix()}\0{file_sha256(path)}\n".encode())
    return digest.hexdigest()


@lru_cache(maxsize=4)
def packs(workspace: Path) -> dict[str, Json]:
    """Return every available pack by name: enabled installed packs, then packs committed in the workspace's plugins/<pack>/ folders (a
    workspace pack replaces an installed one of the same name and records it)."""
    found = {name: {"id": e["id"], "name": name, "version": e["version"], "sha256": e["sha256"], "source": "installed",
                    "folder": folder(e).as_posix(), "manifest": e["manifest"]} for name, e in enabled().items()}
    for path in sorted(workspace.glob("plugins/*/hve-plugin.json")):
        import manifest  # manifest imports the lifecycle catalog, which imports this module
        data = manifest.load(path.parent)
        replaced = {"overrides": f"installed {found[data['name']]['version']}"} if data["name"] in found else {}
        found[data["name"]] = {"id": data["id"], "name": data["name"], "version": data["version"], "sha256": content_sha256(path.parent),
                               "source": "workspace", "folder": path.parent.resolve().as_posix(), "manifest": data} | replaced
    return found


def pack(workspace: Path, name: str) -> Json:
    """Return the available pack with this name, or raise naming how to install or enable it."""
    found = packs(workspace).get(name)
    if found is None:
        raise LookupError(f"pack {name!r} is not available: install it (Frontier HVE: Install plugin, or `plugin.py install <package>`), "
                          f"enable it (`plugin.py enable {name}`), or commit it as plugins/{name}/ in the workspace")
    return found
