"""Git workflow for loop features: stacked feature branches, PR records, and a push queue that only human-ticked PRs leave."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCOPE_CREEP_LINES = 1500

Json = dict[str, Any]


def git(project: Path, *args: str) -> str:
    """Run git in the project and return stdout; raise with stderr on failure."""
    result = subprocess.run(["git", *args], cwd=project, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {project}:\n{result.stdout}{result.stderr}")
    return result.stdout


def read_json(path: Path) -> Any:
    """Return the parsed JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    """Write data as indented JSON, creating parent folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def pr_file(project: Path, feature: str) -> Path:
    """Return the PR record path of a feature."""
    return project / ".harness" / "prs" / f"{feature}.json"


def start(project: Path, feature: str) -> None:
    """Check out feature/<name>, creating it from the current HEAD so it stacks on earlier features."""
    branch = f"feature/{feature}"
    git(project, "checkout", *([branch] if git(project, "branch", "--list", branch).strip() else ["-b", branch]))


def open_pr(project: Path, feature: str, base: str, verify: Json, base_branch: str, status: str) -> Json:
    """Write the feature's PR record (diff stats, verify result, scan status, scope-creep flag, stacked base branch)."""
    files: list[Json] = []
    for line in git(project, "diff", "--numstat", f"{base}..HEAD").splitlines():
        added, deleted, path = line.split("\t")
        lines = len((project / path).read_text(encoding="utf-8").splitlines()) if added != "-" and (project / path).exists() else None
        files.append({"path": path, "added": None if added == "-" else int(added), "deleted": None if deleted == "-" else int(deleted),
                      "lines": lines})
    added_total = sum(f["added"] or 0 for f in files)
    record = {"feature": feature, "branch": f"feature/{feature}", "base_branch": base_branch, "base": base,
              "head": git(project, "rev-parse", "HEAD").strip(), "status": status, "verify": verify,
              "no_fallback_scan": "passed (pre-commit hook)",
              "lines_added": added_total, "scope_creep": added_total > SCOPE_CREEP_LINES,
              "largest_file_lines": max((f["lines"] or 0 for f in files), default=0), "files": files}
    write_json(pr_file(project, feature), record)
    return record


def queue(project: Path) -> list[Json]:
    """Return the queued PRs (verified, not pushed) with what the human needs to tick them."""
    records = [read_json(p) for p in sorted((project / ".harness" / "prs").glob("*.json"))]
    return [{"branch": r["branch"], "base_branch": r["base_branch"], "lines_added": r["lines_added"], "scope_creep": r["scope_creep"],
             "verify": r["verify"]["command"]} for r in records if r["status"] == "queued"]


def approved(project: Path) -> list[str]:
    """Return the branches the human ticked for pushing (written by the plugin's choice recorder hook)."""
    path = project / ".harness" / "push_approved.json"
    return read_json(path)["branches"] if path.exists() else []


def pushed(project: Path, feature: str, url: str) -> Json:
    """Mark a ticked, queued PR as pushed with its URL."""
    record = read_json(pr_file(project, feature))
    if record["status"] != "queued" or record["branch"] not in approved(project):
        raise ValueError(f"{record['branch']} is {record['status']} and {'ticked' if record['branch'] in approved(project) else 'not ticked'}"
                         " for pushing")
    record |= {"status": "pushed", "url": url}
    write_json(pr_file(project, feature), record)
    return record


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "list":
        for path in sorted((Path(args[1]) / ".harness" / "prs").glob("*.json")):
            pr = read_json(path)
            print(f"{pr['branch']} (base {pr['base_branch']}): {pr['status']}, +{pr['lines_added']} lines, verify exit "
                  f"{pr['verify']['exit_code']}" + (", SCOPE CREEP" if pr["scope_creep"] else ""))
    elif len(args) == 2 and args[0] == "queue":
        print(json.dumps(queue(Path(args[1])), indent=2))
    elif len(args) == 4 and args[0] == "pushed":
        print(json.dumps(pushed(Path(args[1]), args[2], args[3]), indent=2))
    else:
        raise SystemExit("usage: branch_workflow.py list <project> | queue <project> | pushed <project> <feature> <pr_url>")
