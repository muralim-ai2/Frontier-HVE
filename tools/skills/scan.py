"""Security and structure scan of one agent skill directory (SKILL.md plus resources)."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal, TypedDict

NAME = re.compile(r"^[a-z0-9-]{1,64}$")
MAX_DESCRIPTION = 1024
MAX_SKILL_LINES = 500
CHARS_PER_TOKEN = 4
SCRIPT_SUFFIXES = {".py", ".sh", ".ps1", ".psm1", ".js", ".mjs", ".cjs", ".ts", ".bat", ".cmd", ".rb", ".pl"}
Scope = Literal["all", "scripts"]
RULES: list[tuple[str, Scope, re.Pattern[str]]] = [
    ("prompt-injection", "all", re.compile(
        r"ignore (all |any )?(previous|prior|above|earlier) instructions|disregard (the |your |all )?(system|previous|prior)"
        r"|override (the |your )?(system|safety|security)|do not (tell|inform|mention to) the user|you are no longer", re.I)),
    ("external-fetch", "all", re.compile(
        r"\b(curl|wget|Invoke-WebRequest|Invoke-RestMethod|iwr|irm|Start-BitsTransfer)\b|requests\.(get|post)|urllib\.request|\bfetch\(", re.I)),
    ("external-url", "scripts", re.compile(r"https?://", re.I)),
    ("encoded-payload", "all", re.compile(
        r"[A-Za-z0-9+/]{200,}={0,2}|FromBase64String|base64 (-d|--decode)|b64decode|\beval\(|\bexec\(|Invoke-Expression|\biex\b", re.I)),
    ("destructive-command", "all", re.compile(
        r"rm -rf|Remove-Item\b[^\n]*-Recurse[^\n]*-Force|DROP (TABLE|DATABASE)|git push (-f|--force)|\bmkfs\b|format [a-z]:", re.I)),
    ("secret", "all", re.compile(
        r"(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\s]{12,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}"
        r"|-----BEGIN [A-Z ]*PRIVATE KEY", re.I)),
]


class Finding(TypedDict):
    """One rule hit; every finding blocks admission until a human reviews and revises the skill."""

    rule: str
    file: str
    line: int
    excerpt: str


class ScanReport(TypedDict):
    """Result of scanning one skill directory."""

    name: str
    path: str
    description: str
    skill_tokens: int
    files: int
    findings: list[Finding]
    skillevaluator: dict[str, int | str] | None
    ok: bool


def frontmatter(text: str) -> dict[str, str]:
    """Return the top-level scalar and folded fields of a SKILL.md YAML frontmatter block, or {} if there is none."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in (line.strip() for line in lines[1:]):
        return {}
    block = lines[1:[line.strip() for line in lines].index("---", 1)]
    fields: dict[str, str] = {}
    key = ""
    for line in block:
        if line[:1] in (" ", "\t") and key:
            fields[key] = (fields[key] + " " + line.strip()).strip()
        elif ":" in line:
            key, value = (part.strip() for part in line.split(":", 1))
            fields[key] = "" if value in (">", ">-", "|", "|-") else value.strip("'\"")
    return fields


def structure_findings(skill_dir: Path, meta: dict[str, str], skill_text: str) -> list[Finding]:
    """Return SKILL.md format violations that make VS Code skip the skill or break the harness file-size rule."""
    problems = []
    name, description = meta.get("name", ""), meta.get("description", "")
    if not meta:
        problems.append("no YAML frontmatter")
    if not NAME.match(name):
        problems.append(f"name {name!r} is not 1-64 lowercase letters, digits, or hyphens")
    if name != skill_dir.name:
        problems.append(f"name {name!r} differs from directory name {skill_dir.name!r}")
    if not description or len(description) > MAX_DESCRIPTION:
        problems.append(f"description is empty or over {MAX_DESCRIPTION} characters ({len(description)})")
    if skill_text.count("\n") > MAX_SKILL_LINES:
        problems.append(f"SKILL.md has over {MAX_SKILL_LINES} lines")
    return [Finding(rule="structure", file="SKILL.md", line=1, excerpt=p) for p in problems]


def content_findings(skill_dir: Path, files: list[Path]) -> list[Finding]:
    """Return security rule hits in every file of the skill; binary files are findings because they cannot be reviewed."""
    findings = []
    for path in files:
        rel = path.relative_to(skill_dir).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(Finding(rule="binary-file", file=rel, line=0, excerpt="not UTF-8 text"))
            continue
        is_script = path.suffix.lower() in SCRIPT_SUFFIXES
        for number, line in enumerate(text.splitlines(), 1):
            for rule, scope, pattern in RULES:
                if (scope == "all" or is_script) and (match := pattern.search(line)):
                    findings.append(Finding(rule=rule, file=rel, line=number, excerpt=line.strip()[:160] or match.group(0)))
    return findings


def run_skillevaluator(skill_dir: Path) -> dict[str, int | str]:
    """Return the exit code and output tail of NVIDIA SkillEvaluator's keyless `quality-check` on the skill."""
    exe = shutil.which("skillevaluator")
    if exe is None:
        raise FileNotFoundError("skillevaluator is not installed: uv tool install --python 3.13 "
                                "\"skillevaluator[all] @ git+https://github.com/NVIDIA/SkillEvaluator.git\"")
    result = subprocess.run([exe, "quality-check", str(skill_dir)], capture_output=True, text=True, encoding="utf-8")
    return {"exit_code": result.returncode, "output": (result.stdout + result.stderr)[-4000:]}


def scan(skill_dir: Path, skillevaluator: bool = False) -> ScanReport:
    """Return the scan report of a skill directory; ok is False if any finding exists or SkillEvaluator fails."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"{skill_md} not found: a skill is a directory containing SKILL.md")
    skill_text = skill_md.read_text(encoding="utf-8")
    meta = frontmatter(skill_text)
    files = sorted(p for p in skill_dir.rglob("*") if p.is_file())
    findings = structure_findings(skill_dir, meta, skill_text) + content_findings(skill_dir, files)
    evaluator = run_skillevaluator(skill_dir) if skillevaluator else None
    return ScanReport(name=meta.get("name", skill_dir.name), path=skill_dir.as_posix(), description=meta.get("description", ""),
                      skill_tokens=len(skill_text) // CHARS_PER_TOKEN, files=len(files), findings=findings, skillevaluator=evaluator,
                      ok=not findings and (evaluator is None or evaluator["exit_code"] == 0))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[1:] not in ([], ["--skillevaluator"]):
        raise SystemExit("usage: scan.py <skill_dir> [--skillevaluator]")
    report = scan(Path(args[0]), skillevaluator=bool(args[1:]))
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ok"] else 1)
