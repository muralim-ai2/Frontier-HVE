"""Validate an expertise pack (plugin) folder and return its normalized manifest: Markdown and JSON only, every asset declared, well
formed and measured in tokens."""

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools" / "loop"), str(ROOT / "tools" / "templates"), str(ROOT / "tools" / "evaluation")]
from compose import plugin_contract  # noqa: E402
from contract import load_contract  # noqa: E402
from lifecycle_catalog import validate as validate_lifecycle  # noqa: E402
from manage import IDENTITY, KINDS, SECTION  # noqa: E402
from stage_evidence import project_path  # noqa: E402

API_VERSIONS = (1,)
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
KIND = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
COMPARATOR = re.compile(r"^(>=|<=|>|<|=)(\d+\.\d+\.\d+)$")
RESERVED = {"frontier-hve", "hve", "core"}
DATA_SUFFIXES = {".md", ".json", ".txt"}
LICENSE_NAMES = {"LICENSE", "NOTICE"}
ASSET_FOLDERS = ("agents", "templates", "lifecycles", "knowledge", "evaluation")
KNOWLEDGE_KINDS = ("process-map", "runbook", "solution", "reference")
MAX_PACKAGE_BYTES = 20 * 1024 * 1024
CHARS_PER_TOKEN = 4
AGENT_KEYS = {"name", "description", "tools", "agents", "user-invocable", "argument-hint"}
MANIFEST_KEYS = {"$schema", "name", "displayName", "version", "publisher", "harness", "description", "routing", "agents", "skills",
                 "templates", "lifecycles", "knowledge", "evaluation", "tools"}
REQUIRED_KEYS = {"name", "displayName", "version", "publisher", "harness", "description", "routing", "agents", "skills", "templates", "tools"}
CORE_CONTRACT = ROOT / "evaluation" / "frontier.eval.json"

Json = dict[str, Any]


def tokens(path: Path) -> int:
    """Return a file's estimated token count."""
    return len(path.read_text(encoding="utf-8")) // CHARS_PER_TOKEN


def version_tuple(value: str) -> tuple[int, int, int]:
    """Return a semantic version as a tuple, or raise."""
    match = VERSION.fullmatch(value)
    if not match:
        raise ValueError(f"version must be MAJOR.MINOR.PATCH, got {value!r}")
    return int(match[1]), int(match[2]), int(match[3])


def satisfies(version: str, spec: str) -> bool:
    """Return whether version meets every space-separated comparator in spec (for example '>=0.9.0 <2.0.0')."""
    ops = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, "<": lambda a, b: a < b, "=": lambda a, b: a == b}
    parts = spec.split()
    matches = [COMPARATOR.fullmatch(p) for p in parts]
    if not parts or not all(matches):
        raise ValueError(f"version range must be comparators like '>=0.9.0 <2.0.0', got {spec!r}")
    return all(ops[m[1]](version_tuple(version), version_tuple(m[2])) for m in matches if m)


def core_version() -> str:
    """Return the core version from the extension manifest (repository layout) or the packaged runtime's parent folder."""
    repo, packaged = ROOT / "extension" / "package.json", ROOT.parent / "package.json"
    path = repo if (ROOT / "extension").is_dir() else packaged
    return json.loads(path.read_text(encoding="utf-8"))["version"]


def strings(value: object, field: str) -> list[str]:
    """Return a list of non-empty strings, or raise."""
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"{field} must be a list of non-empty strings")
    return list(value)


def frontmatter(path: Path) -> Json:
    """Return an agent file's frontmatter fields (top-level keys only; list values as lists of strings)."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"{path.name} needs YAML frontmatter between --- lines")
    fields: Json = {}
    for line in text[4:text.index("\n---\n", 4)].splitlines():
        if not line.strip() or line[0] in " \t":
            if line.strip():
                raise ValueError(f"{path.name}: nested frontmatter (for example hooks) is not allowed in plugin agents: {line.strip()!r}")
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"{path.name}: frontmatter line is not 'key: value': {line!r}")
        value = value.strip()
        fields[key.strip()] = [v.strip() for v in value[1:-1].split(",") if v.strip()] if value.startswith("[") else value.strip("'\"")
    return fields


def files_of(folder: Path) -> list[Path]:
    """Return every file of a package after rejecting links, case collisions, scripts and an oversized package."""
    files, seen, size = [], set(), 0
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder).as_posix()
        if path.is_symlink() or (path.is_dir() and path.resolve() != path.absolute().resolve()):
            raise ValueError(f"links are not allowed in a plugin: {relative}")
        if relative.lower() in seen:
            raise ValueError(f"names that differ only by case are not allowed: {relative}")
        seen.add(relative.lower())
        if path.is_dir():
            if path.name == "hooks":
                raise ValueError(f"plugins cannot ship hooks: {relative}")
            continue
        if path.suffix.lower() not in DATA_SUFFIXES and path.name not in LICENSE_NAMES:
            raise ValueError(f"plugins contain Markdown and JSON only; not allowed: {relative}")
        size += path.stat().st_size
        files.append(path)
    if size > MAX_PACKAGE_BYTES:
        raise ValueError(f"plugin is {size} bytes, over the {MAX_PACKAGE_BYTES} byte limit")
    return files


def declared(folder: Path, value: object, field: str) -> Path:
    """Return a declared package file after checking it is relative, inside the package and present."""
    path = folder / project_path(value, field)
    if not path.is_file():
        raise ValueError(f"{field} {value} does not exist")
    return path


def agents(folder: Path, raw: object, tools: list[str]) -> list[Json]:
    """Return validated agents: frontmatter name matches, no hooks or unknown keys, tools within the manifest tools."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("agents must be a non-empty list")
    result = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or set(item) - {"name", "file", "capabilities", "handoffFrom"} or not NAME.fullmatch(str(item.get("name"))):
            raise ValueError(f"agents[{i}] needs a kebab-case name, a file, capabilities and optional handoffFrom")
        path = declared(folder, item.get("file"), f"agents[{i}].file")
        if not path.name.endswith(".agent.md") or path.parent != folder / "agents":
            raise ValueError(f"agents[{i}].file must be agents/<name>.agent.md")
        front = frontmatter(path)
        unknown = sorted(set(front) - AGENT_KEYS)
        if unknown:
            raise ValueError(f"{path.name}: frontmatter keys {unknown} are not allowed (allowed: {sorted(AGENT_KEYS)}; no hooks)")
        if front.get("name") != item["name"] or not front.get("description"):
            raise ValueError(f"{path.name}: frontmatter name must be {item['name']!r} and description non-empty")
        outside = sorted(set(front.get("tools", [])) - set(tools))
        if outside:
            raise ValueError(f"{path.name}: tools {outside} are not in the manifest tools the user consents to")
        result.append({"name": item["name"], "file": path.relative_to(folder).as_posix(), "description": front["description"],
                       "capabilities": strings(item.get("capabilities"), f"agents[{i}].capabilities"), "tokens": tokens(path)})
    if len({a["name"] for a in result}) != len(result):
        raise ValueError("agent names must be unique")
    return result


def categories(folder: Path, name: str) -> dict[str, Json]:
    """Return the pack's task categories, namespaced '<pack>:<category>', from the optional categories.json."""
    path = folder / "categories.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if set(raw) != {"categories"} or not isinstance(raw["categories"], dict):
        raise ValueError("categories.json has exactly {\"categories\": {<name>: {\"task_pattern\": <regex>}}}")
    result = {}
    for key, value in raw["categories"].items():
        if not NAME.fullmatch(key) or not isinstance(value, dict) or set(value) != {"task_pattern"}:
            raise ValueError(f"category {key!r} needs a kebab-case name and exactly a task_pattern")
        re.compile(value["task_pattern"])
        result[f"{name}:{key}"] = {"task_pattern": value["task_pattern"]}
    return result


def skills(folder: Path, name: str, raw: object, cats: dict[str, Json]) -> list[Json]:
    """Return skill entries normalized for the ranker: admitted (organization-vetted), tokens from SKILL.md, no measured lift."""
    if raw != "registry.json":
        raise ValueError("skills must be \"registry.json\"")
    data = json.loads(declared(folder, raw, "skills").read_text(encoding="utf-8"))
    if set(data) != {"skills"} or not isinstance(data["skills"], list):
        raise ValueError("registry.json has exactly {\"skills\": [{name, description, task_categories}]}")
    core_cats = set(json.loads((ROOT / "skills" / "categories.json").read_text(encoding="utf-8"))["categories"])
    result = []
    for i, item in enumerate(data["skills"]):
        if not isinstance(item, dict) or set(item) != {"name", "description", "task_categories"} or not NAME.fullmatch(str(item["name"])):
            raise ValueError(f"registry.json skills[{i}] needs exactly a kebab-case name, description and task_categories")
        skill = declared(folder, f"skills/{item['name']}/SKILL.md", f"skill {item['name']}")
        own = [f"{name}:{c}" if f"{name}:{c}" in cats else c for c in strings(item["task_categories"], f"skill {item['name']}.task_categories")]
        unknown = sorted(set(own) - core_cats - set(cats))
        if unknown or not isinstance(item["description"], str) or not item["description"]:
            raise ValueError(f"skill {item['name']}: description must be non-empty and categories known; unknown {unknown}")
        result.append({"name": item["name"], "description": item["description"], "task_categories": own, "status": "admitted",
                       "skill_tokens": tokens(skill), "quality_lift_pp": None})
    if len({s["name"] for s in result}) != len(result):
        raise ValueError("skill names must be unique")
    return result


def templates(folder: Path, raw: object) -> dict[str, Json]:
    """Return templates by kind: markers match the kind and version; kinds the core lacks declare an output with one {slug}."""
    if not isinstance(raw, dict):
        raise ValueError("templates must be an object of kind -> {file, version[, output]}")
    result = {}
    for kind, spec in raw.items():
        if not KIND.fullmatch(kind) or not isinstance(spec, dict) or set(spec) - {"file", "version", "output"}:
            raise ValueError(f"template {kind!r} needs an alphanumeric kind and file, version and (for new kinds) output")
        version = spec.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError(f"template {kind}.version must be a positive integer")
        path = declared(folder, spec.get("file"), f"template {kind}.file")
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        if IDENTITY.findall(text) != [(kind, str(version))] or not SECTION.findall(text):
            raise ValueError(f"template {kind} needs exactly one '<!-- hve-template: {kind}@{version} -->' marker and section markers")
        entry = {"file": spec["file"], "version": version, "tokens": tokens(path)}
        if kind in KINDS:
            if "output" in spec:
                raise ValueError(f"template {kind} is a core kind; its output comes from the workspace policy")
        else:
            output = project_path(spec.get("output"), f"template {kind}.output")
            if output.count("{slug}") != 1 or not output.endswith(".md"):
                raise ValueError(f"template {kind}.output must be a Markdown path with exactly one {{slug}}")
            entry["output"] = output
        result[kind] = entry
    return result


def knowledge(folder: Path, raw: object) -> list[Json]:
    """Return the knowledge index: each document's id, file, title, kind, when to open it, the stages it serves, and its tokens."""
    if not isinstance(raw, list):
        raise ValueError("knowledge must be a list of {id, file, title, kind, use_when, stages}")
    result = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or set(item) != {"id", "file", "title", "kind", "use_when", "stages"} or not NAME.fullmatch(str(item["id"])):
            raise ValueError(f"knowledge[{i}] needs exactly a kebab-case id, file, title, kind, use_when and stages")
        if item["kind"] not in KNOWLEDGE_KINDS or not all(isinstance(item[k], str) and item[k] for k in ("title", "use_when")):
            raise ValueError(f"knowledge {item['id']}: kind must be one of {list(KNOWLEDGE_KINDS)}; title and use_when non-empty")
        path = declared(folder, item["file"], f"knowledge {item['id']}.file")
        if path.parent != folder / "knowledge":
            raise ValueError(f"knowledge {item['id']}.file must be in knowledge/")
        stages = item["stages"] if item["stages"] == [] else strings(item["stages"], f"knowledge {item['id']}.stages")
        result.append({k: item[k] for k in ("id", "file", "title", "kind", "use_when")} | {"stages": stages, "tokens": tokens(path)})
    if len({k["id"] for k in result}) != len(result):
        raise ValueError("knowledge ids must be unique")
    return result


def references(lifecycle: Json, name: str, agent_names: set[str], skill_names: set[str], kinds: set[str]) -> None:
    """Raise unless every '<pack>:' reference in the pack's lifecycle names this pack's own agent, skill or template kind."""
    own = {"agent": agent_names, "skill": skill_names, "template": {k.partition(":")[2] for k in kinds if ":" in k}}
    for stage in lifecycle["stages"]:
        refs = ([("agent", stage["agent"])] + [("skill", s) for s in stage["skills"]] + [("template", t) for t in stage["templates"]]
                + [("template", e["kind"]) for e in stage.get("evidence", []) if e["type"] == "template-valid"])
        for kind, ref in refs:
            prefix, sep, asset = ref.partition(":")
            if sep and (prefix != name or asset not in own[kind]):
                raise ValueError(f"lifecycle {lifecycle['name']}: stage {stage['name']} {kind} {ref!r} is not a {kind} of pack {name}")
        if any(":" in p for p in stage["plugin_skills"]):
            raise ValueError(f"lifecycle {lifecycle['name']}: stage {stage['name']} plugin_skills name harness-assist skills only")


def lifecycles(folder: Path, name: str, raw: object, agent_names: set[str], skill_names: set[str], kinds: set[str]) -> dict[str, Json]:
    """Return the pack's lifecycles (process overlays) as '<pack>:<name>', validated like core lifecycles, with their tokens."""
    result = {}
    for i, path in enumerate(strings(raw, "lifecycles") if raw != [] else []):
        file = declared(folder, path, f"lifecycles[{i}]")
        if file.parent != folder / "lifecycles":
            raise ValueError(f"lifecycles[{i}] must be in lifecycles/")
        lifecycle = json.loads(file.read_text(encoding="utf-8"))
        if not NAME.fullmatch(str(lifecycle.get("name"))):
            raise ValueError(f"{path}: lifecycle name must be kebab-case")
        lifecycle = validate_lifecycle(lifecycle, f"pack {name} {path}")
        references(lifecycle, name, agent_names, skill_names, kinds)
        full = f"{name}:{lifecycle['name']}"
        result[full] = lifecycle | {"name": full, "file": path, "tokens": tokens(file)}
    return result


def load(folder: Path) -> Json:
    """Return the normalized manifest of a pack folder, or raise naming the first problem."""
    files = files_of(folder)
    manifest_file = declared(folder, "hve-plugin.json", "manifest")
    raw = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) - MANIFEST_KEYS or not REQUIRED_KEYS <= set(raw):
        raise ValueError(f"hve-plugin.json keys: required {sorted(REQUIRED_KEYS)}, optional lifecycles, knowledge, evaluation, $schema; "
                         f"got {sorted(raw)}")
    name, publisher = raw["name"], raw["publisher"]
    if not (isinstance(name, str) and NAME.fullmatch(name) and isinstance(publisher, str) and NAME.fullmatch(publisher)):
        raise ValueError("name and publisher must be lowercase kebab-case")
    if name in RESERVED or publisher in RESERVED:
        raise ValueError(f"{sorted(RESERVED)} are reserved")
    version_tuple(raw["version"])
    harness = raw["harness"]
    if not isinstance(harness, dict) or set(harness) != {"apiVersion", "frontierHve"} or harness["apiVersion"] not in API_VERSIONS:
        raise ValueError(f"harness needs apiVersion in {API_VERSIONS} and a frontierHve version range")
    if not satisfies(core_version(), harness["frontierHve"]):
        raise ValueError(f"plugin needs Frontier HVE {harness['frontierHve']}; this core is {core_version()}")
    plugin_json = folder / "plugin.json"
    if plugin_json.exists() and "hooks" in json.loads(plugin_json.read_text(encoding="utf-8")):
        raise ValueError("plugin.json must not declare hooks")
    routing = raw["routing"]
    if not isinstance(routing, dict) or set(routing) != {"domains", "keywords", "task_pattern", "workspace_signals"}:
        raise ValueError("routing has exactly domains, keywords, task_pattern and workspace_signals")
    re.compile(routing["task_pattern"])
    for key in ("domains", "keywords"):
        strings(routing[key], f"routing.{key}")
    if routing["workspace_signals"] != []:
        strings(routing["workspace_signals"], "routing.workspace_signals")
    tools = strings(raw["tools"], "tools")
    agent_list = agents(folder, raw["agents"], tools)
    cats = categories(folder, name)
    skill_list = skills(folder, name, raw["skills"], cats)
    template_map = templates(folder, raw["templates"])
    docs = knowledge(folder, raw.get("knowledge", []))
    kinds = set(KINDS) | {f"{name}:{k}" for k in template_map if k not in KINDS}
    flows = lifecycles(folder, name, raw.get("lifecycles", []), {a["name"] for a in agent_list}, {s["name"] for s in skill_list}, kinds)
    contracts = [raw["evaluation"]] if "evaluation" in raw else []
    for path in contracts:
        plugin_contract(json.loads(declared(folder, path, "evaluation").read_text(encoding="utf-8")), load_contract(CORE_CONTRACT))
    listed = ({"hve-plugin.json", "plugin.json", "registry.json", "categories.json"} | {a["file"] for a in agent_list}
              | {s["file"] for s in template_map.values()} | {f["file"] for f in flows.values()} | {d["file"] for d in docs} | set(contracts))
    hidden = [p.relative_to(folder).as_posix() for p in files
              if p.relative_to(folder).as_posix() not in listed and p.parts[len(folder.parts)] in ASSET_FOLDERS]
    if hidden:
        raise ValueError(f"undeclared assets: {hidden}")
    for doc in ("README.md", "LICENSE"):
        declared(folder, doc, "package file")
    return {"id": f"{publisher}.{name}", "name": name, "publisher": publisher, "version": raw["version"], "displayName": raw["displayName"],
            "description": raw["description"], "frontierHve": harness["frontierHve"], "routing": routing, "tools": tools,
            "agents": agent_list, "categories": cats, "skills": skill_list, "templates": template_map, "lifecycles": flows,
            "knowledge": docs, "evaluation": raw.get("evaluation"), "manifest_tokens": tokens(manifest_file)}
