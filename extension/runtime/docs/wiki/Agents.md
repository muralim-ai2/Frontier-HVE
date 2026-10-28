# Agents

## Agents in the extension

Pick these in a new chat. In VS Code the extension's agents and their agent-scoped hooks appear with Session Target **Local**; for Copilot (CLI or the VS Code Copilot harness), Claude Code, Codex, Cursor and the Copilot cloud agent run **Frontier HVE: Install for other harnesses** ([Adapters](Adapters.md)).

Since 0.15.0 the picker shows only the delivery agents (D-055), and since 0.15.3 `HVE creator` again (D-058). They ask VS Code for a top model in this order: GPT-6 Astra, Gemini 4 Argon, Claude Fable 5, Claude Opus 5.5 (the first one available is used), with `reasoning-effort: high`. VS Code does not apply `reasoning-effort` from agent files (D-020), so also set the effort to high in the model picker. Every deliverable a user sees ends with the **wow uplift** loop (`wow-uplift` skill): a top-model judge (`HVE uplift-judge`) names two or three targeted UI/UX or presentation improvements, the agent applies them, re-runs the checks and captures before and after images, and the judge looks again, up to 3 rounds or until it says done. Any deck follows the `presentation-deck` skill (NorthStar style, discovery form, python-pptx build, lint and previews); when the user picks web slides it routes to `frontend-slides` (animated single-file HTML decks, D-059).

| Agent | Use it for | Guard hooks | Needs Python |
|---|---|---|---|
| `Frontier HVE Auto` (`hve-e2e`, autonomous; formerly Frontier E2E Delivery) | End-to-end delivery along a lifecycle (SDLC, team delivery, consulting or a plugin/workspace one), pausing only after the milestones you tick in the plan; build stages run as feature loops with their persona. E.g. a leave app from discovery to release with one review after design | as creator | Yes |
| `Frontier HVE Collab` (`hve-agile`, collaborative; formerly Frontier BYOW) | Come in at any stage and run one, several or all stages of `team-delivery` with the right persona, each visit its own ask with a project ledger; a pack lifecycle can run in place of a stage; or sprints along your team's agile overlay. E.g. data architecture and build with the Oracle pack now, a design review next week | as creator | Yes |
| `Frontier Prototype Creator` (`hve-prototype`) | Fast UI/UX clickthrough (HTML or TypeScript) in the ask folder's `prototype/`, self-checked (`tools/prototype/check.py`) with a screenshot per screen; no loop; output evaluation on request. E.g. three screens of a leave request flow for a stakeholder demo | loop (safety only) | Yes |
| `HVE creator` | Build software: verified feature loop, then output evaluation ([Evaluation](Evaluation.md)) | loop, module, error, prototype, template, skill, profile, compaction, choice | Yes |

Hidden in the extension (`user-invocable: false`): the agents below still ship and can be called as sub-agents, but you do not pick them. In this repository the research arms in `.github/agents/` (`minimal`, `single`, `creator`, `creator-flow`, `creator-github`) are the user-invocable versions.

| Agent | Use it for | Guard hooks | Needs Python |
|---|---|---|---|
| `HVE creator-flow` | Build through the graph workflow (Designer → ... → Maintainer) | as creator; stage agents add the stage guard | Yes |
| `HVE creator-github` | Product work on GitHub: stacked branches, options you pick, PRs pushed only when you tick them | as creator | Yes |
| `HVE product-manager` | Research, PRD in the configured template, backlog ([Product Manager](Product-Manager.md)); the product manager persona of Auto and Collab | template (PRD only), skill (`prd` always loaded), profile, compaction | Yes |
| `HVE single` | One agent with file, search and terminal tools | template | Yes |
| `HVE minimal` | Baseline answer, no tools | none | No |
| `HVE skill-evaluator` | Onboard a skill with evidence ([Skills](Skills.md)) | none | Yes (tools) |
| `HVE azure-devops` | Azure DevOps work items, PRs and builds ([Adapters](Adapters.md)) | none | Yes (MCP setup command) |

Other hidden helpers: `HVE council` and `HVE evaluation-reviewer` (read-only reviewers), `HVE uplift-judge` (read-only wow-uplift judge on a top model), `HVE flow-*` (stages), `HVE engineer` (one feature to its check), `HVE skill-worker` and `HVE skill-judge`.

**Tool lists.** Working agents have no `tools:` list, so they see every tool the harness offers, including your MCP servers. Only `HVE council`, `HVE evaluation-reviewer`, `HVE uplift-judge`, `HVE flow-architect`, `HVE flow-maintainer` (read-only), `HVE skill-judge`, `HVE skill-worker` (blind) and `HVE minimal` (baseline) keep a fixed list. Token cost stays visible instead of being capped: the ask contract records each harness's MCP servers with an estimated tool-definition load (1,500 tokens per server, warning over 6,000; `skills/categories.json` → `context_load`), and the plan and chat flag it.

## Ask contract (every agent, every harness)

Every working agent starts with `lifecycle.py where .hve/asks/request.md`: it prints the workspace's project, the open ask with its paths, and a verdict (`continue`, `new-ask`, `new-workspace` or `new-project`) that the agent confirms with you in one form. To continue it runs `lifecycle.py open <ask>`; for a new ask, `lifecycle.py contract <lifecycle> <slug> "<agent>" .hve/asks/request.md` (`direct` for agents without a lifecycle; `+<skill>` requires a skill, as `HVE product-manager` does with `+prd`). Both are terminal commands, so they work with or without hooks. One workspace holds one project; each ask gets its own timestamped folder (UTC), so nothing from one ask clutters the workspace root or another ask:

```
.hve/project/                      project.json, feature_list.json (+ feature_list.add.json), progress.txt, tracker.json, state.json
.hve/asks/
  active.json                      the open ask
  <YYYYMMDD-HHMM>-<slug>/
    request.md  contract.json  plan.md  provenance.md  prototype/
    loop/                          attempts/, evidence/<feature>/, prs/, choices/, checks/, tool_log.jsonl
```

The contract prints `paths` (ask, plan, loop, evidence, project, feature list, feature list add) and `project` (goal, asks, features, and `loop`: `init` for the first ask, `amend` afterwards). The skill loader repeats the open ask's paths on every prompt and the compaction hook gives them to every sub-agent, so agents never search for `plan.md`. `.hve/` is git-ignored, so the loop's commits carry a read-only copy of the locked checks: `[init]` and `[amend]` list each `name: verify`, `[progress]` names the check that passed. Each locked feature records the ask that added it; an ask's tasks and report count only its own features. Checks write screenshots and logs to `$HVE_EVIDENCE/<feature>/`, which `loop.py` and the output evaluation set to the open ask's `loop/evidence/`. With no ask open in a project (the research arms, `bench.py`), the loop keeps its old layout: loop files in the project root and state in `.harness/`. `contract.json` maps:

| Field | Holds |
|---|---|
| `skills` | Every relevant library skill (reason, status, tokens), their total, `over_budget`, the `suggested` set within the guideline and the user's `choice` |
| `stages` | Milestones with agent, skills, plugin skills, templates and exit gate |
| `personas` | Who owns which stages |
| `tasks` | The features this ask added to the project's feature list (`lifecycle.py tasks-sync`) with milestone, persona, skills and pass state |
| `environment` | Harness, MCP servers per harness with tool load, Frontier HVE hook files, plugin skills |
| `delegations`, `reported` | Each sub-agent brief and the `SKILLS-USED` line it returned |
| `previous_ask` | The ask open before this one, with the new-workspace recommendation when this ask starts a different project |
| `checklist` | Your sign-off of each option (`opt:evaluation`), milestone (`stage:<name>`) and task (`task:<feature>`): value, note, and whether it came from the agent's form or a tick in `plan.md` ([Ways of working](Ways-of-Working.md#what-you-are-asked-and-why)) |

When another ask is still open (milestones not done, or an evaluation you asked for not run), the new ask still gets its own folder; the contract reports it as `previous_open` and the other chat is told once to run `lifecycle.py open <its ask>` ([Parallel chats](Ways-of-Working.md#parallel-chats)).

**Skills per ask (D-056).** The contract shortlists every relevant library skill, with no cap, ranked by relevance (shared categories plus rare shared words); all of them load when the shortlist fits the guideline of 10 skills and 32,000 tokens. Over it (say 40 skills), the agent scores each shortlisted skill 0-10 for this ask across its stages, judging from its description, and runs `lifecycle.py skills score <scores.json>`: the shortlist is re-ranked by score and the required skills plus the top-scored, up to 10, become the suggested set. The agent shows you the shortlist size and the suggested skills with scores, reasons and tokens, and asks once: suggested top 10, all, or named (`lifecycle.py skills suggested|all|<a,b>`). Scores and reasons show in `plan.md`. The choice stops the skill loader adding prompt-ranked skills for the rest of the ask. The provenance report adds the skill load and the prompt cache: cache reads against prompt tokens when the session has metrics rows (the research arms' metrics hook with Copilot OTel), otherwise "not measured".

**Different projects.** One workspace holds one project (`.hve/project/project.json`, started by the first ask). When a prompt starts a different project (a different kind of deliverable, for example a War of the Worlds app then a revenue-forecast presentation: `sdlc` against `document`; or a new build sharing almost no subject words with the project's goal, asks and features), `where`, the skill loader (once per ask) and `contract` recommend a new workspace. It never blocks; if you stay, the agent opens a new ask. `lifecycle.py shift "<prompt>"` shows the verdict.

`plan.md` carries a generated skills-and-tools block (kept out of the plan check's hash). Sub-agent prompts start with `lifecycle.py brief "<persona>" [task=<feature>|stage=<stage>]`: skills to read, plugin skills, MCP servers, rules and the `SKILLS-USED` reply line; the parent records it with `lifecycle.py used`. `lifecycle.py report` adds a recommended-against-used table (skills read by hook or self-reported, personas delegated, tasks, MCP servers called, hook files) to `provenance.md`. `lifecycle.py close` stops workspace and user-level hooks from acting in the workspace; `lifecycle.py open <ask-id>` reopens an ask and prints its paths, current milestone and open items.

## Lifecycles

`Frontier HVE Auto` and `Frontier HVE Collab` start with `tools/loop/lifecycle.py route <request-file>` (expertise packs routed by the request, then lifecycles with matched packs' overlays first), show the stages and ask which lifecycle, which stages to skip and, when packs match, which packs to use; the practitioner's call wins. A stage with `loop: true` is a feature loop the orchestrator runs itself, each feature delegated to the stage's agent (`HVE engineer`, `HVE db-engineer`, `HVE ui-engineer`, `HVE test-engineer`, `HVE devops-engineer`). Lifecycles are JSON files with stages (goal, agent, library skills, plugin skills, templates, exit gate, when to skip, and optionally `loop`, `evidence` checked before the stage is done and a capped `rework` step back):

| Source | Folder | Wins over |
|---|---|---|
| Built-in | `templates/lifecycles/` (`sdlc`, `agile-scrum`, `team-delivery`, `consulting-delivery`, `document`, `direct`) | - |
| Plugin | `plugins/<name>/lifecycles/` (folders without `hve-plugin.json`) | built-in |
| Workspace | `.hve/lifecycles/` | built-in and plugin |
| Expertise pack | `<pack>/lifecycles/`, named `<pack>:<name>` ([Expertise packs](Plugins.md)) | - (own names) |

`lifecycle.py contract` writes the ask's `contract.json` (expected agent, skills and templates per stage, plus the fields above); `stage` records each stage's status with a one-line note; the skill loader loads and allows the current stage's skills; `lifecycle.py report <session>` (in `tools/loop/ask_report.py`) writes the ask's `provenance.md` with expected against used skills and authored templates, gaps in done stages, plan revisions and sync state, guard trips and waivers, and every decision. `tools/observe/provenance.py` adds the same facts as its `contract` component (failed on gaps or an unsynced plan) and a `guards` summary for every agent.

The repository's `.github/agents/` holds the research arms (`minimal`, `single`, `creator`, `creator-flow`, `creator-github`): pinned model, time budget, metrics and Graphify, working in `.hve/outputs/<mode>/current/`. They exist for `tools/observe/bench.py` and differ from the product agents on purpose.

## Personas, Collab stage entry and Auto gates

**Personas.** `templates/personas/catalog.json` lists 18 personas. Two are existing agents: TPM is `HVE product-manager` and Engineer is `HVE engineer`. The other 16 are rendered by `tools/loop/personas.py` from one template per kind when `extension/build.py` runs, so edit the catalog, not the generated `hve-<id>.agent.md` files:

| Kind | Personas | Works how |
|---|---|---|
| builder | `HVE db-engineer`, `HVE devops-engineer`, `HVE test-engineer`, `HVE ui-engineer` | One feature at a time inside the feature loop, to its locked check |
| designer | `HVE data-scientist`, `HVE solution-architect`, `HVE db-architect`, `HVE security-architect`, `HVE test-architect`, `HVE ux-designer` | One stage's document in the ask folder (through the template manager when the stage names a template), decisions and risks explicit |
| reviewer | `HVE code-reviewer`, `HVE architecture-reviewer`, `HVE security-reviewer`, `HVE ux-reviewer`, `HVE test-reviewer`, `HVE product-reviewer` | `<ask>/<stage>/review.md` with a verdict and findings by severity; never edits the work |

Each persona has a goal, a focus (what it checks), library and plugin skills, and keywords. `personas.py match "<text>"` ranks personas for a request, and the brief tells the sub-agent its role. Expertise packs extend a persona's stage with their skills, knowledge and `<pack>:<agent>` agents. MCP servers configured in the workspace are listed in every brief.

**Team delivery.** The `team-delivery` lifecycle has one stage per persona: requirements, ux-design, solution-architecture, security-architecture, data-architecture, architecture-review, data-build, build, ui-build, data-science, test-strategy, test, devops, and the code, security, UX, test and product reviews.

**Frontier HVE Collab** lets people come in at any stage:

1. `lifecycle.py ledger` shows every stage of the project as done, active or not started, with the ask that did it.
2. The user picks the stages for this visit, or all remaining stages.
3. Each visit is a new ask: `lifecycle.py contract team-delivery <slug> "Frontier HVE Collab" <request> only=<stage,stage>`.
4. When an expertise pack has a lifecycle for the stage (for example Oracle migration for data-architecture or data-build), it runs in place of the stage plan: `contract oracle-offering:oracle-migration <slug> "Frontier HVE Collab" <request> for=team-delivery:data-build @oracle-offering`. The ledger then shows the stage delivered through that pack lifecycle.

Example: a team with a partial build runs data-architecture and data-build with the Oracle pack in one visit, and comes back days later for architecture-review and security-review in another.

**Frontier HVE Auto** contracts with `gates=ticked`. The plan form asks which milestones to pause after (`gate:<stage>` items in the checklist, ticked in the form or in `plan.md`); the other stages run without stopping. Escalations, evidence that does not hold, a reviewer's reject or blocker, and decisions the plan did not cover still stop and ask.

## Guardrails

| Guard | File | When | Enforces |
|---|---|---|---|
| loop | `hooks/loop_guard.py` | before/after tools, stop | Loop state (`.harness/`, or `.hve/project/` and the ask's `loop/` folder) always, and the loop files `feature_list.json`, `progress.txt` and `tracker.json` while features still fail, change only through `loop.py` (edit targets are matched by path, shell commands only when they write); new features go through `feature_list.add.json` and `loop.py amend`; pushes only for ticked PRs; stop on escalation; a victory check before stopping. **Awareness mode (D-056, `hooks/guard_mode.json`):** loop-file and loop-state edits and the victory check are shown to the user as "Advisory alert (experimental): surfaces LLM behaviour that helps to know" with the change, not blocked; escalation, hook bypass, resume and push rules still block |
| error | `hooks/error_guard.py` | prompt, before/after tools (Auto, Collab, Prototype Creator, engineer) | After 3 failed terminal commands in a row (feature-loop checks excluded) the agent pauses with "Error guard - paused for your attention", the commands and their output, and must ask you for direction (fix the environment, change approach or skip); only reading and asking are allowed until you answer |
| module | `hooks/module_guard.py` | after edits | No file over 500 lines; the agent proposes a split |
| prototype | `scripts/guardrail.py` | after tools | Flags code over 5,000 lines, files over 20 MB, non-enterprise components and self-built infrastructure, and names the experts to involve |
| template | `hooks/template_guard.py` | session start, prompt, stop | Requested PRDs, technical designs and test strategies come from the configured template and validate before the agent may finish |
| skill | `hooks/skill_loader.py` | prompt, tools | Loads every library skill whose category matches the prompt, or whose rare words do (relevance at least `keyword_floor`), most relevant first whatever its status, plus the ask's skills; over 10 skills or 32,000 tokens is flagged, scored and put to the user, not cut; blocks other library skills |
| profile | `hooks/profile_detector.py` | session start, prompt | Applies learned preferences; challenges token-wasteful requests |
| compaction | `hooks/compaction.py` | sub-agent start | Sub-agents return short summaries, not raw tool output; inside an ask, they get its folder, evidence path, skills and the `SKILLS-USED` rule |
| choice | `scripts/choice_recorder.py` | after ask-questions | Records your ticks (options, manual checks, PRs to push) |
| stage | `hooks/flow_guard.py` | stage agent stop | A flow stage may not finish without moving the flow along an edge |
| plan check | `hooks/plan_check.py` | prompt, before tools (`Frontier HVE Auto`, `Frontier HVE Collab`) | When the ask's `plan.md` changed since `lifecycle.py plan-sync`, adds a reconcile instruction to each prompt and holds `loop.py init/next/amend` and `lifecycle.py stage` until the agent reconciles and syncs |
| no fallback | `hooks/no_fallback.py` | git pre-commit (set by `loop.py init`) | Rejects swallowed errors and TODOs in committed code |

Every deny, block or stop is logged to `.hve/runs/<session>.interventions.jsonl`.

**Waivers** (`hooks/guard_policy.py`): after 3 trips in a session of the loop-file, skill or module guard, its message asks the agent to put a `guard-waiver:<guard>` question to you: keep it on, or lay it down for this session (saved in `.hve/runs/<session>.waivers.json`). `.harness/` state, escalation, hook bypass, pushes and the plan check are never waivable, and waivers are ignored while an output evaluation run is open. `provenance.py` and `lifecycle.py report` list trips, your answers and the calls let through.

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
