"""Build the solution map of any repository: views, modules, files, symbols, concepts and typed edges with evidence."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extract import Facts, file_facts, first_sentence, list_files

CONFIG = Path("docs/architecture/solution-map.config.json")
EXPLORER = Path(__file__).parent / "explorer"
SIZE = {"medium": (50, 5_000), "large": (300, 50_000)}
CODE_KINDS = ("code", "test", "iac", "sql")
NODE_BUILTINS = {"fs", "path", "os", "child_process", "crypto", "url", "util", "events", "stream", "http", "https", "zlib", "assert",
                 "buffer", "readline", "net", "process", "worker_threads", "vscode"}


def load_config(root: Path, path: Path | None) -> dict[str, Any]:
    """Return the map config: the given file, the repository's default file, or an empty config."""
    target = root / (path or CONFIG)
    if path and not target.is_file():
        raise FileNotFoundError(f"map config {target} not found")
    return json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}


def _git(root: Path, *args: str) -> str:
    """Return a git command's output in the repository, or an empty string outside git."""
    if not (root / ".git").exists():
        return ""
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def size_class(files: list[Facts]) -> dict[str, Any]:
    """Return small, medium or large from source files and lines, with the reasons."""
    code = [f for f in files if f["kind"] in CODE_KINDS]
    lines = sum(f["lines"] for f in code)
    cls = "large" if len(code) >= SIZE["large"][0] or lines >= SIZE["large"][1] else "medium" if len(code) >= SIZE["medium"][0] or lines >= SIZE["medium"][1] else "small"
    return {"class": cls, "code_files": len(code), "code_lines": lines, "files": len(files), "tokens": sum(f["tokens"] for f in files),
            "why": [f"{len(code)} code files", f"{lines:,} code lines", f"thresholds medium {SIZE['medium'][0]} files or {SIZE['medium'][1]:,} lines, large {SIZE['large'][0]} or {SIZE['large'][1]:,}"]}


def _placement(rel: str, rules: list[dict[str, Any]]) -> tuple[str, str, str, str]:
    """Return view id, module id, module name and module purpose: the first matching config rule, else the file's folder."""
    for rule in rules:
        if re.search(rule["match"], rel):
            return rule["view"], rule["id"], rule["name"], rule.get("purpose", "")
    parts = rel.split("/")
    folder = "/".join(parts[:-1]) or "."
    return (parts[0] if len(parts) > 1 else "root"), f"mod:{folder}", folder, ""


class Resolver:
    """Resolve imports and file-name mentions to mapped files."""

    def __init__(self, paths: list[str]) -> None:
        """Index the mapped paths by full path, basename and dotted module name."""
        self.paths = set(paths)
        self.by_name: dict[str, list[str]] = defaultdict(list)
        self.by_module: dict[str, list[str]] = defaultdict(list)
        for p in paths:
            self.by_name[Path(p).name].append(p)
            if p.endswith(".py"):
                dotted = p[:-3].replace("/", ".").removesuffix(".__init__")
                parts = dotted.split(".")
                for i in range(len(parts)):
                    self.by_module[".".join(parts[i:])].append(p)

    def mention(self, text: str) -> str | None:
        """Return the file a mention names: an exact or suffix path match, else a unique basename."""
        if text in self.paths:
            return text
        if "/" in text:
            hits = [p for p in self.paths if p.endswith("/" + text)]
            if len(hits) == 1:
                return hits[0]
        hits = self.by_name.get(Path(text).name, [])
        return hits[0] if len(hits) == 1 else None

    def python(self, name: str, source: str) -> str | None:
        """Return the file a Python import names, resolving relative imports from the importing file."""
        if name.startswith("."):
            dots = len(name) - len(name.lstrip("."))
            base = Path(source).parents[dots - 1].as_posix() if dots <= len(Path(source).parents) else ""
            rest = name.lstrip(".").replace(".", "/")
            for cand in (f"{base}/{rest}.py", f"{base}/{rest}/__init__.py"):
                if cand.lstrip("./") in self.paths:
                    return cand.lstrip("./")
            return None
        hits = self.by_module.get(name, [])
        return hits[0] if len(hits) == 1 else None

    def script(self, spec: str, source: str) -> str | None:
        """Return the file a JS or TS import names when it is local, trying extensions and index files."""
        if spec.startswith("."):
            base = (Path(source).parent / spec).as_posix()
        elif spec.startswith(("@/", "~/")):
            base = spec[2:]
        else:
            return None
        base = re.sub(r"(^|/)\./", r"\1", base)
        while "/../" in base or base.startswith("../"):
            base = re.sub(r"[^/]+/\.\./", "", base, count=1) if "/../" in base else base[3:]
        for cand in [base] + [base + ext for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")] + [f"{base}/index{ext}" for ext in (".ts", ".tsx", ".js")] + [f"src/{base}.ts", f"src/{base}.tsx"]:
            if cand in self.paths:
                return cand
        return None


def build(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Return the solution map of a repository."""
    exclude = [re.compile(x) for x in config.get("exclude", [])]
    facts = [file_facts(root, rel) for rel in list_files(root, exclude)]
    if not facts:
        raise ValueError(f"no mappable files under {root}")
    for path, text in config.get("purposes", {}).items():
        match = next((f for f in facts if f["path"] == path), None)
        if not match:
            raise ValueError(f"map config purpose for {path}, which is not a mapped file")
        match["purpose"] = text
    rules = config.get("modules", [])
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    readme = next((f for f in facts if f["path"].lower() == "readme.md"), None)
    nodes["system"] = {"id": "system", "level": "system", "name": config.get("name", root.name),
                       "purpose": config.get("purpose") or (readme["purpose"] if readme else ""), "source": "README.md" if readme else ""}
    views = {v["id"]: v for v in config.get("views", [])}
    readmes = {str(Path(f["path"]).parent.as_posix()): f["purpose"] for f in facts if f["path"].lower().endswith("readme.md")}

    def add(node: dict[str, Any], parent: str) -> None:
        nodes[node["id"]] = node
        edges.append({"from": parent, "to": node["id"], "type": "contains", "evidence": node.get("source") or "map placement"})

    for view_id, view in views.items():
        add({"id": f"view:{view_id}", "level": "view", "view": view_id, "name": view["name"], "purpose": view.get("purpose", ""),
             "roles": view.get("roles", [])}, "system")
    resolver = Resolver([f["path"] for f in facts])
    for f in facts:
        view_id, module_id, module_name, module_purpose = _placement(f["path"], rules)
        if f"view:{view_id}" not in nodes:
            add({"id": f"view:{view_id}", "level": "view", "view": view_id, "name": view_id, "purpose": readmes.get(view_id, ""), "roles": []}, "system")
        if module_id not in nodes:
            folder = module_name if module_id.startswith("mod:") else ""
            add({"id": module_id, "level": "module", "view": view_id, "name": module_name, "purpose": module_purpose or readmes.get(folder, ""),
                 "roles": views.get(view_id, {}).get("roles", []), "files": [], "tokens": 0, "placed": not module_id.startswith("mod:")}, f"view:{view_id}")
        nodes[module_id]["files"].append(f["path"])
        nodes[module_id]["tokens"] += f["tokens"]
        fid = f"file:{f['path']}"
        add({"id": fid, "level": "file", "view": view_id, "module": module_id, "kind": f["kind"], "lang": f["lang"], "name": f["name"],
             "purpose": f["purpose"], "source": f["path"], "tokens": f["tokens"], "lines": f["lines"], "hash": f["hash"]}, module_id)
        for s in f["symbols"]:
            add({"id": f"{fid}#{s['name']}", "level": "symbol", "view": view_id, "module": module_id, "kind": s["kind"], "name": s["name"],
                 "purpose": s["purpose"], "source": f"{f['path']}:{s['line']}-{s['end']}"}, fid)
        for d in f["decisions"]:
            add({"id": f"decision:{d['id']}", "level": "symbol", "view": view_id, "module": module_id, "kind": "decision", "name": d["id"],
                 "purpose": d["title"], "source": f"{f['path']}:{d['line']}"}, fid)
    agents = {n["name"]: n["id"] for n in nodes.values() if n.get("kind") == "agent"}
    by_path = {f["path"]: f for f in facts}
    local = {p.split("/")[0] for p in by_path} | {k.split(".")[0] for k in resolver.by_module}

    def link(a: str, b: str, kind: str, evidence: str) -> None:
        if a != b:
            edges.append({"from": a, "to": b, "type": kind, "evidence": evidence})

    for f in facts:
        fid, rel = f"file:{f['path']}", f["path"]
        external = set()
        for name in f["imports"]:
            target = resolver.python(name, rel) if f["lang"] == "python" else resolver.script(name, rel)
            if target and f["kind"] == "test":
                link(f"file:{target}", fid, "tested-by", f"{rel} imports {name}")
            elif target:
                link(fid, f"file:{target}", "imports", f"{rel} imports {name}")
            elif not name.startswith((".", "@/", "~/")):
                top = name.split(".")[0] if f["lang"] == "python" else ("/".join(name.split("/")[:2]) if name.startswith("@") else name.split("/")[0].removeprefix("node:"))
                if top not in sys.stdlib_module_names and top not in NODE_BUILTINS and top not in local:
                    external.add(top)
        nodes[fid]["external"] = sorted(external)
        for hook in f["hooks"]:
            if (target := resolver.mention(hook)):
                link(fid, f"file:{target}", "guarded-by", f"{rel} hook runs {hook}")
        for m in f["mentions"]:
            target = resolver.mention(m)
            if not target or target == rel or m in f["hooks"]:
                continue
            if f["kind"] == "test":
                link(f"file:{target}", fid, "tested-by", f"{rel} names {m}")
            elif f["kind"] == "doc":
                link(f"file:{target}", fid, "documented-in", f"{rel} names {m}")
            elif f["kind"] != "decisions" and by_path[target]["kind"] in CODE_KINDS:
                link(fid, f"file:{target}", "invokes", f"{rel} names {m}")
        for ref in f["refs"]:
            if ref in agents:
                link(fid, agents[ref], "delegates-to", f"{rel} names `{ref}`")
        for d in f["decisions"]:
            for m in d["mentions"]:
                if (target := resolver.mention(m)) and by_path[target]["kind"] != "decisions":
                    link(f"file:{target}", f"decision:{d['id']}", "decided-in", f"{d['id']} names {m}")
    for store in config.get("stores", []):
        sid = f"store:{store['id']}"
        add({"id": sid, "level": "module", "view": store.get("view", "state"), "name": store["name"], "purpose": store.get("purpose", ""),
             "source": store["path"], "kind": "store", "roles": []}, f"view:{store.get('view', 'state')}" if f"view:{store.get('view', 'state')}" in nodes else "system")
        marker = re.compile(store["marker"])
        for f in facts:
            if f["kind"] in ("code",):
                lines = (root / f["path"]).read_text(encoding="utf-8").splitlines()
                for i, line in enumerate(lines):
                    if marker.search(line):
                        link(f"file:{f['path']}", sid, "uses", f"{f['path']}:{i + 1}")
        for module in store.get("written_by", []):
            if module not in nodes:
                raise ValueError(f"store {store['id']} names unknown writer module {module}")
            link(module, sid, "writes", "map config")
    concepts = _concepts(config, nodes, edges)
    unique = list({(e["from"], e["to"], e["type"]): e for e in edges}.values())
    for e in unique:
        if e["from"] not in nodes or e["to"] not in nodes:
            raise ValueError(f"edge to an unknown node: {e}")
    return {"version": 1, "commit": _git(root, "rev-parse", "--short", "HEAD") or "none", "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "root": root.name, "size": size_class(facts), "conventions": config.get("conventions", []), "flows": config.get("flows", []),
            "concepts": concepts, "nodes": list(nodes.values()), "edges": unique, "files": {f["path"]: f["hash"] for f in facts}}


def _concepts(config: dict[str, Any], nodes: dict[str, dict[str, Any]], edges: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Return the concepts from the config, else one per view; add concept nodes and their 'includes' edges."""
    files = [n for n in nodes.values() if n["level"] == "file"]
    specs = config.get("concepts") or [{"id": v["view"], "name": v["name"], "explain": v.get("purpose", ""), "view": v["view"], "derived": True}
                                        for v in nodes.values() if v["level"] == "view"]
    out = []
    for spec in specs:
        if spec.get("view"):
            members = [f["id"] for f in files if f["view"] == spec["view"]]
        else:
            pattern = re.compile("|".join(f"(?:{m})" for m in spec["members"]))
            members = [f["id"] for f in files if pattern.search(f["source"])] + [f"store:{s}" for s in spec.get("stores", []) if f"store:{s}" in nodes]
        if not members:
            raise ValueError(f"concept {spec['id']} matches no mapped file: {spec.get('members') or spec.get('view')}")
        cid = f"concept:{spec['id']}"
        nodes[cid] = {"id": cid, "level": "concept", "name": spec["name"], "purpose": first_sentence(spec.get("explain", "")), "explain": spec.get("explain", ""),
                      "keywords": spec.get("keywords", []), "derived": spec.get("derived", False)}
        edges += [{"from": cid, "to": m, "type": "includes", "evidence": "concept members"} for m in members]
        start = spec.get("start")
        if start and f"file:{start}" not in members:
            raise ValueError(f"concept {spec['id']} start {start} is not one of its members")
        out.append({"id": cid, "name": spec["name"], "explain": spec.get("explain", ""), "keywords": spec.get("keywords", []),
                    "start": f"file:{start}" if start else members[0], "members": members, "derived": spec.get("derived", False),
                    "questions": spec.get("questions", [])})
    return out


def overview(data: dict[str, Any]) -> str:
    """Return the Markdown overview: views and modules, stores, concepts, conventions and flows."""
    nodes = {n["id"]: n for n in data["nodes"]}
    s = data["size"]
    lines = [f"# Solution map: {nodes['system']['name']}", "", nodes["system"]["purpose"], "",
             f"Map of commit `{data['commit']}` built {data['built'][:10]}. Size **{s['class']}** ({', '.join(s['why'][:2])}; {s['files']} mapped files, {s['tokens']:,} tokens).",
             "Read this first. Ask `solution_map.py explain \"<topic>\"` for a concept, `impact --seeds` before a change, `open` for the explorer.", "", "## Concepts", ""]
    for c in data["concepts"]:
        lines.append(f"- **{c['name']}** (`{c['id']}`, {len(c['members'])} files): {first_sentence(c['explain']) or 'no explanation yet'}")
    for view in (n for n in data["nodes"] if n["level"] == "view"):
        mods = [n for n in data["nodes"] if n["level"] == "module" and n.get("view") == view["view"]]
        lines += ["", f"## {view['name']}", "", (view["purpose"] + (f" Roles: {', '.join(view['roles'])}." if view.get("roles") else "")).strip(), "",
                  "| Module | Purpose | Files | Tokens |", "|---|---|---|---|"]
        for m in mods:
            lines.append(f"| `{m['id']}` | {m.get('purpose') or ''} | {len(m.get('files', [])) or ''} | {m.get('tokens', 0):,} |")
    if data["conventions"]:
        lines += ["", "## Conventions", ""] + [f"- {c}" for c in data["conventions"]]
    for flow in data["flows"]:
        lines += ["", f"**Flow: {flow['name']}**", ""] + [f"{i}. `{step}`: {what}" for i, (step, what) in enumerate(flow["steps"], 1)]
    return "\n".join(lines).replace("\n\n\n", "\n\n") + "\n"


def explorer(data: dict[str, Any], focus: str = "") -> str:
    """Return the explorer page with its styles, scripts and the map inlined; focus opens it filtered."""
    page = (EXPLORER / "explorer.html").read_text(encoding="utf-8")
    page = page.replace("/*STYLE*/", (EXPLORER / "explorer.css").read_text(encoding="utf-8"))
    scripts = "\n".join((EXPLORER / name).read_text(encoding="utf-8") for name in ("graph.js", "query.js", "views.js", "app.js"))
    keep = ("id", "level", "name", "purpose", "view", "module", "kind", "source", "tokens", "external", "roles")
    slim = {"commit": data["commit"], "built": data["built"], "size": data["size"], "concepts": data["concepts"], "focus": focus,
            "nodes": [{k: n[k] for k in keep if n.get(k)} for n in data["nodes"]],
            "edges": [[e["from"], e["to"], e["type"], e["evidence"]] for e in data["edges"]]}
    blob = json.dumps(slim, separators=(",", ":")).replace("</", "<\\/")
    return page.replace("/*SCRIPT*/", f"const MAP = {blob};\n{scripts}")
