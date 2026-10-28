# Decision log

## D-001 — Pinned model: Claude Sonnet 5.5 (copilot)
- Requested pin `claude-sonnet-4-20260514` is absent from this account's Copilot model list (available Sonnets: `claude-sonnet-5`, `claude-sonnet-5.5`).
- An unavailable pin can fall back to the picker model and break cross-mode consistency. Pinned the latest available Sonnet in all 3 modes.
- Check: every record in `research/runs/*.jsonl` carries the served `model`; a mismatch invalidates the run.

## D-002 — Token metrics source: Copilot OTel file export, not hook payloads
- VS Code hook payloads (`PreToolUse`/`PostToolUse`/`Stop`) carry `session_id`, `tool_name`, `tool_use_id`, `timestamp` — no token counts or model.
- Copilot OTel `chat` spans carry `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_read.input_tokens`, `gen_ai.response.model`, and `copilot_chat.chat_session_id`.
- `hooks/metrics.py` joins hook events (tool name, latency from Pre→Post timestamps) with chat spans (tokens, model) by session ID and time. Both sources are runtime-produced; no LLM-authored data.
- Spans are batch-exported (~5 s lag), so the last turn of a session is finalized by `python hooks/metrics.py flush`.

## D-003 — Per-mode models (supersedes D-001 for minimal and single)
- minimal: `GPT-6 Astra (copilot)`. single: `Claude Opus 5.5 (copilot)` with `reasoning-effort: high`. creator: `Claude Sonnet 5.5 (copilot)`.
- User request. Mode comparisons now confound model with harness; `compare.py` must group by `model` as well as `mode`.

## D-004 — creator model: GPT-5.6 Sol (copilot), reasoning-effort medium
- User edit to `creator.agent.md`; supersedes the creator entry in D-003. All three modes now use different model families (GPT-6 Astra, Claude Opus 5.5, GPT-5.6 Sol).

## D-005 — OTel settings live in User settings; sessions run on the Local harness
- Evidence (2026-10-05 smoke test): `single` ran tools but `research/runs/` stayed empty. The `github.copilot.chat.otel.*` settings are `application`-scoped, so `.vscode/settings.json` ignores them. Agent-scoped frontmatter hooks run only on the Local harness; the session ran on the Copilot (Agent Host) target.
- Fix: add to VS Code User settings, then reload:
  ```json
  "github.copilot.chat.otel.enabled": true,
  "github.copilot.chat.otel.exporterType": "file",
  "github.copilot.chat.otel.outfile": "C:\\PwC_HarnessEngineering2\\enterprise-harness\\research\\runs\\copilot-otel.jsonl"
  ```
- Run every benchmark session with Session Target = Local. `init.sh` checks the User settings.

## D-006 — Token scope: session + sub-agent turns; model pin enforced at flush (extends D-002)
- Evidence (session a187413b, now in `research/runs/invalid/`): `single` served `gpt-5.6-sol` instead of its pin, and its `execution_subagent` turns (`gpt-5.6-luna`, chat spans with `copilot_chat.parent_chat_session_id` = session) were missing from the session JSONL.
- Included: chat spans whose `chat_session_id` is the session or whose `parent_chat_session_id` is the session and that carry their own `chat_session_id` (sub-agents). Rows carry `subagent_session` (null for the session's own turns); `context_tokens` is cumulative per conversation.
- Excluded: Copilot utility calls (title, categorization; `gpt-4o-mini`) that have a parent but no `chat_session_id`. They are mode-independent overhead the harness cannot change.
- `metrics.py flush` fails when any of the session's own turns was served by a model other than the agent file's `model:` (display name → id: lowercase, drop ` (copilot)`, spaces → `-`). Sub-agent turns are exempt; their model is recorded per row.
- `single` lists explicit tools instead of the `read`/`edit`/`search`/`execute` tool sets, which include sub-agent tools (`executionSubagent`, possibly `searchSubagent`).

## D-007 — Errored or canceled chat calls invalidate a run
- Evidence (minimal session 91dd46e1, now in `research/runs/invalid/`): the user canceled the first request; its chat span has `status.code` 2, `error.type`, and no `gen_ai.usage.*` or `gen_ai.response.model`. `metrics.py` crashed on it in the Stop hook, so no session JSONL was written.
- Errored chat spans are now excluded from rows, so hooks keep working, and `metrics.py flush` fails for the session: its token totals are incomplete, so it cannot be a benchmark run.

## D-008 — Run outputs live under tests/outputs/; scored by human and AI from screenshots
- User decision (N7). `single` and `creator` build in `tests/outputs/<mode>/current/` (set in each agent body). `minimal` has no file tools, so `tools/observe/collect.py` writes its reply to `response.md` and extracts each path-labelled code block into a file.
- After each run, `python tools/observe/collect.py` moves `current/` to `tests/outputs/<mode>/<session_id>/` and writes `research/runs/<session_id>.run.json` (mode, prompt file + sha256, start/end from the transcript, output dir, files). The transcript path comes from the Stop hook payload, so the record is runtime data, not model text.
- A benchmark session has exactly one user message equal to `tests/prompts/color-palette.md`; anything else fails collect and goes to `research/runs/smoke/` or `invalid/`.
- Contamination guard: finished run folders are in `search.exclude`, and agent bodies forbid reading other runs. A terminal command can still list them; this is instruction-level, not enforced.

## D-009 — minimal: told it has no tools, ≤200 lines of code inline
- Evidence (run 91dd46e1): with only "Respond to the user's request", GPT-6 Astra called the built-in `tool_search` 3–4 times and replied that it was blocked. Copilot's built-in agent prompt pushes it to act with tools.
- User decision (N8, option a): minimal's body states it has no tools and must reply with complete source inline, at most 200 lines in total, each file preceded by its path. The research question becomes "what does the raw output of a frontier model look like under a 200-line budget".

## D-010 — creator runs without the one-feature-per-session loop until Phase 5
- `feature_list.json` is empty until `initializer.py` (Phase 5) decomposes the prompt. A hand-seeded list would be an agent-authored decomposition that Phase 5 replaces, and multi-session runs would make Phase 2 runs incomparable with single's one-session runs.
- Phase 2 creator = sub-agents + verification rules in one session. The loop section is removed from `creator.agent.md` and returns in Phase 5; H1's "more loop iterations" part is tested then.

## D-011 — Baseline before benchmark; minimal reasoning-effort high; tool calls joined by call id
- User decision: Phase 2 now runs each mode once as a baseline via `tools/observe/bench.py` (no manual chat steps). The 3-runs-per-mode benchmark happens once all phases are implemented.
- minimal pins `reasoning-effort: high` (same as single). Evidence: unpinned, run 91dd46e1 followed the picker (`xhigh`, then `medium`).
- Tool rows are attributed to their conversation through OTel `execute_tool` spans (`gen_ai.tool.call.id` = hook `tool_use_id` before `__vscode`), not by time. Time-based attribution misassigns a parent tool call made while a sub-agent runs. `flush` fails if a settled tool call has no `execute_tool` span.

## D-012 — Phase 2 deferred; Phases 3 and 4 built before the baseline exists
- User decision (2026-10-06): Phase 2 takes too long now. Phases 3–4 are built and unit-tested; their token deltas (3.5, 3.6, 4.4) cannot be measured until the Phase 2 baseline runs exist.

## D-013 — Tokenomics within what Local hooks can do
- Local hooks reference: `PostToolUse` can only add context or block; it cannot replace a tool result, and no hook can edit the system message. So history-rewriting observation masking and a schema-stripping `deferred_tools.py` are not implementable as hooks.
- Observation masking → sub-agents: `hooks/compaction.py` answers `SubagentStart` with "return under 2,000 tokens, summarize tool output". Verbose reads happen in the sub-agent and only the summary enters the parent's context.
- Deferred tools → Copilot already defers schemas behind `tool_search` (seen in run 91dd46e1). creator now lists 9 explicit tools + `agent` + `todo` instead of tool sets, dropping unused schemas and `executionSubagent` (which runs a different model).
- Graphify and Headroom wait for user approval (N12): supply-chain and managed-device policy questions.

## D-014 — Persistent memory via SessionStart/UserPromptSubmit hooks (creator only)
- `hooks/profile_detector.py` validates `user_profile.json` against fixed allowed values, learns preferences from each prompt (`UserPromptSubmit`), and injects them as context at `SessionStart`. Episodic memory stays in the conversation and is never written.
- `UserPromptSubmit` output supports only a user-visible `systemMessage`, so the challenge is shown to the user deterministically; the model-side challenge comes from creator's instructions plus the SessionStart note of past triggers.
- Only creator gets these hooks: single and minimal are controls. Benchmark caveat: the profile changes between runs (the color-palette prompt marks the user an over-specifier), so benchmark runs must start from the same profile file.

## D-015 — Headroom not adopted for now
- `headroom wrap vscode` reroutes all Copilot traffic in VS Code (every chat and mode) through a local proxy via User settings, needs its own Copilot OAuth token in a plaintext file, and fails closed when stopped. It cannot be scoped to one agent.
- User decision (2026-10-06): do not implement; regular chat must not be affected. Evaluation notes: `research/findings/phase-3-tokenomics.md` §2.

## D-016 — Graphify for creator only, code-only and local
- Official package `graphifyy` 0.9.71 (latest on the Microsoft PyPI proxy), installed as a uv tool. `graphify extract --code-only` makes no LLM or network calls; the query log is disabled.
- `hooks/graph_refresh.py` indexes only `tests/outputs/harness/current/` and publishes `tests/outputs/harness/graph/graph.json` atomically (empty graph when there is no code, because the MCP server exits on a missing file). `.vscode/mcp.json` serves it; creator gets 4 query tools.
- Expected value on the empty-start color-palette task is low; measured later as creator with vs without Graphify.

## D-017 — Cost per call from Copilot OTel
- Every completed chat span carries `copilot_chat.copilot_usage_nano_aiu` (140/140 spans checked). `metrics.py` records it per row as `cost_nano_aiu`; cost per task = sum over unique `turn_id`. User request.

## D-018 — 10-minute wall-clock budget per run; agents work autonomously
- User decision (2026-10-06, time constraint): single and creator must finish within 10 minutes and run without pausing for confirmation.
- `hooks/budget.py`: SessionStart records the start; PreToolUse is silent until 8 min, then adds a wrap-up note, at 10 min tells the agent to stop and summarize, and after a 1-minute grace denies the tool call with `continue: false`. Deterministic, not an instruction the model can ignore.
- Evidence for the bench rewrite: the first `code chat` run produced no hook events and no OTel spans for a new session (only this conversation's), so the chat did not run on the Local harness; the old bench waited silently until interrupted. `bench.py` now runs one agent, logs progress live to the terminal and `research/runs/bench.log`, and fails after 120 s without a SessionStart hook.
- Second attempt (2026-10-06): `code chat -m minimal -r -` again created no chat session in any VS Code workspace store. `code chat` is dropped. `bench.py` now copies the prompt to the clipboard (20,472 characters, identical to earlier pasted prompts), tells the user to open a new Local chat with the agent and paste, then detects the session through the SessionStart hook (5-minute limit) and runs unattended from there.

## D-019 — A pasted prompt arrives as an attachment; collect verifies it from the chat session store
- Evidence (minimal run 392cc6ec): VS Code turned the 20,472-character paste into `#attachment:Pasted text #1`; the transcript holds only that reference. The attachment value in `workspaceStorage/<ws>/chatSessions/<session>.jsonl` equals `tests/prompts/color-palette.md` after newline normalization.
- `collect.py` accepts a single user message that is either the prompt itself or one pasted-text attachment whose stored value equals the prompt. The chat session store is not a stable VS Code API; if its layout changes, collect fails loudly rather than accepting the run.
- Evidence (single run 6a754bb3): when a background terminal finished, Copilot injected a `[Terminal <id> notification: command completed ...]` user message and started a second top-level `invoke_agent` span; the first one ended at 4 min while the agent was still working. `collect.py` ignores these injected messages; `bench.py` now treats a run as finished only when the Stop hook follows the last PreToolUse, a top-level agent span ended after that Stop, and 15 s pass without new events or spans.

## D-020 — `reasoning-effort` in agent frontmatter is not honored; the model picker decides (N14)
- Evidence (OTel `copilot_chat.request.options`, `reasoning.effort` for GPT, `output_config.effort` for Claude): minimal pins `high` but sent `medium` (392cc6ec); creator pins `medium` but sent `high` (fcd288c9); only single matched (`high`, 6a754bb3). The effort comes from the model picker, not the agent file.
- Metrics rows now carry `reasoning_effort` (the effort actually sent) and `cache_read_tokens`; `compare.py` groups by mode, model, and effort, and computes `cache_ratio` from cache reads only (cache writes are not savings).
- `bench.py` fails a new run at the first main-agent call whose effort differs from the agent file's pin, telling the user to set the picker. `flush` does not fail retroactively, so the three baselines stay valid with their effort recorded as a confound: minimal ran at medium, creator at high.

## D-021 — Background terminals end runs early; agents must not leave them running (N15)
- Evidence (creator fcd288c9): Stop at 12.2 min, then an injected terminal-notification turn and a second Stop at 16.9 min. The budget hook only acts on tool calls, so it cannot stop a running command.
- single and creator now must run every command in the foreground and leave nothing running when they stop. `bench.py` waits 30 s (was 15 s) of quiet before collecting. A late notification turn can still appear; collect then fails on the locked folder rather than recording a partial run.

## D-022 — Phase 9 skill gate: methods only, skills imported later from a separate repo
- User decision (2026-10-07): bring over only these skill groups from the external skill source: UX, architecture, de-slop, scrub, graph workflow agents (Grower/Sweeper/Maintainer), dreams/self-learning, researcher. Set up the gate now; no skills are imported yet. The keyword patterns per category in `skills/categories.json` are first guesses to revise once the skills are read.
- `tools/skills/scan.py`: structure checks (VS Code skips a skill whose `name` is invalid or differs from its folder; description ≤ 1024 chars; ≤ 500 lines) and security rules (prompt injection, external fetch, URLs in scripts, encoded payloads/eval, destructive commands, secrets, binary files). Any finding blocks. `--skillevaluator` adds NVIDIA SkillEvaluator's keyless `quality-check` (not installed; v0.5.0, experimental).
- SkillEvaluator Tier 3 (paired live eval) needs provider API keys, Docker, and Claude Code/Codex/OpenCode as the agent, not Copilot. The paired eval therefore uses our bench: `tools/skills/eval_skill.py run` alternates without/with runs of creator, `report` computes lift (score delta in points of the 0–5 scale), token overhead, latency and cost deltas from blind scores and OTel metrics.
- `tools/skills/onboard.py` admits only at lift ≥ 10 pp and token overhead < 20% and a matching category; otherwise records the reasons in `skills/registry.json`.
- Task-use gate `hooks/skill_loader.py` (creator): VS Code auto-discovers only `.github/skills/`, `.claude/skills/`, `.agents/skills/` and the user skill folders, so `skills/admitted/` stays invisible unless the hook announces it. On UserPromptSubmit it picks the top 3 admitted skills by lift for the prompt's categories (or `skills/eval_override.json` during an eval); on the first PreToolUse it tells the agent to read them; it denies reading any other `SKILL.md`, including user or plugin skills.

## D-023 — Phase 5 loop: one creator chat, a fresh sub-agent per feature, script-owned state (supersedes D-010)
- The user was unavailable for the design questions (2026-10-06) and asked for autonomous decisions; these are the agent's choices for review.
- Context reset per feature = a fresh sub-agent that gets only the feature description, verify command and paths. A new chat per feature would need the user to paste a prompt each time ("dont ask me to manually run things").
- `tools/loop/loop.py` replaces the planned `initializer.py`/`worker.py` (one module, shared state): `init` validates `feature_list.json` (≥ 3 features, exact fields, non-trivial shell `verify`), locks names/descriptions/verify in `.harness/state.json`, writes `progress.txt`, runs `git init` with the B1 pre-commit hook; `next` checks out a stacked `feature/<name>` branch; `verify` runs the locked command, commits, and only then flips `passes` (no-commit-no-flip by construction), logs progress, and writes a PR record.
- Guards (`hooks/loop_guard.py`): edits to `feature_list.json`, `progress.txt`, `.harness/` after `init` are denied except through the loop scripts (anti-gaming, B5); `loop.py` also re-checks the lock; 5 failed verifies escalate and the next tool call stops the agent; Stop is blocked while features fail, unless escalated or the budget is spent (victory check).
- creator's budget is 20 minutes (was 10) because one session now builds every feature; bench waits up to 30 minutes. single keeps 10, so creator vs single now also differs in time budget.

## D-024 — Phase 6 without Jaeger: Copilot OTel + JSONL + an interventions log
- Jaeger needs Docker on this managed device, and Copilot already exports OTel spans per session, turn, and tool (D-002). `hooks/tracing.py` would duplicate them, so 6.1/6.2 are not built.
- Hook interventions (loop guard, module guard, skill loader, budget stop) go to `research/runs/<sid>.interventions.jsonl`; blindspot-coded ones (B1, B5) also go to `research/blindspots/detected_blindspots.jsonl`.
- `tools/observe/trajectory.py <sid>` prints per model call: time, main/sub-agent, model/effort, prompt, cache-read and completion tokens, tools (failed ones marked), then interventions, feature status, a context-rot check (10-call window success rate falling > 20 points below the first window), and context growth. Growth uses `prompt_tokens` per call (the context actually sent), not `context_tokens`, which is cumulative by definition (D-006). `--growth` compares runs.

## D-025 — Phase 8: local PR records, autonomous module splits, instruction-level role isolation
- No git remote and no `gh` CLI here, and pushing needs approval. PRs are local JSON records in `.harness/prs/` (diff stats, verify result, scan status, scope-creep flag at > 1,500 added lines). Branches stack (`feature/b` starts from `feature/a`) so the loop runs without waiting for review; the human runs `branch_workflow.py approve` in feature order (squash merge, `-X theirs`), then `tag`. The agent cannot run `approve`, `tag`, or `--no-verify` (loop guard).
- `hooks/no_fallback.py` runs as the project's git pre-commit hook: Python AST (except bodies that only pass/continue or return None), JS/TS empty `catch {}` and `.catch(() => {})`, and `TODO`/`FIXME` comments.
- `hooks/module_guard.py` (PostToolUse) blocks after an edit leaves a file over 500 lines. Because runs are autonomous (D-018), the agent splits it right away and lists the split in its final summary for review, instead of waiting for approval.
- `tools/git/parallel_options.py`: one worktree and branch per approach, verify each, the passing one with the smallest diff wins (a proxy: quality and tokens per branch would need a session per branch), the feature branch fast-forwards to it, losing branches stay as evidence.
- Role isolation is instruction-level: SubagentStart tells every sub-agent to work in exactly one role. A hook cannot see which role a sub-agent's edits belong to.

## D-026 — Review modes and creator variants (supersedes D-025's approve/tag)
- User decision (2026-10-06): benchmark runs drop human approval; product work uses real PRs. `loop.py init --review local|github` stores the mode. `local` (creator, creator-flow): one stacked branch per feature as a record, PR records with status `recorded`. `github` (creator-github): status `queued`; `branch_workflow.py approve/tag` and the local squash merge are removed.
- `creator-github` (new agent): no time budget and no benchmark metrics (product work, kept out of `collect.py`); stop policy `once` (the victory check pushes back one time). Pushes and PR creation are denied by the loop guard unless the loop is `github` and the human ticked every named branch; force pushes are always denied. `creator-azdo` is deferred until someone needs Azure DevOps.
- The loop guard reads its project and stop policy from hook env (`HARNESS_PROJECT`, `HARNESS_STOP_POLICY`), so each variant guards its own folder under `tests/outputs/<variant>/current/`.

## D-027 — Attempt ledger and deterministic rules instead of open-ended retries
- User decision: each failure gets one rule-chosen fix, then the human. `loop.py next` records attempt 0 (the check must fail before any work, else R5). Every failed `verify` appends a ledger entry (`.harness/attempts/<feature>.jsonl`): check exit code, error fingerprint (output with paths, numbers and hex removed), `HARNESS_CHECKS passed/total` if printed, file hashes, and tool failures, repeated commands and retrieval misses from the loop guard's tool log.
- Rules, first match (tools/loop/diagnose.py): R6 environment (registry 403 → AGENTS.md proxy fix, else human); R5 same failure as the baseline again → human; R1 same error with the same files as an earlier attempt (A→B→A) → human; R2 same error twice → fresh sub-agent, different approach or parallel options; R3 a tool failing 3+ times or a repeated command → fixed tool hint; R4 2+ retrieval misses → graph and exact paths; R0 new error → retry. A rule firing a second time for a feature → R7 human. 5 attempts → human. `loop.py resume <note>` is human-only.
- Parallel options use the ledger too: every option is ledgered with its approach; options rank by passing, share of checks, smallest diff; all options failing with one fingerprint → R5. Benchmark loops adopt the best automatically; GitHub loops keep the worktrees, print `preview` commands per port, and `choose` adopts only the option the human ticked. Tokens per option are not attributed yet (no reliable sub-agent → approach mapping).
- Not verified live: hooks fire PostToolUse only on success, so a failed tool shows as a pre-call without a post-call; the ask-questions tool's hook name (`vscode_askQuestions`) and response shape are taken from this chat's tool.

## D-028 — creator-flow: the user's graph workflow as an evidence-gated state machine
- Stages and edges from the user's picture (designer → prototyper → builder ⇄ architect → sweeper → grower ⇄ maintainer → done; prototyper → designer). `tools/loop/flow.py` moves only along drawn edges, each with deterministic evidence: design.json fields; prototype check passes; every feature check passes; no file over 500 lines and a clean no-fallback scan; lint passes, all checks still pass and code did not grow; roadmap items linked to features; final health check. Back-edges need a note and are capped at 2 (benchmark: Grower one pass, `new-opportunity-found` cap 0); the cap escalates to the human.
- Stage agents `flow-designer`, `flow-prototyper`, `flow-architect`, `flow-sweeper`, `flow-grower`, `flow-maintainer` (not user-invocable) finish by running the transition themselves; their Stop hook (`flow_guard.py`, treated as SubagentStop) sends a stage back once if it did not move. The orchestrator runs the Builder stage as the creator feature loop.
- Benchmark mode `flow`: 40-minute budget, `bench.py creator-flow`, collected like creator. Skill categories map to stages (UX/research → Designer, architecture → Architect, de-slop/scrub → Sweeper, graph workflow → Grower/Maintainer). Not verified live: the `agents:` frontmatter list and custom-agent sub-agent invocation.

## D-029 — harness-assist plugin for advanced users; technical level in the profile
- `plugins/harness-assist` (Agent Plugins 1.0): skills `feature-checklist`, `run-tests`, `code-review`, `parallel-options`, `pr-push`, `explain-walkthrough`, `prototype-guardrail`; plugin-wide PostToolUse hooks `choice_recorder.py` and `guardrail.py --hook`. All 7 skills pass the Phase 9 scan.
- Human ticks are enforced, not trusted to the model: the agent asks with the ask-questions tool using fixed headers (`choose:<feature>`, `push`, `technical-level`) and a `[project: ...]` or `[profile: ...]` tag; the recorder writes the user's selection into the project's `.harness/` (which the agent cannot edit), and `parallel_options.py choose`, `branch_workflow.py pushed` and the loop guard's push gate read only that. Push approvals accumulate across sessions.
- `user_profile.json` gains `technical_level` (`executive`, `partial`, `developer`), learned from explicit role statements ("I'm the CTO", "as a TPM") or the explain skill's one-time question; SessionStart tells the agent how to explain and when to recommend experts (UI/UX, backend/full-stack, data scientist, AI engineer, solution architect, DevOps, security).
- Prototype guardrail: review verdict above 5,000 code lines, for catalogued non-enterprise components (graph DBs such as FalkorDB, OCR such as Tesseract, embedded DBs such as SQLite, local vector stores, self-hosted LLMs, self-managed queues, self-built auth) with their licensed Azure alternative, and for self-built infrastructure files; it names the experts (always a solution architect for components or infra) and offers a `complexity_report.json`. Thresholds and the catalogue are data (`scripts/enterprise_catalog.json`).
- The skills call harness tools by relative path, so the plugin works in this harness workspace (or the separate repo once the tools move there). Plugin-wide hooks run in every session while enabled; keep it disabled for benchmark runs (N20).

## D-030 — 15-minute budget with a user continue prompt for creator, creator-flow and creator-github (supersedes the 20- and 40-minute budgets in D-023 and D-028)
- User decision (2026-10-06): 40 minutes is too long; the creator agents get 15 minutes, and the user decides whether to continue.
- `hooks/budget.py` now needs `HARNESS_BUDGET_ON_END` at SessionStart. `stop` (minimal, single: 10 minutes) keeps the old behaviour: nudge 2 minutes before the end, final-summary nudge, hard stop after 1 minute of grace. `ask` (creator, creator-flow, creator-github: 15 minutes): after the nudge, every tool call returns `permissionDecision: ask`, so VS Code asks the user to allow it. When an asked call runs (its PostToolUse fires), the budget grows by another 15 minutes and is logged as `budget_extended`; a denied call tells the agent to stop and summarize. There is no hard stop in `ask` mode: the user decides.
- Benchmark caveat: in `ask` mode a run's wall-clock time includes the time the prompt waits for the user, and extended runs are not comparable with 15-minute ones. `bench.py` still waits up to 50 minutes.

## D-031 — Prune the Copilot OTel export after each run
- Evidence (2026-10-06): `research/runs/copilot-otel.jsonl` reached 344 MB. The export is a User setting, so every Copilot chat writes to it, mostly development chats unrelated to benchmarks; it grew without bound, and `metrics.py flush` re-reads the whole file for every session.
- `tools/observe/otel_prune.py` streams the export once, writes each collected session's spans (chat and tool spans of the session and its sub-agents, the same filter metrics uses) plus the per-window export watermark to `research/runs/otel/<session>.otel.jsonl.gz`, checks that the archive rebuilds exactly the metrics rows on disk, and only then empties the live file. It refuses while `bench.lock` exists or any session is uncollected. `metrics.py` reads a session from its archive once one exists.
- `bench.py` holds `bench.lock` during a run and prunes after collect. Archives are local only (gitignored): spans can contain chat content.
- Lesson for the harness: an innocent request ("export telemetry to a file") carried an unbounded storage cost nobody asked for. The prototype guardrail now also flags any project file over 20 MB as a retention question (`file_mb_limit` in the catalog).

## D-032 — Frontier HVE as a standalone VS Code extension; workspace state in .hve/
- User decision (2026-10-06): ship the harness as its own extension (sibling product, separate repo), keep the agent names with an HVE label, Python is an accepted runtime dependency.
- State is separated from code. Hooks keep state in `<workspace>/.hve/` (`hooks/hve_paths.py`; hooks run with the workspace root as working directory): `runs/`, `outputs/`, `blindspots/`, `user_profile.json`. This repository's data moved there from `research/runs`, `research/blindspots`, `tests/outputs` and the root profile; research records (decisions, findings, comparisons, blind scoring) stay in `research/`. Worktrees for parallel options now live in the project's ignored `.worktrees/` so a workspace never writes outside itself.
- `extension/` holds the extension: product agent templates (`HVE minimal`, `HVE single`, `HVE creator`, `HVE creator-flow`, `HVE creator-github`, six `HVE flow-*` stage agents) with a `{{RUNTIME}}` placeholder, `build.py` (copies the shipped hooks, loop and git tools, guardrail and choice-recorder scripts and the harness-assist skills, compiles them, and checks every runtime path the templates reference), `render.js` and `extension.js`. The "Frontier HVE: Set up" command checks Python 3.11+, renders the agents and skills as an Agent Plugin in the extension's global storage, registers it in `chat.pluginLocations`, creates `.hve/` with the profile and the technical level, offers to ignore `.hve/`, and optionally points the Copilot telemetry export at the workspace. After an update the plugin is re-rendered on activation.
- Product agents work on the open workspace (`HARNESS_PROJECT: .`), get the choice recorder and guardrail as agent-scoped hooks (the plugin-wide hooks file is removed, so ordinary chats are unaffected), and leave out the research-only metrics, Graphify and skill loader. Telemetry stays optional because the export grows without bound outside the research prune (D-031).
- Not verified live yet: VS Code loading agents from an Agent Plugins 1.0 folder registered by setting, hook commands with absolute quoted paths, and the tool ids `vscode/askQuestions` and `github.vscode-pull-request-github/*`.

## D-033 — Product agents: picked model, no time budget, loop init in an existing repo, judged errors
- Evidence (2026-10-06, first live test of extension 0.1.0): the HVE agents, skills and setup worked. `HVE creator` asked for a hello-world program; `loop.py init` refused because the workspace already had `.git` (a rule written for empty benchmark folders), and the agent then built and tested the program without the loop, so no `progress.txt` was written.
- `loop.py init` now works in an existing repository: it keeps the repo's identity and current branch (stored as `trunk`, the base of the first PR record), installs the B1 pre-commit hook at git's hooks path, and fails with instructions if a different pre-commit hook exists. It refuses only when `.harness/state.json` exists. New folders still get `git init -b main` with the harness identity.
- User decision: the agent judges errors and continues when there is a sound way around them; it stops only for critical errors (data loss, security or credentials, broken harness state) or an error that repeats after a change of approach. Added to the creator agents (research and product). For trivial requests the product creator agents ask once whether to run the loop.
- User decision: model pins and time budgets serve benchmarking only. Product agents have no `model` or `reasoning-effort` (VS Code then uses the picker's model, including Auto), no budget hook (loop_guard's victory check uses the `once` stop policy), and the extension no longer ships `budget.py`. Research agents keep pins and budgets (D-020, D-030). Extension version 0.1.1 so the installed plugin re-renders.
- Evidence (0.1.1 update): the re-render deleted and recreated the plugin folder; on Windows VS Code holds it open, so the delete failed after removing the agents and the plugin stayed at 0.1.0 with no agents. `render.js` now updates files in place and removes only stale entries (0.1.2).

## D-034 — Infer explanation depth; never ask how technical the user is
- User decision (2026-10-06): asking users to classify themselves as technical or non-technical is demeaning and unreliable (people who say "pro code" are often vibe-coding TPMs). The classification is inferred and stored in the profile; at most the user is asked how they prefer to build.
- Profile: `technical_level` is replaced by `build_preference` (stated: `no_code`, `low_code`, `pro_code`), `depth_evidence` (an int within ±6 learned from prompts) and `explanation_depth` (`guided`, `balanced`, `expert`). The preference is a prior (-3, 0, +3); role statements weigh 3 (a TPM or architect statement pulls the total toward balanced); each prompt adds +1 for working signs of code fluency (code fences, `name()`, file paths, error names, terms like refactor or mocks) and -1 for guided signs ("what is a pull request", "just make it work"). A total of 2 or more is expert, -2 or less guided, else balanced.
- The session context tells agents to adapt silently and never label, classify or quiz the user. Setup's quick pick and the `explain-walkthrough` fallback question ask "How do you prefer to build?"; the choice recorder stores `build_preference`. Extension 0.1.3.
- The thresholds and patterns are first guesses; check them against real sessions.

## D-035 — delivery-coach: participatory, verified delivery for product users
- User decision (2026-10-07): "pro code" means using AI to code and review continuously, not writing code by hand; setup now says so. Product users get a participatory loop that guards against vibe-coding production applications.
- New plugin skill `delivery-coach`, activated by a `Delivery: participatory` line the profile hook adds once setup has recorded a build preference (research benchmarks have none, so they are unaffected). It applies the long-running pattern: initializer (`feature_list.json`, `progress.txt`, new `tracker.json`), generator (fresh sub-agent per feature) and evaluator (locked check, screenshot evidence produced by the check into `.harness/evidence/<feature>/`, second sub-agent reviewing diff and screenshot).
- `loop.py` writes `tracker.json` at init and after `next`, `verify`, `resume` and the new `status`; it is protected like the other loop files. A manual check is offered after each passing feature (`check:<feature>` ask-questions header); the choice recorder writes `.harness/checks/<feature>.json` and the tracker shows it. `needs changes` becomes a fix in the next feature or a follow-up request; the locked list is not reopened.
- Discovery sprints: parallel-options worktrees moved from `.worktrees/` to `.hve/discovery/<feature>--<approach>`; loop init ignores `.hve/`. HVE creator and creator-flow gain the ask-questions tool and the choice recorder.
- Guided and balanced users are coached first and their choices challenged (explain-walkthrough, prototype-guardrail) before building.

## D-036 — Sub-agent model routing is documented, not overridden
- Evidence (2026-10-07): a built-in Explore sub-agent ran on Claude Haiku 4.5 under a Claude Opus 5.5 session; run a187413b had `gpt-5.6-luna` sub-agent calls under `gpt-5.6-sol`. No setting named "hydra" exists; VS Code documents the order: model passed by the main agent, then the custom agent's `model`, then Auto when `chat.subagents.defaultToAuto` is on, then the main model, and refuses models above the main model's cost tier.
- README explains this. Research flow stage agents keep pinned models; HVE product agents set no model so their sub-agents inherit the picker's model; metrics keep recording the sub-agent model per call.

## D-037 — Skill library: authored skills, provisional gate, budgeted loading, /recommend-skills
- User decisions (2026-10-07): bring in UX, architecture, de-slop, scrub, dreams/self-learning and researcher skills after evaluation; rewriting is fine and the source is credited as its license requires; the fixed 3-skill cap is replaced by a budget (up to 10 skills and 2,000 tokens per task), with anything beyond it flagged and offered to the user ranked.
- Token cost drove the design: a discoverable skill puts its name and description into every request of every chat (plugin skills are global), so 13 more would add roughly 700-1,000 tokens per request and invite reading bodies. Library skills are therefore not discoverable; only `recommend-skills` is (about 60 tokens). SkillsBench (arXiv 2602.12670): curated skills +16.6 pp on average, focused skills beat exhaustive bundles.
- 13 skills authored in `skills/authored/` (original text; topics informed by the external library credited in `skills/authored/NOTICE`): ux-flows, accessibility, ui-content, ui-anti-slop, architecture-options, api-design, build-approach, code-hygiene, prose-anti-slop, scrub, dreams, web-research, analyst. The source had no dreams skill and only a browser-automation research skill needing an MCP server, so those were written from scratch. Each is 360-440 tokens.
- Two-stage evaluation: `onboard.py --provisional` (scan, category, at most 800 tokens, description at most 200 characters, no non-Python scripts) gives status `provisional`; the paired with/without evaluation promotes to `admitted`. Registry entries now carry `status` and `description`.
- `recommend.py` ranks matching skills: admitted first, then relevance (shared categories plus shared word stems weighted by rarity across the library; stop words and stems in over half the library ignored), then measured lift, then size; it fills the budget greedily and returns the rest as recommendations. `skill_loader.py` uses it (`HARNESS_SKILLS_MIN_STATUS`: `provisional` for HVE agents, `admitted` for research agents), copies loaded skills into `.hve/skills/` so reads stay inside the workspace, offers over-budget skills through an ask-questions `load-skills` question and loads only ticked ones (PostToolUse), and denies only library skills outside the loadout, so plugin skills stay readable.
- Task patterns for de-slop, scrub and self-learning no longer match every prompt. The extension ships the library in `runtime/skills/`, not in the plugin's discoverable `skills/`. Extension 0.2.0.
- Ranking and thresholds are first guesses; the live paired evaluation per category is the next step.
- Coverage clarification (2026-10-07): this records a curated batch of 13 original authored skills, not a verified exhaustive selection from all 134 AgentX skills. No persisted full-source triage or per-source inclusion/exclusion ledger was found. The claim about no dreams counterpart and only browser-automation research is not evidence that adjacent memory, feedback, retrieval or analysis capabilities are absent. The [selection and coverage audit](../findings/phase-9-skill-selection-coverage.md) pins the source checked, reconciles source/library/plugin counts and lists relevant unassessed candidates. The per-task load budget is not a cap on library size.

## D-038 — Micro paired evaluation replaces 15-minute session runs for skill admission
- User decision (2026-10-07): 52 session runs of 15 minutes are too slow; use 5 small tasks per skill, single-agent calls under 30 s, an AI judge on blind pairs, the whole check within 15 minutes, and mind the limited token pool. Models: deployed Foundry `gpt-5.4-mini`, `gpt-5.2-chat`, `Kimi-K2.6` (Kimi for reasoning or judging only).
- `tools/skills/micro_eval.py` with tasks in `tests/skill_tasks/<skill>.json`. Generator `gpt-5.4-mini` (reasoning effort low); judge `gpt-5.2-chat`. Kimi-K2.6 was tried as judge first: it spent its whole 2,000-token budget thinking and returned no content, and the deployment rejects a `thinking` switch, so it was dropped to save tokens. The `gpt-5.2` deployment name does not exist; `gpt-5.2-chat` does. Both answers in a pair come from the same generator, so judge self-preference cannot favour a condition.
- Keyless Entra auth via `az account get-access-token`; endpoint from the git-ignored `.env.local`; every response cached by request hash in `.hve/evals/micro/` (ignored); empty replies raise instead of being cached.
- Gate additions for micro evals: at least 3 of 5 task wins and no task lost by more than 1 point, on top of lift >= 10 pp and overhead < 20%. The rule was fixed before the run and applied as is.
- Result (130 answers, 65 judgements, 144 s, about 140K tokens including the pilot): admitted dreams 56, analyst 44, scrub 40, build-approach 28, ux-flows 28, web-research 28, api-design 16, architecture-options 12; rejected prose-anti-slop (28 pp but 2 wins, 3 ties), ui-anti-slop (12 pp, 2 wins), code-hygiene (8), ui-content (4), accessibility (0). Rejected skills stay in `skills/authored/` but leave the library.
- Limits: 5 tasks per skill and one judge pass; tasks and checks were written by the agent that wrote the skills, which can favour the skills. Low lift for accessibility and UI copy likely means the model already does them well without help. Full-session evaluation stays available for the most used skills.
- User decision (same day, after the results): a tie counts as a win, since a tie means the skill did no harm. The gate became wins plus ties >= 3 of 5 (`micro_min_wins_or_ties`) and was re-applied to the saved evals without new model calls: prose-anti-slop (28 pp, 2/2/1) and ui-anti-slop (12 pp, 2/3/0) are admitted, giving 10 admitted and 3 rejected (code-hygiene, ui-content, accessibility). Because the rule changed after seeing results, those two admissions should be confirmed with fresh tasks. Method and results: `research/findings/phase-9-skill-micro-eval.md`.

## D-039 — Skill evaluator and context-load guardrail ship in the extension
- User decision (2026-10-07): extension users must be able to onboard their own skills with the same evidence, and the harness must flag bloat from too many skills or always-on instructions without a fixed token threshold. When the check runs and how to invoke it must be documented.
- `HVE skill-evaluator` agent with two tool-less helper agents (`HVE skill-worker`, `HVE skill-judge`, not user-invocable, so they do not inherit the evaluator's instructions). `tools/skills/evaluate.py`: `static` (scan, category, limits, overlap, cost), `blind` (A/B judge prompts ordered by task-id hash), `record` (unblind, score, gate, workspace registry and library), `foundry` (micro eval on the workspace's own endpoint). Default path needs no keys: answers and judging run as sub-agents on the user's chat model. `micro_eval.py` was refactored to share blinding, scoring and the runner.
- Workspace registry `.hve/skills-registry.json` and library `.hve/skill-library/` are ranked and loaded by `recommend.py` and `skill_loader.py` with the harness library.
- `tools/skills/context_load.py` counts discoverable skills (workspace, user and plugin folders including `chat.pluginLocations` and marketplace plugins), always-on instruction files, an optional agent prompt and an MCP estimate per server; reports total, share of the context window, top contributors, duplicates and unmeasured skills; warns on 20% growth since the last check or 10% of the window (relative settings in `skills/categories.json`). Invoked by `/check-context-load` (new plugin skill), at setup (notification), in the delivery-coach close-out and at the end of a skill evaluation. Notes: `research/findings/phase-9-skill-evaluator-and-context-load.md`.
- First measurement in this window: 11,632 always-on tokens, 42 skills, 9 duplicates because the harness-assist plugin is registered twice (repository path and installed extension).
- Wiki topics for later are listed in `tracker.json` (`wiki_topics`); no wiki pages are written yet. Extension 0.3.0.

## D-040 — Screen all 134 source skills; import verbatim into the hidden library and evaluate in tiers
- User decision (2026-10-07): the first batch of 13 authored skills was a scope choice (the six requested areas), not a verdict on the other source skills. Bring more over without making them always-on; copy them verbatim instead of rewriting, and evaluate them. The user is a co-contributor of the source project and chose to build Frontier HVE from scratch to keep it lean and take only what proves itself.
- All 134 source skills (pinned commit `fc39b297`) were screened statically with no model calls; one disposition per skill is in `research/findings/phase-9-source-skill-manifest.json`: 38 tier 1 (requested areas, 5 of them with scripts or source-runtime steps not shipped), 72 tier 2 (outside the requested areas, a scope decision), 24 for human review (scanner flags that are mostly expected in security, DevOps and language skills). Positioning and plan: `research/findings/phase-9-skill-selection-coverage.md` section 6.
- Imported skills will keep their text, `LICENSE` and `NOTICE` unchanged, live in `skills/imported/agentx/`, never be discoverable, and load per task within the loadout budget; skills over 2,000 tokens are offered for the user to tick. Same micro paired evaluation and gate; skills with an authored counterpart are compared on the same tasks.
- Fix: rejected registry entries now carry `status: "rejected"` (they kept the status they were evaluated with).

## D-041 — Admit the 27 imported skills untested; strict evaluation deferred
- User decision (2026-10-07): imports must win all 3 tasks with uplift confirmed by a significance test, and token use must stay low. The Foundry endpoint was unreachable from this machine (DNS failures and connection resets), so the user asked to stop retrying, admit the 27 skills and mark them for testing later.
- Strict gate (`micro-strict`, built in `onboard.decide` and `import_eval.py`, unit-tested): micro gate plus every task won plus a one-sided exact sign test on check-level gains vs losses, p < `strict_alpha` 0.05.
- `onboard.py ... untested` admits with scan and category checks only: status `provisional`, `evaluation: "pending"`. Registry: 37 admitted entries, 27 of them pending. The manifest records the same.
- No bloat: the 27 are not discoverable or always-on; they are ranked per task for HVE agents only and, being large, are mostly offered rather than auto-loaded. Research agents ignore provisional skills.
- The extension ships the source `LICENSE` and `NOTICE` in `runtime/skills/licenses/agentx/`. Its build compiles harness Python only: the imported `documentation/scripts/generate-readme.py` does not compile upstream and is kept verbatim.
- Notes: `research/findings/phase-9-skill-selection-coverage.md` section 6.4. Follow-up: tracker `N26`.

## D-042 — Client adapters: one exporter and one hook shim; Azure DevOps through Microsoft's MCP server
- User decision (2026-10-07): keep the VS Code path as it is; Azure DevOps, Cursor, Claude Code and Codex CLI are the important additions. Prefer established tools such as MCP servers, otherwise build lighter; give each target agents and skills to invoke; nothing is accepted without a test, recorded in the research notes.
- Azure DevOps uses the official `@azure-devops/mcp` server (MIT), limited to the `core work work-items repositories pipelines` domains, plus an `HVE azure-devops` agent that writes only ticked changes. The source project's ADO agents and instructions (about 41K characters) were not copied: the server covers the operations and the instructions would add always-on load.
- `tools/adapters/export.py` renders the existing agent templates and plugin skills for each client (Claude subagents with frontmatter hooks; Cursor and Codex agents as explicitly invoked skills) and copies the runtime into `.hve/runtime`. `hooks/agent_compat.py` maps each client's hook payload and response to the VS Code shape, so all hooks run unchanged. Deviation from the plan (`.cursor/rules`, `CLAUDE.md`): those are always-on and would load the creator prompt into every request.
- Safety: organization names are validated; hook files the harness did not write are never overwritten; Cursor gets no `permission: allow` (could skip its own approval); Codex PreToolUse output drops `continue`, which Codex would treat as a failed hook and let the tool run.
- Verified by `tests/test_adapters.py` with each client's documented payloads against the exported configuration. Not verified live: no client CLI is installed and the npm proxy reset the connection. Notes: `research/findings/phase-10-adapters.md`. Follow-up: tracker `N27`, `N28`. Extension 0.4.0 adds the agent, the `/export-harness` skill and the runtime files.

## D-043 — The wiki lives in docs/wiki, ships with the runtime and is pointed to from always-on instructions
- User decision (2026-10-07): the adapters need a how-to wiki that GitHub Copilot agents can also find.
- Pages are Markdown in `docs/wiki/` (GitHub-wiki compatible names, index `Home.md`); the first page is `Adapters.md` (topic W19, status drafted). Agents in this repository find it through one line in `.github/copilot-instructions.md` and `AGENTS.md`. Extension users' agents find it in the runtime: the build copies `docs/wiki/` to `runtime/docs/wiki/`, the `/export-harness` skill and the `HVE azure-devops` agent reference it, and the exporter's report names it (`guide`). Exported clients get it in `.hve/runtime/docs/wiki/`.
- The page is not loaded into context: only the pointer lines are always-on (about 40 tokens); the page is read when needed. Pages name files in backticks instead of relative links so the shipped copy has no broken links; `tests/test_adapters.py` checks that wiki links resolve and that every pointer reaches the shipped page.
- Not published to the GitHub wiki repository; publishing is a user action.

## D-044 — HVE product-manager: AgentX judgment, Frontier mechanisms; backlog in the user's tracker
- User decisions (2026-10-12): bring the AgentX product manager as an optimized HVE agent with no template content in its instructions; council on different models with honest reporting of which ran; the backlog goes to the tracker the user chooses (local JSON, Azure DevOps, GitHub), never into the PRD; PRDs only; `web/fetch` allowed; no export to other clients yet. Plan reviewed before implementation.
- Kept from AgentX (`.github/agents/product-manager.agent.md`, ~22 KB): discovery before drafting, research before writing, intent preservation, measurable requirements, non-goals, the AI product contract, item quality and a three-lens challenge. Dropped: the PRD and roadmap templates, the 12-section list, fixed paths, issue and label formats, the self-review and report checklists, the Node policy hooks, `frontier.ps1` council/loop/stage-gate, the shared protocol files and the model pin (D-033). The agent prompt is about 1.5K tokens.
- Mechanisms: structure from the configured template through `manage.py` and `template_guard.py`. A new `HVE_TEMPLATE_TYPES` variable limits registration, so the PRD-only agent is not blocked at Stop by an unwritten TDS. The prompt hook sets `HARNESS_REQUIRED_SKILLS: prd`: the loader reserves its tokens and slot before optional skills, even when the prompt matches no category. Missing, ambiguous, disallowed or over-budget required skills fail explicitly, naming the matching paths. The agent reads the installed `.hve/skills/prd/SKILL.md` copy only once; research runs as up to 3 compacted sub-agents; the hidden `HVE council` runs with no tools. PRD revisions edit in place and `register`, since `init` never overwrites.
- Council models: the agent passes a model per call from different vendors. VS Code refuses a model above the session's cost tier and lists the allowed ones; the agent then picks another vendor, or runs the lens without a model labelled "host-selected; actual model unconfirmed" (Auto may be enabled). Only the Copilot OTel export confirms which model answered; the report says "not confirmed" otherwise.
- Backlog: one item shape for all trackers. Local JSON is checked by `tools/backlog/backlog.py validate`:
  - exact fields and strict JSON types, including an integer version and string path, ids and references;
  - epic → feature → story hierarchy;
  - unique ids, known dependencies and no cycles;
  - non-goals and Given/When/Then criteria;
  - requirement IDs that exist in the PRD.

  A valid backlog also reports `uncovered` PRD `FR`/`NFR` IDs. These are not errors, since a PRD can sequence requirements for later. Azure DevOps goes through a handoff to `HVE azure-devops` (a new backlog-to-work-items workflow, ticked writes only, epic/feature/story mapped per process including Basic's Epic/Issue/Task). GitHub uses the GitHub MCP server's `search_issues` for repository-scoped duplicate discovery, then `issue_read`, `issue_write` and `sub_issue_write`, ticked writes only, existing types and labels only, and no `gh` CLI fallback. On both, a ticked item's parent and dependencies must be ticked or already exist, and they are created first.
- Verified by `tests/test_backlog.py`, `tests/test_templates.py` and `tests/test_extension.py`. Not verified live: tool ids, per-call model selection and handoffs. Follow-up: tracker `N29`. Extension 0.6.0.

## D-045 — The admitted `prd` skill is adapted, an exception to D-040's verbatim rule
- User decision (2026-10-12): make the PRD skill generic so it works with any configured template.
- `skills/imported/agentx/product/prd/` stays verbatim as provenance. The loaded copy `skills/admitted/prd/` is adapted:
  - no template file, section numbers, AgentX paths or issue formats;
  - content blocks mapped to the configured template's sections;
  - stable `FR`/`NFR`/`AC` IDs;
  - the backlog moved out of the PRD;
  - an item shape with field mapping for local JSON, Azure DevOps and GitHub.
- Apache-2.0 §4(b): every changed file carries a modification notice. The registry `source` says "adapted" and `skill_tokens` is recounted (1,206, after moving the AI contract, examples and consumer checklist into `references/requirements-quality.md` so the required skill leaves room in the 2K loadout for task skills such as `web-research`). The status stays `provisional` with evaluation `pending`, so the adapted text still needs the same paired evaluation before admission. `tests/test_skills.py` checks that no template-specific text returns.

## D-046 — Output reflection loop: contract, grounded rubrics, triggered validation, model council, decision
- User decision (2026-10-12): evaluate what the creator delivers in five layers: an evaluation contract (YAML, after AgentX `evaluation/frontier.eval.yaml`), rubrics, validation of low scores with hooks and screenshots, a council of high-tier models (critical, balanced, constructive coach), and a judge that marks risks, misses and questionable designs, then asks for another pass or hands the output to the human.
- The work is additive. It runs after the feature loop. The only hook change is in `loop_guard`: files written to `.hve/evaluations/input/<name>.json|md` may cite `.harness/` and `feature_list.json` paths. Before this, grounded scores were denied as anti-gaming edits. Loop state stays locked, and traversal out of that folder is still denied. `tools/evaluation/` holds `contract.py` (a dependency-free strict YAML subset and validation), `workflow.py` (stages and decision) and `reflection.py` (CLI). The default contract is `evaluation/frontier.eval.yaml`, shipped in the runtime. A hidden, read-only `HVE evaluation-reviewer` / `evaluation-reviewer` agent is the council member. Only the two `creator` agents gained an "Output reflection" section and a one-line rule that UI checks save screenshots to `.harness/evidence/`.
- Anti-gaming:
  - each stage runs once, in order (manifest status), on a contract snapshot;
  - every rubric score cites existing project files;
  - validation runs real checks; a timeout counts as a failure;
  - every council marker cites `rubric:`, `validation:` or an existing `file:`;
  - deterministic markers (a score below its blocking threshold, a failed required hook) cannot be voted away;
  - a revision pass needs the previous decision to be `revise`, is capped by `maxRevisionPasses`, and re-runs every hook.
- Council models follow D-044: a different vendor per role, refusals handled, the requested model recorded and never claimed as confirmed.
- Verified by `tests/test_evaluation.py` and `tests/test_extension.py` (18 agents, runtime contract). Not verified live: a creator run that goes through the reflection. Follow-up: tracker `N30`. Extension 0.7.0.

## D-047 — JSON evaluation contract, hook triggers by output kind, human verdict; install without setup; provenance check
- User decisions (2026-10-13, discussion in [research/findings/2026-10-13-evaluation-review-and-distribution.md](../findings/2026-10-13-evaluation-review-and-distribution.md)): JSON contract instead of the YAML subset (D-046); evaluation at the milestone plus on request; screenshots only for UI outputs; CLI/API logs recommended, not required; agents warn rather than hide when Python is missing; distribution by VSIX; agent composition and the harness-evaluation bridge deferred (`N31`, `N32`).
- Evaluation: `contract.py` lost its YAML parser and shares its JSON helpers with `workflow.py`. Each hook has `trigger` (`always`, `below-warning`) and `outputKinds`; optional hooks need a `recommendation`, which goes to the report's `recommendations` when they fail; every hook must be used by a rubric. `prepare` takes `--output-kind` and refuses when the delivered files' fingerprint equals the latest report's. `record-human` writes `human.json`; `check` exits 1 when the human asks for a revision.
- Install: the extension renders on activation (first install, update, Python change) with the first of `python`, `python3`, `py -3` that runs 3.11+. Without Python it renders hookless agents marked "(Needs Python)" with a warning, and shows a status bar item. Hooks create `.hve/runs/` and the profile on first use. OTel is its own command. Agents with SessionStart hooks tell the user to switch to Local when the hook context is missing. This deliberately runs without guards when Python is absent (an exception to fail-fast), but never silently.
- Provenance: `tools/observe/provenance.py <agent file> <session|latest>` checks the evidence each declared component leaves (skill loadout, profile, template registry and document validation, metrics events, loop state, evaluation report); `bench.py` logs it after every run.
- Verified by `tests/test_evaluation.py`, `tests/test_extension.py`, `tests/test_collect.py`. Not verified live: install on a clean profile with and without Python (`N33`). Extension 0.8.0.

## D-048 — Lifecycle-driven delivery agents, ask contracts, path-based loop guard
- User decisions (2026-10-15): fix the loop guard over-blocking; add `HVE e2e` (lifecycle baked into the plan), `HVE agile` (overlay with persona agents) and `HVE prototype` (UI/UX clickthrough, safety guards only); contract as a sibling `contract.json`; check in at every stage gate or sprint review.
- Loop guard: edit tools are matched on their target paths inside the project, not on the JSON content; shell commands only when they write; `feature_list.json`, `progress.txt` and `tracker.json` are released once every feature passes; `.harness/` stays protected. The old evaluation-input exception is no longer needed.
- Lifecycles: JSON in `templates/lifecycles/`, `plugins/*/lifecycles/` and `.hve/lifecycles/` (later wins). `lifecycle.py contract` checks each stage's skills against the loadout budget (fail fast), writes `.hve/asks/<slug>/contract.json` and `active.json`; the skill loader loads and allows the current stage's skills; `report` compares expected with the session's used skills and authored templates.
- `loop.py amend` appends features from `feature_list.add.json` between features; locked features never change. `HVE engineer` is the hidden feature worker; the UI/UX persona is `HVE prototype`.
- Deferred: moving the loop files and `.harness/` under `.hve/asks/<slug>/`, guard waivers after N trips, plan.md drift check (`N34`).
- Verified by `tests/test_loop.py`, `tests/test_skills.py`, `tests/test_extension.py` (22 agents). Not verified live. Extension 0.9.0.

## D-049 — Guard waivers, plan check, contract provenance
- User decisions (2026-10-15): defer moving loop files under `.hve/asks/<slug>/`; build guard waivers, plan checks and the provenance report next. Plan and delivery notes: [2026-10-15-harness-refactor-plan.md](../findings/2026-10-15-harness-refactor-plan.md).
- Waivers: `hooks/guard_policy.py` records every trip; from the 3rd trip of a waivable kind (`loop_guard/loop_files`, `skill_loader/skill_denied`, `module_guard/oversized_file`) the reason asks the agent to put a `guard-waiver:<guard>` question to the user. Only the PostToolUse answer of the ask-questions tool (from the user, not the agent) writes `.hve/runs/<session>.waivers.json`; a skipped or free-text answer keeps the guard on. `.harness/` state (now its own kind `anti_gaming`), escalation, bypass, pushes and the plan check are never waivable; an open evaluation run (contract.json without report.json) makes all guards strict.
- Plan check: `lifecycle.py plan-sync` stores the hash of `plan.md` as a revision with a one-line note; `hooks/plan_check.py` adds reconcile context on each prompt and denies `loop.py init/next/amend` and `lifecycle.py stage` while the hash differs, for edits by the user or the agent.
- Provenance: `lifecycle.facts` compares the contract with the session's facts (skills used, templates authored, plan sync, decisions, guard trips and waivers); `provenance.py` reports it as the `contract` component (failed on gaps in done stages or an unsynced plan) plus a `guards` summary for every agent.
- Verified by `tests/test_loop.py`, `tests/test_collect.py`, `tests/test_skills.py`, `tests/test_extension.py`. Not verified live. Extension 0.10.0.

## D-050 — Relevance-first skills without a cap, an ask contract for every agent, open tool lists, every harness
- User decisions (2026-10-19):
  - rank skills by relevance with status ignored and include the imported skills;
  - drop no skills, but flag a load over 2,000 tokens in `plan.md`;
  - sub-agents get the skills, MCP servers, plugin skills and rules;
  - work in every harness;
  - give every ask a contract of skills, tasks, personas and milestones;
  - provenance compares recommended with used;
  - remove `tools:` lists without a token blow-up;
  - OpenTelemetry comes later.

  Install level (my recommendation, user asked): user scope by default, project scope only for the cloud agent.
- Why the agents appeared only in Local:
  - `chat.pluginLocations` is read only by VS Code's Local harness.
  - Agent-scoped hooks and handoffs are Local-only (VS Code docs).
  - The Copilot harness and Copilot CLI read `~/.copilot` and `.github`, Claude reads `.claude`, and the cloud agent reads only the repository.
  - Copilot's config-file hooks drop prompt-submit output and add no context before a tool.
- Skills (`recommend.rank`):
  - Candidates are skills sharing a task category with the prompt, or rare words at relevance ≥ `loadout.keyword_floor` (0.5). The floor is my addition: without it the color-palette prompt loaded 17 skills (24,590 tokens), including keyword noise at 0.14.
  - Order is by relevance, then measured lift, then tokens; status only filters by the agent's floor.
  - Every candidate loads; `over_budget` flags more than 10 skills or 2,000 tokens. The `load-skills` offer is removed.
  - Known weakness: the `ux` category is broad (it holds `prd`, `power-automate-desktop` and `model-driven-app`), so the color-palette prompt still loads 14 skills (19,668 tokens). Category assignment needs a review.
- Ask contract (`tools/loop/lifecycle.py`):
  - `contract` (built-in lifecycle `direct` for agents without one; `+skill` to require one) records `skills`, `personas`, `tasks` (`tasks-sync`), `environment`, `delegations` and `reported`.
  - It installs the skills to `.hve/skills/` and writes a generated skills-and-tools block in `plan.md`, which the plan check's hash excludes.
  - `brief` gives each sub-agent its skills, plugin skills, MCP servers, rules and the `SKILLS-USED` reply line; `used` records that line; `close` and `open` toggle the active ask.
  - `tools/loop/environment.py` detects the harness, MCP servers per harness with an estimated tool load (`context_load.tool_load`: 1,500 tokens per server, warning over 6,000), Frontier HVE hook files and plugin skills.
  - All commands run in a terminal, so they work without hooks.
- Hooks:
  - `compaction.py` adds the ask's skills and the `SKILLS-USED` rule to every sub-agent.
  - When the prompt hook could not run, `skill_loader` derives the loadout from the open ask.
  - The PreToolUse and PostToolUse skill loaders carry `HARNESS_SKILLS_MIN_STATUS`.
- Tools: working agents have no `tools:` list. Council, evaluation-reviewer, flow-architect and flow-maintainer (read-only), skill-judge and skill-worker (blind) and minimal (baseline) keep theirs. Token cost is measured and warned about, not capped. The before/after benchmark gate (≤ +15% first-request and ≤ +10% total prompt tokens, from provenance) is not run yet.
- Every harness (`tools/adapters/export.py`, `hooks/agent_compat.py`):
  - Every HVE agent is exported, at `--user` or project scope.
  - `copilot` (user) writes `~/.copilot/agents`, `skills` and `hooks/hve.json`; `cloud` (project) writes `.github/...` with a committed runtime and `python3` hooks.
  - Copilot agents lose the Local-only fields; kept tool lists map to Copilot's aliases.
  - Hook files that every session runs use `agent_compat --ask-only` and act only while `.hve/asks/active.json` exists. Copilot payloads and outputs are mapped, with the timestamp as the tool call id.
  - **Frontier HVE: Install for other harnesses** runs the exports and sets `chat.hookFilesLocations` so Local does not run those files twice.
- Provenance: `lifecycle.facts.usage` and `report` add a recommended-against-used table:
  - skills, read (hook) or reported (self-reported);
  - personas, planned or delegated;
  - tasks;
  - MCP servers, called per the feature-loop tool log;
  - hook files and the hooks seen.

  `provenance.py` names the unused recommendations.
- Verified by `tests/test_skills.py`, `test_collect.py`, `test_hooks.py`, `test_adapters.py`, `test_extension.py` and `test_loop.py`. Not verified live:
  - the user-level folders for Copilot, Codex and Cursor skills;
  - the VS Code Copilot harness listing `~/.copilot/agents`;
  - Copilot's acceptance of PascalCase events and flat outputs;
  - the cloud agent run;
  - the benchmark gate.

  Extension 0.11.0.

## D-051 — Timestamped ask folders, topic-switch recommendations, a suggested skill set
- User decisions (2026-10-19): move each ask's files (`feature_list.json`, `progress.txt`, `tracker.json` and the rest) under `.hve/asks/<YYYYMMDD-HHMM>-<slug>/loop/`; recommend a new session or workspace when the topic switches; over 2,000 skill tokens, recommend a set under 2,000 or, if the user keeps all, record how much was cached. The user accepted all my recommendations below.
- Layout (`tools/loop/loop_paths.py`): with an ask open in the project, the loop files and loop state (`state.json`, `attempts/`, `evidence/`, `prs/`, `choices/`, `checks/`, `tool_log.jsonl`, `options/`, `flow.json`) live in the ask's `loop/`. With no ask open (research arms, `bench.py`, `collect.py`, trajectories) the old layout stays: loop files in the project, state in `.harness/`. Ask ids are UTC `YYYYMMDD-HHMM-<slug>`, checked wherever `active.json` is read; `contract` refuses an existing folder and copies the request to `request.md`.
- Git: `.hve/` stays ignored, so the loop files leave git. Commits keep a read-only record instead: `[init]` and `[amend]` bodies list each locked `name: verify`; `[progress]` names the check that passed. Commits are `--allow-empty` because a fresh repo may have nothing else to commit.
- Evidence: `loop.py` and the output evaluation run checks with `HVE_EVIDENCE` set to the evidence folder; `.harness/` patterns in the evaluation contract resolve to the ask's `loop/`.
- Guards: `loop_guard` protects the ask's `loop/` state always and its loop files while features fail; `flow_guard`, the plugin's choice recorder and guardrail, diagnosis, branch workflow, parallel options, flow and provenance all go through `loop_paths`.
- Topic switch (`lifecycle.topic_shift`): compares the prompt's subject words (stems without creation verbs and lifecycle fit words) with the open ask's request and task names. A different kind of deliverable (best-fitting lifecycle, e.g. `sdlc` against the new `document` lifecycle) with overlap under 0.2 recommends a new workspace; a prompt starting with a creation verb, at least 3 subject words and overlap under 0.2 recommends a new chat; anything else is a follow-up. `skill_loader` shows it once per ask per session (`systemMessage` plus context for the agent); `contract` records it as `previous_ask`. Never blocks. Heuristic, so false positives cost one line.
- Skills: `rank` adds `suggested` (required skills, then the most relevant per token that fit 10 skills and 2,000 tokens). For the color-palette prompt: 22 candidates at 29,574 tokens, suggested `ux-flows`, `api-design`, `ui-anti-slop`, `architecture-options` at 1,606. Agents ask once; `lifecycle.py skills suggested|all|<a,b>` records the choice with the tokens over the guideline and stops prompt ranking for the rest of the ask.
- Caching: `provenance.md` adds a skill-load line and a prompt-cache line from the session's metrics rows (cache reads against prompt tokens, measured from Copilot OTel), or "not measured" when the session has no metrics rows. Only the research arms run the metrics hook, so product-agent sessions read "not measured" until a metrics hook for product agents is added. Live OTel for product sessions stays deferred.
- New `document` lifecycle (brief, research, outline, draft, review) and `document` skill category; `prose-anti-slop` is tagged with it.
- `lifecycle.py` split: `tools/loop/ask_report.py` holds facts, usage, cache and the report (`lifecycle.py report` still works).
- Verified by `tests/test_loop.py` (ask-mode loop, evidence, guard), `test_skills.py` (choice, topic shift, suggested set), `test_collect.py` (paths, request copy, choice, cache line, new-workspace recommendation) and the full suite. Not verified live: the `systemMessage` in each harness, and the cache line on a real telemetry session. Extension 0.12.0.

## D-052 — Sign-off checklist in plan.md, persona hand-offs, opt-in evaluation and telemetry, one open ask per workspace, pillars in provenance
- User findings (2026-10-20 live tests of creator, e2e, agile, prototype): `plan.md` listed milestones but not personas per milestone, and nothing let the user tick milestones off after reviewing evidence; agile did not pause between personas; only creator and e2e evaluated; two parallel chats in one workspace opened separate ask folders, but the second (prototype) ran without a contract, run tracking or harness process. Nice to have: pillars in `provenance.md`, telemetry as a plan opt-in with a reminder to switch it off.
- Built:
  - `tools/loop/ask_plan.py`: a generated `<!-- hve:checklist -->` block in `plan.md` (options `opt:evaluation`, `opt:telemetry`; one `stage:<name>` per milestone with goal, persona, skills, templates, gate and status; one `task:<feature>` per feature with its check state and evidence folder). Sign-offs live in `contract.json` → `checklist`. `lifecycle.py tick <item> <value> [note]` records a form answer; ticks the user makes in `plan.md` are taken in on the next lifecycle write or `lifecycle.py checklist` (diffed against `checklist_rendered`, the last rendered state). The block, like the skills block, is excluded from the plan hash. A stage set back to planned loses its sign-off.
  - Agents ask sign-off forms: e2e at every gate, agile at every persona hand-off (pause, what was delivered and where, next persona), creator and the GitHub/flow variants for features with evidence folders, prototype and product manager for their deliverable.
  - Output evaluation: automatic for creator and e2e (`opt:evaluation on`), a checkbox for agile, prototype, product manager, creator-flow and creator-github; single only when the request asks. The steps moved into the plugin skill `output-evaluation` (agile and e2e used to point at "as HVE creator does", which a different agent cannot read). Outputs without a feature loop are evaluated; `locked-feature-checks` is marked not applicable with a reason (`notApplicableWhy`).
  - One open ask per workspace: `contract` refuses to replace an ask whose milestones are not done or whose requested evaluation has not run, unless `--replace` (recorded as a decision in the new ask). Agents end with `lifecycle.py stage deliver done`. Prototype (run directly) and product manager open their own ask; when their prompt starts with `Frontier HVE brief` they work inside the parent's ask.
  - `provenance.md` starts with a five-pillar table: quality (checks passing, sign-offs, latest evaluation) always; cost, tokens, latency and cache from metrics rows (research arms) or straight from the Copilot OTel export (`metrics.load_chat_spans`) when research telemetry is on. It lists the checklist and reminds to turn telemetry off.
  - Extension: **Frontier HVE: Turn off research telemetry** and a status bar item shown while the Copilot OTel export is on.
- Decisions to note for later features (surfaced, not settled):
  1. **Checklist schema.** Item ids `opt:`, `stage:`, `task:` and values `on|off|done`, `accepted|changes|skipped` are now a contract other tools may read (an Azure DevOps or GitHub sync of sign-offs would build on them). Asks from 0.12.0 get an empty checklist on first read.
  2. **"Continue without reviewing" ticks the box.** It counts as signed off (value `skipped`, shown as "continued without review"), so a full checklist does not mean everything was reviewed; the value says which. Alternative: leave such items unticked.
  3. **`plan.md` block is generated.** Only the checkbox state inside it is read back; other edits inside the block are overwritten. Ticks outside the block are ignored.
  4. **Parallel chats in one workspace are not supported concurrently.** There is one active pointer (`.hve/asks/active.json`) and the CLI does not know which chat runs it, so two chats would act on the same ask. The guard only stops silent replacement. Per-chat ask binding (session id → ask, an `--ask` option or environment variable for every ask-scoped command, hooks recording the binding) is deferred: hooks see the session id but cannot pass it to terminal commands, and sub-agent session ids are not verified. Recommendation until then: separate workspace folders or git worktrees.
  5. **"Finished" means milestones done.** Agents must close `stage:deliver`; one that forgets makes the next ask need `--replace`. Research arms do not use contracts and are unaffected.
  6. **The `Frontier HVE brief` header is an agent-to-agent protocol** that tells a persona not to open its own ask; its first words must stay stable.
  7. **Prototype lost `agents: []`** so its opt-in evaluation can run reviewer sub-agents; its only hook is still the loop guard.
  8. **Evaluation without a loop passes on rubrics and council alone.** A future option is a per-output-kind check (document lint, link check) so documents get a deterministic gate too.
  9. **Telemetry is a global VS Code user setting.** The ask records intent only; turning it on records every chat in every workspace to the open workspace's file until switched off, and it measures chats started afterwards (a window reload may be needed). The status bar item is the safeguard; per-ask scoping is not possible with the Copilot settings.
  10. **Product-agent pillars read the OTel export directly** (no metrics hook, no tool-call join), so tool-level latency and failures are not attributed; `provenance.md` must be generated from the workspace root.
  11. **Two copies of the evaluation steps**: `HVE creator` keeps its inline steps, the other agents use the `output-evaluation` skill; they can drift. Moving creator to the skill is a follow-up once the skill is verified live.
- Verified by `tests/test_collect.py` (checklist from form and `plan.md`, values, sign-off reset, open-ask refusal and `--replace`, pillars from metrics rows, telemetry reminder), `test_evaluation.py` (no-loop output), `test_extension.py`, `test_flow_plugin.py` (13 plugin skills) and the full suite. Not verified live: the forms in each agent, persona hand-offs, the OTel-derived pillars, the status bar item. Extension 0.13.0.

## D-053 — Agent ledger and Agents table; parallel asks open their own folder instead of being refused
- Discussion: `research/findings/2026-10-21-parallel-sessions-and-agent-ledger.md` (diagrams and examples).
- Agent ledger: new hook `hooks/agent_ledger.py` on `SubagentStart` and `SubagentStop` of creator, e2e, agile, product manager, creator-flow and creator-github writes `.hve/runs/<session>.agents.jsonl` (time, session, ask, parent agent from the ask's contract, sub-agent name and id, and the model when the client sends one: Cursor and Codex). Not the tool log: that exists only during a feature loop and feeds loop diagnosis.
- Agents table in `provenance.md`, across every session of the ask: parent agent, sub-agent, id, session, start, seconds, the brief logged just before the start (role and skills), the skills that role reported, and the model (client payload, else OTel spans of sub-agents inside the start-stop window, else "not measured"). Both joins go by time; the harness sees no id that links a brief or an OTel conversation to a hook's `agent_id`.
- Parallel asks (user decision, reverses the D-052 refusal): `contract` always opens the new ask in its own folder and reports the ask it left open as `previous_open` (also a decision in the new ask); `--replace` is removed. Minimal safety: `skill_loader` remembers which ask a chat opened (after its `lifecycle.py contract|open` command) and, when another chat has moved the open-ask pointer, tells the chat once before its next tool call to run `lifecycle.py open <its ask>` and to tell the user that parallel builds belong in separate folders or git worktrees.
- Not built (recommended against): worktree creation commands and copying `.hve` settings between folders (a worktree gets its own `.hve/` on first use), and per-chat ask binding for every command (terminal commands cannot know their chat).
- Decisions to note: the notice relies on the agent re-opening its ask (instruction-level, not enforced); prototype has only the loop guard, so a displaced prototype chat is not told; two feature loops in one folder remain impossible (one git checkout); branch names are shared across worktrees, so parallel asks need distinct feature names (an ask-scoped branch prefix is optional and not built); `SubagentStop` on the parent agent and in Copilot's `hve.json` is not verified live.
- Verified by `tests/test_collect.py` (ledger hook rows, Agents table with brief, reported skills, client and OTel models, `previous_open`), `test_skills.py` (one-time displacement note) and the full suite. Extension 0.14.0.

## D-054 — One project per workspace, continuation of asks, engineer stages as loops, prototype self-check, three renames (2026-10-21 17:26 UTC)
- Findings, discussion and the user's decisions verbatim: `research/findings/2026-10-21-1856-feedback-project-level-continuation-renames.md`.
- User decisions:
  1. **Project level.** Each ask keeps its own implementation `plan.md`, and one central project feature list is shared by all asks.
  2. **Continuation.** A returning user or a follow-up continues the open ask; a new ask opens only for new work, and the agent confirms the choice with the user.
  3. **Activity log.** No per-session activity log; the agent ledger is enough.
  4. **Prototype.** A self-check script plus screenshots.
  5. **Renames, only these three.** E2E becomes **Frontier E2E Delivery**, agile becomes **Frontier BYOW** (Bring your own way of working), and prototype becomes **Frontier Prototype Creator**.
- Built:
  - **Project folder.** `.hve/project/` holds `project.json` (name, goal, kind, asks), `feature_list.json`, `feature_list.add.json`, `progress.txt`, `tracker.json` and `state.json`. Each ask keeps its attempts, evidence, PR records, choices and tool log in `.hve/asks/<id>/loop/`.
    - `tools/loop/loop_paths.py`: an external edit, adopted.
    - The lock records the ask that added each feature, and the tracker takes evidence from that ask.
    - A second `init` fails and points to `loop.py amend`.
    - `tasks-sync` and the quality pillar count only the ask's own features.
    - The guard protects `.hve/project/`.
  - **Continuation and paths.**
    - `lifecycle.py where [request-file]` prints the project, the open ask with its paths and unfinished items, and a verdict: `continue`, `new-ask`, `new-workspace` or `new-project`.
    - `lifecycle.py open` prints the ask's paths and open items.
    - Every ask-opening agent runs `where` and confirms the verdict in one form; `HVE single` follows the verdict.
    - The skill loader adds the open ask's paths to every prompt, and the compaction hook gives every sub-agent the ask folder and evidence path. Agents never search for `plan.md`.
  - **Different project.** `topic_shift` compares a prompt with the project's text (goal, asks, features) and returns only `new-workspace`; `new-session` is removed.
  - **Engineer stages.** Agile's sprint build and E2E's build stage are feature loops the orchestrator runs, one `HVE engineer` per feature, and the engineer refuses a whole-stage brief.
  - **Prototype self-check.** `tools/prototype/check.py lint` checks the prototype's safety rules, its screens and its `#` links. `check.py shots` saves headless Edge or Chrome screenshots to the ask's `loop/evidence/prototype/`. Both run before the sign-off form.
  - **Renames.** Display names and detailed descriptions with example uses for `hve-e2e`, `hve-agile` and `hve-prototype`; file ids are kept. The lifecycle JSON files, wiki and tests are updated.
- Decisions to note:
  - There is no `roadmap.md`: `project.json` and the project feature list are the central record.
  - Features from abandoned asks stay locked; there is no retire status.
  - "New chat" is no longer recommended: one workspace holds one project.
  - Continuation depends on the agent instructions and is not enforced.
  - Tool logs stay per ask and are written only while a loop runs.
  - Screenshots need a local Edge or Chrome, and the lint is static.
  - `where` verdicts are heuristic, and the user's answer wins.
  - Loops started under 0.12 to 0.14 kept their files in `<ask>/loop/`. There is no migration: restart them.
- Verified by `tests/test_collect.py` (`where` verdicts, `project.json`, project paths), `test_loop.py` (project-level files, the lock's ask, guard, prototype lint and screenshot with Edge), `test_skills.py` (paths on every prompt, new-workspace message), `test_hooks.py` (sub-agent paths), `test_adapters.py` and the full suite. Not verified live: the forms, continuation across chats, and the agile and E2E loops. Extension 0.15.0.

## D-055: three visible agents on top models, a wow-uplift loop, and the NorthStar presentation skill (2026-10-21)
- Requests, sources, what was built and the open points: `research/findings/2026-10-21-2000-frontier-agents-uplift-presentation.md`.
- **Visible agents.** The extension shows only Frontier E2E Delivery, Frontier BYOW and Frontier Prototype Creator.
  - Every other user agent gets `user-invocable: false`: creator, creator-flow, creator-github, single, minimal, product-manager, skill-evaluator and azure-devops. They still ship and can run as sub-agents.
  - The research arms in `.github/agents/` stay user-invocable in this workspace.
- **Models.** The three agents and `HVE uplift-judge` pin `model: [GPT-6 Astra, Gemini 4 Argon, Claude Fable 5, Claude Opus 5.5]` (all "(copilot)"; VS Code uses the first one available) and set `reasoning-effort: high`.
  - VS Code ignores `reasoning-effort` in agent files (D-020).
  - The Copilot export strips both fields.
  - This reverses the D-050 rule that product agents use the model the user picks.
- **Wow uplift (every deliverable the user sees).** A new plugin skill, `wow-uplift`, and a new hidden read-only judge, `HVE uplift-judge` (returns JSON). The loop runs up to 3 rounds:
  1. The judge names two or three targeted changes.
  2. The changes are applied.
  3. Every check is re-run.
  4. The same views are captured again into `loop/evidence/uplift/round-<n>/`.

  The loop stops when the judge returns `done`, after round 3, or when every change in a round had to be dropped. `uplift.md` records before and after.
  - E2E runs it before each gate whose stage produced something the user sees.
  - BYOW runs it before such persona hand-offs.
  - Prototype Creator runs it before its sign-off.
- **Presentation skill.** A new plugin skill, `presentation-deck`, based on the user's NorthStar `python-pptx` builders:
  - a discovery form (kind of deck, audience, theme, text level, how visual, speaker notes, length, logo);
  - a story spine for each kind of deck;
  - the visual grammar and a table that turns text into smart art;
  - `deck_kit.py` (slide primitives) and `check_deck.py` (lint, plus PowerPoint previews).

  The `document` lifecycle's draft stage lists the skill, and E2E and BYOW must use it for any deck.
- **Open points (to decide):**
  - The two model names "Gemini 4 Argon" and "Claude Fable 5" are inferred.
  - The hidden skill-evaluator and azure-devops have no visible copy anywhere.
  - A prototype running as a sub-agent may not be able to start the judge (BYOW then runs the uplift).
  - The uplift costs up to 3 top-model calls per deliverable.
  - `python-pptx==1.0.2` is a new dependency.
  - Previews need PowerPoint on Windows.
- **Verified:**
  - The full suite passes:
    - `test_extension` checks 23 agents and 15 skills, the visibility, and the model pins;
    - `test_flow_plugin` checks that 15 plugin skills pass the scan.
  - A smoke deck and the skill's example deck were built, linted and previewed with PowerPoint.
  - Not verified live: the judge, the uplift loop and the presentation form.
  - Extension 0.15.0.

## D-056: loop guard awareness mode, error-streak guard, telemetry trim, per-ask skill scoring (2026-10-21)
- Requests, findings and the open points: `research/findings/2026-10-21-2130-guard-awareness-error-streak-telemetry-skills.md`.
- **Loop guard awareness mode.** Temporary, switched in `hooks/guard_mode.json` (`advise`, or `enforce` to block again).
  - Loop-file edits, loop-state edits and the victory check no longer block.
  - They record the trip and show "Guard Invoked - For your attention: during the run ... The modification was ..." to the user. The agent relays it word for word.
  - Escalation, hook bypass, resume and push rules still block.
- **Error-streak guard** (`hooks/error_guard.py`; E2E, BYOW, Prototype Creator, engineer): this guard was missing.
  - After 3 failed terminal commands in a row, it stops the agent with "Error guard - paused for your attention", the commands and their output.
  - Feature-loop scripts are excluded.
  - Tools other than reading and asking stay held until the user's next prompt.
- **Telemetry trim** (`tools/observe/otel_trim.py`): the extension runs it on every activation (when the export exists) and when telemetry is turned on.
  - It keeps the last 3 days of the export, at most 200 MB, rewritten in place.
  - It adds the export to `.gitignore` and tells the user what it did.
  - It refuses during a benchmark run.
- **Skills (corrected by the user the same day: do not curtail the shortlist):**
  - The rank shortlists every relevant skill, with no cap, ranked by relevance.
  - Within the guideline (10 skills, 32,000 tokens; up from 2,000) all of them load.
  - Over it, the agent scores each shortlisted skill 0-10 for the ask across its stages and runs `lifecycle.py skills score`, which re-ranks and suggests the required plus the top-scored up to 10.
  - The agent then shows the user the suggested skills with scores and reasons and asks: suggested, all or named.
  - Scores show in `plan.md`.
- **Open points:**
  - The streak limit is 3 (the user said 3-5).
  - Awareness mode also applies to the research arms.
  - Copilot CLI and Cursor drop the awareness message.
  - The trim deletes old spans that reports or uncollected benchmarks may need.
  - Scoring is an agent judgement.
  - `lifecycle.py` is at 495 lines.
- **Verified:**
  - `test_loop`: awareness messages; push still blocked; error streak pause, hold and reset.
  - `test_adapters`: Claude Code shows the awareness message; denies in enforce mode.
  - `test_metrics`: trim and `.gitignore`.
  - `test_skills`: the uncapped ranked shortlist and the suggested set.
  - `test_collect`: `skills score` suggests without dropping.
  - The full suite passes.
  - Not verified live.
  - Extension 0.15.0.

## D-057: plugin skills are part of the ask contract; a deck request always carries presentation-deck (2026-10-22)
- **Finding:** the user's live test (Frontier E2E Delivery, "create a deck ... 10-12 slides") showed "presentation deck skill not picked up".
  - The transcript shows the agent did read `presentation-deck` and planned with `deck_kit.py`, but only after it had already shown the plan.
  - The user never saw the skill: the skills form and `plan.md` list only library skills (16 shortlisted, several weakly related), and plugin skills sat only in stage briefs.
  - The deck discovery form (kind, theme, text level, notes) was never asked.
- **Built:**
  - `contract` records `skills.plugin`: the plugin skills of the ask's stages, plus `presentation-deck` for any request that mentions a presentation, deck, slides or pptx.
  - `plan.md` lists them as "always on, outside the skill budget", and briefs pass them to sub-agents.
  - E2E and BYOW show them whenever they show skills, and for a deck read `presentation-deck` and ask its discovery form before writing the plan.
  - The `document` lifecycle no longer names the deck skill for every document (a memo is not a deck).
- **Verified:** `test_collect` (a deck request lists `presentation-deck` in the contract and `plan.md`; a palette page does not) and the full suite. Extension 0.15.1.
- **Follow-up (user, same day):** the NorthStar deck was given only as a style reference, and agents should never need it. `presentation-deck` now states that the NorthStar style is built in (`deck_kit.py`, the visual grammar). A linked or named NorthStar deck means "use this style": never fetch, download, open or ask for it. A template `.pptx` is used only when it is already in the workspace. Extension 0.15.2.

## D-058: review questions link their files, the advisory alert is renamed, HVE creator is back in the picker (2026-10-22)
- **Live feedback:**
  - A gate asked "Accept this research and story direction ...?" without a link to anything, so the user could not see what to review.
  - The "Guard Invoked - For your attention" note read oddly.
- **Built:**
  - **Review links.** Every sign-off question (E2E gates, BYOW hand-offs, Prototype Creator, product manager, creator feature sign-off) puts a markdown link to each file and evidence folder to review in the question's message, each with one line on what to look at. It never asks for a review without them.
  - **Advisory alert.** The loop guard's awareness note now reads "Advisory alert (experimental): surfaces LLM behaviour that helps to know. During the run ...".
  - **HVE creator in the picker.** It is user-invocable again, with the same top-model list and `reasoning-effort: high`, and gains the error guard. Creator is the hook source for other harnesses, so the error guard is now also exported to them.
- **Verified:** the full suite. Extension 0.15.3.

## D-059: frontend-slides joins presentation-deck as a plugin skill; the AGPL and image-API deck skills are left out (2026-10-22)
- **Request:** add the presentation skills from open-design.ai's "Claude PPT skills" post, except PPT Master, and make sure a presentation ask picks them up.
- **Assessed:**

| Skill | Licence | Size | Decision | Why |
|---|---|---|---|---|
| frontend-slides (`zarazhangrui/frontend-slides`) | MIT | 3.4 MB, about 1.7 MB as text | Added | Animated single-file HTML decks, 12 presets plus 34 bold templates |
| guizang-ppt-skill | AGPL-3.0 | 5.8 MB | Left out (user) | Shipping AGPL inside the extension puts AGPL obligations on it |
| dashiAI-ppt-skill | AGPL-3.0 | 57.7 MB (fonts, vendor JS, npm project) | Left out (user) | Same licence issue, plus size |
| codex-ppt-skill | MIT | 42.8 MB | Left out (user) | Renders each slide through an external image-generation API with a key |

- **Built:**
  - `plugins/harness-assist/skills/frontend-slides/` holds the MIT text files at commit `9906a34`, with `LICENSE` and `NOTICE.md`.
  - Removed from the copy: `deploy.sh` (publishes decks to a public Vercel URL, a client-data risk), `export-pdf.sh` (bash, downloads Chromium), the README and screenshots. Phase 6 now keeps decks in the workspace and makes PDFs through the browser's print dialog. One template phrase was reworded so the skill scan passes.
  - `presentation-deck` stays the router. Its discovery form asks the format first: an editable NorthStar `.pptx` (recommended) or web slides. Web slides go on to `frontend-slides` from its style previews, with previews in the evidence folder and the deck at `presentation/<slug>/index.html`.
  - Any deck request adds both skills to the contract's `skills.plugin` and `plan.md`. E2E and BYOW name both and the format question.
- **Verified:** the scan passes (16 plugin skills), `test_collect` checks both skills on a deck request, and the full suite passes. Extension 0.15.4.

## D-060: expertise packs (the plugin architecture) route into the E2E and BYOW lifecycle contract, with their token load recorded (2026-10-22)
- **Request:** bring the plugin architecture of branch `plugin-architecture/pj-1013` into E2E and especially BYOW: tribal knowledge per practice (skills, overlays, process maps, templates) with routing in a manifest, so the model reads the manifest and not the folder. Later in the same request: the plan, the contract and the provenance must capture the packs in use and their context contribution in tokens, absolute and relative.
- **Found:** the branch holds only the design plan. The code is open PR #8 (`feature/plugin-architecture`, jnPiyush; its decision D-048 clashes with ours). It is built on an older main; at its HEAD the skill loader's plugin routing calls removed functions; routing is a yes/no match; the process is a creator-flow graph; there are no knowledge documents.
- **Decided with the user (discussion first):** port selectively (PR #8 at `be8284a`, credited); lifecycles are the only process format, with optional stage `evidence` and a capped `rework` step taken from the flow graphs; a manifest `knowledge` section with `use_when`; packs from the workspace (`plugins/<pack>/`) and the installed store; pack rubrics now.
- **Built:**
  - `tools/plugins/` (manifest, route, store, plugin, author), `schemas/hve-plugin.schema.json`, `tools/evaluation/compose.py`, and the Oracle sample rewritten with a lifecycle overlay (evidence, rework) and two knowledge documents. Manifest keys: `flows` replaced by `lifecycles` and `knowledge`; every asset is measured in tokens.
  - `tools/loop/lifecycle_catalog.py` (catalog, pick, `route`: packs named, missing, matched with why; matched packs' overlays first), `ask_packs.py` (the pack choice check, the contract record, the token load, brief and plan lines, the provenance table) and `stage_evidence.py` (evidence checks, rework), keeping `lifecycle.py` at 497 lines.
  - `contract ... @<pack>|@core` records `packs` and `pack_load`; it refuses an offered pack choice left unrecorded and a pack lifecycle without its pack. `stage <s> done` refuses missing evidence; `rework <s> <why>` steps back within the cap.
  - Token load per pack: always loaded (manifest index, knowledge index, its lifecycle, its selected skills) and on demand (knowledge documents, agent prompts, templates), absolute and as a share of the ask's contracted context and of a 128K window; in the provenance also of the first and peak measured prompt. In `contract.json`, `plan.md`, `provenance.md` and `.hve/runs/<session>.provenance.json`.
  - Skill loader: pack skills load as `<pack>:<skill>` into `.hve/skills/<pack>__<skill>`; skills of packs the ask did not choose are denied. Template manager: `<pack>:<kind>` and `plugin:<pack>/<kind>@<v>`. Output evaluation: `--plugin-contract` and `--rubric-selection`.
  - Extension: Install plugin and Manage plugins commands, `frontierHve.pluginIndex`, reconcile and requirements on start, pack agents rendered as `<pack>:<agent>` with core hooks (`extension/packs.js`, `render.js renderPacks`).
  - E2E and BYOW: `route` first, the `Expertise packs` question, `@pack` contract arguments, pack load shown, pack knowledge per stage, evidence and rework. Wiki `Plugins.md`.
- **Not ported:** creator-flow pack flows, per-prompt plugin routing in the skill loader for the creator agents, export of pack agents to other harnesses (briefs name the agent file instead), the wrapper-extension API.
- **Verified:** new `tests/test_plugins.py` (validation, install lifecycle, archive and index, routing into the contract with token load, plan, brief, provenance, skill allow and deny, pack template, evidence, rework cap, rubric composition, rendering, author kit) and the full suite. Extension 0.16.0. Not verified live.

## D-061: a solution map for any repository, read by concept in chat and in an offline explorer (2026-10-23)
- **Request:** a flag for medium and larger apps and a map that saves context (TDS `docs/design/TDS-solution-map.md`); then: build it for this repo first and perfect it, add a UI like Graphify but different (force diagram, Cypher and fuzzy search, two levels open, expand on demand), make it understandable by concept (Concept, Modules, Files, Functions, Connections, Dependencies, explanation), filter with a clear way back, add a tree and zoomable circles, make it work on any repository, and answer "help me understand <topic>" in Copilot, Claude Code and Codex with a slash command.
- **Decided with the user:** size thresholds medium 50 files or 5,000 lines, large 300 or 50,000 (Q-1); no fresh sub-agent at the 25% checkpoint (Q-2); release snapshots committed to `docs/architecture/` (Q-3); no stack-specific framework conventions first (Q-4); views ordered Tree, Circles, Force.
- **Found while prototyping:** word matching cannot pick an impact's start points (agent-picked seeds work); views, modules and purposes are a reviewed file, not code; read against write on data stores is not extractable by text (`uses` from code, `writes` curated).
- **Built:** `tools/map/extract.py`, `map_build.py`, `solution_map.py` (build, explain, impact, search, overview, status, open) with no repository-specific code; `docs/architecture/solution-map.config.json` (views, modules, purposes, stores, 16 concepts, conventions, flows); `tools/map/explorer/` inlined into one offline page; plugin skill `solution-map` (17 plugin skills) followed by E2E, BYOW and HVE creator; wiki `Solution-Map.md`.
- **Verified:** `tests/test_map.py` (generic map without config on a Python and TypeScript fixture, concepts and explain, impact, status, offline page with the Cypher engine run in Node, this repo's config) and the full suite; the unrelated Next.js benchmark app mapped without config; the explorer checked in the browser (filters, Back, Show whole map, queries, views, canvas sizing). Extension 0.17.0. The chat path is not verified live.

## D-062: Frontier HVE Auto and Collab, 18 personas from a catalog, stage entry with a project ledger (2026-10-23)
- **Request:** Frontier agents start on Claude (Opus or Fable, highest available), then GPT Astra, then Gemini Argon; rename Frontier E2E Delivery to Frontier HVE Auto (autonomous end to end) and Frontier BYOW to Frontier HVE Collab (come in at any stage, run all or one, invoke a persona with its own skills, MCP servers, plugins and knowledge packs, each visit its own ask with the whole project tracked); personas TPM, DS, Solution Architect, DB Engineer, DevOps Engineer, Security Architect, DB Architect, Engineer, Test Engineer, Test Architect, UX Designer, UI Engineer, and Code, Architecture, Security, UX, Test and Product Reviewers.
- **Decided with the user:** one persona catalog rendered into agents; each Collab entry is a new ask scoped to its stages with a project stage ledger; a matching pack lifecycle replaces the stage plan in the same ask; Auto pauses only at the milestones the user ticks; all 18 personas now with minimal skills; HVE product-manager covers TPM and HVE engineer is the Engineer.
- **Built:** model lists `Claude Opus 5.5, Claude Fable 5, GPT-6 Astra, Gemini 4 Argon` for the Frontier agents and HVE creator; display names `Frontier HVE Auto` and `Frontier HVE Collab` (files stay `hve-e2e`, `hve-agile`); `templates/personas/` (catalog and builder, designer and reviewer templates) and `tools/loop/personas.py` (validate, render, match, check) rendering 16 agents at build; lifecycle `team-delivery` with a stage per persona and `loop: true` on build stages (also on sdlc build and agile sprint-build; sdlc design goes to the solution architect); `tools/loop/ask_project.py` (project functions moved out of lifecycle.py, plus `ledger`); `contract ... only=<stages> for=<lifecycle>:<stage> gates=ticked`; `gate:<stage>` checklist items; briefs name the persona's role, stage goal and gate; Collab and Auto prompts; wiki Agents.
- **Verified:** `tests/test_personas.py` (catalog current and every lifecycle agent exists, scoped asks, pack lifecycle for a stage, ledger across asks, ticked gates) and the full suite. Extension 0.18.0. Not verified live.

## D-063: Mission Control, a sidebar UI inside the Frontier HVE extension, and no extension dependency on Copilot Chat (2026-10-28)
- **Request:** a UI for the harness operated from the left side panel; ideas and a visual example; the user chose the card-based "Mission Control" (sidebar plus Overview, Evidence and Approvals in the editor), live and integrated with the harness. First built as a separate companion extension; after a pilot editor could not load it, the user asked to build it in this project without breaking anything existing.
- **Found:** the pilot editor's bundled Copilot Chat was disabled (API proposal mismatch), and `extensionDependencies: ["GitHub.copilot-chat"]` then disabled Frontier HVE and everything depending on it. The extension calls no Copilot Chat API: it writes `chat.*` settings and runs Python tools. The original `tick` acts on whichever ask is active when it runs, so a stale screen could sign off a different ask.
- **Decided with the user:** a small guarded review API in the core (`lifecycle.py review-status` and `tick-for`, exact ask and review revision, the original `tick` unchanged); UI code kept apart in `extension/ui/`; Mission Control registers first in `activate` so a later setup failure cannot hide it; it uses the extension's own Python detection and runtime, with no settings of its own.
- **Built:** `extension/ui/` (views, read-only state reader, task and review workflow over an allowlist of lifecycle operations, escaped rendering with a strict content security policy), five `frontierHve.*` commands and the `frontierHve` Activity Bar container; removed `extensionDependencies`; wiki `Mission-Control.md`; `npm --prefix extension run test:release`.
- **Verified:** `tests/mission-control/` (36 Node tests, real lifecycle subprocesses in temporary projects), `tests/test_ui_reviews.py`, the full Python suite, a strict type check, and the release check: the VSIX keeps all 41 agents, skills and runtime files, installs into a throwaway profile, and with Copilot Chat disabled activates on startup, renders its agents and opens Mission Control on a live ask. Extension 0.19.0. Agent runs started from Mission Control are not verified live.

## D-064: Mission Control follows the agent live, shows the plan, and replaces the telemetry question with a switch (2026-10-28)
- **Request:** the user found 0.19.0 poor: it did not update while lots was happening, put the whole request in the sidebar as the current task, gave no readable view of `plan.md` to edit, ran pack commands without saying what they do, and Continue in Chat put the whole task prompt in the Chat input where an accidental Enter restarts the work. Redo it to be helpful and live; remove Continue in Chat; keep the research telemetry button and drop the telemetry question from the agents' optional questions; confirm the updated `wow-uplift` skill is available.
- **Found:** in a real Pawstagram session the harness files barely change while the agent works (an ask, a plan with only generated sections, an error-guard record, a skill load), so a view of them looks frozen. Copilot Chat writes a per-window transcript (`workspaceStorage/<id>/GitHub.copilot-chat/transcripts/<session>.jsonl`: turns, tool calls with arguments, results, messages) and its telemetry spans name the session (`gen_ai.conversation.id`); aborted calls carry no usage. Installed 0.19.0 and its rendered plugin still had the old `wow-uplift`; the repository has the new one (`0ed5927`).
- **Decided:** read the transcript for live activity (status, current step, to-do list, files, commands, failures), the session's run files (error guard, skill load, guard alerts) and, when on, telemetry tokens per model; refresh within a second of a change while a view is visible; render in the webview from a JSON model with allowlisted tags and attributes and no HTML strings; plan as formatted Markdown with Edit opening `plan.md` beside; no Chat drafts; the telemetry switch runs the extension's own commands; `opt:telemetry` leaves the plans, agents and docs, and the report reminds to switch telemetry off only when it measured the ask. A transcript format change shows as an error in the Live section only.
- **Built:** `extension/ui/activity.js`, `media/vnode.js`, `markdown.js`, `views.js` (sidebar), `pages.js` (Live, Plan, Progress, Skills and packs, Settings), new `app.js` and `app.css`; controller rewrite (watchers on `.hve/**` and the transcript folder, pack list, telemetry switch, `frontierHve.editPlan`, no `continueInChat`); `opt:telemetry` removed from `ask_plan.py`, eight agent prompts and the wiki; `tests/mission-control/preview.js`.
- **Verified:** `tests/mission-control/` (57 Node tests), `tests/test_telemetry_switch.py`, the full Python suite, a strict type check, the previews of the real Pawstagram session at 250, 320, 400 and 1180 px, and the release check: installed from the VSIX with Copilot Chat disabled, the current `wow-uplift` rendered, no Continue in Chat, and new transcript lines shown live through VS Code's file watcher. Extension 0.20.0. A live agent session in the user's editor is not verified here.

## D-065: Mission Control navigates asks and links chats to them (2026-10-28)
- **Request:** open a session and, within it, new asks; each New ask creates a folder under `.hve/asks/`; asks in a dropdown; each ask folder and its contents easy to navigate. The user then restated the definition: an ask is a distinct piece of work within a project, not every chat; agents run `lifecycle.py where` and confirm continuing the open ask, a new ask or a new workspace; follow-ups reuse the folder through `lifecycle.py open <ask-id>`; new asks use `contract`, creating `.hve/asks/<YYYYMMDD-HHMM>-<slug>/` (UTC, duplicates fail); `active.json` points to the open ask and earlier folders stay; features, progress, tracker and state stay shared under `project`.
- **Found:** Copilot Chat transcripts record each `run_in_terminal` command with its time, so a chat that ran `lifecycle.py contract <lifecycle> <slug>` matches the ask folder of that slug created in the same UTC minute or shortly after, and `open <ask-id>` names the ask; edits under `.hve/asks/<id>/` show which ask a chat worked on. The skill loader records an ask only for agents with its hook, so it cannot link every chat. `workbench.action.chat.open` and `workbench.action.chat.newChat` exist in VS Code 1.140 without Copilot Chat.
- **Decided:** one ask has many chats; a chat is linked to the asks it created, reopened or edited files in, to the ask it was opened for from Mission Control (the first chat started within an hour after New ask or New chat for this ask), or to the ask you link it to by hand; links made in Mission Control live in its window state, never in harness files. The dropdown only changes what Mission Control shows; **Make active** confirms and runs `lifecycle.py open` (added to the allowlist); sign-off only for the active ask. **New ask** takes one input, runs `where`, offers Continue the open ask on a follow-up, proposes a name from the request (editable), creates the ask with `contract` and opens an empty chat (never prefilled). Features and progress stay project-wide, each feature showing its ask. A Files page shows the ask folder as a bounded tree; links are listed, never followed.
- **Built:** `extension/ui/asks.js` (asks, folder tree, proposed name), `chats.js` (incremental transcript index and links), `actions.js` (user actions moved out of the controller); `snapshot(workspace, selected)`; `activity()` for one chosen chat; dropdown, viewing notice, chat list, Files page in `views.js` and `pages.js`; `select` and `option` in the view allowlist; `frontierHve.newTask` renamed `frontierHve.newAsk`.
- **Verified:** loop features `ask-picker`, `ask-files` and `chat-per-ask` (`tests/mission-control/asks.test.js`, `files.test.js`, `sessions.test.js`, real lifecycle subprocesses); 74 Mission Control tests; a strict type check; previews of a scratch project with three real asks and the real Pawstagram chat at 250, 320 and 1100 px; and the release check: installed from the VSIX with Copilot Chat disabled, the dropdown lists the active ask, the Files page shows its folder, the chat and Explorer commands exist, and a chat that reopens the ask is linked live. A live agent session in the user's editor is not verified here.
