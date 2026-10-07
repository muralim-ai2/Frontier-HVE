# Implementation Plan: Enterprise AI Harness

Oct 6, 2026 · @Muralidharan

Build order: scaffold → 3 modes with metrics → tokenomics → memory → Anthropic loop → observability → metrics priority + research notes → anti-vibe-code guardrails + git workflow → SkillOpt gate → selective adoption + adapters. Each phase testable independently. Decision priority: Quality (human blind test) > token usage > latency > caching.

## Phase 1: Scaffold (Day 1 morning)

Goal: repo exists, SDK runs, all 3 modes are defined, color palette prompt is the first test.

| Step | Action | Done when |
| --- | --- | --- |
| 1.1 | `Open VS Code with GHCP extension active. Confirm access to frontier models (Astra, Fable, Qwen, etc.) via model picker. No SDK install needed — the harness runs through VS Code + GHCP CLI + .agent.md custom agents` | `GHCP chat responds in VS Code. /model shows available models. copilot --agent minimal works from terminal` |
| 1.2 | Create repo: `enterprise-harness/`. Add `.github/agents/`, `tools/`, `skills/`, `hooks/`, `tests/` dirs | `ls` shows structure |
| 1.3 | Copy color palette prompt from the Google Doc into `tests/prompts/color-palette.md` verbatim — this is the test prompt for all 3 modes | File exists, content matches doc |
| 1.4 | Create `minimal.agent.md`: no tools, no MCP, no skills, no custom agents. Just the raw system message + the prompt. Pin one model (e.g. `model: claude-sonnet-4-20260514`) | Agent invokable via `copilot --agent minimal` |
| 1.5 | Create `single.agent.md`: same pinned model + best-practice system message ("be concise, define done, verify before declaring success") + `tools: [file_write, file_read, shell]` + ripgrep override. No MCP, no sub-agents | Agent invokable, has tools |
| 1.6 | Create `creator.agent.md`: same pinned model + curated skills (tdd, diagnose) + MCP servers (CodeGraph, Headroom) + sub-agent capability via `tools: [agent]` + governance hook | Agent invokable with full stack |
| 1.7 | Create `hooks/metrics.py`: a minimal `onPostToolUse` hook that logs `prompt_tokens`, `context_tokens`, `cache_tokens`, `completion_tokens`, `model`, `tool_name`, `latency_ms` to a JSONL file per session | Hook fires, JSONL grows on each tool call |
| 1.8 | First smoke test: run the color palette prompt through `minimal` mode. Capture output + metrics JSONL. This is the baseline | Output exists, JSONL has at least one entry with all 7 fields |

## Phase 2: Three Modes + Metrics (Day 1 afternoon – Day 2)

Goal: run the same color palette prompt through all 3 modes, capture comparable metrics, prove the harness adds measurable value.

### Mode definitions

| Mode | What it is | What it proves | Tools/MCP/Skills |
| --- | --- | --- | --- |
| **Minimal** | Raw prompt → pinned model → output. No tools, no system message beyond identity. Pure prompt engineering ceiling. | Baseline cost and quality. What the model does with nothing but the prompt. | None |
| **Single** | Same model + best-practice system message + tools (file I/O, shell, ripgrep) + "be concise; define done; verify before declaring success" instruction. One node, improved. | What good prompt engineering + tool access adds. The "improved node" benchmark. | `file_write`, `file_read`, `shell`, ripgrep |
| **Harness** | Same model + curated skills (mattpocock/tdd, diagnose) + MCP servers (CodeGraph for code graph, Headroom for compression) + sub-agent capability + governance hooks + verification gate | What the full harness adds. Skills, context reduction, verification loop. | All above + skills + MCP + sub-agents + hooks |

### Metrics captured per run (all 3 modes, same prompt)

| Metric | How captured | What it shows |
| --- | --- | --- |
| `prompt_tokens` | `onPostToolUse` hook logs SDK response metadata | System message + tools + prompt overhead per turn |
| `context_tokens` | Same hook, cumulative | Growth curve — flat (good) vs exponential (rot) |
| `cache_tokens` | Same hook, `cache_creation_input_tokens` + `cache_read_input_tokens` | Cache hit ratio. Higher = cheaper. Harness mode should have stable prefix = better caching |
| `cost_per_task` | Computed from token counts × model pricing | Total $ to complete the color palette. The number the C-level cares about |
| `tool_calls` | Count from JSONL | Fewer = better (CodeGraph should reduce) |
| `wall_clock` | Session start to completion | Harness slower (more steps) but should complete correctly |
| `output_quality` | Blind human score 1–5 on the color palette output. Does it match spec? | Quality delta across modes |

### Steps

| Step | Action | Done when |
| --- | --- | --- |
| 2.1 | Run color palette prompt through **minimal** mode 3 times. Save output + JSONL per run | 3 runs × (output + JSONL) |
| 2.2 | Run same prompt through **single** mode 3 times. Same model, same prompt text | 3 runs × (output + JSONL) |
| 2.3 | Run same prompt through **harness** mode 3 times | 3 runs × (output + JSONL) |
| 2.4 | Build `tools/observe/compare.py`: reads all 9 JSONL files, produces a comparison table — mode × metric averages with std dev | Table printed to stdout, shows clear deltas |
| 2.5 | Blind quality review: have someone (or yourself, shuffled) score the 9 outputs without knowing which mode produced them. Record scores | Scores added to comparison table |
| 2.6 | Write up findings: which mode won on cost? On quality? On cache ratio? Where does the harness help vs hurt? | One-paragraph finding per metric. This becomes the demo evidence. |

### What a good result looks like

Minimal costs least but may miss spec requirements. Single catches more spec details with tools. Harness costs more per run but CodeGraph reduces tool calls, Headroom compresses context, and the verification loop catches errors the other modes miss. If harness mode doesn't beat single on quality, the added complexity isn't justified — rethink before proceeding.

## Phase 3: Tokenomics (Day 2 – Day 3)

Goal: measurably reduce token spend in harness mode without degrading quality. Every technique must show its delta in the metrics JSONL.

### Techniques to implement (proven only)

| Technique | How | Expected delta | Evidence |
| --- | --- | --- | --- |
| **Graphify MCP** | `pip install graphify-cli && graphify init . && graphify build`. Register as MCP server in creator.agent.md. Agent queries graph instead of grepping files | −55% tool calls (CodeGraph independent test). Graphify adds docs+SQL+PDF coverage | arXiv usage, 124K stars |
| **Context reset between features** | Each feature in the Anthropic loop starts a fresh session. No carry-over history. State lives in git + feature\_list.json + progress.txt, not in conversation | Eliminates context rot entirely. Flat token trajectory per feature | Anthropic: "structured handoff files rather than summary-only compaction" |
| **Sub-agents with dropped-in context only** | When spawning a sub-agent, pass ONLY the feature description + relevant file paths. Never the parent's full history. Cap sub-agent response at 2K tokens, compress before injecting back | Sub-agent starts at <4K prompt tokens. Parent context stays flat | Anthropic: multi-agent = 15× tokens. This caps it. |
| **Observation masking** | After tool output is used, replace raw output in history with a one-line summary. Keep the tool call, drop the verbose result | Halves cost while matching solve rate | JetBrains, NeurIPS '25 |
| **Deferred tool loading** | Don't inject all tool schemas into every turn. Load tool definitions only when the model's plan references that tool | Practitioner cut 25K→8K prompt tokens by disabling unused tools | Claude Code issue #46526 |
| **Headroom MCP** | `pip install headroom && headroom wrap copilot`. Compresses JSON-heavy tool outputs before they enter context. Originals recoverable via `headroom_retrieve` | \~20% on coding sessions, 60–95% on JSON | Independent: 20.7% over 152 requests |

### Anti-bloat guards (things to block, not implement)

| Pattern | Why it's bad | What the harness does instead |
| --- | --- | --- |
| Caveman / terse-speak skills | 3% savings vs "be concise" (maintainer's own data). Degrades readability. No effect on Copilot | One-line instruction: "be concise; define done" |
| Continuous conversation loops | History grows linearly → context rot after \~100K tokens | Context reset per feature (Anthropic pattern) |
| "Create .md files for everything" | Markdown state files bloat context when re-read every turn | JSON for machine state, git for history, progress.txt for handoff (only 3 files) |
| Agent swarms | 15× token cost. Tightly-coupled tasks worse with multiple agents | Cap sub-agents at 2–3, isolated worktrees, minimal context drop-in |

### Steps

| Step | Action | Done when |
| --- | --- | --- |
| 3.1 | Install and index Graphify: `graphify init . && graphify build` | `graphify query "color palette"` returns relevant results |
| 3.2 | Register Graphify + Headroom as MCP servers in `creator.agent.md` | Both appear in tool list during harness mode |
| 3.3 | Implement observation masking in `hooks/compaction.py`: after tool result is processed, replace with `[tool_name returned N items, summary: ...]` | Raw tool output no longer persists in history after the turn that used it |
| 3.4 | Implement deferred tool loading: `hooks/deferred_tools.py` strips tool schemas from system message, injects only when model's plan mentions the tool name | `prompt_tokens` drops measurably vs Phase 2 harness runs |
| 3.5 | Re-run color palette prompt through harness mode 3 times with all tokenomics active | New JSONL shows lower `prompt_tokens`, `context_tokens`, and `cost_per_task` vs Phase 2 harness baseline |
| 3.6 | Run `compare.py` across Phase 2 harness runs and Phase 3 harness runs — quantify the delta | Table shows token reduction %, cost reduction %, quality maintained |

## Phase 4: Memory Optimization (Day 3 – Day 4)

Goal: separate what the harness remembers within a session (episodic) from what it persists across sessions (persistent). Persistent memory should learn user behavior patterns and push back on token-wasteful habits.

### Episodic memory (within session, dies at context reset)

This is the working memory for the current feature. It lives in the conversation context and gets wiped at each context reset (Anthropic pattern). Contents: current feature being worked on, tool results from this session, reasoning steps so far.

No action needed — this is the default. The key is to NOT persist it. Context reset between features is the mechanism.

### Persistent memory (survives across sessions, stored in files)

This is what the harness learns about the user and carries forward. Two categories:

**User preferences** (store in `user_profile.json`):

| What to detect | How to detect | What to store | How it changes behavior |
| --- | --- | --- | --- |
| Simple vs over-specified prompts | Count tokens in user's input. If >500 tokens for a single ask, flag as over-specification | `"prompt_style": "over_specifier"` | Harness decomposes long prompts into features automatically rather than attempting a one-shot |
| Asks for evidence / citations | User says "with evidence", "cite sources", "show me proof" | `"wants_evidence": true` | Verification gate includes source-linking step |
| Conciseness preference | User says "in 200 words", "keep it short", "be brief" | `"verbosity": "concise"` | System message includes word-limit constraint |
| Token-bloat request patterns | User asks to create .md files for state, continuous loops, use swarms, "keep going until done" | `"bloat_triggers": ["md_state_files", "infinite_loop"]` | Harness **challenges** rather than follows. E.g.: "Creating markdown state files will add \~3K tokens/turn to context. Using feature\_list.json instead — same state, 90% fewer tokens. Proceed?" |
| Output format preference | User asks for tables vs prose vs code | `"output_format": "tables"` | Default formatting matches preference |

**Behavior the harness challenges** (not stores and follows):

| User asks for | Why it's bad | Harness response |
| --- | --- | --- |
| "Create .md files for tracking" | Markdown re-read every turn bloats context. JSON is 90% smaller for machine state | "JSON is more token-efficient for state tracking. Using feature\_list.json instead. Your progress notes go in progress.txt." |
| "Keep going until it's all done" | Infinite loop = context rot + token burn. No verification checkpoints | "I'll work one feature at a time with verification between each. This prevents context rot and catches errors early." |
| "Use 5 agents in parallel" | 15× token cost for tightly-coupled tasks | "For this task, a single agent with context reset between features outperforms parallel agents. I'll use sub-agents only for isolated reads." |
| "Don't stop to check, just finish" | Skipping verification = gaming the output | "Verification after each feature is what prevents the 'looks done but is broken' problem. It adds 30 seconds but saves hours of debugging." |

### Core principle: JSON + deterministic hooks over Markdown + LLM writeups

All harness state is machine-verifiable. No LLM-authored markdown summaries that could hallucinate or lie about what actually executed.

| State type | Use JSON (deterministic) | Never use Markdown (non-deterministic) | Why |
| --- | --- | --- | --- |
| Feature tracking | `feature_list.json` — boolean `passes` field, immutable descriptions | ~~status.md with LLM-written summaries~~ | JSON is 90% fewer tokens. Model can't silently rewrite structure. Machine-parseable for verification gates. |
| Execution proof | Deterministic hooks (`onPostToolUse`) log what actually ran — tool name, input, output, exit code, latency | ~~LLM-written "I ran the tests and they passed"~~ | Hooks capture ground truth. An LLM can claim it ran tests without running them. A hook logs the actual `pytest` exit code. |
| Progress handoff | `progress.txt` — free-text BUT verified against git diff. What the model says it did must match what git shows. | ~~session\_summary.md that the model writes from memory~~ | The git diff is the source of truth. progress.txt is a convenience index into it, not an authoritative record. |
| User preferences | `user_profile.json` — typed fields, validated schema | ~~preferences.md with freeform notes~~ | Typed fields prevent drift. `"verbosity": "concise"` is unambiguous. A markdown note "user seems to prefer shorter answers" is subjective and lossy. |
| Metrics | JSONL per session — one line per turn, all 7 fields | ~~metrics\_report.md written by the model~~ | JSONL is append-only, machine-parseable, diffable. A model-authored report cherry-picks what looks good. |
| Verification results | Hook output: `{"test": "pytest", "exit_code": 0, "stdout": "...", "passed": 12, "failed": 0}` | ~~"All tests passed" in a markdown note~~ | The hook's exit code is unforgeable. The model's claim is not. |

### Steps

| Step | Action | Done when |
| --- | --- | --- |
| 4.1 | Create `user_profile.json` schema with fields above. Initialize with defaults | File exists with all fields set to null/default |
| 4.2 | Implement `hooks/profile_detector.py`: `onSessionStart` reads user\_profile.json. `onPreToolUse` detects patterns (over-specification, bloat requests) and updates profile | Profile updates after detecting a pattern in test prompts |
| 4.3 | Implement challenge logic: when a bloat trigger is detected, the hook injects a system message fragment challenging the request with the token-cost reason | Test: send "create markdown files to track progress" → harness responds with JSON alternative and cost comparison |
| 4.4 | Implement preference application: `onSessionStart` reads profile and adjusts system message (add conciseness constraint, evidence requirement, format preference) | Test: set `"verbosity": "concise"` → output is measurably shorter |
| 4.5 | Verify episodic/persistent boundary: run two sessions back-to-back. Session 1 learns a preference. Context resets. Session 2 reads the preference from file and applies it. Session 1's working memory is gone. | Preference persists, working memory doesn't |

## Phase 5: Anthropic Loop Pattern (Day 4 – Day 5)

Goal: implement the initializer/worker pattern from Anthropic's "Effective harnesses for long-running agents." The color palette prompt becomes a multi-feature epic to test this.

### Decompose the color palette into features

The initializer agent reads the color palette prompt and produces `feature_list.json`. Example structure for the color palette task — each feature is independently verifiable:

```
[
  {"name": "base_palette", "description": "Generate 5 primary colors with hex, RGB, HSL", "verify": "output contains exactly 5 colors, each with all 3 formats", "passes": false},
  {"name": "contrast_ratios", "description": "Calculate WCAG contrast ratios for all color pairs", "verify": "matrix is 5x5, all ratios are valid numbers >0", "passes": false},
  {"name": "accessibility", "description": "Flag pairs that fail WCAG AA (ratio <4.5:1)", "verify": "every failing pair is listed with its ratio", "passes": false},
  {"name": "dark_mode", "description": "Generate dark-mode variants preserving hue relationships", "verify": "5 dark variants exist, hue delta <10 degrees from originals", "passes": false},
  {"name": "export", "description": "Output as CSS custom properties file", "verify": "valid CSS, parseable by stylelint, all 10 colors present", "passes": false}
]
```

### Session flow

| Step | Agent | Action | State change |
| --- | --- | --- | --- |
| 1 | Initializer | Read color palette prompt. Decompose into features. Write `feature_list.json` (all false). Write empty `progress.txt`. Run `git init && git add -A && git commit -m "[init] color palette scaffold"` | feature\_list.json + progress.txt + git commit exist |
| 2 | Worker (session 1) | Read git log + progress.txt + feature\_list.json. Pick `base_palette` (first failing). Implement. Run verify step. If passes: `git commit`, flip `passes: true`, write progress note. | One feature done. Clean git state. |
| 3 | Worker (session 2) | Fresh context. Read state files. Pick `contrast_ratios`. Same cycle. | Two features done. |
| ... | Worker (session N) | Repeat until all `passes: true` | All features done. |

### Kill switch + verification gate

| Guard | Trigger | Action |
| --- | --- | --- |
| Retry cap | >5 attempts on same feature without `passes` flipping | Pause session, log failure, escalate to human |
| Anti-gaming | Model attempts to edit `description`, `verify`, or `name` fields in feature\_list.json | Reject the diff. Log as blindspot B5. |
| No-commit-no-flip | Model tries to flip `passes: true` without a preceding `git commit` | Block the flip. Require commit first. |
| Victory check | Model says "done" but feature\_list.json still has `passes: false` entries | Block completion. List remaining features. |

### Steps

| Step | Action | Done when |
| --- | --- | --- |
| 5.1 | Implement `tools/loop/initializer.py`: takes a prompt, decomposes into features, writes feature\_list.json + progress.txt + runs git init | Given color palette prompt, produces valid feature\_list.json with ≥3 features |
| 5.2 | Implement `tools/loop/worker.py`: reads state, picks feature, works on it, verifies, commits, updates. Uses context reset (new session per feature) | Completes one feature per invocation, flips status only after verify |
| 5.3 | Implement guards (retry cap, anti-gaming, no-commit-no-flip, victory check) as `onPreToolUse` hook conditions | Test: attempt to edit feature description → rejected. Attempt flip without commit → blocked. |
| 5.4 | End-to-end test: run initializer → then worker sessions until all features pass. Count total sessions, total cost, total tokens across the full epic | All features `passes: true`. Metrics JSONL covers the full run. Compare cost to single-mode one-shot. |
| 5.5 | Measure: does the loop pattern produce better output than the one-shot? At what cost? Is the quality delta worth the token multiplier? | Written comparison: loop vs one-shot on quality, cost, correctness |

## Phase 6: Observability (Day 5 – Day 6)

Goal: see inside every run. Trajectory view shows what happened. OTel traces show where time and tokens went. This is what makes everything before it debuggable.

### What the trajectory view must show

For any session, drill into: the exact system message assembled for that turn (with all injected fragments), which tools were available vs which were called, tool input/output payloads, token counts per turn (all 4 metrics), which model was used (routing decision), cache hit/miss per turn, any hook interventions (governance blocks, challenge messages, kill switch triggers), and the feature\_list.json state before and after.

### OTel spans

One trace per session, one span per turn, child spans for tool calls. Attributes on each span:

| Attribute | Type | Source |
| --- | --- | --- |
| `session.id` | string | SDK session metadata |
| `session.mode` | string | minimal / single / harness |
| `turn.number` | int | Sequential counter |
| `turn.prompt_tokens` | int | SDK response metadata |
| `turn.context_tokens` | int | Cumulative context at this turn |
| `turn.cache_tokens` | int | Cache read + creation tokens |
| `turn.completion_tokens` | int | Output tokens |
| `turn.model` | string | Which model served this turn |
| `turn.cost_usd` | float | Computed from tokens × pricing |
| `tool.name` | string | On tool-call child spans |
| `tool.latency_ms` | int | Wall-clock tool execution time |
| `tool.success` | bool | Did the tool return without error |
| `hook.intervention` | string | If a hook blocked/challenged this turn |
| `feature.name` | string | Current feature being worked on |
| `feature.passes` | bool | Status at end of turn |

### Steps

| Step | Action | Done when |
| --- | --- | --- |
| 6.1 | Install OTel: `pip install opentelemetry-sdk opentelemetry-exporter-otlp`. Set up local Jaeger: `docker run -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one` | Jaeger UI accessible at localhost:16686 |
| 6.2 | Implement `hooks/tracing.py`: create trace per session, span per turn, child span per tool call. Attach all attributes from table above | Spans appear in Jaeger after a test run |
| 6.3 | Build trajectory view: `tools/observe/trajectory.py` reads the session JSONL and renders a CLI timeline — turn number, model, tokens (prompt/context/cache/completion), tools called, hook interventions, feature status | `python trajectory.py session_001.jsonl` prints readable timeline |
| 6.4 | Add context-rot detector to trajectory: plot `tool_call_success_rate` across turns. If it drops >20%, flag the turn where rot started | Detector fires on a synthetically degraded session log |
| 6.5 | Add token-growth visualizer: plot `context_tokens` across turns. Flat = good, exponential = rot. Compare minimal vs single vs harness curves | Chart shows harness mode is flat (context resets), minimal/single may grow |
| 6.6 | Integration test: run the full Anthropic loop (Phase 5) on the color palette with all tokenomics (Phase 3) and memory (Phase 4) active. Capture OTel traces. Open Jaeger. Walk through the trace end to end — every span should have all attributes, every tool call visible, every hook intervention logged | Full trace visible in Jaeger. Can drill from session → turn → tool call. Token counts match JSONL. Feature status transitions visible. |

### What debugging looks like after this

Something goes wrong → open Jaeger → find the session → see which turn failed → drill into the tool call → see the input/output → check if a hook intervened → check token counts for rot signal → check feature\_list.json delta. Total time to root-cause: minutes, not hours. This is what opaque observability (P1) looks like when solved.

## Phase 7: Metrics Priority & Research Notes (Continuous)

All implementation decisions are ranked by this priority stack. When two approaches trade off against each other, the higher-ranked metric wins.

### Decision priority

1. **Quality** (human blind test) — does the output meet spec? Scored 1–5 by a reviewer who doesn't know which mode produced it. This overrides everything. A cheaper run that produces wrong output is a failed run.
2. **Token usage** — total tokens consumed to complete the task. Lower is better, but never at the cost of quality. Includes prompt + context + completion across all turns and sub-agents.
3. **Latency** — wall-clock time from prompt to verified completion. Faster is better, but a fast wrong answer is still wrong.
4. **Caching ability** — cache hit ratio (`cache_read_tokens / total_input_tokens`). Higher = cheaper per-token. A stable system prompt prefix maximizes this. Measures how well the harness architecture supports prefix caching.

### Research notes folder

Every test run, comparison, finding, and decision gets stored in `research/` — not in chat, not in memory, not in scattered files.

```
research/
├── runs/
│   ├── 2026-10-06_minimal_color-palette_run1.jsonl
│   ├── 2026-10-06_single_color-palette_run1.jsonl
│   └── 2026-10-06_harness_color-palette_run1.jsonl
├── comparisons/
│   ├── mode_comparison_color-palette.json    # output of compare.py
│   └── tokenomics_delta_phase3.json          # before/after tokenomics
├── findings/
│   ├── 001_baseline_metrics.md               # Phase 2 findings
│   ├── 002_tokenomics_impact.md              # Phase 3 delta
│   ├── 003_memory_behavior.md                # Phase 4 observations
│   └── 004_loop_vs_oneshot.md                # Phase 5 comparison
├── blindspots/
│   └── detected_blindspots.jsonl             # every blindspot flag with session ID
└── decisions/
    └── decision_log.md                       # why we chose X over Y, with metric evidence
```

Every finding references the run data it came from. Every decision references the finding that justified it. This is the audit trail for the client.

| Step | Action | Done when |
| --- | --- | --- |
| 7.1 | Create `research/` folder structure as above | All dirs exist |
| 7.2 | Update `compare.py` to output to `research/comparisons/` and rank results by the 4-metric priority stack | Comparison output shows quality first, then tokens, then latency, then cache |
| 7.3 | After every phase completion, write a finding in `research/findings/` — what was measured, what changed, what decision follows | Finding exists for each completed phase |

## Phase 8: Anti-Vibe-Code Guardrails + Git Workflow (Day 6 – Day 7)

Goal: prevent the harness from producing bloated monoliths, hiding errors behind fallbacks, or merging unreviewed code. Every output is modular, versioned, and PR-gated.

### Module size guardrails

The harness enforces code structure constraints before any output is accepted.

| Rule | Threshold | On violation |
| --- | --- | --- |
| Max lines per module/file | 500 lines | Split into 2+ modules. Agent proposes the split, human approves. |
| Ideal module range | 200–300 lines (logic), 400–500 lines (if includes tests) | No action — this is the target |
| Lines > 500 in a single file | Hard block | Escalate to human: "This file is 847 lines. Splitting into 3 modules of \~280 each. Approve?" Or route to a stronger model for the decomposition. |
| Total codebase per feature | Track cumulative lines added per feature | If a single feature adds >1,500 lines, flag as potential scope creep. Check if it should be 2 features. |
| No fallback error hiding | Zero tolerance | AST scan (blindspot B1): any `except: pass`, `catch {}`, bare `return None` in error paths, or `# TODO` in shipped code → block commit |
| No multi-role prototyping | Agent must not simultaneously play frontend, backend, infra, data eng | One role per session/sub-agent. If task spans roles, decompose into sub-agents with isolated worktrees per role |

### Git workflow (enforced by harness)

| Rule | How enforced |
| --- | --- |
| Every feature on its own branch | Initializer creates `feature/<name>` branch. Worker operates only on that branch. Never commit to main directly. |
| PR required before merge | After feature passes verification gate, harness creates a PR (via `gh pr create`) with: diff summary, test results, metrics (tokens, cost, quality score), blindspot scan results |
| Human reviews PR | Harness pauses. Human reviews diff, approves or requests changes. Agent addresses review comments on the same branch. |
| Squash merge to main | After approval, `gh pr merge --squash`. Clean single-commit history on main. |
| Tag releases | After all features merged: `git tag v0.1.0`. Semantic versioning. |

### Dynamic workflows: parallel branches for options

When a feature has multiple valid approaches (e.g., "implement caching" could use Redis, SQLite, or in-memory), the harness spawns parallel sub-agents in separate branches to develop each option independently.

| Step | What happens |
| --- | --- |
| 1. Agent identifies multiple approaches | Worker detects >1 viable implementation for a feature |
| 2. Spawn sub-agents | One sub-agent per approach, each in its own branch: `feature/caching-redis`, `feature/caching-sqlite`, `feature/caching-memory` |
| 3. Isolated worktrees | Each sub-agent gets a git worktree (instant via Btrfs/APFS snapshot). No cross-contamination. |
| 4. Independent development + test | Each sub-agent implements, tests, captures metrics (tokens, latency, quality). Verification gate runs on each. |
| 5. Compare | Harness runs `compare.py` across the branches: quality (human blind test) > tokens > latency > cache. Best option wins. |
| 6. PR the winner | Winning branch gets a PR to main. Losing branches are archived (not deleted — research evidence). |
| 7. Human confirms | Human reviews the comparison + the winning PR. Merges or picks a different branch. |

This is the Anthropic-endorsed pattern: parallel sub-agents in worktrees, test-gated, human-approved merge.

### Steps

| Step | Action | Done when |
| --- | --- | --- |
| 8.1 | Implement `hooks/module_guard.py`: `onPostToolUse` checks if any file in the diff exceeds 500 lines. If yes, block and propose split. | Test: write a 600-line file → blocked with split suggestion |
| 8.2 | Implement `hooks/no_fallback.py`: AST scan on every commit for error-hiding patterns. Extends blindspot B1. | Test: commit with `except: pass` → blocked |
| 8.3 | Implement git workflow in `tools/git/branch_workflow.py`: create feature branch, work on branch, create PR with metrics, wait for human approval | Test: feature completion → PR created with diff + metrics + blindspot report |
| 8.4 | Implement parallel branching in `tools/git/parallel_options.py`: spawn sub-agents in worktrees, compare results, PR the winner | Test: give a feature with 2 approaches → 2 branches created, compared, winner PR'd |
| 8.5 | Configure role isolation: system message for each sub-agent restricts to one role (frontend OR backend OR data eng). No multi-role sessions. | Test: prompt agent to "build the API and the frontend" → decomposes into 2 sub-agents |

## Phase 9: SkillOpt — Skill Onboarding Gate (Day 7 – Day 8)

Goal: no skill enters the harness's `skills/admitted/` folder without proving it helps. No skill stays loaded in a task unless it earns its tokens.

### Two thresholds

| Gate | What it checks | Threshold | On fail |
| --- | --- | --- | --- |
| **Onboarding gate** (admission to `skills/admitted/`) | Paired eval: run the same task suite WITH and WITHOUT the skill. Measure lift on quality (blind score). Measure token delta. | Quality lift ≥ 10 pp AND token overhead < 20% | Skill rejected. Logged in `research/decisions/` with the eval data. Can re-test after revision. |
| **Task-use gate** (loaded into a specific task session) | Per-task relevance check: does this skill's trigger match the current task type? Is it in the top 3 by lift for this task category? | Must be top-3 lift for task category. Max 3 skills loaded per session. | Skill available but not loaded. Session runs with fewer, better-matched skills. |

### SkillOpt pipeline

| Step | What happens |
| --- | --- |
| 1. Candidate skill arrives | From mattpocock/skills, addyosmani/agent-skills, vendor catalogs, or custom-written |
| 2. Security scan | SkillCheck: reject if skill contains override instructions, external fetches, or encoded payloads |
| 3. Paired eval | Run 5 tasks from the harness task suite (color palette, FinCon, etc.) with and without the skill. 3 runs each = 30 runs total |
| 4. Compute lift | Quality lift (blind score delta), token delta (%), latency delta (%), cost delta ($) |
| 5. Rank by lift-per-dollar | Lift / cost\_increase. Higher = more efficient skill |
| 6. Admit or reject | If passes both thresholds → copy to `skills/admitted/`, add to `skills/registry.json` with lift scores |
| 7. Per-task loading | At session start, harness reads task type → loads top-3 skills by lift for that category → disables the rest |

### registry.json structure

```
{
  "admitted": [
    {
      "name": "tdd",
      "source": "mattpocock/skills",
      "quality_lift_pp": 18.2,
      "token_overhead_pct": 8.4,
      "cost_per_lift_pp": 0.003,
      "task_categories": ["coding", "refactoring"],
      "admitted_date": "2026-10-08",
      "eval_run_ids": ["run_042", "run_043", "run_044"]
    }
  ],
  "rejected": [
    {
      "name": "verbose-planner",
      "source": "custom",
      "quality_lift_pp": 2.1,
      "token_overhead_pct": 45.0,
      "reason": "lift below 10 pp threshold, token overhead 45%",
      "rejected_date": "2026-10-08"
    }
  ]
}
```

### Steps

| Step | Action | Done when |
| --- | --- | --- |
| 9.1 | Build `tools/skills/eval_skill.py`: takes a skill path + task suite, runs paired eval (with/without, 3 runs each), outputs lift metrics | Produces lift report for a test skill |
| 9.2 | Build `tools/skills/onboard.py`: runs security scan → paired eval → checks thresholds → admits or rejects → updates registry.json | Test: submit mattpocock/tdd → passes, admitted. Submit a bloated custom skill → rejected with reason |
| 9.3 | Build task-use gate in `hooks/skill_loader.py`: at `onSessionStart`, reads task type, loads top-3 skills from registry, disables rest | Test: start a coding task → tdd + diagnose loaded. Start a non-coding task → different skills loaded (or none if none qualify) |
| 9.4 | Run onboarding pipeline on 5 candidate skills from the skill ecosystem. Document results in `research/findings/` | 5 skills evaluated, registry.json populated, findings written |

## Phase 10: Selective Adoption + Adapters (Day 9+)

Goal: once the core harness is proven (Phases 1–9 passing), selectively adopt components from external projects and build adapters to other platforms.

### Selective parts adoption

The harness is working. Now cherry-pick components from external projects — but only through the SkillOpt gate (Phase 9). Nothing enters the harness without paired eval.

| Source | What to evaluate | What to skip |
| --- | --- | --- |
| External project skills/templates | PRD template, ADR template, tech spec format — evaluate as skills via onboarding pipeline. Admit only if lift ≥ 10 pp | 24-agent routing, Model Council, PowerShell orchestration, self-generated skills |
| External project evaluation folder | Check for real test cases. If they have domain-specific evals (e.g. for financial workflows), extract and add to our task suite | Anything that looks auto-generated without real assertions |
| External project doc templates | Document structure patterns for compliance, audit, regulatory — useful for non-coding client workflows | Templates that inject themselves into every session |

Every adopted component goes through: security scan → paired eval → threshold check → admit or reject. No exceptions.

### Platform adapters

The harness core (metrics hooks, verification gate, skill loader, memory, Anthropic loop) is platform-agnostic by design. The `.agent.md` format and SKILL.md format are cross-platform standards. Build thin adapters:

| Platform | Adapter approach | Effort |
| --- | --- | --- |
| **Cursor** | Cursor reads `.cursor/rules/` — map our `.agent.md` modes to Cursor rules files. Skills in SKILL.md already work in Cursor. MCP servers portable as-is. | Low — config mapping |
| **Claude Code** | Claude Code reads `CLAUDE.md` + `.claude/` — map modes to CLAUDE.md profiles. Skills work natively. Sub-agents supported. Hooks translate to Claude Code hooks.json. | Low-Medium — hooks format differs |
| **Codex CLI** | Reads `AGENTS.md` — map modes. SKILL.md supported natively. MCP portable. | Low — config mapping |
| **OpenCode** | Config-driven agents already. SKILL.md supported. MCP portable. | Low |

The key insight: skills, MCP servers, and the Anthropic loop pattern (feature\_list.json + progress.txt + git) are platform-independent. Only the hooks and agent definitions need adaptation per platform.

### Steps

| Step | Action | Done when |
| --- | --- | --- |
| 10.1 | Run SkillOpt on 3–5 templates from external project (PRD, ADR, tech spec). Document lift in `research/findings/` | Each template has a lift score. Admitted ones in `skills/admitted/` |
| 10.2 | Extract any real test cases from external project eval folder. Add to `tests/task_suite/` | Task suite expanded with domain-specific evals |
| 10.3 | Build Cursor adapter: `adapters/cursor/generate_rules.py` reads `.agent.md` modes → writes `.cursor/rules/` files | Cursor reads our modes. Same skills, same behavior. |
| 10.4 | Build Claude Code adapter: `adapters/claude/generate_config.py` reads modes → writes `CLAUDE.md` + `hooks.json` | Claude Code runs with same modes and hooks |
| 10.5 | Validate cross-platform: run color palette prompt through GHCP, Cursor, and Claude Code adapters. Compare metrics (same model, same prompt) | Results within 5% across platforms — proves portability |
