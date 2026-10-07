"""Prototype complexity guardrail: flag oversized code, non-enterprise components and self-built infrastructure, and name who to involve."""

import hashlib
import json
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

CATALOG = json.loads((Path(__file__).parent / "enterprise_catalog.json").read_text(encoding="utf-8"))
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".scss", ".html", ".vue", ".svelte", ".sql"}
SKIP_DIRS = {"node_modules", ".next", ".git", ".harness", ".hve", "dist", "build", "coverage", ".venv", "venv",
             "__pycache__"}
REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9_.\-]+)")
IMAGE = re.compile(r"^\s*(?:image:|FROM)\s+([^\s:@]+)", re.I | re.M)
INFRA_NAMES = re.compile(r"^(Dockerfile|docker-compose[\w.-]*\.ya?ml|Chart\.yaml|.*\.tf|.*\.bicep)$", re.I)

Json = dict[str, Any]


def walk(project: Path) -> list[Path]:
    """Return the project's files, skipping dependency, build and state folders."""
    files = []
    for folder, dirs, names in os.walk(project):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        files += [Path(folder) / n for n in names]
    return files


def dependencies(files: list[Path]) -> list[tuple[str, str]]:
    """Return (name, manifest) for every declared package and container image."""
    found = []
    for path in files:
        if path.name == "package.json":
            data = json.loads(path.read_text(encoding="utf-8"))
            found += [(n, path.name) for key in ("dependencies", "devDependencies") for n in data.get(key, {})]
        elif path.name.startswith("requirements") and path.suffix == ".txt":
            found += [(m.group(1), path.name) for line in path.read_text(encoding="utf-8").splitlines()
                      if not line.lstrip().startswith(("#", "-")) and (m := REQUIREMENT_NAME.match(line))]
        elif path.name == "pyproject.toml":
            deps = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {}).get("dependencies", [])
            found += [(m.group(1), path.name) for d in deps if (m := REQUIREMENT_NAME.match(d))]
        elif INFRA_NAMES.match(path.name) and path.suffix not in (".tf", ".bicep"):
            found += [(image.split("/")[-1], path.name) for image in IMAGE.findall(path.read_text(encoding="utf-8"))]
    return found


def scan(project: Path) -> Json:
    """Return the guardrail report: code size, flagged components with enterprise alternatives, infra files, verdict, experts."""
    files = walk(project)
    sizes = {p: len(p.read_text(encoding="utf-8", errors="replace").splitlines()) for p in files if p.suffix.lower() in CODE_SUFFIXES}
    flagged = []
    for name, manifest in dependencies(files):
        for component in CATALOG["components"]:
            if re.match(component["pattern"], name.lower()):
                flagged.append({"name": name, "manifest": manifest, "category": component["category"], "enterprise": component["enterprise"]})
    infra = sorted(p.relative_to(project).as_posix() for p in files
                   if INFRA_NAMES.match(p.name) or ".github/workflows/" in p.relative_to(project).as_posix())
    code_lines = sum(sizes.values())
    large = sorted((p.relative_to(project).as_posix(), round(p.stat().st_size / 1e6, 1)) for p in files
                   if p.stat().st_size > CATALOG["file_mb_limit"] * 1e6)
    reasons = ([f"{code_lines} lines of code (limit {CATALOG['code_lines_limit']})"] if code_lines > CATALOG["code_lines_limit"] else [])
    reasons += [f"{name} is {mb} MB (limit {CATALOG['file_mb_limit']} MB): unbounded logs, exports or data files need retention"
                for name, mb in large]
    reasons += [f"{f['name']} ({f['category']}) in {f['manifest']}: enterprise option is {f['enterprise']}" for f in flagged]
    reasons += [f"self-built infrastructure: {', '.join(infra)}"] if infra else []
    areas = ({"size"} if code_lines > CATALOG["code_lines_limit"] else set()) | ({"storage"} if large else set())
    areas |= {f["category"] for f in flagged} | ({"infrastructure"} if infra else set())
    return {"project": project.as_posix(), "code_lines": code_lines, "largest_files": sorted(
                ({"path": p.relative_to(project).as_posix(), "lines": n} for p, n in sizes.items()), key=lambda f: -f["lines"])[:5],
            "flagged": flagged, "infrastructure_files": infra, "verdict": "review" if reasons else "ok", "reasons": reasons,
            "experts": sorted({e.strip() for a in areas for e in CATALOG["experts"][a].split(",")})}


def hook() -> None:
    """PostToolUse: re-scan harness projects and tell the user and agent once per new finding set."""
    payload = json.load(sys.stdin)
    if payload["hook_event_name"] != "PostToolUse":
        raise ValueError(f"guardrail.py --hook does not handle {payload['hook_event_name']!r}")
    cwd = Path.cwd()
    for harness in [cwd / ".harness", *cwd.glob(".hve/outputs/*/current/.harness")]:
        if not harness.is_dir():
            continue
        report = scan(harness.parent)
        digest = hashlib.sha1(json.dumps(report["reasons"]).encode()).hexdigest()
        state_file = harness / "guardrail.json"
        seen = json.loads(state_file.read_text(encoding="utf-8"))["digest"] if state_file.exists() else None
        state_file.write_text(json.dumps({"digest": digest, "report": report}, indent=2), encoding="utf-8")
        if report["verdict"] == "review" and digest != seen:
            message = (f"Prototype guardrail ({harness.parent.name}): " + "; ".join(report["reasons"]) +
                       f". Involve: {', '.join(report['experts'])}. Use the prototype-guardrail skill before adding more.")
            print(json.dumps({"systemMessage": message, "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message}}))
            return


if __name__ == "__main__":
    if sys.argv[1:] == ["--hook"]:
        hook()
    elif len(sys.argv) == 2:
        print(json.dumps(scan(Path(sys.argv[1]).resolve()), indent=2))
    else:
        raise SystemExit("usage: guardrail.py <project> | --hook")
