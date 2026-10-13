# Agents

## Agents in the extension

Pick these in a new chat with Session Target **Local**. They run on the model you pick.

| Agent | Use it for | Guard hooks | Needs Python |
|---|---|---|---|
| `HVE creator` | Build software: verified feature loop, then output evaluation ([Evaluation](Evaluation.md)) | loop, module, prototype, template, skill, profile, compaction, choice | Yes |
| `HVE creator-flow` | Build through the graph workflow (Designer → ... → Maintainer) | as creator; stage agents add the stage guard | Yes |
| `HVE creator-github` | Product work on GitHub: stacked branches, options you pick, PRs pushed only when you tick them | as creator | Yes |
| `HVE product-manager` | Research, PRD in the configured template, backlog ([Product Manager](Product-Manager.md)) | template (PRD only), skill (`prd` always loaded), profile, compaction | Yes |
| `HVE single` | One agent with file, search and terminal tools | template | Yes |
| `HVE minimal` | Baseline answer, no tools | none | No |
| `HVE skill-evaluator` | Onboard a skill with evidence ([Skills](Skills.md)) | none | Yes (tools) |
| `HVE azure-devops` | Azure DevOps work items, PRs and builds ([Adapters](Adapters.md)) | none | Yes (MCP setup command) |

Hidden helpers are called by the agents above, not by you: `HVE council` and `HVE evaluation-reviewer` (read-only reviewers), `HVE flow-*` (stages), `HVE skill-worker` and `HVE skill-judge`.

The repository's `.github/agents/` holds the research arms (`minimal`, `single`, `creator`, `creator-flow`, `creator-github`): pinned model, time budget, metrics and Graphify, working in `.hve/outputs/<mode>/current/`. They exist for `tools/observe/bench.py` and differ from the product agents on purpose.

## Guardrails

| Guard | File | When | Enforces |
|---|---|---|---|
| loop | `hooks/loop_guard.py` | before/after tools, stop | `feature_list.json`, `progress.txt` and `.harness/` change only through `loop.py`; pushes only for ticked PRs; stop on escalation; a victory check before stopping |
| module | `hooks/module_guard.py` | after edits | No file over 500 lines; the agent proposes a split |
| prototype | `scripts/guardrail.py` | after tools | Flags code over 5,000 lines, files over 20 MB, non-enterprise components and self-built infrastructure, and names the experts to involve |
| template | `hooks/template_guard.py` | session start, prompt, stop | Requested PRDs, technical designs and test strategies come from the configured template and validate before the agent may finish |
| skill | `hooks/skill_loader.py` | prompt, tools | Loads the best library skills within 10 skills / 2,000 tokens; blocks other library skills |
| profile | `hooks/profile_detector.py` | session start, prompt | Applies learned preferences; challenges token-wasteful requests |
| compaction | `hooks/compaction.py` | sub-agent start | Sub-agents return short summaries, not raw tool output |
| choice | `scripts/choice_recorder.py` | after ask-questions | Records your ticks (options, manual checks, PRs to push) |
| stage | `hooks/flow_guard.py` | stage agent stop | A flow stage may not finish without moving the flow along an edge |
| no fallback | `hooks/no_fallback.py` | git pre-commit (set by `loop.py init`) | Rejects swallowed errors and TODOs in committed code |

Every deny, block or stop is logged to `.hve/runs/<session>.interventions.jsonl`.

## Onboard an agent

Until agent composition lands (tracker `N31`), a new agent is a copy: later changes to `HVE creator` do not reach it.

1. Copy the closest agent in `extension/agents/`: `hve-creator.agent.md` for agents that build, `hve-product-manager.agent.md` for agents that write documents. Name it `hve-<name>.agent.md` with `name: HVE <name>`.
2. Write hook and tool commands as `python "{{RUNTIME}}/<path>.py"`. Never write an absolute path or `python3`: rendering fills in the runtime folder and this machine's Python launcher, and drops the hooks with a warning when Python is missing. Hidden helpers get `user-invocable: false`.
3. Keep the hooks the agent's work needs (table above). For deliverables set `HVE_TEMPLATE_TYPES` on the template guard; for a skill that must always load set `HARNESS_REQUIRED_SKILLS` on the skill loader.
4. If its output should be evaluated, copy the "Output reflection" section and, for other rubrics, add `evaluation/<name>.eval.json` (validated by `tools/evaluation/contract.py`).
5. Add any new runtime file to `FILES` in `extension/build.py`; the build fails when an agent references a runtime file it did not copy.
6. Update `tests/test_extension.py` (agent count and an assertion on the new agent's hooks) and run it.
7. Build and package ([Install](Install.md#build-the-vsix-maintainers)), bump the version in `extension/package.json`, install and reload, run one chat, then check it with `provenance.py <agent file> latest --require <components>`.
8. Record the decision in `research/decisions/decision_log.md` and a check for the user in `tracker.json`.
