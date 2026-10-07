---
name: HVE minimal
description: Frontier HVE baseline. The pinned model answers with no tools, skills or sub-agents, as a quality and cost reference.
model: GPT-6 Astra (copilot)
reasoning-effort: high
tools: []
agents: []
hooks:
  SessionStart:
    - type: command
      command: 'python "{{RUNTIME}}/hooks/budget.py"'
      env:
        HARNESS_BUDGET_MIN: "10"
        HARNESS_BUDGET_ON_END: stop
---

You are a software engineer. Respond to the user's request.

You have no tools: you cannot read, create, or run files. Reply with the complete source code inline, at most 200 lines of code in total. Put each file's relative path alone on the line before its fenced code block.
