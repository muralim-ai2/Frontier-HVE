"""Language-neutral code facts for the solution map: files, purposes, symbols, imports, mentions, agents and decisions."""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from pathlib import Path
from typing import TypedDict

SKIP_DIRS = {"node_modules", "dist", "build", "out", ".next", "coverage", "vendor", "__pycache__", ".venv", "venv", "target", "bin", "obj", ".git", ".hve"}
SKIP_PREFIXES = (".github/hve/",)
SKIP_NAMES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", ".min.js", ".map", ".tsbuildinfo")
LANGS = {".py": "python", ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js", ".ts": "ts", ".tsx": "ts", ".cs": "csharp",
         ".java": "java", ".go": "go", ".sh": "shell", ".ps1": "shell", ".md": "markdown", ".json": "json", ".yaml": "yaml",
         ".yml": "yaml", ".bicep": "iac", ".tf": "iac", ".sql": "sql", ".toml": "config"}
MAX_BYTES = 300_000
CHARS_PER_TOKEN = 4
TEST = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]+\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$")
MENTION = re.compile(r"(?<![\w.-])((?:[\w.-]+/)*[\w-][\w.-]*\.(?:py|js|mjs|cjs|ts|tsx|jsx|cs|java|go|sh|ps1|json|yaml|yml|bicep|tf|sql))(?![\w-])")
FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---", re.S)
HOOK = re.compile(r"command:.*?([\w-]+\.(?:py|js|sh|ps1))")
DECISION = re.compile(r"^#{2,3}\s+((?:D|ADR)-?\d+)\b\s*[:\u2014-]?\s*(.*)$", re.M)
ADR_FILE = re.compile(r"(^|/)(adr|adrs|decisions)/(\d{3,4})-[^/]+\.md$", re.I)
BACKTICK = re.compile(r"`([^`\n]{3,60})`")
COMMAND_LINE = re.compile(r"[\"']?\b(command|run|script|scripts|exec|main|bin|entry|test|start|build)[\"']?\s*:\s*[\"']?\s*\S|:\s*[\"']\s*(python3?|py|node|npx|npm|pnpm|yarn|bash|sh|pwsh|dotnet|go)\s")
JS_IMPORT = re.compile(r"(?:import|export)[^'\"`;]*?from\s*['\"]([^'\"]+)['\"]|require\(\s*['\"]([^'\"]+)['\"]\s*\)|import\(\s*['\"]([^'\"]+)['\"]\s*\)|^\s*import\s+['\"]([^'\"]+)['\"]", re.M)
JS_SYMBOLS = [
    (re.compile(r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)", re.M), "function"),
    (re.compile(r"^(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)", re.M), "class"),
    (re.compile(r"^(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=>", re.M), "function"),
    (re.compile(r"^export\s+(?:type|interface)\s+([A-Za-z_$][\w$]*)", re.M), "type"),
]
OTHER_SYMBOLS = {
    "csharp": [(re.compile(r"^\s*(?:public|internal)\s+(?:[\w<>,\s]+\s+)?(?:class|interface|record|enum)\s+(\w+)", re.M), "class"),
               (re.compile(r"^\s*public\s+(?:static\s+|async\s+|override\s+|virtual\s+)*[\w<>\[\],?]+\s+(\w+)\s*\(", re.M), "function")],
    "java": [(re.compile(r"^\s*public\s+(?:abstract\s+|final\s+)*(?:class|interface|record|enum)\s+(\w+)", re.M), "class"),
             (re.compile(r"^\s*public\s+(?:static\s+|final\s+|synchronized\s+)*[\w<>\[\],?]+\s+(\w+)\s*\(", re.M), "function")],
    "go": [(re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Z]\w*)\s*\(", re.M), "function"),
           (re.compile(r"^type\s+([A-Z]\w*)\s+(?:struct|interface)", re.M), "class")],
}


class Symbol(TypedDict):
    """One function, class or type in a file."""

    name: str
    kind: str
    purpose: str
    line: int
    end: int


class Decision(TypedDict):
    """One recorded decision and the files its text names."""

    id: str
    title: str
    line: int
    mentions: list[str]


class Facts(TypedDict):
    """Everything the map takes from one file."""

    path: str
    lang: str
    kind: str
    name: str
    purpose: str
    tokens: int
    lines: int
    hash: str
    symbols: list[Symbol]
    imports: list[str]
    mentions: list[str]
    hooks: list[str]
    refs: list[str]
    decisions: list[Decision]
    error: str


def list_files(root: Path, exclude: list[re.Pattern[str]]) -> list[str]:
    """Return the repository's mappable text files: tracked and untracked-not-ignored under git, else every file."""
    if (root / ".git").exists():
        listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=root,
                                capture_output=True, text=True, check=True).stdout.splitlines()
    else:
        listed = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
    keep = []
    for rel in sorted(set(listed)):
        path = root / rel
        if (any(part in SKIP_DIRS for part in rel.split("/")[:-1]) or rel.startswith(SKIP_PREFIXES) or rel.endswith(SKIP_NAMES) or Path(rel).suffix.lower() not in LANGS
                or any(x.search(rel) for x in exclude) or not path.is_file() or path.stat().st_size > MAX_BYTES):
            continue
        keep.append(rel)
    return keep


def first_sentence(text: str | None) -> str:
    """Return the first sentence of a docstring, comment or paragraph, without Markdown emphasis."""
    if not text:
        return ""
    text = " ".join(text.replace("**", "").replace("`", "").split())
    return text.split(". ")[0].rstrip(".") + "." if text else ""


def _frontmatter(text: str) -> dict[str, str]:
    """Return the simple key: value pairs of a Markdown front matter block."""
    block = FRONTMATTER.match(text)
    if not block:
        return {}
    pairs = (re.match(r"^([\w-]+):\s*(.+)$", line) for line in block[1].splitlines())
    return {m[1]: m[2].strip().strip("'\"") for m in pairs if m}


def _python(text: str) -> tuple[str, list[Symbol], list[str], str]:
    """Return a Python file's docstring sentence, public top-level symbols, imported module names, and its syntax error if it does not parse."""
    try:
        tree = ast.parse(text)
    except SyntaxError as err:
        return "", [], [], f"does not parse as Python ({err.msg}, line {err.lineno})"
    symbols: list[Symbol] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            symbols.append({"name": node.name, "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                            "purpose": first_sentence(ast.get_docstring(node)), "line": node.lineno, "end": node.end_lineno or node.lineno})
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            imports += [base] + [f"{base}.{a.name}" if node.module else base + a.name for a in node.names]
    return first_sentence(ast.get_docstring(tree)), symbols, imports, ""


def _comment_before(lines: list[str], index: int) -> str:
    """Return the first text line of the comment block just above a line."""
    j = index - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    block = []
    while j >= 0 and re.match(r"^\s*(/\*\*?|\*|//|///)", lines[j]):
        block.insert(0, re.sub(r"^\s*(/\*\*?|\*/?|///?)\s?", "", lines[j]).replace("*/", "").strip())
        if lines[j].lstrip().startswith("/*"):
            break
        j -= 1
    text = next((b for b in block if b and not b.startswith(("@", "<"))), "")
    return first_sentence(text)


def _regex_symbols(text: str, patterns: list[tuple[re.Pattern[str], str]]) -> list[Symbol]:
    """Return symbols found by line-anchored patterns, each ending where the next one starts."""
    lines = text.splitlines()
    found = sorted({(text.count("\n", 0, m.start()), m[1], kind) for pattern, kind in patterns for m in pattern.finditer(text)})
    symbols: list[Symbol] = []
    for i, (index, name, kind) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else len(lines)
        symbols.append({"name": name, "kind": kind, "purpose": _comment_before(lines, index), "line": index + 1, "end": max(index + 1, end)})
    return symbols


def _header_comment(text: str) -> str:
    """Return the first sentence of a source file's leading comment."""
    head = re.match(r"\s*(?:#![^\n]*\n)?\s*(?:['\"]use (?:strict|client|server)['\"];?\s*)?(/\*\*?(.*?)\*/|((?:\s*//[^\n]*\n)+)|((?:\s*#[^\n]*\n)+))", text, re.S)
    if not head:
        return ""
    body = head[2] or head[3] or head[4] or ""
    return first_sentence(re.sub(r"^\s*(\*|//|#)\s?", "", body, flags=re.M))


def _markdown(text: str, meta: dict[str, str]) -> str:
    """Return a Markdown file's description, or its title and first paragraph sentence."""
    if meta.get("description"):
        return first_sentence(meta["description"])
    body = FRONTMATTER.sub("", text)
    heading = re.search(r"^#\s+(.+)$", body, re.M)
    para = next((p for p in re.split(r"\n\s*\n", body) if p.strip() and not p.lstrip().startswith(("#", "<!--", "|", "-", "```", ">", "*", "!"))), "")
    sentence = first_sentence(para)
    return f"{heading[1].strip()}: {sentence}" if heading and sentence else (heading[1].strip() if heading else sentence)


def _data(text: str, lang: str) -> str:
    """Return a JSON or YAML file's own description, title or name."""
    for key in ("description", "summary", "title", "name"):
        m = re.search(rf"^\s*\"?{key}\"?\s*:\s*\"?([^\"\n]+)", text, re.M)
        if m and (lang != "json" or text.lstrip().startswith("{")):
            return first_sentence(m[1].strip().rstrip(","))
    return ""


def _kind(rel: str, lang: str, decisions: int) -> str:
    """Return the role of a file: agent, skill, prompt, instructions, test, decisions, doc, code, config, iac or sql."""
    name = Path(rel).name
    if name.endswith(".agent.md") or re.search(r"(^|/)\.claude/agents/[^/]+\.md$", rel):
        return "agent"
    if name == "SKILL.md":
        return "skill"
    if name.endswith(".prompt.md"):
        return "prompt"
    if name in ("AGENTS.md", "CLAUDE.md", "copilot-instructions.md") or name.endswith(".instructions.md"):
        return "instructions"
    if TEST.search(rel) and lang not in ("markdown", "json"):
        return "test"
    if decisions:
        return "decisions"
    return {"markdown": "doc", "json": "config", "yaml": "config", "config": "config", "iac": "iac", "sql": "sql"}.get(lang, "code")


def file_facts(root: Path, rel: str) -> Facts:
    """Return the map facts of one file; a file that is not UTF-8 or does not parse is kept with its error instead of its symbols."""
    raw = (root / rel).read_bytes()
    error = ""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text, error = raw.decode("utf-8", errors="replace"), "is not UTF-8 text"
    lang = LANGS[Path(rel).suffix.lower()]
    meta = _frontmatter(text) if lang == "markdown" else {}
    symbols: list[Symbol] = []
    imports: list[str] = []
    if lang == "python" and not error:
        purpose, symbols, imports, error = _python(text)
    elif lang == "python":
        purpose = ""
    elif lang in ("js", "ts"):
        purpose, symbols = _header_comment(text), _regex_symbols(text, JS_SYMBOLS)
        imports = [next(g for g in m.groups() if g) for m in JS_IMPORT.finditer(text)]
    elif lang in OTHER_SYMBOLS:
        purpose, symbols = _header_comment(text), _regex_symbols(text, OTHER_SYMBOLS[lang])
        imports = re.findall(r"^\s*import\s+([\w.]+);", text, re.M) if lang == "java" else []
    elif lang == "markdown":
        purpose = _markdown(text, meta)
    elif lang in ("json", "yaml", "config"):
        purpose = _data(text, lang)
    else:
        purpose = _header_comment(text)
    decisions: list[Decision] = []
    if lang == "markdown":
        heads = list(DECISION.finditer(text))
        adr = ADR_FILE.search(rel)
        if len(heads) >= 2:
            for i, m in enumerate(heads):
                body = text[m.start(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
                decisions.append({"id": m[1], "title": first_sentence(m[2]) or m[1], "line": text.count("\n", 0, m.start()) + 1,
                                  "mentions": sorted(set(MENTION.findall(body)))})
        elif adr:
            decisions.append({"id": f"ADR-{adr[3]}", "title": purpose, "line": 1, "mentions": sorted(set(MENTION.findall(text)))})
    kind = _kind(rel, lang, len(decisions))
    refs = BACKTICK.findall(text) if kind in ("agent", "skill", "prompt", "instructions") else []
    if lang == "json":
        refs = re.findall(r"\"agents?\"\s*:\s*\"([^\"]+)\"", text)
    mentioned = text if lang not in ("json", "yaml", "config") else "\n".join(line for line in text.splitlines() if COMMAND_LINE.search(line))
    return {"path": rel, "lang": lang, "kind": kind, "name": meta.get("name", Path(rel).name) if kind == "agent" else Path(rel).name,
            "purpose": purpose, "tokens": len(text) // CHARS_PER_TOKEN, "lines": text.count("\n") + 1,
            "hash": hashlib.sha256(raw).hexdigest()[:16], "symbols": symbols, "imports": imports,
            "mentions": sorted(set(MENTION.findall(mentioned)) - {Path(rel).name, rel}), "hooks": sorted(set(HOOK.findall(text))) if kind == "agent" else [],
            "refs": refs, "decisions": decisions, "error": error}
