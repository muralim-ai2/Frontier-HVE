# Product Manager

`HVE product-manager` turns a product idea into a validated PRD and a backlog. It does not write code, technical designs, test strategies or UX designs; use `Frontier Lite` for those.

## What it does

1. **Discovery.** If the problem, success metric, persona, constraints or stack are unclear, it asks 2-4 questions at once. Otherwise it records unknowns as `TBD` open questions.
2. **Research.** Up to 3 parallel sub-agents research prior art, standards and compliance, and user evidence, with cited URLs (`web/fetch`).
3. **Council.** For epic-scale or contested work, or AI-bearing requirements, the hidden `HVE council` agent challenges the scope three times: analyst, strategist and skeptic. Each call requests a model from a different vendor (see below).
4. **PRD.** Written in the workspace's configured PRD template through the template manager (see [Templates](Templates.md)): `init` for a new PRD, edit in place plus `register` for an existing one. It is validated before handoff, and the Stop hook blocks an invalid PRD once. Requirements get stable IDs (`FR-n`, `NFR-n`, `AC-n`).
5. **Backlog.** Never in the PRD. The agent asks where it goes:

| Target | What happens |
|---|---|
| Local JSON | `docs/product/BACKLOG-<slug>.json`, checked by `python <tools>/backlog/backlog.py validate <file>` |
| Azure DevOps | The agent shows the backlog; the **Create work items in Azure DevOps** handoff opens `HVE azure-devops`, which maps types to the project's process and writes only the items you tick (see [Adapters](Adapters.md) for setup) |
| GitHub | The agent shows the planned issues, creates only the ones you tick through the GitHub MCP server, and links children as sub-issues |

For Azure DevOps and GitHub, a ticked item's parent and dependencies must also be ticked or already exist, and they are created first so every link has a target.

6. **Report.** PRD path, validation exit codes, sources, open questions, backlog ids or links, PRD requirements without a backlog item, and the council model table.

`<tools>` is `tools` in this repository or `<installed-extension>/runtime/tools` for extension users.

## Skill loading

The prompt hook sets `HARNESS_REQUIRED_SKILLS: prd`. The skill loader reserves the `prd` skill (about 1.2K tokens) and one slot before ranking optional skills, whatever the prompt's categories; task-matching skills such as `web-research` fill the rest of the 2K budget. Missing, ambiguous (for example a workspace skill also named `prd`), disallowed or over-budget required skills are errors that name the matching paths; the loader does not bypass the read gate or exceed the budget. Other agents keep task-ranked loading.

## Backlog file (local JSON)

```json
{"version": 1, "prd": "docs/product/PRD-leave-portal.md", "items": [
  {"id": "E1", "type": "epic", "parent": null, "title": "...", "persona": "...", "problem": "...", "outcome": "...",
   "scope": "...", "non_goals": ["..."], "acceptance": [{"given": "...", "when": "...", "then": "..."}],
   "verification": "...", "dependencies": [], "priority": "P0", "priority_rationale": "...", "requirements": ["FR-1"]}
]}
```

The validator checks:
- exact fields, integer version `1`, a string PRD path and non-empty text;
- the hierarchy: an epic has no parent, a feature's parent is an epic, a story's parent is a feature;
- unique string ids and known string dependency/parent references, with no cycles;
- at least one non-goal and one complete Given/When/Then criterion per item;
- every requirement ID exists in the PRD.

It exits 1 with the errors. A valid backlog also lists `uncovered`: the PRD's `FR`/`NFR` IDs that no item delivers. They are reported, not errors, because a PRD can sequence requirements for later; the agent explains each one. The field mapping to Azure DevOps (per process: Agile, Scrum, CMMI, Basic) and GitHub is in the `prd` skill (`skills/admitted/prd/references/pbi-examples.md`).

## GitHub setup

Add the GitHub MCP server under the name `github` (MCP: Add Server in VS Code; remote URL `https://api.githubcopilot.com/mcp/`) and sign in. The agent uses `search_issues`, `issue_read`, `issue_write` and `sub_issue_write`. It confirms the target repository, searches by title/outcome in that repository, inspects candidates and reuses matching issue numbers rather than creating duplicates. If those tools are missing, it says so and stops. It never creates labels or issue types.

## Council models

VS Code lets an agent request a model per sub-agent call. A request above the session model's cost tier is refused, and the refusal lists the allowed models. The agent then picks another vendor from that list. If none is left, it runs the lens without an explicit model and labels it "host-selected; actual model unconfirmed". The host may use Auto (`chat.subagents.defaultToAuto`), so this is not proof that the session model ran. The report table states, per lens:
- the requested model;
- whether it ran or was refused;
- whether telemetry confirmed it.

Only the Copilot OpenTelemetry export can confirm which model answered; otherwise the report says "not confirmed".

## Limits

- Structural validation does not prove requirement quality or approval.
- It is the only HVE agent with outbound web access (`web/fetch`); sources must be cited.
- Not exported to Claude Code, Cursor or Codex yet.
- Not verified live yet; see `tracker.json`.
