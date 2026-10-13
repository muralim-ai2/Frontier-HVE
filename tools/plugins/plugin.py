"""Install and manage Frontier HVE plugins in the global store: inspect, install, enable, disable, uninstall, pack, reconcile."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import author  # noqa: E402
import manifest  # noqa: E402
import store  # noqa: E402
from route import candidates  # noqa: E402

SUMS = "SHA256SUMS"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
REQUIREMENTS = "frontier-hve.plugins.json"

Json = dict[str, Any]


@contextmanager
def store_lock() -> Iterator[None]:
    """Hold the store lock so two windows never change plugins at once."""
    path = store.home() / "plugins.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.open("x").close()
    except FileExistsError as error:
        raise RuntimeError(f"another Frontier HVE window is changing plugins ({path}); retry when it finishes, "
                           "or delete the lock file if no install is running") from error
    try:
        yield
    finally:
        path.unlink()


def write_registry(data: Json) -> None:
    """Replace the registry atomically: the single commit point of every change."""
    path = store.registry_file()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def file_sha256(path: Path) -> str:
    """Return the SHA-256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_sha256(folder: Path) -> str:
    """Return the SHA-256 over a package's relative paths and file contents."""
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        digest.update(f"{path.relative_to(folder).as_posix()}\0{file_sha256(path)}\n".encode())
    return digest.hexdigest()


def extract(archive: Path, target: Path) -> None:
    """Extract a .hveplugin archive after rejecting unsafe names and checking its SHA256SUMS."""
    with zipfile.ZipFile(archive) as package:
        for info in package.infolist():
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts or ":" in info.filename or "\\" in info.filename \
                    or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"unsafe entry in {archive.name}: {info.filename!r}")
        package.extractall(target)
    sums = target / SUMS
    if not sums.is_file():
        raise ValueError(f"{archive.name} has no {SUMS}; build packages with `plugin.py pack`")
    listed = dict(reversed(line.split("  ", 1)) for line in sums.read_text(encoding="utf-8").splitlines() if line)
    actual = {p.relative_to(target).as_posix(): file_sha256(p) for p in target.rglob("*") if p.is_file() and p != sums}
    if listed != actual:
        raise ValueError(f"{archive.name}: {SUMS} does not match the files")
    sums.unlink()


def fetch(url: str, target: Path) -> None:
    """Copy a local file or download an https URL to target."""
    if url.startswith("https://"):
        with urllib.request.urlopen(url, timeout=60) as response:
            target.write_bytes(response.read())
    elif "://" in url:
        raise ValueError(f"only https URLs or local paths are allowed, got {url!r}")
    else:
        shutil.copyfile(url, target)


def read_index(index: str) -> Json:
    """Return the organization plugin index from a path or https URL."""
    if index.startswith("https://"):
        with urllib.request.urlopen(index, timeout=60) as response:
            data = json.loads(response.read())
    else:
        data = json.loads(Path(index).read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("plugins"), list):
        raise ValueError(f"{index} is not a version 1 plugin index")
    return data


def stage(source: str, index: str | None, staging: Path) -> bool:
    """Put the package into staging; return whether its hash was verified against the organization index."""
    staging.mkdir(parents=True)
    if source.startswith("index:"):
        if index is None:
            raise ValueError("index sources need --index (the frontierHve.pluginIndex setting)")
        name, _, version = source[len("index:"):].partition("@")
        found = [p for p in read_index(index)["plugins"] if p["name"] == name and p["version"] == version]
        if len(found) != 1:
            raise LookupError(f"{name}@{version} is not in the index {index}")
        if found[0].get("revoked"):
            raise PermissionError(f"{name}@{version} is revoked in the index and cannot be installed")
        archive = staging.parent / f"{staging.name}.hveplugin"
        fetch(found[0]["url"], archive)
        if file_sha256(archive) != found[0]["sha256"]:
            raise ValueError(f"{name}@{version}: the downloaded package does not match the index sha256")
        extract(archive, staging)
        archive.unlink()
        return True
    if source.startswith("https://") and source.endswith(".git"):
        subprocess.run(["git", "clone", "--depth", "1", "--quiet", source, str(staging / "src")], check=True)
        shutil.rmtree(staging / "src" / ".git")
        for item in (staging / "src").iterdir():
            item.rename(staging / item.name)
        (staging / "src").rmdir()
        return False
    path = Path(source)
    if path.is_dir():
        shutil.copytree(path, staging, dirs_exist_ok=True)
    elif path.is_file():
        extract(path, staging)
    else:
        raise FileNotFoundError(f"plugin source not found: {source}")
    return False


def summary(data: Json, digest: str, verified: bool, current: Json | None) -> Json:
    """Return what the user confirms: identity, hash, tools, and whether confirmation is needed."""
    grew = sorted(set(data["tools"]) - set(current["tools"])) if current else data["tools"]
    return {"id": data["id"], "name": data["name"], "publisher": data["publisher"], "version": data["version"], "sha256": digest,
            "tools": data["tools"], "newTools": grew, "verifiedByIndex": verified,
            "needsConfirmation": not verified or bool(current is None or grew)}


def inspect(source: str, index: str | None) -> Json:
    """Validate a package without installing it; return what the user must confirm."""
    staging = store.home() / "staging" / uuid.uuid4().hex
    try:
        verified = stage(source, index, staging)
        data = manifest.load(staging)
        return summary(data, content_sha256(staging), verified, store.registry()["plugins"].get(data["id"]))
    finally:
        remove(staging)


def install(source: str, index: str | None, confirm: str | None, owner: str) -> Json:
    """Validate, confirm and commit a package to the store and registry; the same version with the same content is a no-op."""
    with store_lock():
        cleanup()
        staging = store.home() / "staging" / uuid.uuid4().hex
        try:
            verified = stage(source, index, staging)
            data = manifest.load(staging)
            digest = content_sha256(staging)
            registry = store.registry()
            clash = [e["id"] for e in registry["plugins"].values() if e["name"] == data["name"] and e["id"] != data["id"]]
            if clash:
                raise ValueError(f"plugin name {data['name']!r} is already used by {clash[0]}")
            current = registry["plugins"].get(data["id"])
            if current and current["version"] == data["version"]:
                if current["sha256"] != digest:
                    raise ValueError(f"{data['id']} {data['version']} is installed with different content; publish a new version")
                return {"installed": False, "unchanged": True, "id": data["id"], "version": data["version"]}
            info = summary(data, digest, verified, current)
            if info["needsConfirmation"] and confirm != digest:
                raise PermissionError("confirm this plugin by passing --confirm <sha256> after reviewing it: " + json.dumps(info))
            target = store.home() / "plugins" / data["id"] / data["version"]
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            staging.rename(target)
            registry["plugins"][data["id"]] = {
                "id": data["id"], "name": data["name"], "version": data["version"], "source": source, "sha256": digest,
                "enabled": True, "disabledReason": None, "tools": data["tools"], "owner": owner,
                "installed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "previous": current["version"] if current else None,
                "manifest": data}
            write_registry(registry)
            return {"installed": True, "id": data["id"], "version": data["version"], "previous": current["version"] if current else None}
        finally:
            remove(staging)


def find(name: str) -> tuple[Json, Json]:
    """Return the registry and the entry with this short name, or raise."""
    registry = store.registry()
    found = [e for e in registry["plugins"].values() if e["name"] == name]
    if not found:
        raise LookupError(f"plugin {name!r} is not installed")
    return registry, found[0]


def set_enabled(name: str, enabled: bool, reason: str | None) -> Json:
    """Enable or disable an installed plugin."""
    with store_lock():
        registry, entry = find(name)
        entry["enabled"], entry["disabledReason"] = enabled, reason
        write_registry(registry)
        return {"id": entry["id"], "enabled": enabled}


def uninstall(name: str) -> Json:
    """Remove a plugin from the registry, then its store and rendered folders."""
    with store_lock():
        registry, entry = find(name)
        del registry["plugins"][entry["id"]]
        write_registry(registry)
        for folder in (store.home() / "plugins" / entry["id"], store.home() / "rendered" / entry["id"]):
            remove(folder)
        return {"uninstalled": entry["id"]}


def remove(path: Path) -> None:
    """Delete a file or folder that may not exist."""
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def cleanup() -> list[str]:
    """Delete staging leftovers and store versions the registry no longer points to; return what was removed."""
    removed = []
    for leftover in (store.home() / "staging").glob("*"):
        remove(leftover)
        removed.append(leftover.name)
    plugins = store.registry()["plugins"]
    for version in (store.home() / "plugins").glob("*/*"):
        entry = plugins.get(version.parent.name)
        if entry is None or entry["version"] != version.name:
            shutil.rmtree(version)
            removed.append(f"{version.parent.name}/{version.name}")
    return removed


def reconcile(index: str | None) -> Json:
    """On activation: clean up, and disable plugins that are revoked in the index or whose store content changed."""
    with store_lock():
        removed = cleanup()
        registry = store.registry()
        revoked = {(p["name"], p["version"]) for p in read_index(index)["plugins"] if p.get("revoked")} if index else set()
        disabled = []
        for entry in (e for e in registry["plugins"].values() if e["enabled"]):
            reason = ("revoked in the organization index" if (entry["name"], entry["version"]) in revoked
                      else "store content changed since install" if content_sha256(store.folder(entry)) != entry["sha256"] else None)
            if reason:
                entry["enabled"], entry["disabledReason"] = False, reason
                disabled.append({"id": entry["id"], "reason": reason})
        write_registry(registry)
        return {"removed": removed, "disabled": disabled}


def pack(folder: Path, out: Path) -> Json:
    """Validate a plugin folder and write a deterministic <name>-<version>.hveplugin with SHA256SUMS; return its path and hash."""
    data = manifest.load(folder)
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    sums = "".join(f"{file_sha256(p)}  {p.relative_to(folder).as_posix()}\n" for p in files)
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f"{data['name']}-{data['version']}.hveplugin"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for name, content in [(p.relative_to(folder).as_posix(), p.read_bytes()) for p in files] + [(SUMS, sums.encode())]:
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            package.writestr(info, content)
    return {"package": str(archive), "sha256": file_sha256(archive), "id": data["id"], "version": data["version"]}


def listing() -> list[Json]:
    """Return the installed plugins without their full manifests."""
    return [{k: e[k] for k in ("id", "name", "version", "enabled", "disabledReason", "owner", "source")} | {
        "agents": [a["name"] for a in e["manifest"]["agents"]], "flows": sorted(e["manifest"]["flows"]),
        "templates": sorted(e["manifest"]["templates"])} for e in store.registry()["plugins"].values()]


def requirements(workspace: Path) -> Json:
    """Compare the workspace's committed frontier-hve.plugins.json with the installed plugins: ok, missing, or a version conflict."""
    path = workspace / REQUIREMENTS
    if not path.exists():
        return {"file": None, "ok": [], "missing": [], "conflicts": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("plugins"), list):
        raise ValueError(f"{path} must be {{\"version\": 1, \"plugins\": [{{\"name\", \"range\", \"source\"}}]}}")
    installed = {e["name"]: e for e in store.registry()["plugins"].values()}
    result: Json = {"file": str(path), "ok": [], "missing": [], "conflicts": []}
    for need in data["plugins"]:
        if not isinstance(need, dict) or set(need) != {"name", "range", "source"}:
            raise ValueError(f"{path}: each plugin needs exactly name, range and source")
        entry = installed.get(need["name"])
        if entry is None:
            result["missing"].append(need)
        elif not entry["enabled"] or not manifest.satisfies(entry["version"], need["range"]):
            result["conflicts"].append(need | {"installed": entry["version"], "enabled": entry["enabled"]})
        else:
            result["ok"].append(need | {"installed": entry["version"]})
    return result


def main() -> None:
    """Run one plugin command and print its JSON result."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate").add_argument("folder", type=Path)
    for name in ("inspect", "install"):
        command = commands.add_parser(name)
        command.add_argument("source", help="plugin folder, .hveplugin file, https git URL ending in .git, or index:<name>@<version>")
        command.add_argument("--index", help="organization plugin index (path or https URL)")
        if name == "install":
            command.add_argument("--confirm", help="the sha256 shown by inspect, confirming the source and tools")
            command.add_argument("--owner", default="user", help="'user', or the id of the wrapper extension that installed it")
    for name in ("enable", "disable", "uninstall"):
        commands.add_parser(name).add_argument("name")
    commands.add_parser("list")
    commands.add_parser("reconcile").add_argument("--index")
    packer = commands.add_parser("pack")
    packer.add_argument("folder", type=Path)
    packer.add_argument("--out", type=Path, required=True)
    resolver = commands.add_parser("resolve", help="show which plugins a prompt routes to")
    resolver.add_argument("prompt")
    starter = commands.add_parser("init", help="scaffold a plugin repository: plugin/ package and a release workflow")
    starter.add_argument("repo", type=Path)
    starter.add_argument("--name", required=True)
    starter.add_argument("--publisher", required=True)
    starter.add_argument("--display-name", required=True)
    commands.add_parser("test", help="validate a package and run its tests/routing.json cases").add_argument("folder", type=Path)
    commands.add_parser("requirements", help=f"check the workspace's {REQUIREMENTS}").add_argument("workspace", type=Path)
    args = parser.parse_args()
    failed = False
    if args.command == "validate":
        result: object = manifest.load(args.folder.resolve())
    elif args.command == "init":
        result = author.init(args.repo.resolve(), args.name, args.publisher, args.display_name)
    elif args.command == "test":
        result = author.test(args.folder.resolve())
        failed = not result["passed"]
    elif args.command == "requirements":
        result = requirements(args.workspace.resolve())
    elif args.command == "inspect":
        result = inspect(args.source, args.index)
    elif args.command == "install":
        result = install(args.source, args.index, args.confirm, args.owner)
    elif args.command in ("enable", "disable"):
        result = set_enabled(args.name, args.command == "enable", None if args.command == "enable" else "disabled by the user")
    elif args.command == "uninstall":
        result = uninstall(args.name)
    elif args.command == "list":
        result = listing()
    elif args.command == "reconcile":
        result = reconcile(args.index)
    elif args.command == "pack":
        result = pack(args.folder.resolve(), args.out.resolve())
    else:
        result = candidates(args.prompt, Path.cwd())
    print(json.dumps(result, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
