---
name: check-context-load
description: Measure what loads into every request before the user types - discoverable skills, always-on instructions, agent prompt, MCP tools - and warn about skill and instruction bloat with fixes.
---

# Check context load

Run from the workspace root; `<tools>` is the harness tools folder named in your agent instructions.

1. Run `python <tools>/skills/context_load.py --agent "<your agent name>"`. Add `--context-tokens <n>` when you know the selected model's context window; otherwise the report shows the share for 128K, 200K and 1M windows.
2. Report in a short table:
   - always-on tokens and their share of the context window;
   - the split: skills (name and description of every discoverable skill), always-on instructions (`copilot-instructions.md`, `AGENTS.md`, `*.instructions.md` with `applyTo: **`), the agent prompt, MCP tool schemas (an estimate per server);
   - the top contributors;
   - duplicate skills (same name, or very similar descriptions) and skills never measured with a paired evaluation.
3. If there are warnings (the load grew noticeably since the last check, or takes a large share of the window), state the cost per request and the fixes: move rarely used skills into the Frontier HVE library (loaded per task within a budget, evaluated with `HVE skill-evaluator`), merge duplicates, narrow `applyTo`, disable unused plugins or MCP servers.
4. Change nothing yourself; the user decides. VS Code's own system prompt and built-in tools are not counted.

The report is saved to `.hve/context_load.json`; the next check compares against it.
