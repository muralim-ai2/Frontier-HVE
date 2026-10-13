"""Measure what Copilot loads before the user types: discoverable skills, always-on instructions, an agent prompt and MCP tools."""

import json
import os
import re
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

from recommend import stems
from scan import CHARS_PER_TOKEN, frontmatter

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
SKILL_DIRS = (".github/skills", ".claude/skills", ".agents/skills")
USER_SKILL_DIRS = (".copilot/skills", ".claude/skills", ".agents/skills")
INSTRUCTION_FILES = (".github/copilot-instructions.md", "AGENTS.md", "CLAUDE.md")
ALWAYS_ON = re.compile(r"^\*\*(/\*)?$")
SKILL_ENTRY_OVERHEAD_TOKENS = 15

Json = dict[str, Any]


def tokens(text: str) -> int:
    """Return the estimated token count of text."""
    return len(text) // CHARS_PER_TOKEN


def vscode_user_dir() -> Path:
    """Return the VS Code user settings folder for this platform."""
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / "Code" / "User"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Code" / "User"
    return Path.home() / ".config" / "Code" / "User"


def read_jsonc(path: Path) -> Any:
    """Return a JSON-with-comments file (VS Code settings) parsed, ignoring comments and trailing commas."""
    text, out, i, in_string = path.read_text(encoding="utf-8"), [], 0, False
    while i < len(text):
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\":
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_string = False
        elif c == '"':
            in_string = True
            out.append(c)
        elif text.startswith("//", i):
            i = text.find("\n", i) if "\n" in text[i:] else len(text)
            continue
        elif text.startswith("/*", i):
            i = text.index("*/", i) + 2
            continue
        else:
            out.append(c)
        i += 1
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", "".join(out)))


def plugin_roots(user_dir: Path) -> list[Path]:
    """Return enabled plugin folders from chat.pluginLocations plus marketplace-installed agent plugins."""
    roots = []
    settings = user_dir / "settings.json"
    if settings.is_file():
        roots += [Path(p) for p, on in read_jsonc(settings).get("chat.pluginLocations", {}).items() if on]
    installed = Path.home() / ".vscode" / "agent-plugins"
    if installed.is_dir():
        roots += [p.parent for p in installed.rglob("plugin.json")]
    return [r for r in dict.fromkeys(roots) if r.is_dir()]


def skill_entries(folders: list[tuple[str, Path]]) -> list[Json]:
    """Return one entry per discoverable SKILL.md with the tokens its name, description and path add to every request."""
    entries = []
    for origin, folder in folders:
        for skill_md in sorted(folder.glob("*/SKILL.md")) if folder.is_dir() else []:
            meta = frontmatter(skill_md.read_text(encoding="utf-8"))
            cost = tokens(meta.get("name", "") + meta.get("description", "") + skill_md.as_posix()) + SKILL_ENTRY_OVERHEAD_TOKENS
            entries.append({"kind": "skill", "origin": origin, "name": meta.get("name", skill_md.parent.name),
                            "description": meta.get("description", ""), "path": skill_md.as_posix(), "tokens": cost})
    return entries


def instruction_entries(workspace: Path, user_dir: Path) -> list[Json]:
    """Return the always-on instruction files: root instruction files and *.instructions.md that apply to every file."""
    files = [workspace / f for f in INSTRUCTION_FILES if (workspace / f).is_file()]
    for folder in (workspace / ".github" / "instructions", user_dir / "prompts"):
        files += [p for p in sorted(folder.rglob("*.instructions.md")) if folder.is_dir()
                  and ALWAYS_ON.match(frontmatter(p.read_text(encoding="utf-8")).get("applyTo", "").strip())]
    return [{"kind": "instructions", "origin": "workspace" if workspace in p.parents else "user", "name": p.name, "path": p.as_posix(),
             "tokens": tokens(p.read_text(encoding="utf-8"))} for p in files]


def agent_entry(name: str, workspace: Path, plugins: list[Path]) -> Json:
    """Return the prompt cost of the named custom agent, searched in the workspace and plugin agent folders."""
    folders = [workspace / ".github" / "agents"] + [r / sub for r in plugins for sub in ("agents", "com.github.copilot/agents")]
    for path in (p for f in folders if f.is_dir() for p in sorted(f.glob("*.agent.md"))):
        if frontmatter(path.read_text(encoding="utf-8")).get("name") == name:
            return {"kind": "agent", "origin": "agent", "name": name, "path": path.as_posix(), "tokens": tokens(path.read_text(encoding="utf-8"))}
    raise FileNotFoundError(f"custom agent {name!r} not found in {[f.as_posix() for f in folders]}")


def mcp_entries(workspace: Path, user_dir: Path, per_server: int) -> list[Json]:
    """Return an estimated tool-schema cost per configured MCP server (actual schemas are only known at runtime)."""
    entries = []
    for origin, path in (("workspace", workspace / ".vscode" / "mcp.json"), ("user", user_dir / "mcp.json")):
        if path.is_file():
            entries += [{"kind": "mcp", "origin": origin, "name": server, "path": path.as_posix(), "tokens": per_server, "estimate": True}
                        for server in read_jsonc(path).get("servers", {})]
    return entries


def measured_names(workspace: Path) -> set[str]:
    """Return skill names with a paired evaluation in the harness library or the workspace's own registry."""
    names = set()
    for registry in (SKILLS_DIR / "registry.json", workspace / ".hve" / "skills-registry.json"):
        if registry.is_file():
            data = json.loads(registry.read_text(encoding="utf-8"))
            names |= {e["name"] for e in data["admitted"] + data["rejected"] if e.get("eval_method")}
    return names


def duplicates(skills: list[Json], similarity: float) -> list[Json]:
    """Return skill pairs with the same name or descriptions sharing at least the given share of word stems."""
    pairs = []
    for a, b in combinations(skills, 2):
        sa, sb = stems(a["description"]), stems(b["description"])
        score = len(sa & sb) / len(sa | sb) if sa | sb else 0.0
        if a["name"] == b["name"] or score >= similarity:
            pairs.append({"a": a["path"], "b": b["path"], "same_name": a["name"] == b["name"], "similarity": round(score, 2)})
    return pairs


def measure(workspace: Path, agent: str | None, context_tokens: int | None) -> Json:
    """Return the always-on load report, compare it with the previous check, and save it to .hve/context_load.json."""
    config = json.loads((SKILLS_DIR / "categories.json").read_text(encoding="utf-8"))["context_load"]
    user_dir, home = vscode_user_dir(), Path.home()
    plugins = plugin_roots(user_dir)
    skills = skill_entries([("workspace", workspace / d) for d in SKILL_DIRS] + [("user", home / d) for d in USER_SKILL_DIRS]
                           + [(f"plugin:{r.name}", r / "skills") for r in plugins])
    items = skills + instruction_entries(workspace, user_dir) + mcp_entries(workspace, user_dir, config["mcp_tokens_per_server_estimate"])
    if agent:
        items.append(agent_entry(agent, workspace, plugins))
    total = sum(i["tokens"] for i in items)
    windows = [context_tokens] if context_tokens else config["reference_windows"]
    shares = {str(w): round(total / w * 100, 1) for w in windows}
    history_file = workspace / ".hve" / "context_load.json"
    previous = json.loads(history_file.read_text(encoding="utf-8"))["total_tokens"] if history_file.is_file() else None
    measured = measured_names(workspace)
    report: Json = {"checked": datetime.now(timezone.utc).isoformat(timespec="seconds"), "total_tokens": total, "share_pct": shares,
                    "previous_total_tokens": previous, "by_kind": {k: sum(i["tokens"] for i in items if i["kind"] == k)
                                                                    for k in ("skill", "instructions", "agent", "mcp")},
                    "skill_count": len(skills), "top": sorted(items, key=lambda i: -i["tokens"])[:10],
                    "duplicates": duplicates(skills, config["duplicate_similarity"]),
                    "unmeasured_skills": sorted({s["name"] for s in skills} - measured),
                    "not_counted": "VS Code's built-in system prompt and built-in tool schemas", "warnings": []}
    if previous and (total - previous) / previous * 100 >= config["growth_warn_pct"]:
        report["warnings"].append(f"always-on load grew {round((total - previous) / previous * 100)}% since the last check "
                                  f"({previous:,} -> {total:,} tokens, paid on every request)")
    if shares[str(windows[0])] >= config["share_warn_pct"]:
        report["warnings"].append(f"always-on load is {shares[str(windows[0])]}% of a {windows[0]:,}-token context window before the user types")
    if report["warnings"]:
        report["fixes"] = ["move rarely used skills into the Frontier HVE library (loaded per task within a budget) instead of skill folders",
                           "merge the duplicate skills listed", "narrow applyTo on *.instructions.md files that apply to every file",
                           "disable plugins or MCP servers this workspace does not use"]
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    args = sys.argv[1:]
    options = dict(zip(args[::2], args[1::2]))
    if len(args) % 2 or set(options) - {"--agent", "--context-tokens"}:
        raise SystemExit('usage: context_load.py [--agent "<custom agent name>"] [--context-tokens <model context window>]')
    result = measure(Path.cwd(), options.get("--agent"), int(options["--context-tokens"]) if "--context-tokens" in options else None)
    print(json.dumps(result, indent=2))
