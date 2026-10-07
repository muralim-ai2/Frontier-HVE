# Enterprise AI Harness Blueprint v2

dsh (Cordis) + Python Tools · Anthropic Long-Running Pattern · Blindspot Detection · 3 Weeks

1. [Engineering Progression (5 Layers)](#s1)
2. [Architecture: dsh Orchestrator + Python Tools](#s2)
3. [System Flow: Problem → Decision → Execution](#s3)
4. [Anthropic Long-Running Agent Pattern](#s4)
5. [Ranked Problems × Proven vs Rabbit Hole](#s5)
6. [Vetted Tooling & Skill Ecosystem](#s6)
7. [3 Personas × 3 Test Suites + 4 Metrics](#s7)
8. [Blindspot Detection Checklist](#s8)
9. [Research Adoption List](#s9)
10. [3-Week Roadmap](#s10)

## 1. Engineering Progression: What Each Layer Adds

Each layer widens what you control. The model stays fixed — only the harness changes.

## 2. Architecture: dsh Orchestrator + Python Tools

dsh (TypeScript/Cordis) is the orchestrator you **configure**, not code. Your Python runs as tools via MCP/subprocess. The harness language is irrelevant to domain logic.

```
dsh (Cordis kernel, TypeScript)        ← configure via settings.yaml, don't code
│
├── settings.yaml                      ← model routing, plugin config, token caps
├── plugins/                           ← hot-swappable: session log, sandbox, loop
│   ├── session-log (append-only)      ← trajectory view, OTel export
│   ├── sandbox (WASM / worktree)      ← read+write+network fencing
│   ├── compaction                     ← observation masking, deferred tools
│   └── routing (HyDRA pattern)        ← capability-profile YAML per model
│
└── tools/ (MCP servers → YOUR PYTHON)
    ├── skills/                        ← SKILL.md format, paired-eval gated
    │   └── (cross-platform: Claude Code, Codex, Copilot, Cursor, OpenCode)
    ├── verify/                        ← Jev judge + pytest + linters + blindspot checks
    ├── optimize/                      ← DSPy/GEPA pipelines (metric-backed only)
    ├── observe/                       ← metrics collection → OTel → dashboard
    └── domain/                        ← client's non-coding workflows (Python)
```

**Why this works for a Python DS:** dsh calls Python tools via MCP servers or subprocess. You write Python for everything that matters — domain logic, skills, evaluation, DSPy, verification judges. dsh handles the plumbing (agent loop, plugin lifecycle, session log, routing). You configure it via YAML and markdown manifests, no TypeScript required for 90%+ of use cases.

## 3. System Flow: Problem → Decision → Execution Loop

Every user request flows through this loop. Each node maps to a ranked problem we solve.

## 4. Anthropic Long-Running Agent Pattern

From [Anthropic Engineering (Nov 2025)](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents). This is our implementation spec for the Loop Engineering layer.

**Core insight:** Agents fail across context windows because (1) they try to one-shot everything, (2) they leave broken state for the next session, (3) they declare victory early, (4) they mark features done without e2e testing. The fix: structured handoff files + git history as memory between windows.

### Two-part solution we adopt

| Component | Runs | What it does | Artifacts it creates |
| --- | --- | --- | --- |
| **Initializer Agent** | Once per epic | Sets up environment for all features. Prevents one-shotting. | `feature_list.json` (all features marked "passes: false"), `progress.txt`, `init.sh`, initial git commit |
| **Worker Agent** | Every session | Picks ONE feature, implements, tests e2e, commits, updates progress. Leaves clean state. | Git commit with descriptive message, updated `progress.txt`, feature status flipped to "passes: true" only after e2e verification |

### Worker agent session flow (from Anthropic)

```
1. Run `pwd` — see the working directory
2. Read git logs + progress.txt — get up to speed
3. Read feature_list.json — pick highest-priority failing feature
4. Run init.sh — start dev server
5. Run basic e2e test — verify app isn't broken from last session
6. Implement ONE feature
7. Test e2e (browser automation / domain-specific verification)
8. If passes → mark "passes: true", git commit, update progress.txt
9. If fails → fix, retry (max 5 attempts, then escalate)
```

**Critical rules from Anthropic:** Use JSON for feature list, not Markdown — model is less likely to overwrite JSON. Strongly word: "It is unacceptable to remove or edit tests." Agent may only change the `passes` field. This prevents the agent from gaming its own success criteria.

## 5. Ranked Problems × Proven vs Rabbit Hole

**Key evidence:** Multi-agent systems use \~15× more tokens than chats (Anthropic). Users rubber-stamp \~93% of permission prompts (Anthropic). METR RCT (246 tasks, 16 devs): AI tools increased completion time by 19%. Self-generated skills score 8–11 pp below no-skills baseline (SkillsBench). Observation masking halves cost while matching solve rate (JetBrains, NeurIPS '25).

| # | Problem | Technique | Verdict | Evidence |
| --- | --- | --- | --- | --- |
| P1 | Opaque observability → sub-standard outputs | Append-only session log + Trajectory View (dsh pattern) | PROVEN | dsh community plugins track steps, LLM failures, tool latency. Copilot SDK uses OTel. |
| P2 | Token explosion & context rot | Observation masking, deferred tools, PTC code-mode, context compaction | PROVEN | JetBrains: masking halves cost, matches solve rate. Claude Code overhead: 14–17.6K/turn. Practitioner cut 25K→8K by disabling unused tools. |
| P3 | Sandbox & workspace isolation | WASM/gVisor + managed worktrees (Btrfs/APFS snapshots) | PROVEN | dsh "Workspace Write" fences writes only — must add read fencing. Anthropic: 93% rubber-stamp rate means prompt-based security fails. |
| P4 | Frontier model dependency → cost | HyDRA capability-profile routing + cascade with test gate | PROVEN | GitHub A/B: \~1M users/arm, 7–20% cost reduction. V4-Pro→V4-Flash = 14× price diff. |
| P4b | Routing latency | Jev "System One" classifier | PROVEN | LangSmith: 500/500 binary decisions, $0.00035/call, 92–913× lower variance than LLM judges. |
| P5 | Human-in-the-loop deficits | Graduated autonomy: report-only → assisted → unattended + kill switch (>5 iterations) | PROVEN | METR RCT: +19% time with AI. Google ADK 2.0: strict iteration kill switch. |
| P6 | Prompt fragility across personas | DSPy/GEPA for stable pipelines only | PROVEN pipelines only | GEPA (ICLR 2026 oral): +14% vs MIPROv2, 9.2× shorter prompts. Converges to deference in multi-agent. |
| P7 | Sub-agents & worktrees | Isolated sub-agents, fresh context per iteration, capped at 3 | USE WITH CAPS | Anthropic: multi-agent beat single by 90.2% but at 15× tokens. Cold-start delegation. |
| P8 | Skill selection without evaluation | SkillsBench paired eval, ACES CI, cap at 1–3 active skills | PROVEN | Curated skills: +18–25 pp. Self-generated: −8 to −11 pp. |
| ⚠ RABBIT HOLES |  |  |  |  |
| ⚠ | OpenClaw always-on agents | Heartbeat replays, 35.6K tokens/message | RISKY | 180M tokens/month (\~$3,600). Take worktree concept only, neutralize defaults. |
| ⚠ | Ralph loops (verifier-less) | Recursive restart without independent verifier | RISKY | "Expensive way to burn tokens." Cap at 20 iterations + require machine-checkable stop. |
| ⚠ | Multi-agent swarms | N agents for breadth-first | HIGH COST | 15× chat tokens. Tightly coupled tasks do better with single frontier model. |
| ⚠ | Self-generated skills | Agent writes its own SKILL.md | HYPE | SkillsBench: 8–11 pp below no-skills baseline. |
| ⚠ | Harness Evolver (autonomous skill evolution) | Multi-agent proposers evolve behaviors | HYPE | Same self-gen problem. Uncontrolled mutation without eval = quality regression. |

## 6. Vetted Tooling & Skill Ecosystem

### Core stack (build on these)

| Layer | Tool | Why |
| --- | --- | --- |
| Plugin kernel | dsh / Cordis (MIT) | Everything-is-a-plugin. Hot-swap. Reversible registrations. |
| Session log | dsh append-only log | Trajectory View, OTel export, step/failure/latency tracking. |
| Agent config | OpenCode agent definitions | Config-driven agents with model/prompt/perms/step-limits. Stable. |
| Routing | HyDRA pattern + Jev classifier | Capability-profile YAML + cascade + test gate. Production A/B evidence. |
| Sandbox | WASM (gVisor) + git worktrees | Read+write+network fencing. Btrfs/APFS snapshots for instant spin-up. |
| Context compaction | dsh compaction plugins + observation masking | Halves cost (JetBrains evidence). Deferred tool loading. |
| Prompt optimization | DSPy / GEPA | ICLR 2026 oral. For metric-backed pipelines only. |
| Verification | Jev + pytest/linters + blindspot checks | $0.00035/call judge + deterministic gates + anti-gaming checks. |
| Skill evaluation | SkillsBench paired eval + ACES CI | Per-skill lift scoring. Cap 1–3 active skills per task. |
| Loop engineering | Anthropic initializer/worker pattern | Feature list JSON + progress file + git checkpoints. |
| Sub-agent backends | Claude Code, Codex, Copilot (via dsh providers) | Delegation targets. dsh already supports 6 backends. |

### Skill ecosystem (cross-platform SKILL.md standard)

Skills are now supported by Claude Code, OpenAI Codex, GitHub Copilot, Cursor, VS Code, OpenCode, Gemini CLI, Manus, and more. Use the SKILL.md format for portability.

| Source | What | Use |
| --- | --- | --- |
| anthropics/skills | Official Anthropic skill catalog | Baseline reference |
| openai/skills | Official OpenAI skill catalog | Cross-provider testing |
| microsoft/skills | Azure SDK + AI Foundry skills | Client's Azure workflows |
| addyosmani/agent-skills | Production-grade modular skills with context-aware activation | Context compaction patterns |
| benchflow-ai/SkillsBench | 86 tasks × 11 domains benchmark | Paired eval framework |
| huggingface/upskill | Generate and evaluate skills | Skill creation + eval pipeline |
| skillmatic-ai/awesome-agent-skills | Curated directory of everything above + marketplaces | Discovery & reference |

### Vetted from your notes

| Tool | Verdict | Action |
| --- | --- | --- |
| addyosmani/agent-skills | GOOD | Use as skill template reference, context-aware activation patterns |
| dsh compaction plugins | ADOPT | Core architecture — plugins preserve semantics during summarization |
| Citadel/Orca (cross-agent worktrees) | VET FIRST | Right concept — check if real production code or markdown-heavy |
| Mitos MicroVMs | VET FIRST | Snapshot-fork microVMs are ideal sandbox. Check availability/stability |
| Harness Evolver | AVOID | Autonomous skill evolution = self-gen problem (−8 to −11 pp) |
| Harness AI 3.0 | REFERENCE | Enterprise product, not open source. Good sandbox pattern reference |
| walkingslabs/learn-harness-eng (15K★) | STUDY | Educational repo, not a framework. Good for loop engineering primitives |
| Google ADK 2.0 kill-switch | ADOPT | >5 iteration cap pattern. Production-grade. |
| MindStudio Loop Platform | REFERENCE | Hosted platform. Good abstraction (cadence vs infrastructure) but vendor lock-in |
| DenisSergeevitch/agents-best-practices | VET FIRST | "Production-ready blueprints" claim needs star count / age verification |

## 7. Three Personas × Three Test Suites

Every test produces 4 metrics. Results must be comparable across personas. Feature list uses JSON (per Anthropic — less likely to be overwritten by the model).

|  | T1: Long-Prompt Minecraft Builder | T2: Multi-Turn Agentic Workflow | T3: Long-Running Sub-Agents + Worktrees |
| --- | --- | --- | --- |
| C-Level | Cost governance. Trajectory View cost breakdown. Token caps prevent runaway spend. **Pass:** task completes within budget. | Participatory AI. Schema change triggers check-in. Exec approves. **Pass:** zero unverified state changes. | Pareto telemetry dashboard. Cost vs quality vs latency. **Pass:** routing cuts cost ≥40% vs single-frontier. |
| TPM | Skill evaluation. Paired lift in Trajectory View. **Pass:** skill lift >15 pp on spatial tasks. | DSPy compilation. TPM defines goal → harness compiles prompt. **Pass:** schema-recovery without manual editing. | Graph orchestration. Decompose epic → assign workers. **Pass:** all worktree merges pass verification. |
| Dev / DS / AI Eng. | Context compaction. Maintain constraints over 100K+ tokens. **Pass:** flat context trajectory (no exponential growth). | Tool failure recovery. Intentional schema break → log → rewrite → retry. **Pass:** auto-recovery in ≤2 retries. | Sandbox isolation. Sub-agents can't read outside project. HyDRA routes mechanical tasks to Flash. **Pass:** read/write/network fenced. |

### 4 metrics per run

Prompt Tokens

\<8K/turn

Context Tokens

flat growth

Cache Tokens

≥60% ratio

Cost / Task

≤50% baseline

Additional: wall-clock time, model per step (routing log), verification pass/fail, human escalation count, sub-agent count, worktree merge success, blindspot flags.

## 8. Blindspot Detection Checklist

The Anthropic article identified agents gaming their own success criteria. These checks catch that and other blindspots.

**The core problem:** An agent can mark `"passes": true` without actually verifying, use fallback/default values to pass tests, or silently skip error paths. Without independent verification, you won't know until production.

| Blindspot | How it manifests | Detection | Automated check |
| --- | --- | --- | --- |
| **Fallback codes used to pass** | Agent returns hardcoded defaults, HTTP 200 with empty body, or catches all exceptions silently | Grep for bare `except: pass`, `catch {}`, hardcoded return values in test paths | AST analysis: flag functions where every error path returns a default. Jev judge: "does this output look like a real result or a stub?" |
| **Feature marked done without e2e test** | Agent flips `"passes": true` based on unit tests or curl, not real user flow | Require Puppeteer/Playwright screenshot or domain-specific e2e verification before status flip | Trajectory View: check that a browser automation / e2e tool was called BEFORE the status-flip commit |
| **Tests that test the mock, not the system** | Agent writes unit tests that mock the exact function being tested | Static analysis: if a test mocks the function it's testing, flag it | pytest plugin: detect when mock target == test target. Flag circular mocking. |
| **Context rot causing hallucinated tool calls** | After 100K+ tokens, agent calls tools with wrong schemas or invents tool names | Monitor tool call success rate per turn number. Spike in failures = rot signal | Trajectory View: plot tool_call_success_rate vs turn_number. Alert on >20% failure rate. |
| **Agent declares victory early** | Agent sees partial progress and says "done" | Feature list JSON: count remaining `"passes": false`. If >0 and agent says done = flag | Post-session check: parse feature_list.json, compare passes count to total. Reject "done" if ratio \<100%. |
| **Silent permission escalation** | Agent reads files outside project, makes network calls to unexpected hosts | Sandbox audit log: any read/write/network outside fenced scope = hard fail | WASM/gVisor: log all syscalls. Alert on any access outside declared scope. |
| **Token-burning idle loops** | Agent stuck in retry loop, heartbeat replays, or "thinking" without producing output | Monitor tokens_per_useful_output ratio. Spike = loop detected | Kill switch: >5 consecutive iterations without a git commit or status change = escalate to human. |
| **Prompt injection via skills** | Malicious SKILL.md overrides system instructions or exfiltrates data | Skill security audit before registry admission | SkillCheck scanner (agentigy/skillcheck). Reject skills that contain instructions to override system prompt or make external network calls. |
| **Sub-agent context leakage** | Sub-agent result dumps raw tool output into parent context, bloating it | Cap sub-agent response size. Summarize before injecting into parent. | Post-delegation filter: if sub-agent response >2K tokens, compress to structured summary before parent injection. |
| **DSPy over-optimization** | GEPA converges to "extreme-deference" prompts that suppress agent deliberation | Hold out validation set. Compare optimized vs seed prompt on held-out tasks | MAS-PromptBench pattern: keep optimized prompts only if they beat seed on validation. |

### Implementation: 3-layer verification gate

```
Layer 1: DETERMINISTIC (runs every commit)
  - Linters, type checkers, AST analysis
  - Fallback-code detector (grep bare except/catch)
  - Circular mock detector
  - Feature list JSON integrity check
  - Sandbox audit log review

Layer 2: JEV JUDGE (runs per feature completion, $0.00035/call)
  - "Does this output look like a real result or a stub?"
  - "Does this implementation match the feature description?"
  - "Are there untested error paths?"
  - Returns typed probability, not generated text

Layer 3: E2E VERIFICATION (runs before "passes: true")
  - Browser automation (Puppeteer/Playwright) for web features
  - Domain-specific verification for non-coding workflows
  - Screenshot evidence captured in Trajectory View
  - Human check-in for high-stakes state changes
```

## 9. Research Adoption List

**Anthropic: Effective harnesses for long-running agents** — Nov 2025. Initializer/worker pattern, feature list JSON, git-as-memory, e2e testing before status flip. ADOPT — our Loop Eng. spec

**Anthropic: Effective context engineering for AI agents** — Progressive disclosure, compaction, sub-agent isolation. ADOPT

**HyDRA** — arXiv 2605.17106. Capability-profile router, zero retraining on model changes, A/B at \~1M users. ADOPT

**HydraFusion** — GitHub blog, Sep 2026. Cascade workflow only (cheap draft → test gate → escalate). ADOPT CASCADE ONLY

**Jev** — TypeSafe AI. 500/500 decisions, $0.00035/call. arXiv 2609.34862. ADOPT

**GEPA** — ICLR 2026 oral. +14% vs MIPROv2, 9.2× shorter prompts. ADOPT for pipelines

**Observation Masking** — JetBrains, arXiv 2508.21433, NeurIPS '25. Halves cost, matches solve rate. ADOPT

**The Harness Effect** — arXiv 2607.06906. −41% cost/task, −38% tokens from orchestration alone. ADOPT

**The Scaffold Effect** — arXiv 2607.22585. More harness ≠ more quality. REFERENCE

**SkillsBench** — arXiv 2602.12670. Curated +16.6 pp, bundles 1–3 best. Self-gen −8 to −11 pp. ADOPT

**ACES** — arXiv 2608.20614. CI-integrated skill lift + trajectory metrics. ADOPT

**Loop Engineering** — arXiv 2608.21884. Bounded runs, verifiers, budgets, escalation. ADOPT WITH VERIFIERS

**Google ADK 2.0 kill-switch** — >5 iteration cap. ADOPT

**OpenRouter Auto** — Routes by community spend, 7-day window. ADOPT

**LOCA-bench** — arXiv 2602.07962. Benchmark for context growth. BENCHMARK

**O'Reilly Harness Engineering** — Koenigstein. Ch 1–2 available. github.com/Nicolepcx/harness_engineering REFERENCE

**Multi-Agent Teams Hold Experts Back** — arXiv 2602.01011. Single frontier model beats swarms on coupled tasks. CAUTION

**awesome-agent-skills** — github.com/skillmatic-ai/awesome-agent-skills. Curated directory + marketplaces + benchmarks. REFERENCE

## 10. Three-Week Roadmap

| Week | Focus | Persona | Delivers |
| --- | --- | --- | --- |
| Week 1 | Core harness + isolation + observability | Dev / AI Eng. | D1–2: Cordis plugin kernel (model adapter, tool registry, session log, agent loop) D3: WASM sandbox + git worktree isolation (Btrfs/APFS) D4: Append-only session log + Trajectory View + OTel export D5: Python MCP tool servers (verify, observe, domain) connected to dsh Solves: P1, P2, P3 |
| Week 2 | Routing + loop engineering + blindspot detection | TPM + AI Eng. | D6–7: Jev classifier + HyDRA capability routing (settings.yaml) D8: Anthropic initializer/worker pattern (feature_list.json, progress.txt, init.sh) D9: Blindspot detection layer (fallback detector, circular mock detector, kill switch) D10: DSPy/GEPA pipeline for 2–3 stable modules + graduated autonomy check-ins Solves: P4, P5, P6 + blindspots |
| Week 3 | Multi-agent + skills + QA + governance | C-Level + All | D11: DAG orchestration + sub-agent worktrees + token compaction D12: Skill eval pipeline (SkillsBench paired eval + ACES CI gate) D13–14: Run 3×3 test matrix, capture 4 metrics + blindspot flags per run D15: Governance policies + ROI dashboard + client sign-off Solves: P7, P8 + validation |

**Bottom line:** Build on **dsh (Cordis kernel)**, configure in YAML, write domain logic in **Python via MCP tools**. Adopt Anthropic's initializer/worker pattern for loop engineering. Gate every feature completion through the 3-layer verification (deterministic → Jev judge → e2e). Track 4 metrics + blindspot flags per run. Avoid unverified loops, swarms, self-generated skills, and always-on agents.