"""Pack author kit: scaffold an expertise pack repository (package plus release workflow) and test a package's routing cases."""

import json
from pathlib import Path
from typing import Any

import manifest
from route import matches, mentions

Json = dict[str, Any]

WORKFLOW = """name: release-plugin
on:
  push:
    tags: ["v*"]
permissions:
  contents: write
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Get the Frontier HVE core
        run: git clone --depth 1 --branch "${{ vars.FRONTIER_HVE_REF }}" "${{ vars.FRONTIER_HVE_REPO }}" core
      - name: Validate and test
        run: python core/tools/plugins/plugin.py test plugin
      - name: Pack
        run: python core/tools/plugins/plugin.py pack plugin --out dist | tee dist-info.json
      - name: Attach to the release
        env:
          GH_TOKEN: ${{ github.token }}
        run: gh release create "${GITHUB_REF_NAME}" dist/*.hveplugin --notes-file dist-info.json
"""


def scaffold(name: str, publisher: str, display: str) -> dict[str, str]:
    """Return the files of a minimal valid plugin package by relative path."""
    agent, skill = f"{name}-expert", f"{name}-practices"
    hve = {"$schema": "https://github.com/muralim-ai2/Frontier-HVE/schemas/hve-plugin.schema.json", "name": name, "displayName": display,
           "version": "0.1.0", "publisher": publisher, "harness": {"apiVersion": 1, "frontierHve": f">={manifest.core_version()} <1.0.0"},
           "description": f"{display} agents, skills and templates for Frontier HVE.",
           "routing": {"domains": [name], "keywords": [name.replace("-", " ")], "task_pattern": rf"\b{name.replace('-', '[ -]')}\b",
                       "workspace_signals": []},
           "agents": [{"name": agent, "file": f"agents/{agent}.agent.md", "capabilities": ["architecture", "implementation"]}],
           "skills": "registry.json",
           "templates": {"brief": {"file": "templates/brief-v1.md", "version": 1, "output": f"docs/{name}/BRIEF-{{slug}}.md"}},
           "knowledge": [{"id": "common-solutions", "file": "knowledge/common-solutions.md", "title": f"{display} common solutions",
                          "kind": "solution", "use_when": "A known problem comes up: replace with when to open this document.", "stages": []}],
           "tools": ["read/readFile", "search/textSearch", "edit/editFiles", "edit/createFile"]}
    return {
        "hve-plugin.json": json.dumps(hve, indent=2) + "\n",
        "README.md": f"# {display}\n\nOwner: {publisher}. Support: open an issue in this repository.\n",
        "LICENSE": "Replace with your organization's license.\n",
        "registry.json": json.dumps({"skills": [{"name": skill, "description": f"{display} practices: replace with your vetted guidance.",
                                                 "task_categories": ["architecture"]}]}, indent=2) + "\n",
        f"agents/{agent}.agent.md": (f"---\nname: {agent}\ndescription: {display} expert. Replace with what this agent does.\n"
                                     "tools: [read/readFile, search/textSearch, edit/editFiles, edit/createFile]\n---\n\n"
                                     f"You are the {display} expert inside the Frontier HVE harness. The harness tools folder is "
                                     "`{{RUNTIME}}/tools`. Base every statement on files in the workspace.\n"),
        f"skills/{skill}/SKILL.md": (f"---\nname: {skill}\ndescription: {display} practices: replace with your vetted guidance.\n---\n\n"
                                     f"# {display} practices\n\n1. Replace these steps with your organization's guidance.\n"),
        "templates/brief-v1.md": ("<!-- hve-template: brief@1 -->\n# Brief\n\n<!-- hve-section: context -->\n## Context\n"
                                  "{{FILL: What the work is and why.}}\n\n<!-- hve-section: decision -->\n## Decision\n"
                                  "{{FILL: What was decided and the evidence.}}\n"),
        "knowledge/common-solutions.md": f"# {display} common solutions\n\n| Symptom | Cause | Fix |\n|---|---|---|\n| Replace | with | your team's fixes |\n",
        "tests/routing.json": json.dumps({"cases": [{"prompt": f"Help with our {name.replace('-', ' ')} work", "routes": True},
                                                    {"prompt": "Fix the button color", "routes": False}]}, indent=2) + "\n",
    }


def init(repo: Path, name: str, publisher: str, display: str) -> Json:
    """Create a plugin repository: plugin/ (the package) and the release workflow; refuse to overwrite anything."""
    if repo.exists() and any(repo.iterdir()):
        raise FileExistsError(f"{repo} is not empty")
    files = {f"plugin/{path}": text for path, text in scaffold(name, publisher, display).items()}
    files[".github/workflows/release-plugin.yml"] = WORKFLOW
    for path, text in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    data = manifest.load(repo / "plugin")
    return {"created": str(repo), "package": str(repo / "plugin"), "id": data["id"],
            "next": "edit plugin/, then run `plugin.py test plugin`; set the repo variables FRONTIER_HVE_REPO and FRONTIER_HVE_REF, "
                    "and push a v* tag to release"}


def test(folder: Path) -> Json:
    """Validate a package and check every case in tests/routing.json: whether the prompt routes to this plugin."""
    data = manifest.load(folder)
    cases_file = folder / "tests" / "routing.json"
    if not cases_file.is_file():
        raise FileNotFoundError(f"{cases_file} is missing; add {{\"cases\": [{{\"prompt\": ..., \"routes\": true|false}}]}}")
    entry = {"name": data["name"], "manifest": data}
    results = [{"prompt": c["prompt"], "expected": c["routes"], "routed": matches(c["prompt"], entry) or mentions(c["prompt"], entry)}
               for c in json.loads(cases_file.read_text(encoding="utf-8"))["cases"]]
    failed = [r for r in results if r["routed"] != r["expected"]]
    return {"id": data["id"], "version": data["version"], "passed": not failed and bool(results), "cases": results, "failed": failed}
