# Solution map: Frontier HVE

Enterprise AI harness on GitHub Copilot, also exported to Claude Code, Cursor and Codex: agents, guard hooks, delivery lifecycles, a verified feature loop, skills, expertise packs, output evaluation and telemetry.

Map of commit `2d8dd33` built 2026-10-23. Size **medium** (91 code files, 15,900 code lines; 252 mapped files, 516,397 tokens).
Read this first. Ask `solution_map.py explain "<topic>"` for a concept, `impact --seeds` before a change, `open` for the explorer.

## Concepts

- **Agents** (`concept:agents`, 37 files): Agents are Markdown prompt files with YAML front matter: name, description, model list, tools and hooks.
- **Skills and loading** (`concept:skills`, 61 files): Skills are folders with a SKILL.md (name and description in front matter) that agents load when a task matches.
- **Skill evaluation and onboarding** (`concept:skill-gate`, 11 files): A skill enters the library only through a gate.
- **Expertise packs (plugins)** (`concept:packs`, 28 files): An expertise pack is a plugin that carries one practice's knowledge: agents, skills, templates, a lifecycle, knowledge documents and rubrics, declared in hve-plugin.json (schema in schemas/).
- **Telemetry and metrics** (`concept:telemetry`, 11 files): Telemetry has two sources.
- **Asks and delivery lifecycles** (`concept:asks`, 20 files): An ask is one piece of work run through a delivery lifecycle.
- **Verified feature loop** (`concept:feature-loop`, 10 files): Code is built one verified feature at a time.
- **Guards and hooks** (`concept:guards`, 13 files): Hooks run before or after every tool call, prompt and sub-agent, as middleware between the model and the workspace.
- **Deliverable templates and backlog** (`concept:deliverables`, 11 files): Documents such as a PRD, a technical design and a test strategy are created from versioned templates.
- **Output evaluation** (`concept:evaluation`, 9 files): Finished work is judged before it is handed over.
- **VS Code extension** (`concept:extension`, 6 files): The harness ships as one VSIX.
- **Exports to other harnesses** (`concept:adapters`, 3 files): The same agents, skills and hooks run outside VS Code.
- **Git, PRs and parallel options** (`concept:git`, 7 files): Each verified feature gets its own stacked branch.
- **Graph workflow (creator-flow)** (`concept:flow`, 16 files): creator-flow runs work as a graph of stages (designer, prototyper, builder, architect, sweeper, grower, maintainer).
- **Benchmarks and research** (`concept:research`, 23 files): The harness is tested against its own hypotheses.
- **Solution map** (`concept:solution-map`, 8 files): The solution map lets people and agents understand a repository without reading it all.

## Requirements and status

What the harness must do and where it stands: the original request, hypotheses and the tracker. Roles: product-manager.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `requirements:tracker` | Next actions, phases and validation state; only the user marks items validated. | 2 | 18,125 |
| `requirements:request` | The user's original request and design rules. | 1 | 1,689 |
| `requirements:hypothesis` | The research hypotheses the benchmarks test. | 1 | 509 |

## Solution design

Why it is built this way: decisions with evidence, designs, plans, findings and the blueprint. Roles: solution-architect.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `solution-design:designs` | Technical design specifications. | 1 | 7,704 |
| `solution-design:plans` | Execution plans for larger features. | 1 | 734 |
| `solution-design:blueprint` | The harness blueprint and implementation plan the design follows. | 3 | 21,413 |
| `solution-design:decisions` | Every design decision with its evidence (D-001 onwards). | 1 | 24,926 |
| `solution-design:findings` | Findings from benchmarks and investigations. | 13 | 43,801 |

## Agents

The agents users pick, the personas they delegate to, and the research arms; their prompts, hooks and tools. Roles: prompt-engineer, harness-engineer.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `agents:research-arms` | Benchmark agents with pinned models, budgets and metrics hooks. | 12 | 8,327 |
| `agents:frontier` | The agents users pick: E2E Delivery, BYOW, Prototype Creator and HVE creator. | 4 | 13,582 |
| `agents:personas` | Sub-agents the Frontier agents delegate to: engineer, product manager, reviewers, judges and workers. | 9 | 6,046 |
| `agents:modes` | Hidden harness modes (creator-flow, creator-github, single, minimal) and creator-flow stage agents. | 10 | 7,831 |

## Orchestration

Delivery lifecycles, ask contracts and plans, the verified feature loop, the graph workflow and git. Roles: harness-engineer.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `orchestration:feature-loop` | Locked features with checks, verify and commit, attempt ledger and recovery rules. | 4 | 7,296 |
| `orchestration:lifecycle-defs` | sdlc, agile-scrum, consulting-delivery, document and direct. | 5 | 2,081 |
| `orchestration:git` | Stacked feature branches, PR records, push queue and parallel options in worktrees. | 2 | 3,182 |
| `orchestration:asks` | Lifecycle routing and ask contracts: plan, checklist, stages, skills, briefs, evidence, rework and the provenance report. | 7 | 21,161 |
| `orchestration:flow` | The creator-flow state machine with evidence-gated stage transitions. | 1 | 2,588 |

## Guards and hooks

Hooks between the model and the workspace: deny, advise, stop, or add context. Roles: harness-engineer, security-engineer.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `guards:runtime` | Shared hook plumbing: client payload mapping and .hve paths. | 2 | 2,187 |
| `guards:policy` | Guards that deny, advise or stop: loop state, file size, fallbacks, error streaks, flow stages, plan sync, budgets. | 9 | 9,056 |
| `guards:context` | Hooks that add context: skill loadout and gating, templates, sub-agent briefs, user profile, code graph refresh. | 5 | 8,504 |

## Skills, packs and map

What agents know: the skill library and its gate, plugin skills, expertise packs, and the solution map. Roles: knowledge-engineer, practice-lead.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `knowledge:pack-sample` | The pack manifest schema and the Oracle sample pack. | 17 | 5,248 |
| `knowledge:plugin-scripts` | Plugin manifest and hook scripts: the choice recorder and the prototype guardrail. | 4 | 3,435 |
| `knowledge:plugin-skills` | Skills shipped with the extension and always available. | 18 | 15,722 |
| `knowledge:library` | Admitted library skills. | 37 | 56,480 |
| `knowledge:loadout` | Ranking, loadout budgets, the registry and the context-load measurement. | 4 | 13,465 |
| `knowledge:solution-map` | Map any repository into concepts, views, modules, files and typed edges; explain, impact and the explorer. | 7 | 27,910 |
| `knowledge:packs` | Pack manifest validation, routing, store, install lifecycle and author kit. | 5 | 13,031 |
| `knowledge:skill-gate` | Scan, triage, paired evaluation and admission of skills. | 7 | 11,065 |

## Deliverables and backlog

Templated documents (PRD, design, test strategy) and the backlog. Roles: product-manager, tech-writer.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `deliverables:catalog` | The bundled PRD, technical design and test strategy templates. | 5 | 1,495 |
| `deliverables:backlog` | Validate a local JSON backlog against its PRD. | 1 | 2,003 |
| `deliverables:templates` | Resolve, initialize and validate templated deliverables, including pack template kinds. | 1 | 4,099 |

## Output evaluation

Rubrics, validation hooks and the reviewer council that judge finished work. Roles: qa-lead.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `evaluation:contract` | Rubrics, validation hooks, council roles and thresholds. | 1 | 1,187 |
| `evaluation:reflection` | Rubric scoring, validation hooks, council and decision; pack rubric composition. | 4 | 12,432 |

## Telemetry and research

Session metrics, OTel export, provenance, benchmarks, blind scoring and comparisons. Roles: data-analyst, harness-engineer.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `observability:hooks` | Hooks that record metrics, interventions and sub-agent runs per session. | 3 | 4,584 |
| `observability:research` | Benchmarks, run collection, comparisons, blind scoring, trajectories, provenance and OTel trimming. | 8 | 12,620 |

## VS Code extension and exports

The VSIX: activation, agent rendering, pack commands, exports to other harnesses, prototype checks. Roles: extension-developer, devops.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `extension:workspace-settings` | VS Code settings and MCP servers for working on this repository. | 2 | 95 |
| `extension:build` | Assemble the runtime and skills and package the VSIX. | 2 | 1,523 |
| `extension:host` | VS Code activation, agent and pack rendering, pack and telemetry commands, set-up. | 3 | 8,371 |
| `extension:adapters` | Export agents, skills and hooks to Copilot CLI, Claude Code, Codex, Cursor and the cloud agent. | 1 | 4,628 |
| `extension:prototype-check` | Lint clickable prototypes and capture screenshots. | 1 | 1,181 |

## State and data stores

Files the harness reads and writes under .hve and the user's home folder. Roles: harness-engineer.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `store:contract` | One ask: lifecycle, stages, skills, packs, personas, tasks, checklist, decisions. |  | 0 |
| `store:plan` | The plan the user approves, with generated skills and checklist blocks. |  | 0 |
| `store:provenance` | Expected against actual for an ask or session. |  | 0 |
| `store:feature-list` | Locked features, checks and loop state. |  | 0 |
| `store:runs` | Per-session loadouts, metrics, events, agent ledger and errors. |  | 0 |
| `store:pack-store` | Installed expertise packs and their registry. |  | 0 |
| `store:loaded-skills` | Skills copied in for the open ask or session. |  | 0 |
| `store:deliverables` | Documents a session initialized from templates. |  | 0 |
| `store:evaluations` | Contract snapshots, scores, validation, council and reports. |  | 0 |
| `store:otel` | Chat spans with tokens, cost and cache when research telemetry is on. |  | 0 |
| `store:solution-map` | This map: nodes, edges with evidence, concepts and file hashes. |  | 0 |

## Tests

Unit and integration tests, one file per area. Roles: qa-lead.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `tests:suite` | Unit and integration tests, one file per area. | 14 | 60,868 |

## Documentation

The wiki, the README and the always-on instructions. Roles: tech-writer.

| Module | Purpose | Files | Tokens |
|---|---|---|---|
| `docs:instructions` | The README and the instructions every agent loads. | 3 | 11,979 |
| `docs:learnings` | Learnings captured after a delivery. | 1 | 223 |
| `docs:wiki` | How-to pages for users and agents. | 10 | 32,011 |

## Conventions

- extension/runtime/ is a build copy of hooks/, tools/, skills and templates made by extension/build.py: edit the sources, then rebuild.
- Files stay under 500 lines (module_guard.py); fail fast with no fallbacks (no_fallback.py); one-line docstrings; type hints; the runtime stays Python 3.11 compatible.
- Every design choice gets a decision (D-nnn) in research/decisions/decision_log.md and a tracker entry; only the user marks a tracker item validated.
- Tests: python tests/test_<area>.py; extension: node --check extension/*.js; release: bump extension/package.json, build, package, install.

**Flow: Ask lifecycle (E2E Delivery and BYOW)**

1. `extension/agents/hve-e2e.agent.md`: user asks; agent routes a lifecycle and packs
2. `tools/loop/lifecycle.py`: route, then contract writes the ask contract
3. `tools/loop/ask_plan.py`: plan.md for sign-off
4. `extension/agents/hve-engineer.agent.md`: build stages run as verified feature loops
5. `tools/loop/stage_evidence.py`: stage evidence checked; rework on failure
6. `tools/loop/ask_report.py`: provenance report: expected against actual

**Flow: Skill loading**

1. `hooks/skill_loader.py`: on each prompt: rank skills and packs
2. `tools/skills/recommend.py`: relevant skills within the loadout guideline
3. `hooks/metrics.py`: loadout and tokens recorded per session (research arms)
