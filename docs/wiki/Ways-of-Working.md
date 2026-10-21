# Ways of working

How a piece of work runs through the HVE agents since extension 0.13.0, what you are asked and when, where the files go, and how to check it worked. Decisions: D-046 to D-052 in `research/decisions/decision_log.md`.

## One ask, one folder

Every piece of work you give a working agent is an **ask**. The agent's first step is `lifecycle.py contract`, which opens a timestamped folder (UTC) and makes it the active ask:

```
.hve/asks/
  active.json                      the open ask
  20261019-1405-colour-palette/
    request.md                     your request, verbatim
    contract.json                  skills, stages, personas, tasks, environment, delegations, decisions
    plan.md                        the plan, with generated skills-and-tools and sign-off checklist blocks
    provenance.md                  expected against used, written at the end
    prototype/                     HVE prototype output
    loop/                          feature_list.json, progress.txt, tracker.json, state.json, attempts/,
                                   evidence/<feature>/, prs/, choices/, checks/, tool_log.jsonl
```

- Your workspace root holds only the product: source code, tests and documents. Loop files, screenshots and logs stay in the ask folder.
- `.hve/` is git-ignored. The loop's commits carry a read-only record instead: `[init]` and `[amend]` list each locked `name: verify`, and `[progress] <feature> passes` names the check that passed.
- Feature checks write screenshots and logs to `$HVE_EVIDENCE/<feature>/`; `loop.py` and the output evaluation set it to the ask's `loop/evidence/`.
- `lifecycle.py close` closes the active ask (user-level and workspace hooks then stay out of the way); `lifecycle.py open <ask-id>` reopens one.

## The flow of an ask

```mermaid
flowchart LR
  R[Request] --> C[contract: ask folder, skills, personas, checklist]
  C --> Q{Skills over 2,000 tokens?}
  Q -- yes --> S[You pick: suggested, all or named]
  Q -- no --> P
  S --> P[plan.md form: approve, opt into evaluation and telemetry]
  P --> L[Milestones by persona: briefs, checks, evidence]
  L --> G[Sign-off form per milestone: accept, continue without review, needs changes]
  G --> L
  G --> E[Output evaluation: automatic for creator and e2e, opt-in for the rest]
  E --> D{Decision}
  D -- revise --> L
  D -- pass / human-review --> V[Provenance: pillars, checklist, recommended vs used]
```

| Agent | Lifecycle | Where you are asked |
|---|---|---|
| `HVE creator` | `direct` | Skill choice, plan and dependencies with the telemetry option, escalations, feature sign-off, human review of the evaluation |
| `HVE e2e` | You pick (`sdlc`, `consulting-delivery`, `document`, or a plugin or workspace one) and skip stages | Lifecycle and skips, skill choice, plan with the telemetry option, a sign-off and gate form after each stage |
| `HVE agile` | An agile overlay (`agile-scrum` or a plugin or workspace one) | Overlay and skips, skill choice, plan with evaluation and telemetry options, a hand-off review after each persona, each sprint review |
| `HVE prototype` | `direct` when you run it; none as agile's designer (it works in agile's ask) | Screens, skill choice and options in one form; sign-off of the clickthrough |
| `HVE product-manager` | `direct`, `prd` required (none as e2e or agile's persona) | Skill choice, options, research questions, backlog target, PRD sign-off |

## What you are asked, and why

- **Skill choice.** Every library skill relevant to the request is ranked. When the load passes the guideline (10 skills or 2,000 tokens), nothing is dropped silently: the agent shows a suggested set within the guideline (required skills, then the most relevant per token) and asks once. Choose suggested, all, or named skills; `lifecycle.py skills` records the choice and the tokens over the guideline in `plan.md` and `contract.json`. Keeping all costs those tokens on every turn of the ask; the provenance report then shows how much of the prompt was read from cache.
- **Plan.** `plan.md` is the agreement. If you edit it mid-run, the plan check holds `loop.py` and stage changes until the agent tells you what changes and runs `lifecycle.py plan-sync`.
- **Sign-off checklist.** `plan.md` ends with a generated checklist you can tick in the file or through the agent's forms:

  ```
  **Options**
  - [ ] opt:evaluation — Output evaluation when the work is done ...
  - [ ] opt:telemetry — Research telemetry for this ask ...
  **Milestones**
  - [ ] stage:requirements — Agree the problem ... (persona HVE product-manager; skills prd; templates prd; gate: ...; status planned)
  - stage:test — skipped: checks cover it
  **Tasks** (evidence from each check)
  - [ ] task:feed — build, HVE engineer; check passes; evidence `.hve/asks/<id>/loop/evidence/feed/`
  ```

  After each milestone the agent asks: *Reviewed - accept*, *Continue without reviewing* (fine, recorded as such) or *Needs changes*; it skips the question when you already ticked the item. `lifecycle.py tick <item> <value> "<note>"` records an answer, `lifecycle.py checklist` takes in your ticks from `plan.md` and lists what is still open. Ticking inside the generated block does not trigger the plan check. A stage set back to planned (a new sprint, a change of direction) loses its sign-off.
- **Persona hand-offs** (`HVE agile`): after each persona's step (product manager, designer, engineer) the agent pauses, says what was delivered and where, names the next persona, and asks the sign-off question before switching.
- **Output evaluation.** Automatic for `HVE creator` and `HVE e2e`. `HVE agile`, `HVE prototype`, `HVE product-manager`, `HVE creator-flow` and `HVE creator-github` ask for it as a checkbox in the plan form and run it when ticked (shared `output-evaluation` skill); `HVE single` never asks and runs it only when your request does. Outputs without a feature loop (a prototype, a PRD, a memo) are scored and judged; the locked checks are marked not applicable with the reason.
- **Research telemetry** (opt-in per ask, for every agent that asks questions): tick `opt:telemetry` and run **Frontier HVE: Turn on research telemetry**; it records full chat content, measures chats started afterwards, and a status bar item stays visible until you run **Frontier HVE: Turn off research telemetry** (or click the item). The agent and `provenance.md` remind you to turn it off.
- **Gates and sprint reviews** (`HVE e2e`, `HVE agile`): continue, change direction, or stop.
- **Escalations.** When the loop is stuck (same failure, circular fixes, attempt cap) it stops and asks you one question; only you can resume.
- **Guard waivers.** After 3 trips of the same guard in a session, the agent asks whether to keep it or lay it down for the session. Loop state, hook bypass, pushes and the plan check are never waivable, and guards are strict again during the output evaluation.

## Switching topics

Keep one kind of work per chat and one product per workspace. When a prompt starts different work from the open ask, the harness says so once:

| Situation | Example | Recommendation |
|---|---|---|
| Follow-up | "make the timeline scroll smoothly" in a timeline app ask | None |
| New work of the same kind | A chess quiz app after a War of the Worlds app | New chat |
| A different kind of deliverable | A board presentation on revenue forecasting after a War of the Worlds app | New workspace (open another folder) |

It never blocks. If you stay, the agent opens a new ask in the same workspace and records the recommendation in its contract (`previous_ask`). `lifecycle.py shift "<prompt>"` shows the verdict for a prompt. The check compares subject words, so a follow-up phrased very differently can trigger it; that costs one line.

## Parallel chats

Every ask gets its own folder, also when another chat's ask is still open. A folder has one git checkout, though, so pick the pattern by what runs in parallel:

```mermaid
flowchart TD
  W[Work to do in parallel] --> Q{Two separate builds?}
  Q -- "no: one request with parts, e.g. frontend + backend" --> A["One chat, one ask: features api-orders, ui-orders, each with its own sub-agent, check and evidence"]
  Q -- "yes: e.g. Friendly app + revenue memo" --> B["One folder per chat: another folder or a git worktree, one VS Code window each"]
  Q -- "chats share one folder anyway" --> C["Each chat gets its own ask folder; the open-ask pointer moves to the newest one"]
  C --> N["The other chat is told once and runs lifecycle.py open its ask before its next command"]
```

| Pattern | Example | What HVE does |
|---|---|---|
| One ask with parts (recommended) | "Build the orders page and its API" | One contract and checklist; features `api-orders`, `ui-orders` run one after another, each by a fresh sub-agent |
| One folder per parallel chat | `git worktree add ../shop-memo -b memo`, open it in a new window | Each folder has its own `.hve/` (ask, loop, evidence, logs); merge the branches when done. Use different feature names: loop branches are shared across worktrees |
| Two chats in one folder | Prototype in chat 2 while creator plans in chat 1 | Chat 2's `contract` opens its own ask folder and reports `previous_open`; chat 1's skill loader tells it once that the open ask moved, and it runs `lifecycle.py open <its ask>` before going on. Two feature loops at the same time cannot share one checkout |

An ask finishes when its milestones are done (agents end with `lifecycle.py stage deliver done`) and any evaluation you asked for has run. Personas delegated inside an ask (`HVE product-manager`, `HVE prototype`) work in the parent's ask and do not open their own.

## Skills, tools and hooks during an ask

- **Skills**: the contract installs the chosen skills to `.hve/skills/`; other library skills are blocked so they cannot leak into context. Sub-agents get them through their brief (`lifecycle.py brief`) and end their reply with `SKILLS-USED: ...`, which the parent records (`lifecycle.py used`).
- **Tools**: working agents have no fixed tool list, so they see your MCP servers. The contract records each harness's MCP servers with an estimated tool-definition load and warns over 6,000 tokens; disable servers the ask does not need.
- **Hooks** (VS Code Local runs them per agent; other harnesses after **Frontier HVE: Install for other harnesses**):

| Hook | Fires | Leaves |
|---|---|---|
| `skill_loader` | prompt submit, before and after tools | `.hve/runs/<session>.skills.json`; topic-switch message |
| `loop_guard` | before and after tools, stop | `<ask>/loop/tool_log.jsonl`; denies in `.hve/runs/<session>.interventions.jsonl` |
| `module_guard` | after edits | split request for files over 500 lines |
| `plan_check` (e2e, agile) | prompt submit, before loop and stage commands | holds runs while `plan.md` is out of sync |
| `compaction` | sub-agent start | ask skills and rules in every sub-agent |
| `agent_ledger` | sub-agent start and stop | `.hve/runs/<session>.agents.jsonl`: parent agent, sub-agent name and id, ask, time, and the model when the client sends it (Cursor, Codex) |
| `template_guard` | session start and stop | deliverables only from configured templates |
| `profile_detector` | session start, prompt submit | `.hve/user_profile.json` (build preference, explanation depth) |
| `metrics` (research arms in `.github/agents/` only) | every event | `.hve/runs/<session>.events.jsonl` and, with research telemetry, `<session>.jsonl` (tokens, cost, cache per model call) |

`HVE prototype` runs only `loop_guard` (safety); creator, e2e and agile run all but `metrics`.

The ask's `provenance.md` has an **Agents** table built from the ledger, across every session of the ask:

| Agent | Sub-agent | Id | Session | Started | Seconds | Brief: role, skills | Reported skills | Model |
|---|---|---|---|---|---|---|---|---|
| HVE e2e | HVE product-manager | 3434 | 324234 | 06:15:02 | 212 | requirements PM: prd | prd | claude-x (OTel) |
| HVE e2e | HVE engineer | 3521 | 324234 | 06:19:40 | 96 | HVE engineer: build-approach, ui-anti-slop | ui-anti-slop | not measured |

The brief is the one logged just before the sub-agent started; the model comes from the client (Cursor, Codex) or, with research telemetry on, from the sub-agent's calls in its start-stop window. Both joins go by time, so treat them as close, not exact.

## Check that it worked

From the workspace root (`<repo>` is a clone of this repository, or use the extension's `runtime/` folder):

```
python <repo>/tools/observe/provenance.py <repo>/extension/agents/hve-creator.agent.md latest
```

It reports each component the agent declares as `verified`, `not-exercised` or `failed`, plus the ask contract (gaps, skills recommended but unused, skills used outside the contract) and guard trips. The ask's `provenance.md` (`lifecycle.py report <session>`) opens with a **Pillars** table, then the stages, the sign-off checklist, the recommended-against-used table, the skill load and the prompt cache.

Five pillars, in priority order (README section 6). Quality and load are always recorded; per-call tokens, cost, latency and cache need telemetry: the research arms' `metrics` rows, or for every agent the Copilot OTel export when you opted into research telemetry for the ask:

| Pillar | Always | With research telemetry |
|---|---|---|
| Quality | Feature checks passing, milestones and tasks signed off, the latest evaluation decision and score | Same |
| Cost | - | Copilot AI units for the session and its sub-agents |
| Token efficiency | Skill load and estimated MCP tool load | Prompt tokens (first, peak, total), completion tokens, model calls |
| Latency | Minutes since the ask opened | Seconds of model calls, first to last |
| Cache efficiency | - | Share of prompt tokens read from cache |

## Ten-minute smoke test of the four delivery agents

Use an empty folder with `git init` and run each prompt in a **new Local chat** with the named agent. Answer every question with the first or recommended option. Each prompt keeps the work small on purpose.

| # | Agent | Prompt | About |
|---|---|---|---|
| 1 | `HVE prototype` | `Clickthrough of a leave request flow with three screens: my balance, request form, confirmation. Placeholder data only.` | 1.5 min |
| 2 | `HVE creator` | `Build a colour palette page: pick a base colour, show 5 tints and 5 shades, and a WCAG contrast check of each against white and black. Plain HTML, CSS and JS, no dependencies. Use the feature loop with exactly 3 features whose checks run with node or python only.` | 4 min |
| 3 | `HVE e2e` | `Create a one-page executive memo for the board on the FY27 revenue forecast: base 120m, upside 135m, downside 104m, drivers price and volume. I supply the data, so skip research.` Then, in the same chat: `Build a War of the Worlds timeline app.` | 2.5 min |
| 4 | `HVE agile` | `One sprint for a leave portal. Backlog is ready, skip the backlog step: story 1 "see my leave balance", story 2 "request leave". Sprint 1 takes both stories, UI design only: run sprint-design, skip sprint-build and release, then hold the sprint review and stop.` | 2 min |

What to check after each chat:

| Check | Expect |
|---|---|
| `.hve/asks/` | One timestamped folder per ask with `request.md`, `contract.json`, `plan.md`; the prototype in its `prototype/`; creator's loop files and `evidence/` in its `loop/`. Nothing new in the workspace root except product files |
| Skills | Creator and e2e ask the suggested/all/named question (both prompts pass 2,000 tokens; agile may too); `plan.md` shows the choice. `.hve/runs/<session>.skills.json` lists what loaded and was read |
| Briefs | Agile's call to `HVE prototype` and creator's sub-agents start with "Frontier HVE brief"; `contract.json` → `delegations` and `reported` filled |
| Hooks | `.hve/runs/<session>.skills.json` for creator, e2e and agile (skill loader); creator's `loop/tool_log.jsonl` has pre and post rows (loop guard); `.hve/user_profile.json` exists (profile detector); `.hve/runs/<session>.interventions.jsonl` only if a guard tripped |
| Topic switch | The War of the Worlds prompt in chat 3 gets a "new workspace" recommendation |
| Git | `git log` shows `[init] scaffold` with the locked checks in its body and one `[progress]` commit per feature |
| Provenance | `provenance.py` per agent file is `ok` or names what failed; `provenance.md` in each ask gives pillars, sign-off checklist, skill load, recommended against used and decisions |
| Checklist | `plan.md` ends with the sign-off checklist: options, one milestone per stage with its persona, tasks with evidence folders. Each milestone was followed by a sign-off form; ticking an item in `plan.md` then running `lifecycle.py checklist` shows it as signed off |
| Evaluation | Automatic for creator and e2e; agile and prototype ask for it in their first form and run it only when ticked |
| Parallel chats | Starting a second agent in the same folder while the first ask is open: the second gets its own ask folder and reports `previous_open`; the first chat is told once, before its next tool call, to reopen its ask |
| Agents | `provenance.md` → Agents lists every sub-agent with its parent, brief skills, reported skills and model (or "not measured") |
| Pillars | Quality always; with `opt:telemetry` ticked and research telemetry on, cost, tokens, latency and cache too. The status bar shows "Research telemetry on" until you turn it off |
