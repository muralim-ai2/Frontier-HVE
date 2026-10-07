---
name: minimal
description: Baseline mode. Raw prompt to the pinned model with no tools, skills, MCP, or sub-agents.
additional-details: >-
  Does not loop by design. Copilot still offers its built-in tool_search, so
  tool hooks are attached to record any such calls (decision D-009).
model: GPT-6 Astra (copilot)
reasoning-effort: high
tools: []
agents: []
hooks:
  SessionStart:
    - type: command
      command: python hooks/budget.py
      env:
        HARNESS_BUDGET_MIN: "10"
        HARNESS_BUDGET_ON_END: stop
  PreToolUse:
    - type: command
      command: python hooks/metrics.py
      env:
        HARNESS_MODE: minimal
  PostToolUse:
    - type: command
      command: python hooks/metrics.py
      env:
        HARNESS_MODE: minimal
  Stop:
    - type: command
      command: python hooks/metrics.py
      env:
        HARNESS_MODE: minimal
---

You are a software engineer. Respond to the user's request.

You have no tools: you cannot read, create, or run files. Reply with the complete source code inline, at most 200 lines of code in total. Put each file's relative path alone on the line before its fenced code block.
