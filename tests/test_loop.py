"""Tests of the feature loop: rules on the attempt ledger, guards, no-fallback scan, module guard, PR queue, and parallel options."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "tools" / "loop"), str(REPO / "tools" / "git"), str(REPO / "hooks")]
import loop  # noqa: E402
from branch_workflow import git, pushed, queue, read_json  # noqa: E402
from diagnose import decide  # noqa: E402
from no_fallback import scan_file  # noqa: E402
from parallel_options import choose, compare, create  # noqa: E402

CHECK = ("import pathlib, sys\n"
         "note = pathlib.Path('note.txt')\n"
         "print(note.read_text() if note.exists() else '')\n"
         "sys.exit(0 if all(pathlib.Path(p).exists() for p in sys.argv[1:]) else 1)\n")
START_MS = datetime.fromisoformat("2026-10-06T08:00:00+00:00").timestamp() * 1000


def feature(name: str, *files: str) -> dict[str, Any]:
    """Return a feature whose verify passes once the given files exist."""
    return {"name": name, "description": f"create {', '.join(files)}", "verify": f"python check.py {' '.join(files)}", "passes": False}


def make_project(tmp: str, features: list[dict[str, Any]], review: str = "local") -> Path:
    """Return an initialized project folder with check.py and the features."""
    project = Path(tmp) / "project"
    project.mkdir()
    (project / "check.py").write_text(CHECK, encoding="utf-8")
    (project / "feature_list.json").write_text(json.dumps(features), encoding="utf-8")
    loop.init(project, review)  # type: ignore[arg-type]
    return project


def raises(error: type[Exception], fn: Any, *args: Any) -> str:
    """Return the message of the error fn(*args) raises; fail if it does not."""
    try:
        fn(*args)
    except error as e:
        return str(e)
    raise AssertionError(f"{fn.__name__}{args} did not raise {error.__name__}")


def three(tmp: str, review: str = "local") -> Path:
    """Return a project with features a, b, c checked by a.txt, b.txt, c.txt."""
    return make_project(tmp, [feature("a", "a.txt"), feature("b", "b.txt"), feature("c", "c.txt")], review)


def test_init_rejects_bad_feature_lists() -> None:
    """Fewer than 3 features and trivial verify commands are rejected."""
    assert "at least 3" in raises(ValueError, loop.validate, [feature("a", "a.txt")])
    trivial = [feature("a", "a.txt"), feature("b", "b.txt"), {**feature("c", "c.txt"), "verify": "echo ok"}]
    assert "real check" in raises(ValueError, loop.validate, trivial)


def test_init_in_existing_repo() -> None:
    """Init keeps an existing repo's identity and branch, stacks the first PR on that branch, and refuses a foreign hook or a re-init."""
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "project"
        project.mkdir()
        git(project, "init", "-b", "trunk")
        git(project, "config", "user.name", "dev")
        git(project, "config", "user.email", "dev@example.com")
        (project / "check.py").write_text(CHECK, encoding="utf-8")
        (project / "feature_list.json").write_text(json.dumps([feature(n, f"{n}.txt") for n in "abc"]), encoding="utf-8")
        hook = project / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        assert "already exists" in raises(FileExistsError, loop.init, project, "local")
        hook.unlink()
        loop.init(project, "local")  # type: ignore[arg-type]
        assert git(project, "config", "user.name").strip() == "dev"
        assert git(project, "log", "-1", "--format=%an %s").strip() == "dev [init] scaffold"
        assert "already initialized" in raises(FileExistsError, loop.init, project, "local")
        loop.next_feature(project)
        (project / "a.txt").write_text("a\n", encoding="utf-8")
        assert loop.verify(project)["passes"] is True
        assert read_json(project / ".harness" / "prs" / "a.json")["base_branch"] == "trunk"


def test_tracker_reports_status_evidence_and_manual_check() -> None:
    """tracker.json is written at init and shows status, evidence files and the user's recorded manual check per feature."""
    with tempfile.TemporaryDirectory() as tmp:
        project = three(tmp)
        assert [r["status"] for r in read_json(project / "tracker.json")["features"]] == ["pending"] * 3
        assert ".hve/" in (project / ".gitignore").read_text(encoding="utf-8").splitlines()
        loop.next_feature(project)
        (project / "a.txt").write_text("a\n", encoding="utf-8")
        assert loop.verify(project)["passes"] is True
        (project / ".harness" / "evidence" / "a").mkdir(parents=True)
        (project / ".harness" / "evidence" / "a" / "page.png").write_bytes(b"png")
        (project / ".harness" / "checks").mkdir()
        (project / ".harness" / "checks" / "a.json").write_text(json.dumps({"result": "looks right"}), encoding="utf-8")
        loop.next_feature(project)
        data = loop.tracker(project)
        a, b = data["features"][0], data["features"][1]
        assert data["passed"] == 1 and a["status"] == "passed" and b["status"] == "in_progress", data
        assert a["evidence"] == [".harness/evidence/a/page.png"] and a["manual_check"] == "looks right", a


def test_amend_appends_without_changing_locked_features() -> None:
    """Amend appends new features to the lock between features, refuses renames and in-progress work, and deletes the add file."""
    with tempfile.TemporaryDirectory() as tmp:
        project = three(tmp)
        add = project / "feature_list.add.json"
        add.write_text(json.dumps([feature("d", "d.txt")]), encoding="utf-8")
        loop.next_feature(project)
        assert "in progress" in raises(RuntimeError, loop.amend, project)
        (project / "a.txt").write_text("a\n", encoding="utf-8")
        loop.verify(project)
        add.write_text(json.dumps([feature("a", "x.txt")]), encoding="utf-8")
        assert "already locked" in raises(ValueError, loop.amend, project)
        add.write_text(json.dumps([feature("d", "d.txt")]), encoding="utf-8")
        assert loop.amend(project) == {"amended": ["d"], "total": 4}
        assert not add.exists() and [f["name"] for f in read_json(project / "feature_list.json")] == ["a", "b", "c", "d"]
        assert loop.load(project)[0]["order"][-1] == "d"


def test_loop_commits_flips_and_queues() -> None:
    """Verify fails until the work exists, B1 code is rejected at commit, PR records stack, and a passing baseline escalates."""
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(tmp, [feature("a", "a.txt"), feature("b", "b.txt"), feature("c", "a.txt")])
        assert loop.next_feature(project)["name"] == "a"
        (project / "a.txt").write_text("a\n", encoding="utf-8")
        assert loop.verify(project)["passes"] is True
        assert read_json(project / "feature_list.json")[0]["passes"] is True and "a passes" in (project / "progress.txt").read_text()
        assert loop.next_feature(project)["name"] == "b"
        (project / "b.txt").write_text("b\n", encoding="utf-8")
        (project / "bad.py").write_text("try:\n    x = 1\nexcept Exception:\n    pass\n", encoding="utf-8")
        rejected = loop.verify(project)
        assert rejected["passes"] is False and "B1" in rejected["output_tail"], rejected
        (project / "bad.py").write_text("x = 1\n", encoding="utf-8")
        passed = loop.verify(project)
        assert passed["passes"] is True and passed["pr_status"] == "recorded", passed
        assert read_json(project / ".harness" / "prs" / "b.json")["base_branch"] == "feature/a"
        baseline_passes = loop.next_feature(project)
        assert baseline_passes["escalated"] is True and "before any work" in baseline_passes["question"], baseline_passes
        loop.resume(project, "use c.txt instead")
        assert read_json(project / ".harness" / "state.json")["escalated"] is None


def test_rules_stuck_then_spec() -> None:
    """The same failure as the baseline fires R2 (fresh approach), then R5 escalates to the human with a question."""
    with tempfile.TemporaryDirectory() as tmp:
        project = three(tmp)
        loop.next_feature(project)
        first = loop.verify(project)
        assert first["rule"] == "R2" and first["escalated"] is False, first
        second = loop.verify(project)
        assert second["rule"] == "R5" and second["escalated"] is True, second
        assert "escalated" in raises(RuntimeError, loop.next_feature, project)


def test_rules_circular_and_cap() -> None:
    """A-B-A with the same files fires R1; five new errors in a row hit the attempt cap."""
    with tempfile.TemporaryDirectory() as tmp:
        project = three(tmp)
        loop.next_feature(project)
        rules = []
        for note in ("alpha", "beta", "alpha"):
            (project / "note.txt").write_text(note, encoding="utf-8")
            rules.append(loop.verify(project)["rule"])
        assert rules == ["R0", "R0", "R1"], rules
    with tempfile.TemporaryDirectory() as tmp:
        project = three(tmp)
        loop.next_feature(project)
        for note in ("alpha", "beta", "gamma", "delta", "epsilon"):
            (project / "note.txt").write_text(note, encoding="utf-8")
            result = loop.verify(project)
        assert result["escalated"] is True and read_json(project / ".harness" / "state.json")["help"]["rule"] == "cap", result


def entry(fp: str, attempt: int, **extra: Any) -> dict[str, Any]:
    """Return a synthetic ledger entry."""
    return {"attempt": attempt, "fingerprint": fp, "files": {"x": fp}, "output_tail": "boom", "tool_failures": {},
            "repeated_commands": {}, "retrieval_misses": 0, "rule": None} | extra


def test_rules_tool_retrieval_environment() -> None:
    """Repeated tool failures give a tool hint (R3), retrieval misses a graph hint (R4), registry 403 the AGENTS.md fix (R6);
    the same rule a second time escalates (R7)."""
    history = [entry("base", 0)]
    tool = decide(history, entry("e1", 1, tool_failures={"replace_string_in_file": 3}))
    assert tool["rule"] == "R3" and "old text must match" in tool["action"] and not tool["escalate"], tool
    retrieval = decide(history, entry("e1", 1, retrieval_misses=2))
    assert retrieval["rule"] == "R4" and not retrieval["escalate"], retrieval
    env = decide(history, entry("e1", 1, output_tail="npm ERR! code E403 forbidden"))
    assert env["rule"] == "R6" and "packagefeedproxy" in env["action"], env
    again = decide(history + [entry("e1", 1, rule="R6")], entry("e2", 2, output_tail="npm ERR! code E403 forbidden"))
    assert again["rule"] == "R7" and again["escalate"], again
    port = decide(history, entry("e1", 1, output_tail="Error: listen EADDRINUSE"))
    assert port["rule"] == "R6" and port["escalate"], port


def test_parallel_options_auto_and_human_choice() -> None:
    """Benchmark loops adopt the smaller passing option; GitHub loops wait for the human's tick and refuse untick choices."""
    with tempfile.TemporaryDirectory() as tmp:
        project = three(tmp)
        loop.next_feature(project)
        trees = create(project, "a", ["big", "small", "broken"])["worktrees"]
        (Path(trees["big"]) / "a.txt").write_text("x\n" * 50, encoding="utf-8")
        (Path(trees["small"]) / "a.txt").write_text("x\n", encoding="utf-8")
        (Path(trees["broken"]) / "other.txt").write_text("x\n", encoding="utf-8")
        result = compare(project, "a")
        assert result["winner"] == "small" and result["chosen_by"] == "auto", result
        assert not any(Path(t).exists() for t in trees.values()) and loop.verify(project)["passes"] is True
        approaches = [json.loads(line)["approach"] for line in (project / ".harness" / "attempts" / "a.jsonl").read_text().splitlines()]
        assert {"big", "small", "broken"} <= set(approaches), approaches
    with tempfile.TemporaryDirectory() as tmp:
        project = three(tmp, "github")
        loop.next_feature(project)
        trees = create(project, "a", ["one", "two"])["worktrees"]
        for t in trees.values():
            (Path(t) / "a.txt").write_text("x\n", encoding="utf-8")
        result = compare(project, "a")
        assert result["winner"] is None and len(result["preview"]) == 2 and all(Path(t).exists() for t in trees.values()), result
        assert "not ticked" in raises(PermissionError, choose, project, "a", "two")
        (project / ".harness" / "choices").mkdir()
        (project / ".harness" / "choices" / "a.json").write_text(json.dumps({"approach": "two"}), encoding="utf-8")
        assert choose(project, "a", "two")["chosen_by"] == "human"
        assert loop.verify(project)["pr_status"] == "queued"
        assert [q["branch"] for q in queue(project)] == ["feature/a"]
        assert "not ticked" in raises(ValueError, pushed, project, "a", "https://x/pr/1")


def test_parallel_options_same_failure_escalates() -> None:
    """When every option fails with the same error, the check itself is suspect (R5) and the human is asked."""
    with tempfile.TemporaryDirectory() as tmp:
        project = three(tmp)
        loop.next_feature(project)
        trees = create(project, "a", ["one", "two"])["worktrees"]
        for t in trees.values():
            (Path(t) / "other.txt").write_text("x\n", encoding="utf-8")
        assert compare(project, "a")["recommended"] is None
        assert read_json(project / ".harness" / "state.json")["help"]["rule"] == "R5"


def test_ask_mode_keeps_loop_files_in_the_ask_folder() -> None:
    """With an open ask the feature list, progress, tracker and state live in .hve/project/ and the evidence in the ask's loop/ folder,
    all out of git; commits carry the locked checks, checks get HVE_EVIDENCE, locks record the ask, and the guard protects both."""
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "project"
        folder = project / ".hve" / "asks" / "20261019-1200-x" / "loop"
        shared = project / ".hve" / "project"
        folder.mkdir(parents=True)
        shared.mkdir(parents=True)
        (project / ".hve" / "asks" / "active.json").write_text(json.dumps({"active": "20261019-1200-x"}), encoding="utf-8")
        (project / "check.py").write_text("import os, pathlib, sys\n"
                                          "out = pathlib.Path(os.environ['HVE_EVIDENCE']) / pathlib.Path(sys.argv[1]).stem\n"
                                          "out.mkdir(parents=True, exist_ok=True)\n(out / 'log.txt').write_text('checked')\n"
                                          "sys.exit(0 if pathlib.Path(sys.argv[1]).exists() else 1)\n", encoding="utf-8")
        (shared / "feature_list.json").write_text(json.dumps([feature(n, f"{n}.txt") for n in "abc"]), encoding="utf-8")
        loop.init(project, "local")  # type: ignore[arg-type]
        assert {p.name for p in shared.iterdir()} >= {"feature_list.json", "progress.txt", "tracker.json", "state.json"}
        state = json.loads((shared / "state.json").read_text(encoding="utf-8"))
        assert state["lock"]["a"]["ask"] == "20261019-1200-x", state["lock"]
        assert not (project / ".harness").exists() and not (project / "feature_list.json").exists()
        assert ".hve" not in git(project, "ls-files") and "a: python check.py a.txt" in git(project, "log", "-1", "--format=%b")
        loop.next_feature(project)
        (project / "a.txt").write_text("a\n", encoding="utf-8")
        assert loop.verify(project)["passes"] is True
        assert (folder / "evidence" / "a" / "log.txt").read_text(encoding="utf-8") == "checked"
        assert "verify: python check.py a.txt" in git(project, "log", "-1", "--format=%b")
        assert loop.tracker(project)["features"][0]["evidence"] == [".hve/asks/20261019-1200-x/loop/evidence/a/log.txt"]
        root = make_root(tmp)
        env = {"HARNESS_PROJECT": "project", "HARNESS_STOP_POLICY": "once"}
        for path, denied in ((shared / "feature_list.json", True), (shared / "state.json", True), (folder / "evidence" / "a" / "x.txt", True),
                             (project / "feature_list.json", False), (project / "src.py", False)):
            out = fire(root, "loop_guard.py", {"hook_event_name": "PreToolUse", "tool_name": "create_file", "tool_input": {"filePath": str(path)},
                                               "tool_use_id": "t1"}, **env)
            assert (out is not None) is denied, (path, out)


def test_no_fallback_patterns() -> None:
    """Silent except/catch and TODOs are found; re-raising handlers are not."""
    assert scan_file("a.py", "def f():\n    try:\n        g()\n    except ValueError:\n        return None\n")
    assert scan_file("a.py", "try:\n    g()\nexcept ValueError as e:\n    raise RuntimeError('ctx') from e\n") == []
    assert scan_file("a.ts", "try { g(); } catch (e) {}\n")
    assert scan_file("a.ts", "fetch(u).catch(() => {});\n")
    assert scan_file("a.js", "// TODO later\n")
    assert scan_file("a.ts", "try { g(); } catch (e) { throw new Error(`ctx: ${e}`); }\n") == []


def make_root(tmp: str, guard_mode: str = "enforce") -> Path:
    """Return a temp workspace with the guard hooks (loop guard in the given mode), .hve/runs, a 20-minute budget at 08:00 UTC, and a
    project folder."""
    root = Path(tmp)
    (root / "hooks").mkdir()
    for hook in ("loop_guard.py", "module_guard.py", "flow_guard.py", "interventions.py", "hve_paths.py", "guard_policy.py", "error_guard.py"):
        shutil.copy(REPO / "hooks" / hook, root / "hooks")
    (root / "hooks" / "guard_mode.json").write_text(json.dumps({"loop_guard": guard_mode}), encoding="utf-8")
    (root / "tools" / "loop").mkdir(parents=True)
    shutil.copy(REPO / "tools" / "loop" / "loop_paths.py", root / "tools" / "loop")
    (root / ".hve" / "runs").mkdir(parents=True)
    (root / ".hve" / "runs" / "s1.budget.json").write_text(json.dumps({"start_ms": START_MS, "budget_ms": 1_200_000.0, "denied": []}),
                                                          encoding="utf-8")
    (root / "proj" / ".harness").mkdir(parents=True)
    return root


def fire(root: Path, hook: str, payload: dict[str, Any], **env: str) -> dict[str, Any] | None:
    """Run a hook with a payload; return its JSON output or None when it printed nothing."""
    result = subprocess.run([sys.executable, str(root / "hooks" / hook)], input=json.dumps({"session_id": "s1", **payload}),
                            capture_output=True, text=True, env={**os.environ, **env}, cwd=root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def test_loop_guard() -> None:
    """Locked state, hook bypass, resume and unticked pushes are denied; tool calls are logged; Stop blocks per policy."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        proj = root / "proj"
        env = {"HARNESS_PROJECT": "proj", "HARNESS_STOP_POLICY": "budget"}

        def pre(tool: str, tool_input: dict[str, Any], **extra: str) -> dict[str, Any] | None:
            """Fire PreToolUse."""
            return fire(root, "loop_guard.py", {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
                                                "tool_use_id": "t1"}, **(env | extra))

        edit = {"filePath": str(proj / "feature_list.json")}
        assert pre("create_file", edit) is None
        (proj / "feature_list.json").write_text(json.dumps([{"name": "a", "passes": False}]), encoding="utf-8")
        state = {"review": "github", "current": "a", "escalated": None, "help": None}
        (proj / ".harness" / "state.json").write_text(json.dumps(state), encoding="utf-8")
        assert pre("create_file", edit)["hookSpecificOutput"]["permissionDecision"] == "deny"  # type: ignore[index]
        mentions = {"content": "Loop files: feature_list.json, progress.txt, tracker.json, .harness/state.json"}
        assert pre("create_file", {"filePath": str(proj / "README.md")} | mentions) is None
        assert pre("create_file", {"filePath": str(root / "tracker.json")}) is None
        assert pre("runSubagent", {"prompt": "Do not edit feature_list.json or .harness/"}) is None
        assert pre("run_in_terminal", {"command": "Get-Content feature_list.json 2>&1"}) is None
        cites = {"content": '{"evidence": [".harness/evidence/a/page.png", "feature_list.json"]}'}
        assert pre("create_file", {"filePath": str(proj / ".hve" / "evaluations" / "input" / "r-scores.json")} | cites) is None
        escape = str(proj / ".hve" / "evaluations" / "input" / ".." / ".." / ".." / "feature_list.json")
        assert pre("create_file", {"filePath": escape} | cites) is not None
        assert pre("read_file", edit) is None
        assert pre("run_in_terminal", {"command": "python ../../../../tools/loop/loop.py verify ."}) is None
        for bad in ("echo x > feature_list.json", "git commit --no-verify -m x", "python ../../../../tools/loop/loop.py resume . ok",
                    "git push -u origin feature/b", "git push --force origin feature/a", "git push"):
            assert pre("run_in_terminal", {"command": bad}) is not None, bad
        (proj / ".harness" / "push_approved.json").write_text(json.dumps({"branches": ["feature/a"]}), encoding="utf-8")
        assert pre("run_in_terminal", {"command": "git push -u origin feature/a"}) is None
        assert pre("github-pull-request_create_pull_request", {"head": "feature/b", "base": "feature/a"}) is not None
        fire(root, "loop_guard.py", {"hook_event_name": "PostToolUse", "tool_name": "read_file", "tool_input": edit, "tool_use_id": "t1",
                                     "tool_response": "ok"}, **env)
        phases = [json.loads(line)["phase"] for line in (proj / ".harness" / "tool_log.jsonl").read_text().splitlines()]
        assert "pre" in phases and phases[-1] == "post", phases

        def stop(at: str, active: bool, policy: str) -> dict[str, Any] | None:
            """Fire Stop at a time with a stop policy."""
            return fire(root, "loop_guard.py", {"hook_event_name": "Stop", "timestamp": f"2026-10-06T08:{at}:00+00:00",
                                                "stop_hook_active": active}, HARNESS_PROJECT="proj", HARNESS_STOP_POLICY=policy)

        assert stop("05", False, "budget")["hookSpecificOutput"]["decision"] == "block"  # type: ignore[index]
        assert stop("25", True, "budget") is None
        assert stop("05", False, "once") is not None and stop("05", True, "once") is None
        state |= {"escalated": "a", "help": {"question": "Which check?"}}
        (proj / ".harness" / "state.json").write_text(json.dumps(state), encoding="utf-8")
        stopped = pre("read_file", edit)
        assert stopped["continue"] is False and "Which check?" in stopped["stopReason"], stopped  # type: ignore[index]
        kinds = [json.loads(line)["kind"] for line in (root / ".hve" / "runs" / "s1.interventions.jsonl").read_text().splitlines()]
        assert {"loop_files", "hook_bypass", "human_only", "push_blocked", "victory_check", "escalated"} <= set(kinds), kinds
        state |= {"escalated": None, "help": None, "current": None}
        (proj / ".harness" / "state.json").write_text(json.dumps(state), encoding="utf-8")
        (proj / "feature_list.json").write_text(json.dumps([{"name": "a", "passes": True}]), encoding="utf-8")
        assert pre("replace_string_in_file", edit) is None
        assert pre("run_in_terminal", {"command": "echo x > progress.txt"}) is None
        assert pre("create_file", {"filePath": str(proj / ".harness" / "state.json")}) is not None
        assert pre("run_in_terminal", {"command": "rm .harness/state.json"}) is not None


def test_guard_waiver() -> None:
    """After 3 trips the deny asks for a waiver; laid down it allows loop files but never .harness/; an open evaluation makes it strict."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        proj = root / "proj"
        env = {"HARNESS_PROJECT": "proj", "HARNESS_STOP_POLICY": "once"}
        (proj / "feature_list.json").write_text(json.dumps([{"name": "a", "passes": False}]), encoding="utf-8")
        (proj / ".harness" / "state.json").write_text(json.dumps({"review": "local", "current": None, "escalated": None}), encoding="utf-8")

        def pre(path: Path) -> dict[str, Any] | None:
            """Fire PreToolUse for an edit of path."""
            return fire(root, "loop_guard.py", {"hook_event_name": "PreToolUse", "tool_name": "create_file", "tool_input": {"filePath": str(path)},
                                                "tool_use_id": "t1"}, **env)

        reasons = [pre(proj / "progress.txt")["hookSpecificOutput"]["permissionDecisionReason"] for _ in range(3)]  # type: ignore[index]
        assert "guard-waiver:loop_guard" not in reasons[1] and "guard-waiver:loop_guard" in reasons[2], reasons
        ask = {"questions": [{"header": "guard-waiver:loop_guard", "question": "Keep the loop guard?"}]}
        fire(root, "loop_guard.py", {"hook_event_name": "PostToolUse", "tool_name": "vscode_askQuestions", "tool_input": ask, "tool_use_id": "t2",
                                     "tool_response": json.dumps({"answers": {"guard-waiver:loop_guard": {"selected": ["Lay down for this session"]}}})},
             **env)
        assert pre(proj / "progress.txt") is None
        assert pre(proj / ".harness" / "state.json") is not None
        (root / ".hve" / "evaluations" / "r1").mkdir(parents=True)
        (root / ".hve" / "evaluations" / "r1" / "contract.json").write_text("{}", encoding="utf-8")
        strict = pre(proj / "progress.txt")
        assert strict and "strict" in strict["hookSpecificOutput"]["permissionDecisionReason"], strict
        kinds = [json.loads(line)["kind"] for line in (root / ".hve" / "runs" / "s1.interventions.jsonl").read_text().splitlines()]
        assert kinds.count("waived") == 1 and "waiver_answer" in kinds, kinds


def test_loop_guard_awareness_mode() -> None:
    """In advise mode a loop-file edit and an early stop are surfaced to the user with what changed, not blocked; pushes stay blocked."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp, "advise")
        proj = root / "proj"
        env = {"HARNESS_PROJECT": "proj", "HARNESS_STOP_POLICY": "once"}
        (proj / "feature_list.json").write_text(json.dumps([{"name": "a", "passes": False}]), encoding="utf-8")
        (proj / ".harness" / "state.json").write_text(json.dumps({"review": "local", "current": None, "escalated": None}), encoding="utf-8")
        edit = {"filePath": str(proj / "feature_list.json"), "oldString": '"passes": false', "newString": '"passes": true'}
        out = fire(root, "loop_guard.py", {"hook_event_name": "PreToolUse", "tool_name": "replace_string_in_file", "tool_input": edit,
                                           "tool_use_id": "t1"}, **env)
        assert out and "permissionDecision" not in out["hookSpecificOutput"], out
        assert out["systemMessage"].startswith("Advisory alert (experimental): surfaces LLM behaviour that helps to know. During the run a loop "
                                                "file"), out
        assert '`"passes": false` replaced by `"passes": true`' in out["systemMessage"] and "Advisory alert" in out["hookSpecificOutput"]["additionalContext"]
        stop = fire(root, "loop_guard.py", {"hook_event_name": "Stop", "timestamp": "2026-10-06T08:05:00+00:00", "stop_hook_active": False},
                    **env)
        assert stop == {"systemMessage": stop["systemMessage"]} and "stopped while features still fail" in stop["systemMessage"], stop
        push = fire(root, "loop_guard.py", {"hook_event_name": "PreToolUse", "tool_name": "run_in_terminal", "tool_use_id": "t2",
                                            "tool_input": {"command": "git push --force origin main"}}, **env)
        assert push["hookSpecificOutput"]["permissionDecision"] == "deny", push  # type: ignore[index]


def test_error_guard_pauses_after_three_failures_in_a_row() -> None:
    """Three failed commands in a row pause the agent and hold tools until the user's next prompt; a success or a loop check does not count."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)

        def post(command: str, response: str) -> dict[str, Any] | None:
            """Fire PostToolUse for a terminal command."""
            return fire(root, "error_guard.py", {"hook_event_name": "PostToolUse", "tool_name": "run_in_terminal", "tool_use_id": "t",
                                                 "tool_input": {"command": command}, "tool_response": response})

        def pre(tool: str) -> dict[str, Any] | None:
            """Fire PreToolUse."""
            return fire(root, "error_guard.py", {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {}, "tool_use_id": "t"})

        failed = "ModuleNotFoundError: No module named 'pptx'\nCommand exited with code 1"
        assert post("python build_deck.py", failed) is None and post("python build_deck.py", failed) is None
        assert post("python ../tools/loop/loop.py verify .", failed) is None and post("ls", "ok") is None
        assert post("python build_deck.py", failed) is None and post("python build_deck.py", failed) is None
        paused = post("python build_deck.py", failed)
        assert paused and paused["continue"] is False and "last 3 commands failed in a row" in paused["stopReason"], paused
        assert "No module named 'pptx'" in paused["systemMessage"], paused
        assert pre("run_in_terminal")["hookSpecificOutput"]["permissionDecision"] == "deny"  # type: ignore[index]
        assert pre("vscode_askQuestions") is None and pre("read_file") is None
        fire(root, "error_guard.py", {"hook_event_name": "UserPromptSubmit", "prompt": "install python-pptx and retry"})
        assert pre("run_in_terminal") is None
        kinds = [json.loads(line)["kind"] for line in (root / ".hve" / "runs" / "s1.interventions.jsonl").read_text().splitlines()]
        assert kinds == ["error_streak"], kinds


def test_module_guard() -> None:
    """Editing a file over 500 lines is blocked with a split instruction; smaller files pass."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        big, small = root / "big.ts", root / "small.ts"
        big.write_text("x\n" * 600, encoding="utf-8")
        small.write_text("x\n" * 100, encoding="utf-8")
        out = fire(root, "module_guard.py", {"hook_event_name": "PostToolUse", "tool_name": "multi_replace_string_in_file",
                                             "tool_input": {"replacements": [{"filePath": str(big)}, {"filePath": str(small)}]}})
        assert out and out["decision"] == "block" and "big.ts (600 lines)" in out["reason"] and "small.ts" not in out["reason"], out
        patch = {"input": f"*** Begin Patch\n*** Update File: {small}\n@@\n-x\n+y\n*** End Patch"}
        assert fire(root, "module_guard.py", {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "tool_input": patch}) is None


def test_prototype_check() -> None:
    """The prototype lint passes a safe clickthrough, flags unsafe code, missing screens and dead links, and screenshots go to the
    ask's evidence folder when a browser is installed."""
    sys.path.insert(0, str(REPO / "tools" / "prototype"))
    import check  # noqa: E402
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / ".hve" / "asks" / "20261021-1200-x" / "loop").mkdir(parents=True)
        (ws / ".hve" / "asks" / "active.json").write_text(json.dumps({"active": "20261021-1200-x"}), encoding="utf-8")
        proto = ws / "proto"
        proto.mkdir()
        (proto / "index.html").write_text('<h1>Dashboard</h1><a href="#/settings">Settings</a><a href="#/ghost">x</a>', encoding="utf-8")
        (proto / "app.js").write_text("const routes = {'/dashboard': 1, 'settings': 2};\n", encoding="utf-8")
        result = check.lint(proto, ["Dashboard", "Settings", "Billing"])
        assert result["problems"] == ["screen 'Billing' not found in the prototype", "link #ghost has no screen, route or element id"], result
        (proto / "app.js").write_text("fetch('/api'); eval('1');\n<script src='https://cdn.x/y.js'>", encoding="utf-8")
        assert {p.split(": ")[1] for p in check.lint(proto, [])["problems"] if p.startswith("app.js")} == {
            "external URL", "network call", "code from strings"}
        (proto / "app.js").write_text("const routes = {'/dashboard': 1, 'settings': 2, 'ghost': 3};\n", encoding="utf-8")
        assert check.lint(proto, ["Dashboard"])["ok"] is True
        try:
            check.browser()
        except FileNotFoundError:
            return
        assert check.shots(proto, ["/settings"], ws) == [".hve/asks/20261021-1200-x/loop/evidence/prototype/settings.png"]


if __name__ == "__main__":
    test_init_rejects_bad_feature_lists()
    test_init_in_existing_repo()
    test_tracker_reports_status_evidence_and_manual_check()
    test_amend_appends_without_changing_locked_features()
    test_loop_commits_flips_and_queues()
    test_rules_stuck_then_spec()
    test_rules_circular_and_cap()
    test_rules_tool_retrieval_environment()
    test_parallel_options_auto_and_human_choice()
    test_parallel_options_same_failure_escalates()
    test_ask_mode_keeps_loop_files_in_the_ask_folder()
    test_no_fallback_patterns()
    test_loop_guard()
    test_guard_waiver()
    test_loop_guard_awareness_mode()
    test_error_guard_pauses_after_three_failures_in_a_row()
    test_module_guard()
    test_prototype_check()
    print("test_loop: OK")
