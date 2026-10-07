"""Pre-commit scan (blindspot B1): reject staged code that hides errors (empty catch/except, return-None handlers) or ships TODOs."""

import ast
import re
import subprocess
import sys
from pathlib import Path

JS_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
EMPTY_CATCH = re.compile(r"catch\s*(\([^)]*\))?\s*\{\s*\}|\.catch\(\s*\(?\s*\w*\s*\)?\s*=>\s*(\{\s*\}|null|undefined)\s*\)")
TODO = re.compile(r"(#|//|/\*|\*|<!--)\s*(TODO|FIXME)\b")
SKIP_DIRS = ("node_modules/", ".next/", "dist/", "build/")


def python_findings(source: str, path: str) -> list[str]:
    """Return except handlers whose body only passes, continues, or returns None."""
    findings = []
    for node in ast.walk(ast.parse(source, filename=path)):
        if not isinstance(node, ast.ExceptHandler):
            continue
        body = node.body
        silent = all(isinstance(s, (ast.Pass, ast.Continue)) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                     for s in body)
        returns_none = len(body) == 1 and isinstance(body[0], ast.Return) and (
            body[0].value is None or (isinstance(body[0].value, ast.Constant) and body[0].value.value is None))
        if silent or returns_none:
            findings.append(f"{path}:{node.lineno}: except handler hides the error")
    return findings


def scan_file(path: str, source: str) -> list[str]:
    """Return the B1 findings of one file's source."""
    findings = [f"{path}:{n}: {line.strip()}" for n, line in enumerate(source.splitlines(), 1) if TODO.search(line)]
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        findings += python_findings(source, path)
    elif suffix in JS_SUFFIXES:
        findings += [f"{path}:{source.count(chr(10), 0, m.start()) + 1}: empty catch" for m in EMPTY_CATCH.finditer(source)]
    return findings


def staged_findings(repo: Path) -> list[str]:
    """Return B1 findings in the staged (index) version of every added, copied, or modified code file."""
    names = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"], cwd=repo, capture_output=True, text=True,
                           encoding="utf-8", check=True).stdout.splitlines()
    findings = []
    for name in names:
        if name.startswith(SKIP_DIRS) or (Path(name).suffix.lower() not in JS_SUFFIXES | {".py"}):
            continue
        source = subprocess.run(["git", "show", f":{name}"], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True).stdout
        findings += scan_file(name, source)
    return findings


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: no_fallback.py <repo>")
    found = staged_findings(Path(sys.argv[1]))
    if found:
        print("Commit blocked by the no-fallback scan (B1). Surface errors instead of hiding them:\n" + "\n".join(found), file=sys.stderr)
        sys.exit(1)
