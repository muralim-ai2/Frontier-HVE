"""End-to-end tests of hooks/profile_detector.py and hooks/compaction.py on synthetic hook payloads in a temp folder."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
EMPTY_PROFILE = {"prompt_style": None, "wants_evidence": None, "verbosity": None, "output_format": None, "technical_level": None,
                 "bloat_triggers": []}


def make_root(tmp: str, profile: dict[str, Any]) -> Path:
    """Return a temp workspace with the hooks, .hve/runs and the given .hve/user_profile.json."""
    root = Path(tmp)
    (root / "hooks").mkdir()
    for hook in ("profile_detector.py", "compaction.py", "graph_refresh.py", "budget.py", "interventions.py", "hve_paths.py"):
        shutil.copy(REPO / "hooks" / hook, root / "hooks")
    (root / ".hve" / "runs").mkdir(parents=True)
    (root / ".hve" / "user_profile.json").write_text(json.dumps(profile), encoding="utf-8")
    return root


def profile_of(root: Path) -> dict[str, Any]:
    """Return the workspace's saved profile."""
    return json.loads((root / ".hve" / "user_profile.json").read_text(encoding="utf-8"))


def fire(root: Path, hook: str, payload: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run one hook with a payload on stdin, from the workspace root like VS Code does."""
    return subprocess.run([sys.executable, str(root / "hooks" / hook)], input=json.dumps(payload), capture_output=True, text=True,
                          cwd=root)


def output(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """Return the hook's JSON stdout after checking it exited 0."""
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_bloat_request_is_challenged_and_learned() -> None:
    """A prompt asking for markdown tracking and an endless loop gets a challenge and is recorded in the profile."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp, EMPTY_PROFILE)
        message = output(fire(root, "profile_detector.py", {"hook_event_name": "UserPromptSubmit",
                                                            "prompt": "Create markdown files to track progress and keep going until it's all done."}))
        assert "Markdown state files" in message["systemMessage"] and "open-ended loop" in message["systemMessage"], message
        profile = profile_of(root)
        assert profile["bloat_triggers"] == ["infinite_loop", "md_state_files"], profile
        assert profile["prompt_style"] == "simple"


def test_preference_persists_into_next_session() -> None:
    """Session 1 learns 'concise' and 'tables'; session 2 starts with them injected; a neutral prompt prints nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp, EMPTY_PROFILE)
        assert fire(root, "profile_detector.py", {"hook_event_name": "SessionStart", "source": "new"}).stdout == ""
        neutral = fire(root, "profile_detector.py", {"hook_event_name": "UserPromptSubmit", "prompt": "Show the results as a table, keep it short."})
        assert neutral.returncode == 0 and neutral.stdout == "", neutral.stderr
        context = output(fire(root, "profile_detector.py", {"hook_event_name": "SessionStart", "source": "new"}))
        text = context["hookSpecificOutput"]["additionalContext"]
        assert "Keep replies short." in text and "Prefer tables" in text, text


def test_technical_level_from_role() -> None:
    """'I'm the CTO' sets executive, 'as a TPM' then sets partial, and the next session starts with the level's guidance."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp, EMPTY_PROFILE)
        fire(root, "profile_detector.py", {"hook_event_name": "UserPromptSubmit", "prompt": "I'm the CTO, build me a dashboard."})
        assert profile_of(root)["technical_level"] == "executive"
        fire(root, "profile_detector.py", {"hook_event_name": "UserPromptSubmit", "prompt": "As a TPM I need a status view."})
        context = output(fire(root, "profile_detector.py", {"hook_event_name": "SessionStart", "source": "new"}))
        assert "partially technical" in context["hookSpecificOutput"]["additionalContext"], context


def test_over_specified_prompt_and_invalid_profile() -> None:
    """A prompt over 500 tokens marks the user as an over-specifier; an out-of-schema profile value fails the hook."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp, EMPTY_PROFILE)
        fire(root, "profile_detector.py", {"hook_event_name": "UserPromptSubmit", "prompt": "Build a site. " * 200})
        assert profile_of(root)["prompt_style"] == "over_specifier"
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp, {**EMPTY_PROFILE, "verbosity": "chatty"})
        result = fire(root, "profile_detector.py", {"hook_event_name": "SessionStart", "source": "new"})
        assert result.returncode != 0 and "verbosity='chatty'" in result.stderr, result.stderr


def test_subagent_start_gets_return_cap() -> None:
    """Every sub-agent starts with the instruction to return a summary under 2,000 tokens."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp, EMPTY_PROFILE)
        context = output(fire(root, "compaction.py", {"hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "creator"}))
        assert "under 2,000 tokens" in context["hookSpecificOutput"]["additionalContext"]
        assert "exactly one role" in context["hookSpecificOutput"]["additionalContext"]


def test_graph_follows_project() -> None:
    """The served graph is empty without code, gains nodes after a code file appears, and is not rebuilt when nothing changed."""
    bin_dir = subprocess.run(["uv", "tool", "dir", "--bin"], capture_output=True, text=True, check=True).stdout.strip()
    env = {**os.environ, "PATH": bin_dir + os.pathsep + os.environ["PATH"]}
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp, EMPTY_PROFILE)
        graph = root / ".hve" / "outputs" / "harness" / "graph" / "graph.json"

        def run(event: str) -> subprocess.CompletedProcess[str]:
            """Run graph_refresh.py for one hook event."""
            return subprocess.run([sys.executable, str(root / "hooks" / "graph_refresh.py")],
                                  input=json.dumps({"hook_event_name": event}), capture_output=True, text=True, env=env, cwd=root)

        assert run("SessionStart").returncode == 0
        assert json.loads(graph.read_text(encoding="utf-8"))["nodes"] == []
        project = root / ".hve" / "outputs" / "harness" / "current"
        (project / "node_modules" / "x").mkdir(parents=True)
        (project / "node_modules" / "x" / "index.js").write_text("function junk() {}\n", encoding="utf-8")
        (project / "lib.ts").write_text("export function hexToRgb(h: string): number[] { return [0, 0, 0]; }\n"
                                        "export function contrast(a: string): number { return hexToRgb(a)[0]; }\n", encoding="utf-8")
        result = run("PostToolUse")
        assert result.returncode == 0, result.stderr
        labels = sorted(n["label"] for n in json.loads(graph.read_text(encoding="utf-8"))["nodes"])
        assert labels == ["contrast()", "hexToRgb()", "lib.ts"], labels
        before = graph.stat().st_mtime_ns
        assert run("PostToolUse").returncode == 0 and graph.stat().st_mtime_ns == before
        assert not (project / "graphify-out").exists()


def fire_budget(root: Path, event: str, minutes: float, env: dict[str, str], tool_use_id: str = "") -> subprocess.CompletedProcess[str]:
    """Run budget.py for an event the given minutes after 08:00 UTC."""
    stamp = f"2026-10-06T08:{int(minutes):02d}:{round(minutes % 1 * 60):02d}+00:00"
    payload = {"hook_event_name": event, "session_id": "s-1", "timestamp": stamp, "tool_use_id": tool_use_id or f"t{minutes}"}
    return subprocess.run([sys.executable, str(root / "hooks" / "budget.py")], input=json.dumps(payload),
                          capture_output=True, text=True, env={**os.environ, **env}, cwd=root)


def test_budget_nudges_then_stops() -> None:
    """Stop mode, 10 minutes: silent early, a wrap-up nudge at 8.5 min, a final-summary nudge at 10.5, a hard stop at 11.5."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp, EMPTY_PROFILE)
        env = {"HARNESS_BUDGET_MIN": "10", "HARNESS_BUDGET_ON_END": "stop"}
        assert fire_budget(root, "SessionStart", 0, env).returncode == 0
        assert fire_budget(root, "PreToolUse", 1, env).stdout == ""
        assert "left" in output(fire_budget(root, "PreToolUse", 8.5, env))["hookSpecificOutput"]["additionalContext"]
        assert "used up" in output(fire_budget(root, "PreToolUse", 10.5, env))["hookSpecificOutput"]["additionalContext"]
        stop = output(fire_budget(root, "PreToolUse", 11.5, env))
        assert stop["continue"] is False and stop["hookSpecificOutput"]["permissionDecision"] == "deny", stop


def test_budget_asks_user_to_continue() -> None:
    """Ask mode, 15 minutes: after the budget each tool call asks the user; an allowed call adds 15 minutes, so 20 min is quiet again."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp, EMPTY_PROFILE)
        env = {"HARNESS_BUDGET_MIN": "15", "HARNESS_BUDGET_ON_END": "ask"}
        assert fire_budget(root, "SessionStart", 0, env).returncode == 0
        assert "left" in output(fire_budget(root, "PreToolUse", 14, env))["hookSpecificOutput"]["additionalContext"]
        asked = output(fire_budget(root, "PreToolUse", 15.5, env, "x1"))["hookSpecificOutput"]
        assert asked["permissionDecision"] == "ask" and "15 more minutes" in asked["permissionDecisionReason"], asked
        assert output(fire_budget(root, "PreToolUse", 16, env, "x2"))["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert fire_budget(root, "PostToolUse", 16.5, env, "x1").returncode == 0
        assert fire_budget(root, "PreToolUse", 20, env).stdout == ""
        assert "left" in output(fire_budget(root, "PreToolUse", 28.5, env))["hookSpecificOutput"]["additionalContext"]
        state = json.loads((root / ".hve" / "runs" / "s-1.budget.json").read_text(encoding="utf-8"))
        assert state["extensions"] == 1 and state["budget_ms"] == 30 * 60_000, state


if __name__ == "__main__":
    test_bloat_request_is_challenged_and_learned()
    test_preference_persists_into_next_session()
    test_technical_level_from_role()
    test_over_specified_prompt_and_invalid_profile()
    test_subagent_start_gets_return_cap()
    test_graph_follows_project()
    test_budget_nudges_then_stops()
    test_budget_asks_user_to_continue()
    print("test_hooks: OK")
