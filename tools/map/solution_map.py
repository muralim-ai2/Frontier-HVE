"""Solution map CLI: build the map, then answer explain, impact, search, overview and status from it."""

from __future__ import annotations

import argparse
import json
import re
import sys
import webbrowser
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from map_build import build, explorer, load_config, overview  # noqa: E402
from extract import file_facts, list_files  # noqa: E402

MAP_DIR = Path(".hve/map")
SNAPSHOT_DIR = Path("docs/architecture")
STOP = set("the a an and or of to in on for with from into by is are be as at it its this that how what where why who me my our we us i you "
           "help understand explain about show tell does do work works working implementation implemented code".split())


class Map:
    """A loaded solution map with node, child and edge indexes."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Index nodes, children and non-structural edges."""
        self.data = data
        self.nodes = {n["id"]: n for n in data["nodes"]}
        self.children: dict[str, list[str]] = defaultdict(list)
        self.out: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.inc: dict[str, list[dict[str, str]]] = defaultdict(list)
        for e in data["edges"]:
            if e["type"] == "contains":
                self.children[e["from"]].append(e["to"])
            elif e["type"] != "includes":
                self.out[e["from"]].append(e)
                self.inc[e["to"]].append(e)
        self.concepts = {c["id"]: c for c in data["concepts"]}

    def file_of(self, node_id: str) -> str:
        """Return the file node that holds a node, or the node itself."""
        return node_id.split("#")[0] if node_id.startswith("file:") else node_id


def words(text: str) -> set[str]:
    """Return the meaningful lowercase words of a text with a plural strip."""
    return {w[:-1] if len(w) > 4 and w.endswith("s") else w for w in re.findall(r"[a-z][a-z0-9]{2,}", text.lower()) if w not in STOP}


def load(root: Path, path: Path | None) -> Map:
    """Return the map at the path, the workspace map or the committed snapshot."""
    for cand in ([path] if path else [root / MAP_DIR / "map.json", root / SNAPSHOT_DIR / "solution-map.json"]):
        if cand.is_file():
            return Map(json.loads(cand.read_text(encoding="utf-8")))
    raise FileNotFoundError(f"no solution map in {root / MAP_DIR} or {root / SNAPSHOT_DIR}; run `solution_map.py build` first")


def write(root: Path, out: Path, data: dict[str, Any]) -> dict[str, str]:
    """Write map.json, the overview and the explorer into a folder and return their paths."""
    out.mkdir(parents=True, exist_ok=True)
    snapshot = out.resolve() == (root / SNAPSHOT_DIR).resolve()
    names = ("solution-map.json", "solution-map.md", "solution-map.html") if snapshot else ("map.json", "overview.md", "explorer.html")
    (out / names[0]).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    (out / names[1]).write_text(overview(data), encoding="utf-8")
    (out / names[2]).write_text(explorer(data), encoding="utf-8")
    return {"map": str(out / names[0]), "overview": str(out / names[1]), "explorer": str(out / names[2])}


def score_concept(c: dict[str, Any], m: Map, want: set[str]) -> float:
    """Return how well a concept matches the asked words: name and keywords first, then explanation and member names."""
    named = words(c["name"]) | {w for k in c["keywords"] for w in words(k)}
    told = words(c["explain"])
    members = Counter(w for mid in c["members"] for w in words(m.nodes[mid]["name"].replace("_", " ")))
    return 3 * len(want & named) + len(want & told) + 0.3 * sum(min(3, members[w]) for w in want)


def search(m: Map, text: str, limit: int = 12) -> list[dict[str, Any]]:
    """Return the nodes whose name or purpose best match a text."""
    want = words(text)
    scored = []
    for n in m.nodes.values():
        if n["level"] in ("system", "concept"):
            continue
        hit = 2 * len(want & words(n["name"].replace("_", " ").replace("-", " "))) + len(want & words(n.get("purpose", "")))
        if hit:
            scored.append((hit, -len(n["id"]), n))
    return [{"id": n["id"], "level": n["level"], "name": n["name"], "purpose": n.get("purpose", ""), "source": n.get("source", "")}
            for _, _, n in sorted(scored, key=lambda s: (s[0], s[1]), reverse=True)[:limit]]


def concept_card(m: Map, c: dict[str, Any], want: set[str] = frozenset()) -> dict[str, Any]:
    """Return a concept as concept, folders, files, functions (those matching the question first), connections, dependencies and explanation."""
    members = set(c["members"])
    folders: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mid in c["members"]:
        n = m.nodes[mid]
        if n["level"] != "file":
            continue
        functions = [{"name": m.nodes[s]["name"], "purpose": m.nodes[s].get("purpose", ""), "source": m.nodes[s]["source"],
                      "hit": len(want & (words(m.nodes[s]["name"].replace("_", " ")) | words(m.nodes[s].get("purpose", ""))))}
                     for s in m.children[mid] if m.nodes[s].get("kind") in ("function", "class")]
        functions.sort(key=lambda f: -f["hit"])
        module = m.nodes[n["module"]]
        group = n["source"].rsplit("/", 1)[0] if module["id"].startswith("mod:") or "/" not in n["source"] else f"{module['name']} ({n['source'].rsplit('/', 1)[0]})"
        folders[group].append({"file": n["source"], "kind": n["kind"], "purpose": n.get("purpose", ""), "tokens": n.get("tokens", 0),
                               "functions": functions[:12], "more_functions": max(0, len(functions) - 12)})
    other: dict[str, str] = {}
    for oc in m.concepts.values():
        for mid in oc["members"]:
            other.setdefault(mid, oc["name"])
    connections: Counter[tuple[str, str, str]] = Counter()
    for mid in members:
        for e in m.out[mid]:
            if e["to"] not in members and e["type"] in ("imports", "invokes", "guarded-by", "uses", "writes", "delegates-to"):
                connections[("out", e["type"], other.get(m.file_of(e["to"]), m.nodes[e["to"]]["name"]))] += 1
        for e in m.inc[mid]:
            if e["from"] not in members and e["type"] in ("imports", "invokes", "guarded-by", "delegates-to"):
                connections[("in", e["type"], other.get(m.file_of(e["from"]), m.nodes[e["from"]]["name"]))] += 1
    tests = sorted({m.nodes[e["to"]]["source"] for mid in members for e in m.out[mid] if e["type"] == "tested-by"})
    docs = sorted({m.nodes[e["to"]]["source"] for mid in members for e in m.out[mid] if e["type"] == "documented-in"})
    decisions = sorted({m.nodes[e["to"]]["name"] for mid in members for e in m.out[mid] if e["type"] == "decided-in"})
    external = sorted({x for mid in members for x in m.nodes[mid].get("external", [])})
    return {"concept": c["name"], "id": c["id"], "explanation": c["explain"], "derived": c["derived"], "start_at": m.nodes[c["start"]].get("source", c["start"]),
            "folders": dict(folders), "stores": [m.nodes[s]["name"] for s in members if s.startswith("store:")],
            "connections": [{"direction": d, "type": t, "with": w, "count": n} for (d, t, w), n in connections.most_common(25)],
            "external_dependencies": external, "tests": tests, "docs": docs, "decisions": decisions[-12:], "questions": c.get("questions", [])}


def explain(m: Map, topic: str, explorer_path: Path) -> dict[str, Any]:
    """Return the concept cards that answer a topic, or the closest nodes when no concept fits."""
    want = words(topic)
    ranked = sorted(((score_concept(c, m, want), c) for c in m.concepts.values()), key=lambda s: s[0], reverse=True)
    best = [c for s, c in ranked if s >= max(3, ranked[0][0] * 0.6)][:2] if ranked and ranked[0][0] >= 3 else []
    focus = ",".join(c["id"].split(":", 1)[1] for c in best)
    url = explorer_path.resolve().as_uri() + (f"#concept={focus}" if best else "#q=" + re.sub(r"\s+", "+", topic.strip()))
    return {"topic": topic, "map_commit": m.data["commit"], "matched": bool(best), "cards": [concept_card(m, c, want) for c in best],
            "closest_nodes": [] if best else search(m, topic), "explorer": url,
            "note": "" if best else "No concept covers this topic; the closest nodes are listed. Offer to add a concept to the map config."}


def explain_markdown(answer: dict[str, Any]) -> str:
    """Return an explain answer as compact Markdown for chat: concept, folders, files, functions, connections, dependencies, explanation."""
    out = [f"Solution map (commit `{answer['map_commit']}`) for: {answer['topic']}", ""]
    for card in answer["cards"]:
        out += [f"## Concept: {card['concept']}", "", card["explanation"] or "No explanation yet.", "", f"**Start at:** `{card['start_at']}`", "",
                "**Modules, files and functions**"]
        for folder, files in card["folders"].items():
            out.append(f"- {folder}")
            for f in files:
                fns = [fn for fn in f["functions"] if fn["hit"]][:5] or f["functions"][:3]
                names = ", ".join(f"`{fn['name']}`" for fn in fns)
                rest = len(f["functions"]) + f["more_functions"] - len(fns)
                out.append(f"  - `{Path(f['file']).name}`: {f['purpose']}" + (f" Functions: {names}" + (f" (+{rest} more)" if rest > 0 else "") + "." if names else ""))
        if card["stores"]:
            out.append(f"- Data: {', '.join(card['stores'])}")
        conns = [f"{c['direction'].replace('out', 'uses').replace('in', 'used by')} {c['with']} ({c['type']}{' x' + str(c['count']) if c['count'] > 1 else ''})" for c in card["connections"][:10]]
        if conns:
            out += ["", "**Connections:** " + "; ".join(conns)]
        if card["external_dependencies"]:
            out.append("**External dependencies:** " + ", ".join(f"`{x}`" for x in card["external_dependencies"][:15]))
        for label, key in (("Tests", "tests"), ("Docs", "docs"), ("Decisions", "decisions")):
            if card[key]:
                out.append(f"**{label}:** " + ", ".join(f"`{Path(x).name}`" if key != "decisions" else x for x in card[key][:10]))
        out.append("")
    if not answer["matched"]:
        out += [answer["note"], ""] + [f"- `{n['source'] or n['id']}` ({n['level']}): {n['purpose']}" for n in answer["closest_nodes"]] + [""]
    out.append(f"**Explorer, filtered to this:** {answer['explorer']}")
    return "\n".join(out)


def impact(m: Map, seeds: list[str]) -> dict[str, Any]:
    """Return what a change starting at the seed nodes touches: dependencies, dependents, tests, docs, decisions and roles."""
    for s in seeds:
        if s not in m.nodes:
            raise KeyError(f"unknown seed {s}; use `search` to find node ids")
    rel: dict[str, set[str]] = defaultdict(set)
    for s in seeds:
        for e in m.out[s]:
            rel[{"tested-by": "tests", "documented-in": "docs", "decided-in": "decisions"}.get(e["type"], "uses")].add(e["to"])
        for e in m.inc[s]:
            if e["type"] in ("imports", "invokes", "guarded-by", "delegates-to"):
                rel["dependents"].add(e["from"])
    views = {m.nodes[n].get("view") for n in [*seeds, *rel["dependents"]]}
    roles = sorted({r for n in m.nodes.values() if n["level"] == "view" and n["view"] in views for r in n.get("roles", [])})
    src = lambda ids: sorted(m.nodes[i].get("source") or i for i in ids - set(seeds))  # noqa: E731
    return {"seeds": seeds, "uses": src(rel["uses"]), "dependents": src(rel["dependents"]), "tests": src(rel["tests"]), "docs": src(rel["docs"]),
            "decisions": sorted(m.nodes[i]["name"] for i in rel["decisions"]), "views": sorted(v for v in views if v), "roles": roles,
            "read_tokens": sum(m.nodes[s].get("tokens", 0) for s in seeds)}


def status(root: Path, m: Map) -> dict[str, Any]:
    """Return the map's commit and the mapped files added, removed or changed since it was built."""
    exclude = [re.compile(x) for x in load_config(root, None).get("exclude", [])]
    now = set(list_files(root, exclude))
    old = m.data["files"]
    changed = sorted(p for p in now & set(old) if file_facts(root, p)["hash"] != old[p])
    return {"commit": m.data["commit"], "built": m.data["built"], "added": sorted(now - set(old)), "removed": sorted(set(old) - now),
            "changed": changed, "stale": bool(changed or now ^ set(old))}


def main() -> None:
    """Run one solution map command and print JSON or Markdown."""
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["build", "explain", "impact", "search", "overview", "status", "open"])
    p.add_argument("text", nargs="?", default="")
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--config", type=Path)
    p.add_argument("--map", type=Path)
    p.add_argument("--snapshot", action="store_true", help="write the release snapshot to docs/architecture/")
    p.add_argument("--seeds", default="")
    p.add_argument("--json", action="store_true", help="explain as JSON instead of Markdown")
    args = p.parse_args()
    root = args.root.resolve()
    if args.command == "build":
        data = build(root, load_config(root, args.config))
        paths = write(root, root / (SNAPSHOT_DIR if args.snapshot else MAP_DIR), data)
        counts = Counter(n["level"] for n in data["nodes"])
        print(json.dumps({"size": data["size"], "nodes": counts, "edges": Counter(e["type"] for e in data["edges"]),
                          "concepts": len(data["concepts"]), "derived_concepts": all(c["derived"] for c in data["concepts"]),
                          "unplaced_modules": sum(1 for n in data["nodes"] if n["level"] == "module" and n.get("placed") is False),
                          "missing_purpose": sum(1 for n in data["nodes"] if n["level"] in ("module", "file") and not n.get("purpose")),
                          "unreadable_files": [f"{n['source']} {n['error']}" for n in data["nodes"] if n.get("error")], **paths}, indent=1))
        return
    m = load(root, args.map)
    page = (args.map.parent / "explorer.html") if args.map else next((x for x in (root / MAP_DIR / "explorer.html", root / SNAPSHOT_DIR / "solution-map.html") if x.is_file()), root / MAP_DIR / "explorer.html")
    if args.command == "explain":
        answer = explain(m, args.text, page)
        print(json.dumps(answer, indent=1) if args.json else explain_markdown(answer))
    elif args.command == "impact":
        print(json.dumps(impact(m, [s.strip() for s in args.seeds.split(",") if s.strip()]), indent=1))
    elif args.command == "search":
        print(json.dumps(search(m, args.text), indent=1))
    elif args.command == "overview":
        print(overview(m.data))
    elif args.command == "status":
        print(json.dumps(status(root, m), indent=1))
    else:
        fragment = args.text if re.match(r"^(concept|q|node|cypher)=", args.text) else ("q=" + re.sub(r"\s+", "+", args.text.strip()) if args.text else "")
        url = page.resolve().as_uri() + ("#" + fragment if fragment else "")
        webbrowser.open(url)
        print(url)


if __name__ == "__main__":
    main()
