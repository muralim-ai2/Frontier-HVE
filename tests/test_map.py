"""Tests of the solution map: generic extraction without config, concepts and explain, impact, status, and the offline explorer."""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAP = REPO / "tools" / "map"
sys.path.insert(0, str(MAP))

import map_build  # noqa: E402
import solution_map  # noqa: E402

FILES = {
    "README.md": "# Shop\n\nA small shop with billing and a web front end.\n",
    "src/billing.py": '"""Charge customers and write invoices."""\nimport requests\nfrom src import tax\n\n\ndef charge(amount: int) -> int:\n    """Return the charged amount with tax."""\n    return tax.add(amount)\n',
    "src/tax.py": '"""Tax rules."""\n\n\ndef add(amount: int) -> int:\n    """Return the amount with tax added."""\n    return amount * 2\n',
    "web/main.ts": "/** Web entry: renders the cart. */\nimport { total } from './cart';\nimport React from 'react';\n\nexport function render(): number {\n  return total();\n}\n",
    "web/cart.ts": "// Cart totals.\n\n/** Return the cart total. */\nexport const total = (): number => 3;\n",
    "tests/test_billing.py": '"""Tests of billing."""\nfrom src import billing\n\n\ndef test_charge() -> None:\n    """Charging adds tax."""\n    assert billing.charge(1) == 2\n',
    "docs/decisions.md": "# Decisions\n\n## D-001: tax doubles\nSee src/tax.py.\n\n## D-002: carts in TypeScript\nSee web/cart.ts.\n",
    "scripts/broken.py": "for x in range(3):\nprint(x)\n",
    ".hve/skills/copied/scripts/tool.py": "def broken(:\n",
}


def project(tmp: str) -> Path:
    """Return a temp project with Python, TypeScript, a test, docs and decisions."""
    root = Path(tmp) / "shop"
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def edges(data: dict, kind: str) -> set[tuple[str, str]]:
    """Return the (from, to) pairs of one edge type."""
    return {(e["from"], e["to"]) for e in data["edges"] if e["type"] == kind}


def test_generic_map_without_config() -> None:
    """With no config the map has folder views, derived concepts, imports across Python and TypeScript, tests, decisions and dependencies."""
    with tempfile.TemporaryDirectory() as tmp:
        data = map_build.build(project(tmp), {})
        nodes = {n["id"]: n for n in data["nodes"]}
        assert data["size"]["class"] == "small" and {n["view"] for n in data["nodes"] if n["level"] == "view"} >= {"src", "web", "tests", "docs"}
        assert all(c["derived"] for c in data["concepts"]) and len(data["concepts"]) == 6
        assert ("file:src/billing.py", "file:src/tax.py") in edges(data, "imports")
        assert ("file:web/main.ts", "file:web/cart.ts") in edges(data, "imports")
        assert ("file:src/billing.py", "file:tests/test_billing.py") in edges(data, "tested-by")
        assert ("file:src/tax.py", "decision:D-001") in edges(data, "decided-in")
        assert nodes["file:src/billing.py"]["external"] == ["requests"] and nodes["file:web/main.ts"]["external"] == ["react"]
        assert nodes["file:web/cart.ts#total"]["purpose"] == "Return the cart total." and nodes["file:web/main.ts"]["purpose"] == "Web entry: renders the cart."
        assert nodes["system"]["purpose"] == "Shop: A small shop with billing and a web front end."
        broken = nodes["file:scripts/broken.py"]
        assert broken["error"].startswith("does not parse as Python") and broken["purpose"].startswith("Not mapped")
        assert not [n for n in nodes if ".hve/" in n] and "could not read" in map_build.overview(data)


def test_concepts_explain_and_impact() -> None:
    """Configured concepts answer explain with modules, files, functions and connections; an unknown topic lists the closest nodes."""
    config = {"concepts": [
        {"id": "billing", "name": "Billing", "keywords": ["invoice", "charge"], "members": ["^src/"], "start": "src/billing.py",
         "explain": "Billing charges customers and adds tax."},
        {"id": "cart", "name": "Cart", "keywords": ["basket"], "members": ["^web/"], "explain": "The web cart."}]}
    with tempfile.TemporaryDirectory() as tmp:
        root = project(tmp)
        m = solution_map.Map(map_build.build(root, config))
        answer = solution_map.explain(m, "help me understand how invoices are charged", root / "explorer.html")
        card = answer["cards"][0]
        assert answer["matched"] and card["concept"] == "Billing" and card["start_at"] == "src/billing.py"
        files = [f["file"] for fs in card["folders"].values() for f in fs]
        assert files == ["src/billing.py", "src/tax.py"] and card["external_dependencies"] == ["requests"]
        assert card["tests"] == ["tests/test_billing.py"] and card["decisions"] == ["D-001"]
        assert answer["explorer"].endswith("#concept=billing")
        text = solution_map.explain_markdown(answer)
        assert "## Concept: Billing" in text and "`charge`" in text and "**Start at:** `src/billing.py`" in text
        miss = solution_map.explain(m, "kubernetes ingress", root / "explorer.html")
        assert not miss["matched"] and "#q=kubernetes+ingress" in miss["explorer"]
        hit = solution_map.impact(m, ["file:src/tax.py"])
        assert hit["dependents"] == ["src/billing.py"] and hit["decisions"] == ["D-001"]


def test_status_and_cli_build() -> None:
    """The CLI writes map, overview and explorer; status reports a changed file as stale."""
    with tempfile.TemporaryDirectory() as tmp:
        root = project(tmp)
        out = subprocess.run([sys.executable, str(MAP / "solution_map.py"), "build", "--root", str(root)], capture_output=True, text=True, check=True)
        paths = json.loads(out.stdout)
        assert all(Path(paths[k]).is_file() for k in ("map", "overview", "explorer"))
        (root / "src" / "tax.py").write_text(FILES["src/tax.py"] + "\n# changed\n", encoding="utf-8")
        status = solution_map.status(root, solution_map.load(root, None))
        assert status["stale"] and status["changed"] == ["src/tax.py"]


def test_explorer_is_offline_and_queries_run() -> None:
    """The explorer page loads nothing from the network, its scripts parse, and the Cypher engine runs on the embedded map."""
    with tempfile.TemporaryDirectory() as tmp:
        data = map_build.build(project(tmp), {})
        page = map_build.explorer(data)
        assert "<script src" not in page and "fetch(" not in page and "XMLHttpRequest" not in page
        assert not re.search(r"https?://(?!www\.w3\.org/2000/svg)", page)
        for name in ("graph.js", "query.js", "views.js", "app.js"):
            subprocess.run(["node", "--check", str(MAP / "explorer" / name)], check=True)
        blob = re.search(r"const MAP = (\{.*?\});\n", page, re.S)[1]
        script = (f"const MAP = {blob};\n" + (MAP / "explorer" / "graph.js").read_text(encoding="utf-8") + (MAP / "explorer" / "query.js").read_text(encoding="utf-8")
                  + "\nconst rows = execute(parseCypher(\"MATCH (a:file)-[:imports]->(b) WHERE b.name ENDS WITH '.ts' RETURN a, b\"));"
                  + "\nprocess.stdout.write(JSON.stringify(rows.map(r => [r.a.id, r.b.id])));")
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        assert json.loads(result.stdout) == [["file:web/main.ts", "file:web/cart.ts"]]


def test_repository_config_maps_every_file() -> None:
    """This repository's config places every mapped file in a named module and every concept has members, a start and an explanation."""
    data = map_build.build(REPO, map_build.load_config(REPO, None))
    assert not [n["id"] for n in data["nodes"] if n["level"] == "module" and n.get("placed") is False]
    assert len(data["concepts"]) >= 15 and all(c["explain"] and c["members"] and c["start"] for c in data["concepts"])
    assert not [n["id"] for n in data["nodes"] if n["level"] in ("module", "file") and not n.get("purpose")]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
