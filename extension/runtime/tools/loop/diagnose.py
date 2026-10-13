"""Attempt ledger per feature and the deterministic rules that pick one fix per failure cause, else hand over to the human."""

import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ENV_ERROR = re.compile(r"E403|ECONNREFUSED|ENOTFOUND|EADDRINUSE|EACCES|getaddrinfo|registry\.npmjs\.org|"
                       r"is not recognized as an internal or external command|command not found", re.I)
REGISTRY_ERROR = re.compile(r"E403|registry\.npmjs\.org", re.I)
RETRIEVAL_ERROR = re.compile(r"not found|does not exist|no such file|no matches|could not find|ENOENT", re.I)
CHECKS = re.compile(r"HARNESS_CHECKS\s+(\d+)/(\d+)")
NOISE = re.compile(r"\S*[/\\]\S*|0x[0-9a-f]+|\d+", re.I)
RETRIEVAL_TOOLS = {"read_file", "file_search", "grep_search", "list_dir", "mcp_graphify_query_graph", "mcp_graphify_get_node",
                   "replace_string_in_file", "multi_replace_string_in_file", "apply_patch"}
EDIT_HINT = "Read the exact current lines first; the old text must match the file exactly, including whitespace, and appear once."
TOOL_HINTS = {
    "replace_string_in_file": EDIT_HINT,
    "multi_replace_string_in_file": EDIT_HINT,
    "apply_patch": "Re-read the file first; every context line of the patch must match the current file exactly.",
    "create_file": "create_file fails on an existing file; edit the existing file instead.",
    "run_in_terminal": "Run from the project root, check the command or npm script exists, and change the command instead of repeating it.",
    "read_file": "Find the real path with file_search or the code graph before reading.",
}
REPEAT_LIMIT = 3
QUESTIONS = {
    "R1": "The fix is going in circles (the same error came back with the same files). Which approach should it take instead?",
    "R5": "The check fails exactly as it did before any work. Is the check command right, and what does the feature need that its "
          "description does not say?",
    "R6": "The environment blocks the check: {first}. Please fix access or install what is missing, then resume.",
    "R3": "A tool keeps failing and no fixed hint applies to it. How should it proceed?",
    "R7": "Rule {rule} already fired once for this feature and the failure persists. How should it proceed?",
    "cap": "The feature failed its check {n} times. What should change?",
}

Json = dict[str, Any]


def fingerprint(output: str) -> str:
    """Return a short hash of check output with paths, numbers and hex ids removed, so equal errors match across attempts."""
    normalized = " ".join(NOISE.sub("", output.lower()).split())[-1000:]
    return hashlib.sha1(normalized.encode()).hexdigest()[:12]


def checks_passed(output: str) -> list[int] | None:
    """Return [passed, total] from the last `HARNESS_CHECKS passed/total` line, if the check prints one."""
    found = CHECKS.findall(output)
    return [int(found[-1][0]), int(found[-1][1])] if found else None


def file_hashes(project: Path) -> dict[str, str]:
    """Return a content hash per tracked or untracked (not ignored) file of the project."""
    names = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=project, capture_output=True, text=True,
                           encoding="utf-8", check=True).stdout.splitlines()
    return {n: hashlib.sha1((project / n).read_bytes()).hexdigest()[:12] for n in names if (project / n).is_file()}


def read_jsonl(path: Path) -> list[Json]:
    """Return the records of a JSONL file, or [] when it does not exist yet."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def ledger_file(project: Path, feature: str) -> Path:
    """Return the attempt ledger path of a feature."""
    return project / ".harness" / "attempts" / f"{feature}.jsonl"


def append(project: Path, feature: str, entry: Json) -> None:
    """Append one entry to the feature's ledger."""
    path = ledger_file(project, feature)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def tool_signals(project: Path, since_ms: float) -> Json:
    """Return failed tool calls, repeated terminal commands and retrieval misses logged by the loop guard since a time."""
    log = [e for e in read_jsonl(project / ".harness" / "tool_log.jsonl") if e["ts_ms"] >= since_ms]
    settled = {e["id"] for e in log if e["phase"] == "post"}
    pre = [e for e in log if e["phase"] == "pre"]
    failures = Counter(e["tool"] for e in pre if e["id"] not in settled)
    commands = Counter(e["key"] for e in pre if e["tool"] == "run_in_terminal")
    misses = sum(1 for e in pre if e["tool"] in RETRIEVAL_TOOLS and e["id"] not in settled)
    misses += sum(1 for e in log if e["phase"] == "post" and e["tool"] in RETRIEVAL_TOOLS and RETRIEVAL_ERROR.search(e["response"]))
    return {"tool_failures": dict(failures), "repeated_commands": {c: n for c, n in commands.items() if n >= REPEAT_LIMIT},
            "retrieval_misses": misses}


def entry(project: Path, attempt: int, approach: str | None, exit_code: int, output: str, since_ms: float, now_ms: float) -> Json:
    """Return the ledger entry of one check run, before a rule is chosen."""
    return {"attempt": attempt, "approach": approach, "ts_ms": now_ms, "exit_code": exit_code, "fingerprint": fingerprint(output),
            "checks": checks_passed(output), "files": file_hashes(project), "output_tail": output[-1500:],
            **tool_signals(project, since_ms)}


def since_human(ledger: list[Json]) -> list[Json]:
    """Return the ledger entries after the last human note (a resume starts the rules afresh)."""
    notes = [i for i, e in enumerate(ledger) if "human_note" in e]
    return ledger[notes[-1] + 1:] if notes else ledger


def decide(history: list[Json], current: Json) -> Json:
    """Return {rule, action, escalate} for a failed attempt from the ledger so far (baseline first) and the new entry."""
    earlier = [e for e in since_human(history) if "fingerprint" in e]
    baseline = next(e for e in history if e.get("attempt") == 0)
    fp, output = current["fingerprint"], current["output_tail"]
    failing = [t for t, n in current["tool_failures"].items() if n >= REPEAT_LIMIT]
    failing += ["run_in_terminal"] if current["repeated_commands"] else []
    rule, action = "R0", "New error: fix exactly what the check output reports, then run verify again."
    if ENV_ERROR.search(output):
        rule = "R6"
        action = ("Run `npm config set registry https://packagefeedproxy.microsoft.io/npm/` (AGENTS.md), then verify again."
                  if REGISTRY_ERROR.search(output) else "")
    elif fp == baseline["fingerprint"] and any(e["fingerprint"] == fp for e in earlier if e["attempt"] > 0):
        rule, action = "R5", ""
    elif any(e["fingerprint"] == fp and e["files"] == current["files"] for e in earlier[:-1]):
        rule, action = "R1", ""
    elif earlier and earlier[-1]["fingerprint"] == fp:
        rule, action = "R2", ("Same error twice: start a fresh sub-agent with the ledger summary and a different approach, or run "
                              "parallel_options.py with two approaches.")
    elif failing:
        rule, action = "R3", " ".join(TOOL_HINTS[t] for t in failing if t in TOOL_HINTS)
    elif current["retrieval_misses"] >= 2:
        rule, action = "R4", ("Retrieval misses: query the code graph or file_search for every path and symbol named in the error, then "
                              "give a fresh sub-agent those exact paths.")
    if rule in {e.get("rule") for e in earlier} - {None, "R0"}:
        return {"rule": "R7", "action": QUESTIONS["R7"].format(rule=rule), "escalate": True}
    if not action:
        last_line = output.strip().splitlines()[-1][:200] if output.strip() else "no output"
        return {"rule": rule, "action": QUESTIONS[rule].format(first=last_line), "escalate": True}
    return {"rule": rule, "action": action, "escalate": False}
