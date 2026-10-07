"""Tests of tools/observe/trajectory.py: context-rot detection and context growth on synthetic metrics rows."""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "observe"))
from trajectory import context_rot, growth  # noqa: E402


def rows(outcomes: list[bool], prompt_sizes: list[int]) -> list[dict[str, Any]]:
    """Return one main-conversation row per tool outcome, with the given prompt size per call."""
    return [{"turn_id": f"t{i}", "subagent_session": None, "tool_name": "read_file", "tool_ok": ok, "prompt_tokens": size}
            for i, (ok, size) in enumerate(zip(outcomes, prompt_sizes))]


def test_rot_fires_on_degraded_session() -> None:
    """Tool success that falls from 100% to 50% is flagged at the first window below 80%."""
    result = context_rot(rows([True] * 20 + [True, False] * 10, [1000] * 40))
    assert result["rot"] is True and result["baseline"] == 1.0 and result["from_tool_call"] == 26, result


def test_rot_quiet_on_healthy_and_short_sessions() -> None:
    """A steady session is not flagged; fewer than 20 tool calls are not checked."""
    assert context_rot(rows([True, True, True, False] * 10, [1000] * 40))["rot"] is False
    assert context_rot(rows([True] * 5, [1000] * 5))["checked"] is False


def test_growth_ratio() -> None:
    """Growth reports first, last, peak, and last/first prompt size of the main conversation."""
    g = growth(rows([True] * 4, [1000, 4000, 2500, 3000]))
    assert (g["first"], g["last"], g["peak"], g["ratio"]) == (1000, 3000, 4000, 3.0), g


if __name__ == "__main__":
    test_rot_fires_on_degraded_session()
    test_rot_quiet_on_healthy_and_short_sessions()
    test_growth_ratio()
    print("test_trajectory: OK")
