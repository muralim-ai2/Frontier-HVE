"""Parallel options for one feature: a git worktree per approach, checked and ranked; auto-picked in benchmark runs, human-picked otherwise."""

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "loop"))
from branch_workflow import git, read_json, write_json  # noqa: E402
from diagnose import append, entry  # noqa: E402
from loop import escalate, run_check  # noqa: E402

APPROACH = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
FIRST_PORT = 3100

Json = dict[str, Any]


def options_file(project: Path, feature: str) -> Path:
    """Return the options record path of a feature."""
    return project / ".harness" / "options" / f"{feature}.json"


def worktree(project: Path, feature: str, approach: str) -> Path:
    """Return the worktree folder of one approach, inside the project's ignored .hve/discovery/ folder."""
    return project / ".hve" / "discovery" / f"{feature}--{approach}"


def create(project: Path, feature: str, approaches: list[str]) -> Json:
    """Create branch feature/<f>--<approach> and its worktree from the current feature's HEAD for each approach."""
    if read_json(project / ".harness" / "state.json")["current"] != feature:
        raise ValueError(f"{feature!r} is not the current feature: run `loop.py next` first")
    if len(approaches) < 2 or len(set(approaches)) != len(approaches) or not all(APPROACH.match(a) for a in approaches):
        raise ValueError(f"need at least 2 unique approach slugs matching {APPROACH.pattern}: {approaches}")
    base = git(project, "rev-parse", "HEAD").strip()
    for approach in approaches:
        git(project, "worktree", "add", "-b", f"feature/{feature}--{approach}", str(worktree(project, feature, approach)), base)
    write_json(options_file(project, feature), {"feature": feature, "base": base, "approaches": approaches, "results": [],
                                                "recommended": None, "winner": None, "chosen_by": None})
    return {"feature": feature, "worktrees": {a: worktree(project, feature, a).as_posix() for a in approaches}}


def evaluate(project: Path, record: Json, approach: str, command: str, attempt: int, since_ms: float) -> Json:
    """Commit pending work in the approach's worktree, run the feature's check there, ledger it, and return its result."""
    path = worktree(project, record["feature"], approach)
    git(path, "add", "-A")
    code, output = 0, ""
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=path).returncode != 0:
        commit = subprocess.run(["git", "commit", "-m", f"[option] {approach}"], cwd=path, capture_output=True, text=True, encoding="utf-8")
        code, output = commit.returncode, f"commit rejected:\n{commit.stdout}{commit.stderr}" if commit.returncode else ""
    added = sum(int(line.split("\t")[0]) for line in git(path, "diff", "--numstat", f"{record['base']}..HEAD").splitlines()
                if not line.startswith("-"))
    if code == 0 and added == 0:
        code, output = 1, "no changes"
    if code == 0:
        code, output = run_check(command, path)
    result = entry(path, attempt, approach, code, output, since_ms, time.time() * 1000)
    append(project, record["feature"], result | {"rule": None})
    return {"approach": approach, "passes": code == 0, "checks": result["checks"], "lines_added": added,
            "fingerprint": result["fingerprint"], "output_tail": output[-600:]}


def rank(results: list[Json]) -> list[Json]:
    """Return results best first: passing, then share of checks passed, then smallest diff."""
    return sorted(results, key=lambda r: (not r["passes"], -(r["checks"][0] / r["checks"][1] if r["checks"] else 0), r["lines_added"]))


def adopt(project: Path, record: Json, approach: str, chosen_by: str) -> Json:
    """Fast-forward feature/<f> to the approach, remove all worktrees (branches stay as evidence), and save the record."""
    git(project, "merge", "--ff-only", f"feature/{record['feature']}--{approach}")
    for a in record["approaches"]:
        git(project, "worktree", "remove", "--force", str(worktree(project, record["feature"], a)))
    record |= {"winner": approach, "chosen_by": chosen_by}
    write_json(options_file(project, record["feature"]), record)
    return record


def compare(project: Path, feature: str) -> Json:
    """Check and rank every approach; benchmark (review=local) adopts the best passing one, github review waits for the human."""
    state = read_json(project / ".harness" / "state.json")
    record = read_json(options_file(project, feature))
    attempt = state["attempts"][feature] + 1
    record["results"] = rank([evaluate(project, record, a, state["lock"][feature]["verify"], attempt, state["since_ms"])
                              for a in record["approaches"]])
    best = record["results"][0]
    record["recommended"] = best["approach"] if best["passes"] else None
    if not best["passes"] and len({r["fingerprint"] for r in record["results"]}) == 1:
        escalate(project, state, feature, "R5", "Every approach fails the check with the same error. Is the check right, and what does "
                 "the feature need that its description does not say?", {"results": record["results"]})
    write_json(options_file(project, feature), record)
    if state["review"] == "local" and best["passes"]:
        return adopt(project, record, best["approach"], "auto")
    return record | {"preview": preview(project, feature)}


def preview(project: Path, feature: str) -> list[Json]:
    """Return, per approach, its folder and the commands a human runs to try it on its own port."""
    record = read_json(options_file(project, feature))
    rows = []
    for i, approach in enumerate(record["approaches"]):
        path, port = worktree(project, feature, approach), FIRST_PORT + i
        commands = (["npm install", f"npm run dev -- --port {port}"] if (path / "package.json").exists()
                    else [read_json(project / ".harness" / "state.json")["lock"][feature]["verify"]])
        rows.append({"approach": approach, "folder": path.as_posix(), "port": port, "open": f'code -n "{path}"', "commands": commands})
    return rows


def choose(project: Path, feature: str, approach: str) -> Json:
    """Adopt the approach the human ticked (recorded by the plugin's choice recorder hook), whatever the ranking says."""
    choice_file = project / ".harness" / "choices" / f"{feature}.json"
    if not choice_file.exists() or read_json(choice_file)["approach"] != approach:
        raise PermissionError(f"the human has not ticked {approach!r} for {feature!r}: ask with the parallel-options skill first")
    return adopt(project, read_json(options_file(project, feature)), approach, "human")


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) >= 5 and args[0] == "create":
        out: Any = create(Path(args[1]).resolve(), args[2], args[3:])
    elif len(args) == 3 and args[0] in ("compare", "preview"):
        out = {"compare": compare, "preview": preview}[args[0]](Path(args[1]).resolve(), args[2])
    elif len(args) == 4 and args[0] == "choose":
        out = choose(Path(args[1]).resolve(), args[2], args[3])
    else:
        raise SystemExit("usage: parallel_options.py create <project> <feature> <approach> <approach>... | compare <project> <feature> | "
                         "preview <project> <feature> | choose <project> <feature> <approach>")
    print(json.dumps(out, indent=2))
