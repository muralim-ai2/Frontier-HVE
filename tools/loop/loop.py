"""Initializer/worker loop over feature_list.json: init locks features and starts git; next picks one; verify commits, flips, or diagnoses."""

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "git"))
from branch_workflow import git, open_pr, read_json, start, write_json  # noqa: E402
from diagnose import QUESTIONS, append, decide, entry, read_jsonl, ledger_file  # noqa: E402

NO_FALLBACK = ROOT / "hooks" / "no_fallback.py"
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
TRIVIAL_VERIFY = re.compile(r"^\s*(true|exit\s+0|echo\b.*|rem\b.*|:)?\s*$", re.I)
FIELDS = {"name", "description", "verify", "passes"}
MIN_FEATURES = 3
MAX_ATTEMPTS = 5
VERIFY_TIMEOUT_S = 300
GITIGNORE = ("node_modules/", ".next/", ".harness/", ".worktrees/")
Review = Literal["local", "github"]

Json = dict[str, Any]


def validate(features: Any) -> None:
    """Raise unless features is a list of at least 3 unique, unpassed features with a non-trivial verify command."""
    if not isinstance(features, list) or len(features) < MIN_FEATURES:
        raise ValueError(f"feature_list.json must be a list of at least {MIN_FEATURES} features")
    for f in features:
        if not isinstance(f, dict) or set(f) != FIELDS:
            raise ValueError(f"each feature needs exactly the fields {sorted(FIELDS)}: {f}")
        if not NAME.match(f["name"]) or not f["description"].strip() or f["passes"] is not False:
            raise ValueError(f"feature {f['name']!r}: name must match {NAME.pattern}, description non-empty, passes false")
        if TRIVIAL_VERIFY.match(f["verify"]):
            raise ValueError(f"feature {f['name']!r}: verify must be a real check command, not {f['verify']!r}")
    names = [f["name"] for f in features]
    if len(set(names)) != len(names):
        raise ValueError(f"feature names must be unique: {names}")


def init(project: Path, review: Review) -> Json:
    """Validate and lock feature_list.json, write progress.txt and .gitignore, add the B1 pre-commit hook to a new or existing repo, commit."""
    if (project / ".harness" / "state.json").exists():
        raise FileExistsError(f"{project} is already initialized")
    features = read_json(project / "feature_list.json")
    validate(features)
    if not (project / ".git").exists():
        git(project, "init", "-b", "main")
        git(project, "config", "user.name", "harness")
        git(project, "config", "user.email", "harness@localhost")
    hook = project / git(project, "rev-parse", "--git-path", "hooks/pre-commit").strip()
    script = f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{NO_FALLBACK.as_posix()}" .\n'
    if hook.exists() and hook.read_text(encoding="utf-8") != script:
        raise FileExistsError(f"{hook} already exists; add `{script.splitlines()[1]}` to it, then run init again")
    ignore = project / ".gitignore"
    existing = ignore.read_text(encoding="utf-8").splitlines() if ignore.exists() else []
    ignore.write_text("\n".join(existing + [g for g in GITIGNORE if g not in existing]) + "\n", encoding="utf-8")
    (project / "progress.txt").write_text("", encoding="utf-8")
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(script, encoding="utf-8", newline="\n")
    write_json(project / ".harness" / "state.json", {
        "review": review, "trunk": git(project, "symbolic-ref", "--short", "HEAD").strip(), "order": [f["name"] for f in features],
        "lock": {f["name"]: {"description": f["description"], "verify": f["verify"]} for f in features},
        "attempts": {f["name"]: 0 for f in features}, "base": {}, "current": None, "since_ms": None, "escalated": None, "help": None})
    git(project, "add", "-A")
    git(project, "commit", "-m", "[init] scaffold")
    return {"initialized": True, "review": review, "features": [f["name"] for f in features]}


def load(project: Path) -> tuple[Json, list[Json]]:
    """Return the loop state and features after checking the features still match the lock (anti-gaming, blindspot B5)."""
    state = read_json(project / ".harness" / "state.json")
    if state["escalated"]:
        raise RuntimeError(f"feature {state['escalated']!r} is escalated to the human: {state['help']['question']}")
    features = read_json(project / "feature_list.json")
    locked = [(n, state["lock"][n]["description"], state["lock"][n]["verify"]) for n in state["order"]]
    if [(f["name"], f["description"], f["verify"]) for f in features] != locked:
        raise RuntimeError("B5: feature_list.json names, descriptions, or verify commands differ from the locked list")
    return state, features


def run_check(command: str, cwd: Path) -> tuple[int, str]:
    """Run a check command and return its exit code and its output, prefixed with the command and exit code."""
    check = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=VERIFY_TIMEOUT_S)
    return check.returncode, f"verify `{command}` exited {check.returncode}:\n{check.stdout}{check.stderr}"


def escalate(project: Path, state: Json, name: str, rule: str, question: str, evidence: Json) -> None:
    """Hand the feature to the human with one question and the evidence behind it."""
    state["escalated"] = name
    state["help"] = {"feature": name, "rule": rule, "question": question, "evidence": evidence}
    write_json(project / ".harness" / "state.json", state)


def next_feature(project: Path) -> Json:
    """Check out the first failing feature's branch; on first visit record a baseline check run (attempt 0) that must fail."""
    state, features = load(project)
    todo = next((f for f in features if not f["passes"]), None)
    if todo is None:
        return {"done": True}
    name = todo["name"]
    if name not in state["base"]:
        state["base"][name] = git(project, "rev-parse", "HEAD").strip()
    start(project, name)
    now = time.time() * 1000
    state["current"], state["since_ms"] = name, now
    write_json(project / ".harness" / "state.json", state)
    if not ledger_file(project, name).exists():
        code, output = run_check(todo["verify"], project)
        append(project, name, entry(project, 0, None, code, output, now, now) | {"rule": None})
        if code == 0:
            escalate(project, state, name, "R5", "The check passes before any work, so it cannot prove this feature. Which check should "
                     "it use instead?", {"output_tail": output[-600:]})
            return {"name": name, "escalated": True, "question": state["help"]["question"]}
    return {"name": name, "description": todo["description"], "verify": todo["verify"], "attempts": state["attempts"][name],
            "remaining": sum(not f["passes"] for f in features)}


def failed(project: Path, state: Json, name: str, code: int, output: str, approach: str | None = None) -> Json:
    """Ledger a failed attempt, apply the first matching rule, and escalate on a human rule or at the attempt cap."""
    now = time.time() * 1000
    current = entry(project, state["attempts"][name] + 1, approach, code, output, state["since_ms"], now)
    decision = decide(read_jsonl(ledger_file(project, name)), current)
    append(project, name, current | decision)
    state["attempts"][name] += 1
    state["since_ms"] = now
    if decision["escalate"] or state["attempts"][name] >= MAX_ATTEMPTS:
        question = decision["action"] if decision["escalate"] else QUESTIONS["cap"].format(n=MAX_ATTEMPTS)
        escalate(project, state, name, decision["rule"] if decision["escalate"] else "cap", question,
                 {"fingerprint": current["fingerprint"], "output_tail": output[-600:], "tool_failures": current["tool_failures"]})
    else:
        write_json(project / ".harness" / "state.json", state)
    return {"name": name, "passes": False, "attempts": state["attempts"][name], "rule": decision["rule"], "action": decision["action"],
            "escalated": bool(state["escalated"]), "output_tail": output[-1500:]}


def verify(project: Path) -> Json:
    """Run the current feature's check; on success commit, flip passes, log progress, and write its PR record; else diagnose."""
    state, features = load(project)
    name = state["current"]
    if name is None:
        raise RuntimeError("no current feature: run `loop.py next` first")
    if git(project, "rev-parse", "--abbrev-ref", "HEAD").strip() != f"feature/{name}":
        raise RuntimeError(f"not on branch feature/{name}")
    command = state["lock"][name]["verify"]
    code, output = run_check(command, project)
    if code != 0:
        return failed(project, state, name, code, output)
    git(project, "add", "-A")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=project).returncode != 0:
        commit = subprocess.run(["git", "commit", "-m", f"[feature] {name}"], cwd=project, capture_output=True, text=True, encoding="utf-8")
        if commit.returncode != 0:
            return failed(project, state, name, commit.returncode, f"commit rejected:\n{commit.stdout}{commit.stderr}")
    if git(project, "rev-list", "--count", f"{state['base'][name]}..HEAD").strip() == "0":
        return failed(project, state, name, 1, "no commits on the feature branch: a feature passes only with committed work")
    for f in features:
        f["passes"] = f["passes"] or f["name"] == name
    write_json(project / "feature_list.json", features)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with (project / "progress.txt").open("a", encoding="utf-8") as log:
        log.write(f"{stamp} {name} passes after {state['attempts'][name] + 1} attempt(s): {command}\n")
    git(project, "add", "-A")
    git(project, "commit", "-m", f"[progress] {name} passes")
    previous = state["order"][state["order"].index(name) - 1] if state["order"].index(name) else None
    pr = open_pr(project, name, state["base"][name], {"command": command, "exit_code": 0, "output_tail": output[-2000:]},
                 base_branch=f"feature/{previous}" if previous else state["trunk"], status="queued" if state["review"] == "github" else "recorded")
    state["current"] = None
    write_json(project / ".harness" / "state.json", state)
    return {"name": name, "passes": True, "remaining": sum(not f["passes"] for f in features), "pr": pr["branch"],
            "pr_status": pr["status"], "lines_added": pr["lines_added"], "scope_creep": pr["scope_creep"]}


def resume(project: Path, note: str) -> Json:
    """Human-only: record the human's answer, clear the escalation, and give the feature a fresh attempt budget."""
    state = read_json(project / ".harness" / "state.json")
    name = state["escalated"]
    if name is None:
        raise ValueError("nothing is escalated")
    append(project, name, {"human_note": note, "answers": state["help"], "ts_ms": time.time() * 1000})
    state["attempts"][name], state["escalated"], state["help"], state["since_ms"] = 0, None, None, time.time() * 1000
    write_json(project / ".harness" / "state.json", state)
    return {"resumed": name, "note": note}


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 4 and args[0] == "init" and args[2] == "--review" and args[3] in ("local", "github"):
        result = init(Path(args[1]).resolve(), args[3])  # type: ignore[arg-type]
    elif len(args) == 2 and args[0] in ("next", "verify"):
        result = {"next": next_feature, "verify": verify}[args[0]](Path(args[1]).resolve())
    elif len(args) >= 3 and args[0] == "resume":
        result = resume(Path(args[1]).resolve(), " ".join(args[2:]))
    else:
        raise SystemExit("usage: loop.py init <project> --review {local|github} | next <project> | verify <project> | resume <project> <note>")
    print(json.dumps(result, indent=2))
    sys.exit(1 if result.get("passes") is False or result.get("escalated") else 0)
