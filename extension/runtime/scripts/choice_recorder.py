"""PostToolUse hook: record the user's ticks from ask-questions answers (option choice, manual check, PRs to push, build preference) for the harness."""

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ASK_TOOL = "vscode_askQuestions"
TAG = re.compile(r"\[(project|profile):\s*([^\]]+)\]")
PREFERENCES = {"no code": "no_code", "low code": "low_code", "pro code": "pro_code"}
CHECK_RESULTS = ("looks right", "needs changes", "skip")

Json = dict[str, Any]


def harness_dir(cwd: Path, tags: dict[str, str]) -> Path:
    """Return the tagged project's existing .harness folder (only initialized harness projects accept ticks)."""
    folder = (cwd / tags["project"].strip()).resolve() / ".harness"
    if not folder.is_dir():
        raise FileNotFoundError(f"{folder} does not exist: the tagged project is not an initialized harness project")
    return folder


def record(question: Json, selected: list[str], cwd: Path) -> None:
    """Write one answered question to the file the harness reads for it."""
    header = question["header"]
    tags = dict(TAG.findall(question["question"] + " " + question.get("message", "")))
    if header.startswith("choose:"):
        if len(selected) != 1:
            raise ValueError(f"{header}: tick exactly one option, got {selected}")
        path = harness_dir(cwd, tags) / "choices" / f"{header.removeprefix('choose:')}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"approach": selected[0], "ts_ms": time.time() * 1000}), encoding="utf-8")
    elif header.startswith("check:"):
        if len(selected) != 1 or selected[0] not in CHECK_RESULTS:
            raise ValueError(f"{header}: tick exactly one of {CHECK_RESULTS}, got {selected}")
        path = harness_dir(cwd, tags) / "checks" / f"{header.removeprefix('check:')}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"result": selected[0], "ts_ms": time.time() * 1000}), encoding="utf-8")
    elif header == "push":
        path = harness_dir(cwd, tags) / "push_approved.json"
        earlier = json.loads(path.read_text(encoding="utf-8"))["branches"] if path.exists() else []
        branches = sorted(set(earlier) | {s for s in selected if s.startswith("feature/")})
        path.write_text(json.dumps({"branches": branches, "ts_ms": time.time() * 1000}), encoding="utf-8")
    elif header == "build-preference":
        profile = (cwd / tags["profile"].strip()).resolve()
        if profile.name != "user_profile.json" or not profile.is_file() or len(selected) != 1 or selected[0] not in PREFERENCES:
            raise ValueError(f"build-preference needs [profile: .../user_profile.json] and one of {list(PREFERENCES)}, got {profile}, {selected}")
        data = json.loads(profile.read_text(encoding="utf-8"))
        data["build_preference"] = PREFERENCES[selected[0]]
        profile.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    """Record every harness-tagged answer of an ask-questions call; ignore all other tools and questions."""
    payload = json.load(sys.stdin)
    if payload["hook_event_name"] != "PostToolUse" or payload["tool_name"] != ASK_TOOL:
        return
    response = payload["tool_response"]
    answers = (json.loads(response) if isinstance(response, str) else response)["answers"]
    for question in payload["tool_input"]["questions"]:
        header = question["header"]
        if (header.startswith(("choose:", "check:")) or header in ("push", "build-preference")) and not answers[header].get("skipped"):
            record(question, answers[header]["selected"], Path.cwd())


if __name__ == "__main__":
    main()
