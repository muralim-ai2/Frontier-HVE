# Initial request (verbatim, 2026-10-05)

**Build an enterprise AI harness project with the following architecture and constraints.**

**Project:** `enterprise-harness/` — a custom AI harness built on top of GitHub Copilot with 3 operating modes (minimal, single, harness) that tracks tokenomics and enforces verification before declaring any work done.

**Folder structure to scaffold now:**

```
enterprise-harness/
├── .github/agents/
│   ├── minimal.agent.md      # raw prompt only, no tools, no skills
│   ├── single.agent.md       # pinned model + tools + best-practice system msg
│   └── creator.agent.md      # full harness: skills + MCP + sub-agents + hooks
├── hooks/
│   ├── metrics.py            # onPostToolUse: logs prompt_tokens, context_tokens, cache_tokens, completion_tokens, model, tool_name, latency_ms to JSONL
│   ├── compaction.py          # observation masking: replace raw tool output with 1-line summary after use
│   ├── deferred_tools.py      # strip tool schemas from system message, inject only when referenced
│   ├── module_guard.py        # block any file >500 lines, propose split into 200-300 line modules
│   ├── no_fallback.py         # AST scan: block except:pass, catch{}, bare return None in error paths
│   ├── skill_loader.py        # onSessionStart: load top-3 skills by lift for current task type
│   └── profile_detector.py    # detect user patterns (over-specification, bloat requests), update user_profile.json
├── tools/
│   ├── verify/
│   │   ├── blindspots.py      # B1-B10 detectors: fallback codes, circular mocks, false victory, context rot, idle loops
│   │   └── jev_judge.py       # Jev classifier calls for verification gate Layer 2
│   ├── observe/
│   │   ├── compare.py         # reads JSONL from all 3 modes, outputs comparison table ranked by Quality > Tokens > Latency > Cache
│   │   └── trajectory.py      # CLI timeline view of a session: turn, model, tokens, tools, hooks, feature status
│   ├── loop/
│   │   ├── initializer.py     # Anthropic pattern: decompose prompt into feature_list.json (all passes:false) + progress.txt + git init
│   │   └── worker.py          # per-session: read state, pick 1 failing feature, implement, verify, commit, update status
│   ├── skills/
│   │   ├── eval_skill.py      # paired eval: run tasks WITH and WITHOUT skill, compute quality lift + token delta
│   │   └── onboard.py         # security scan → paired eval → threshold check (lift ≥10pp, overhead <20%) → admit or reject
│   └── git/
│       ├── branch_workflow.py # create feature branch, work on branch, create PR with metrics, wait for human approval
│       └── parallel_options.py # spawn sub-agents in worktrees per approach, compare, PR the winner
├── skills/
│   ├── registry.json          # admitted skills with lift scores, token overhead, eval run IDs
│   └── admitted/              # only skills that pass SkillOpt onboarding gate
├── research/
│   ├── runs/                  # raw JSONL per test run
│   ├── comparisons/           # output of compare.py
│   ├── findings/              # one .md per phase with metrics evidence
│   └── decisions/             # decision_log.md: why X over Y, with data
├── tests/
│   └── prompts/
│       └── color-palette.md   # first test prompt (from Google Doc)
├── feature_list.json          # Anthropic pattern: features with passes:true/false — the ONLY mutable field
├── progress.txt               # free-text handoff note, verified against git diff
├── user_profile.json          # persistent memory: user prefs, behavior patterns, bloat triggers
└── init.sh                    # bootstrap: health check, verify model access
```

**Critical design rules — do not violate these:**

1. **All state is JSON, never Markdown.** `feature_list.json` for task tracking, `user_profile.json` for preferences, JSONL for metrics. Markdown is for human docs only, never machine state. JSON is 90% fewer tokens and machine-parseable.
2. **All execution proof is via deterministic hooks, never LLM writeups.** Hooks log what actually ran (tool name, exit code, stdout). An LLM can claim it ran tests without running them. A hook captures the actual pytest exit code. Never trust a model's text summary of what it did.
3. **Decision priority:** Quality (human blind test, 1-5 score) > Token usage > Latency > Caching ability. A cheaper run that produces wrong output is a failed run.
4. **Anthropic loop pattern:** One feature per session. Context resets between features. State survives in git + feature_list.json + progress.txt. The model may ONLY change the `passes` field in feature_list.json. Descriptions and verify steps are immutable. Kill switch at >5 retries without progress.
5. **Module size cap:** No file >500 lines. Target 200-300 lines per module. If >500, escalate to human with a split proposal. No multi-role sessions — one role (frontend/backend/data/infra) per sub-agent.
6. **No fallback error hiding:** AST-scan every commit for bare `except: pass`, `catch {}`, hardcoded returns in error paths, `TODO` in shipped code. Block the commit.
7. **Git workflow:** Every feature on its own branch. PR required with metrics before merge. Squash merge to main. For features with multiple approaches, spawn parallel sub-agents in worktrees, compare, PR the winner.
8. **Skill gate:** No skill enters `skills/admitted/` without paired eval showing ≥10 pp quality lift and <20% token overhead. Max 3 skills loaded per session.
9. **Anti-bloat:** Challenge (don't follow) requests for: .md state files, infinite loops, 5+ parallel agents, "don't stop to check." Respond with the token-cost reason and the better alternative.

**Start now with Phase 1:** Create the folder structure, scaffold the 3 `.agent.md` files, implement `hooks/metrics.py`, and prepare `tests/prompts/color-palette.md`. Pin the model to `claude-sonnet-4-20260514` across all modes for benchmark consistency. The metrics hook must log all 7 fields (prompt_tokens, context_tokens, cache_tokens, completion_tokens, model, tool_name, latency_ms) to a JSONL file named by session ID in `research/runs/`.

See the reference/ folder to understand the background blueprint v3 and the overall implementation plan and reasoning v3, and colorpalette_prompt.txt. Ignore the archive/ folder.

## Later instructions in the same session
- Models changed per mode (decisions D-003, D-004): minimal = GPT-6 Astra; single = Claude Opus 5.5, reasoning-effort high, engineered system prompt; creator = GPT-5.6 Sol, reasoning-effort medium.
- Hypothesis recorded in `research/hypothesis.md`.
- Implementation tracker: `tracker.json` (status per item, what you must validate before the next phase, and `next_actions`).
