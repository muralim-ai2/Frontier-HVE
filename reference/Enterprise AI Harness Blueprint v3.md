# Enterprise AI Harness Blueprint v3

GHCP (Copilot SDK) Base · Minimal & Creator Modes · Anthropic Long-Running Pattern · Blindspot Detection · 3 Weeks

1. [Engineering Progression (5 Layers)](#s1)
2. [Architecture: GHCP Copilot SDK + Custom Modes](#s2)
3. [System Flow: Problem → Decision → Execution](#s3)
4. [Harness Comparison: What We Borrow From Each](#s4)
5. [Anthropic Long-Running Agent Pattern](#s5)
6. [Ranked Problems × Proven vs Rabbit Hole](#s6)
7. [Token Reduction & Code Knowledge Tooling (Vetted)](#s7)
8. [Vetted Tooling, Skills & Governance](#s8)
9. [3 Personas × 3 Test Suites + 4 Metrics](#s9)
10. [Blindspot Detection Checklist](#s10)
11. [Research Adoption List](#s11)
12. [3-Week Roadmap](#s12)

## 1. Engineering Progression: What Each Layer Adds

Each layer widens what you control. The model stays fixed — only the harness changes.

## 2. Architecture: GHCP Copilot SDK + Custom Modes

The Copilot SDK (GA June 2026) is the base. It gives you the same agent runtime as Copilot CLI — planning, tool invocation, file edits, streaming, multi-turn sessions — without building your own orchestration layer. Available in Python, Node.js, Go, .NET, Rust.

### Two modes on one runtime

| Mode | Purpose | Config |
| --- | --- | --- |
| **Minimal (single-node)** | Baseline benchmark. One session, pinned model, no sub-agents, no MCP, all skills disabled. Proves what the raw model + harness loop can do alone. | `.github/agents/minimal.agent.md` — pinned model, `tools: [file_write, build_tool]` only, no `customAgents`, no MCP, logging hook only |
| **Creator (full harness)** | Production mode. Planner/builder/critic agents, curated skills, MCP servers (CodeGraph, Headroom), governance hooks, sub-agent delegation. | `.github/agents/creator.agent.md` — planner + builder + critic `customAgents`, curated `skillDirectories`, MCP servers, AGT policy hooks |

**Benchmarking rule:** Pin one explicit model for both modes. Auto/HyDRA and HydraFusion change models per request — this contaminates the comparison. HydraFusion is a research preview and should not be used in enterprise baselines yet.

### Copilot SDK extensibility points

| Extension | What it gives you |
| --- | --- |
| Custom tools | Register your own functions, override built-in tools like `grep` and `edit_file` |
| MCP servers | Local (stdio) and remote (HTTP/SSE) per session, with per-tool allowlists |
| Hooks | `onPreToolUse`, `onPostToolUse`, `onSessionStart`, `onPermissionRequest` — insertion points for policy, logging, governance |
| Permissions | `availableTools` and `excludedTools` restrict tool surface per session |
| Custom agents | Each with own prompt, tool restrictions, MCP servers, preloaded skills. Defined in `.agent.md` files or SDK code |
| Skills | `skillDirectories` and `disabledSkills` per session. Cross-platform SKILL.md format |
| Session persistence | On resume: reconfigure model, tools, MCP, agents, skills, `infiniteSessions` |

### Architecture diagram

```
GHCP Copilot SDK (Python/Node)       ← your harness runtime
│
├── .github/agents/
│   ├── minimal.agent.md             ← single-node benchmark mode
│   └── creator.agent.md             ← full harness mode
├── copilot-config.json              ← model routing, token caps, session config
│
├── hooks/                           ← onPreToolUse, onPermissionRequest
│   ├── governance.py                ← MS Agent Governance Toolkit (AGT) policy
│   ├── logging.py                   ← append-only session log + OTel export
│   └── token_budget.py              ← per-session/per-loop/per-dollar caps
│
├── mcp-servers/                     ← registered per mode
│   ├── codegraph/                   ← pre-indexed code knowledge graph
│   ├── headroom/                    ← context compression (JSON/tool output)
│   └── graphify/                    ← code + docs + SQL + PDF graph (if needed)
│
├── tools/                           ← YOUR PYTHON — custom tool servers
│   ├── verify/                      ← Jev judge + blindspot detectors + linters
│   ├── observe/                     ← 4-metric collector + rot/idle detectors
│   ├── optimize/                    ← DSPy/GEPA pipelines (metric-backed only)
│   └── domain/                      ← client's non-coding workflows
│
├── skills/                          ← SKILL.md files, paired-eval gated
│   ├── registry.json                ← admitted skills + lift scores
│   └── admitted/                    ← vetted skills only (mattpocock TDD, diagnose)
│
├── feature_list.json                ← Anthropic pattern: all features, passes: false
├── progress.txt                     ← session-over-session handoff log
└── init.sh                          ← bootstrap: start servers, run health check
```

## 3. System Flow: Problem → Decision → Execution Loop

Every request flows through this loop. Each node maps to a ranked problem. 4 metrics tracked at every step.

## 4. Harness Comparison: What We Borrow From Each

We build on GHCP but borrow proven patterns from other harnesses. The model stays the same — only the orchestration changes.

| Harness | License | What we borrow | What we skip |
| --- | --- | --- | --- |
| **GitHub Copilot SDK** | Proprietary (GA) | Base runtime. Agent loop, hooks, MCP, custom agents, skills, OTel tracing, HyDRA routing. Our foundation. | HydraFusion (research preview, no model allowlists, unclear enterprise policy) |
| **OpenCode** | MIT (stable) | Config-driven agent definitions pattern: model/prompt/perms/step-limits per agent. 75+ providers. | Core not replaceable — GHCP's hook system is more extensible |
| **Hermes Agent** | MIT | Compression: summarizes old turns at \~20% budget (2K floor, 12K ceiling). Session lineage rotation. | Messaging gateways (Telegram/Slack/etc.) — not needed for enterprise coding |
| **Claude Code** | Proprietary | Sub-agent delegation pattern. Forked sub-agents reuse parent prompt cache. Hooks + permissions model. | Closed source — call as sub-agent backend, don't build on it |
| **OpenHands** | MIT | Managed worktrees + sub-agent delegation loops. Docker sandbox isolation. The open-source reference for Anthropic-style isolation. | Full framework — take isolation patterns only |

**Key research finding:** A "Scaffold Effect" study (arXiv 2607.22585) treats harness choice as a hidden evaluation variable. More harness features ≠ more quality. Mini-SWE-Agent with Opus outscored Hermes with the same model. The "Harness Effect" study (arXiv 2607.06906) found orchestration design alone delivers −41% cost/task, −38% tokens across 6 models. A 2026 study (arXiv 2606.00189) found hand-engineered static workflows "usually perform best" vs ReAct-style dynamic agents.

## 5. Anthropic Long-Running Agent Pattern

From [Anthropic Engineering](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents). Our Loop Engineering implementation spec. Anthropic's follow-up harness study (March 2026): with Opus 4.5, solo agent = 20 min / $9 / broken output. Full harness = 6 hrs / $200 / working app. 20× costlier, visibly better.

| Component | Runs | What it does | Artifacts |
| --- | --- | --- | --- |
| **Initializer Agent** | Once per epic | Sets up environment. Prevents one-shotting. | `feature_list.json` (all `"passes": false`), `progress.txt`, `init.sh`, git commit |
| **Worker Agent** | Every session | Picks ONE feature, implements, tests e2e, commits, updates progress. | Git commit, updated `progress.txt`, status flip only after e2e verification |

**Anti-gaming rules (Anthropic):** Use JSON for feature list (model less likely to overwrite). Strongly word: "It is unacceptable to remove or edit tests." Agent may only change the `passes` field. Use a fresh container per trial — Anthropic found Claude gained unfair advantage by examining git history from previous trials.

## 6. Ranked Problems × Proven vs Rabbit Hole

**Key evidence:** Multi-agent = \~15× more tokens than chats (Anthropic). Users rubber-stamp \~93% of permission prompts (Anthropic). METR RCT (246 tasks, 16 devs): AI +19% completion time. Self-generated skills −8 to −11 pp (SkillsBench). Observation masking halves cost (JetBrains, NeurIPS '25). Harness design alone −41% cost/task (arXiv 2607.06906).

| # | Problem | Technique | Verdict | Evidence |
| --- | --- | --- | --- | --- |
| P1 | Opaque observability → sub-standard outputs | Append-only session log + OTel traces via GHCP hooks | PROVEN | Copilot SDK has native OTel. Community plugins track steps, failures, latency. |
| P2 | Token explosion & context rot | Headroom compression (\~20% real), CodeGraph (−55% tool calls), observation masking, deferred tools | PROVEN | JetBrains: masking halves cost. Headroom: 20.7% in independent test. CodeGraph: 55% fewer tool calls (independent). Claude Code overhead: 14–17.6K/turn. |
| P3 | Sandbox & workspace isolation | GHCP permissions + AGT policy engine + Docker/gVisor sandbox + managed worktrees (OpenHands pattern) | PROVEN | AGT covers 7/10 OWASP Agentic Top 10 fully. Anthropic: 93% rubber-stamp rate = prompt-based security fails. |
| P4 | Frontier model dependency → cost | HyDRA capability-profile routing + cascade with test gate | PROVEN | GitHub A/B: \~1M users/arm, 7–20% cost reduction. Quality within fractions of a point. |
| P4b | Routing latency | Jev "System One" classifier: typed probabilities, sub-200ms, $0.00035/call | PROVEN | LangSmith: 500/500 binary decisions. 92–913× lower variance than LLM judges. |
| P5 | Human-in-the-loop deficits | Graduated autonomy + kill switch (>5 iterations) + `onPermissionRequest` hooks | PROVEN | METR RCT: +19% time with AI. Google ADK 2.0: strict kill switch. Anthropic: check-ins at plan approval + pre-merge. |
| P6 | Prompt fragility across personas | DSPy/GEPA for stable pipelines. OpenAI Astra guidance: lean skills as routers, define "done" upfront | PROVEN pipelines only | GEPA (ICLR 2026 oral): +14% vs MIPROv2. OpenAI: "make sure to run tests" instructions now cause unnecessary testing on strong models. |
| P7 | Sub-agents & worktrees | Isolated sub-agents (OpenHands pattern), fresh context, capped at 3 | USE WITH CAPS | Anthropic: multi-agent beat single by 90.2% but at 15× tokens. Single frontier model better for tightly-coupled tasks. |
| P8 | Skill selection without evaluation | SkillsBench paired eval, ACES CI, cap 1–3 active skills | PROVEN | Curated: +18–25 pp. Self-generated: −8 to −11 pp. Bundles >3 degrade from +19 to +10 pp. |
| ⚠ RABBIT HOLES |  |  |  |  |
| ⚠ | OpenClaw always-on agents | Heartbeat replays, 35.6K tokens/message | RISKY | 180M tokens/month (\~$3,600). Take worktree concept only. |
| ⚠ | Ralph loops (verifier-less) | Recursive restart without verifier | RISKY | "Expensive way to burn tokens." Cap 20 iterations + require machine-checkable stop. |
| ⚠ | Multi-agent swarms | N agents for breadth-first | HIGH COST | 15× chat tokens. arXiv 2602.01011: "Multi-Agent Teams Hold Experts Back." |
| ⚠ | Self-generated skills / Harness Evolver | Agent writes its own SKILL.md | HYPE | SkillsBench: 8–11 pp below no-skills baseline. |
| ⚠ | Caveman (terse output skill) | Claims 65% token cut by "talking like a caveman" | GIMMICK | Maintainer's own rerun: 3% median savings vs a plain "be concise" instruction. No effect on Copilot (issue #506). |
| ⚠ | HydraFusion | Multi-model panel per request | RESEARCH ONLY | No model allowlists, no plan mode, hidden drafts, billing = sum of all models. Enterprise policy unclear. |

## 7. Token Reduction & Code Knowledge Tooling (Vetted)

| Tool | What | Evidence | Verdict |
| --- | --- | --- | --- |
| **Headroom** `headroomlabs-ai/headroom` | Context compression: library + proxy + MCP server. Content router sends JSON to SmartCrusher, code to tree-sitter compressor. Originals kept locally, model calls `headroom_retrieve` to recover full content. | Independent test (Russ McKendrick): 8.9M → 7.1M tokens (20.7%) over 152 requests. Dashboard credited $9.23 to compression vs $47.36 to prefix-cache discount. 0.21ms p50 compression latency. | PILOT — real but modest. Telemetry on by default (`HEADROOM_TELEMETRY=off`). Best for JSON-heavy tool outputs. |
| **CodeGraph** `colbymchenry/codegraph` | Pre-indexed code graph (tree-sitter → SQLite). Auto-syncs via file watchers. One `codegraph_explore` call returns relevant source, call paths, blast radius. Works with Copilot. | Independent test (HarrisonSec, 40 runs on Hono): tool calls −55% (14.0→6.3), latency −20%, tokens −23%. But cost rose 6.8% on small repo. Gains scale with repo size. | ADOPT — most dependable benefit is fewer, more predictable steps. Add to Creator mode. |
| **Graphify** `Graphify-Labs/graphify` | Code + docs + SQL + PDFs → knowledge graph. Local AST parsing (no embeddings). Leiden community detection. `graphify query/path/explain`. | Academic usage in arXiv papers. Token claims ("71.5×") from promotional coverage only, no independent benchmark. | PILOT — use when context spans specs, schemas and PDFs. CodeGraph is better for pure code. |
| **ripgrep** `BurntSushi/ripgrep` | Fast recursive search respecting .gitignore. Orders of magnitude faster than grep/find. | Industry standard, 50K+ stars, battle-tested. | ADOPT — use as custom tool override for GHCP's built-in grep. |
| **Caveman** `JuliusBrussee/caveman` | Skill that tells model to respond terse. Claims 65% token cut. | Maintainer's own rerun: 3% median output reduction vs "be concise" control. No effect on Copilot (issue #506). Retired stats: earlier versions "applied a fixed ratio without a committed reviewed benchmark." | SKIP — one-line "be concise; define done" captures most benefit without readability cost. |
| **Tritlo/lsp-mcp** | MCP bridge to any LSP server. | \~113 stars, v0.2.0, marked "Unvalidated" on LobeHub. | SKIP — Copilot CLI natively supports LSP servers via `lsp-config.json`. Use native LSP. |

## 8. Vetted Tooling, Skills & Governance

### Core stack

| Layer | Tool | Why |
| --- | --- | --- |
| Runtime | GHCP Copilot SDK (GA) | Same agent loop as Copilot CLI. Hooks, MCP, custom agents, OTel, multi-client sessions. |
| Routing | HyDRA (via Copilot Auto) + Jev classifier | Capability-profile routing, zero retraining on model changes. Jev for sub-200ms triage. |
| Token reduction | Headroom MCP + CodeGraph MCP | Headroom compresses tool output (\~20%). CodeGraph pre-indexes code (−55% tool calls). |
| Sandbox | GHCP permissions + Docker/gVisor + git worktrees | OpenHands-style isolation. Read+write+network fencing. |
| Governance | MS Agent Governance Toolkit (AGT) | Policy enforcement, zero-trust identity, OWASP Agentic Top 10 (7/10 full). Via `onPreToolUse` hooks. |
| Context compaction | Observation masking + Hermes-style summarization | JetBrains: masking halves cost, matches solve rate. Hermes: 20% budget, 2K floor. |
| Prompt optimization | DSPy / GEPA | ICLR 2026 oral. For metric-backed pipelines only. |
| Verification | Jev + pytest/linters + blindspot checks | $0.00035/call judge + deterministic gates + anti-gaming checks. |
| Skill evaluation | SkillsBench paired eval + ACES CI | Per-skill lift scoring. Cap 1–3 active skills per task. |
| Loop engineering | Anthropic initializer/worker pattern | Feature list JSON + progress file + git checkpoints. |

### Skill ecosystem

| Source | What | Verdict |
| --- | --- | --- |
| mattpocock/skills | \~38 composable engineering skills. MIT. Cherry-pick: `tdd`, `diagnose`, `write-a-skill`. Small, composable, nothing injects into every session. | ADOPT selectively |
| OpenAI Astra guidance | "Revisit skill descriptions to avoid bloated context." Make root doc a minimal router. Drop scaffolding written for older models. Define "done" upfront. | APPLY to all skills |
| addyosmani/agent-skills | Production-grade modular skills with context-aware activation | REFERENCE |
| anthropics/skills, openai/skills, microsoft/skills | Official vendor skill catalogs | BASELINE |
| skillmatic-ai/awesome-agent-skills | Curated directory of all skill sources + marketplaces + benchmarks | DISCOVERY |

### MS Agent Governance Toolkit — caveats

Public Preview (Beta classifier on PyPI). Marketing says "10/10 OWASP Agentic Top 10" but own docs say 7/10 full, 3/10 partial. v4→v5 had breaking migration. Pin exact versions. Use for policy enforcement via `onPreToolUse` hooks, but keep your own policy layer thin so you can swap it.

### Dynamic workflows (arXiv 2608.25512)

The Cordis paper formalizes "spatiotemporal composability" for plugin systems: every plugin registers an undo (revertible effects), dependencies are declared reactively (reactive coeffects). Practical takeaway: every hot-loaded skill, MCP server, or sub-agent should register an undo for everything it changes. Use this as a **design pattern**, not a dependency.

## 9. Three Personas × Three Test Suites

Every test produces 4 metrics. Both minimal and creator modes run the same tasks. Delta = what the harness adds.

|  | T1: Long-Prompt Minecraft Builder [\[prompt doc\]](https://docs.google.com/document/d/1gLob3fq25TWFdevQIWwsNCilOp7q4rlIqNiRvew4Sx4/edit?tab=t.0) | T2: Multi-Turn Financial Agent [\[FinCon/InvestorBench\]](https://github.com/The-FinAI/FinCon) | T3: Long-Running Sub-Agents + Worktrees [\[OpenHands\]](https://github.com/All-Hands-AI/OpenHands) |
| --- | --- | --- | --- |
| C-Level | Cost governance. Token caps prevent runaway. **Pass:** task completes within budget. Minimal vs creator cost delta visible. | ROI on financial decision quality. **Pass:** harness-routed agent achieves ≥comparable Sharpe ratio at ≤50% cost of single-frontier. | Pareto telemetry. Cost vs quality vs latency. **Pass:** routing cuts cost ≥40% vs baseline. |
| TPM | Skill evaluation. Paired lift via trajectory view. **Pass:** skill lift >15 pp on spatial tasks. | Loop engineering. FinCon schema change triggers check-in. **Pass:** recovery without manual prompt editing. | Graph orchestration. Decompose epic → workers. **Pass:** all worktree merges pass verification. |
| Dev / DS / AI Eng. | Context compaction. Maintain constraints over 100K+ tokens. **Pass:** flat context trajectory (CodeGraph + Headroom keep growth sub-linear). | Tool failure recovery. Intentional API break → log → rewrite → retry. **Pass:** ≤2 retries. | Sandbox isolation. Sub-agents can't read outside project. **Pass:** read/write/network fenced. AGT audit log clean. |

### Benchmark protocol (from Anthropic + arXiv 2609.11987)

Pin one model (not Auto/HydraFusion). Fresh container per trial. 5–10 runs per mode. Score: deterministic block-checks + blind pairwise human judging. Measure cache-inclusive tokens correctly (arXiv 2609.11987 found double-counting invalidated cost conclusions). Ablate one component at a time.

Prompt Tokens

\<8K/turn

Context Tokens

flat growth

Cache Tokens

≥60% ratio

Cost / Task

≤50% baseline

## 10. Blindspot Detection Checklist

**Core problem:** Agent can mark `"passes": true` without verifying, use fallback defaults to pass tests, or silently skip error paths.

| Blindspot | Detection | Automated check |
| --- | --- | --- |
| **B1: Fallback codes** | AST analysis for bare `except: pass`, `catch {}`, hardcoded returns | AST walker + Jev: "real result or stub?" |
| **B2: Done without e2e** | Check trajectory for e2e tool call BEFORE status flip | Flip blocked if no Puppeteer/Playwright call after last code change |
| **B3: Tests test the mock** | If `mock.patch('module.func')` in test of `module.func`, flag | pytest plugin: mock target == test target → reject |
| **B4: Context rot** | tool_call_success_rate per 10-turn window | Alert on >20% failure rate → trigger compaction |
| **B5: Victory declared early** | Parse `feature_list.json`, count `"passes": false` | If >0 remaining + agent says "done" → session paused |
| **B6: Permission escalation** | Sandbox audit log: access outside project scope | AGT policy engine blocks + logs via `onPreToolUse` |
| **B7: Idle loop burn** | >5 iterations without commit or status change | Kill switch → escalate to human |
| **B8: Skill injection** | SkillCheck scanner pre-admission | Reject skills with override instructions or external fetches |
| **B9: Sub-agent leakage** | Response >2K tokens | Compress to structured summary before parent injection |
| **B10: DSPy over-optimization** | Held-out validation set | MAS-PromptBench: keep only if beats seed on validation |

### 3-layer verification gate

```
Layer 1: DETERMINISTIC (every commit)
  Linters, AST analysis, B1-B3-B5 detectors, feature_list.json integrity, sandbox audit

Layer 2: JEV JUDGE (per feature, $0.00035/call)
  "Real result or stub?" · "Matches feature description?" · "Untested error paths?"

Layer 3: E2E VERIFICATION (before "passes: true")
  Browser automation (Puppeteer/Playwright) or domain-specific verification
  FinCon: market simulation verification · Minecraft: block-diff against spec
  Human check-in for high-stakes state changes
```

## 11. Research Adoption List

**Anthropic: Effective harnesses for long-running agents** — Nov 2025. Initializer/worker, JSON feature list, git-as-memory. ADOPT — Loop Eng. spec

**Anthropic: Harness design for long-running app dev** — Mar 2026. Solo=$9, harness=$200, visibly better. Fresh container per trial. ADOPT — benchmark protocol

**Anthropic: Effective context engineering** — Progressive disclosure, compaction, sub-agent isolation. ADOPT

**HyDRA** — arXiv 2605.17106. Capability-profile router, A/B at \~1M users, 7–20% cost reduction. ADOPT (via Copilot Auto)

**HydraFusion** — GitHub blog, Sep 2026. Cascade workflow. RESEARCH ONLY — no model allowlists

**Jev** — TypeSafe AI. 500/500 decisions, $0.00035/call. arXiv 2609.34862. ADOPT

**GEPA** — ICLR 2026 oral. +14% vs MIPROv2, 9.2× shorter prompts. ADOPT for pipelines

**Observation Masking** — JetBrains, arXiv 2508.21433, NeurIPS '25. Halves cost, matches solve rate. ADOPT

**The Harness Effect** — arXiv 2607.06906. −41% cost/task from orchestration alone. ADOPT — validates harness investment

**The Scaffold Effect** — arXiv 2607.22585. Harness = hidden eval variable. More ≠ better. REFERENCE

**Harness or Model?** — arXiv 2609.11987. Cache token double-counting invalidated cost conclusions. Careful metric accounting. ADOPT — metric methodology

**SkillsBench** — arXiv 2602.12670. Curated +16.6 pp, bundles 1–3 best. Self-gen −8 to −11 pp. ADOPT

**ACES** — arXiv 2608.20614. CI-integrated skill lift + trajectory metrics. ADOPT

**Loop Engineering** — arXiv 2608.21884. Bounded runs, verifiers, budgets, escalation. ADOPT WITH VERIFIERS

**OpenAI: Rethinking skills for GPT-6 Astra** — Sep 2026. Lean skills, routers, drop old scaffolding, define "done." APPLY to all skills

**MS Agent Governance Toolkit** — MIT, Public Preview. Policy, zero-trust identity, sandbox, SRE. 7/10 OWASP full. PILOT — pin versions, plan for breaks

**Spatiotemporal Composability (Cordis)** — arXiv 2608.25512. Revertible effects + reactive coeffects for plugin hot-swap. DESIGN PATTERN

**Dynamic Workflows** — arXiv 2606.00189: hand-engineered static workflows "usually perform best." Use static scaffolding + dynamic choices in bounded slots. ADOPT — static + bounded dynamic

**Google ADK 2.0 kill-switch** — >5 iteration cap. ADOPT

**OpenRouter Auto** — Routes by community spend, 7-day window. ADOPT

**FinCon / InvestorBench** — github.com/The-FinAI/FinCon. Open-source testbed for LLM trading agents. TEST SUITE T2

**OpenHands** — github.com/All-Hands-AI/OpenHands. Managed worktrees + sub-agent delegation. Docker sandbox. ADOPT isolation patterns

**Multi-Agent Teams Hold Experts Back** — arXiv 2602.01011. CAUTION

**O'Reilly Harness Engineering** — Koenigstein. github.com/Nicolepcx/harness_engineering REFERENCE

**awesome-agent-skills** — github.com/skillmatic-ai/awesome-agent-skills DISCOVERY

## 12. Three-Week Roadmap

| Week | Focus | Persona | Delivers |
| --- | --- | --- | --- |
| Week 1 | Core harness + isolation + observability | Dev / AI Eng. | D1–2: GHCP SDK setup. Define minimal.agent.md + creator.agent.md. Wire Python tool servers via MCP. D3: Sandbox isolation (Docker/gVisor + git worktrees + AGT policy hooks). OpenHands-style worktree pattern. D4: Session log + OTel tracing via GHCP hooks. 4-metric dashboard. CodeGraph MCP + Headroom MCP. D5: Python verification tools (Jev judge, AST fallback detector, circular mock detector). End-to-end smoke test. Solves: P1, P2, P3 |
| Week 2 | Routing + loop engineering + blindspot detection | TPM + AI Eng. | D6–7: HyDRA routing via Copilot Auto config. Jev classifier as pre-router. Cascade with test gate. D8: Anthropic initializer/worker pattern (feature_list.json, progress.txt, init.sh, git checkpoints). D9: Full blindspot detection layer (B1–B10). 3-layer verification gate wired to GHCP hooks. D10: DSPy/GEPA for 2–3 stable modules. Graduated autonomy + kill switch. MAS-PromptBench guard. Solves: P4, P5, P6 + blindspots |
| Week 3 | Multi-agent + skills + QA + governance | C-Level + All | D11: Sub-agent orchestration via GHCP customAgents. OpenHands-style worktree isolation. Token compaction. D12: Skill eval (SkillsBench + ACES CI gate). Admit mattpocock/tdd + diagnose. Run SkillCheck security scanner. D13–14: Run 3×3 test matrix (Minecraft + FinCon + OpenHands patterns). Both modes. 4 metrics + blindspot flags per run. Ablate one component at a time. D15: Governance policies (AGT). ROI dashboard. Client demo + sign-off. Solves: P7, P8 + validation |

**Bottom line:** Build on **GHCP Copilot SDK**. Define minimal + creator modes as `.agent.md` profiles on the same runtime. Compress context with **Headroom + CodeGraph**. Route with **HyDRA + Jev**. Govern with **MS AGT via hooks**. Loop with **Anthropic initializer/worker**. Verify with **3-layer gate (deterministic → Jev → e2e)**. Benchmark with pinned models, fresh containers, blind judging. Track 4 metrics + 10 blindspot flags per run. Borrow isolation from OpenHands, compression from Hermes, skill discipline from OpenAI Astra guidance. Avoid unverified loops, swarms, self-generated skills, Caveman, and HydraFusion until GA.