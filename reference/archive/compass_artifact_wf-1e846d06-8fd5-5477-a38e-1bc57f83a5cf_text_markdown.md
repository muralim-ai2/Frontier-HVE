# Building a Custom Enterprise AI Harness: Platforms, Problems, Techniques, and Hype (October 2026)

For a custom enterprise harness, build on an open, plugin-first core and treat the vendor harnesses as things you delegate to, not foundations. OpenCode (MIT) is the most mature open base today. DeepSeek Harness (MIT, developer preview) is the best reference design for observability and swappable runtime parts. The GitHub Copilot SDK is the pragmatic choice if you are a Microsoft/GitHub shop that can accept a proprietary runtime. Claude Code is closed and should be integrated as a sub-agent backend. The highest-impact investments are context and token discipline, per-step model routing, and machine-checkable verification. The weakest-evidence ideas are multi-agent swarms, unattended loops and always-on agents, which reliably raise cost but only sometimes raise quality.

## TL;DR

- **Platform choice:** Use OpenCode or DeepSeek Harness as the open chassis (both MIT, plugin/hook-driven, model-agnostic). Use the Copilot SDK if you want a GA, OpenTelemetry-instrumented runtime and can live with proprietary code. Use Hermes for long-lived, multi-channel assistants rather than coding. Claude Code is proprietary; call it as a delegation target.
- **Biggest problems, by impact:** (1) context/token bloat from replayed history, system prompts and tool output; (2) running everything on frontier models when routing could cut cost by half or more; (3) weak verification, which makes long runs and loops degrade or game tests. Sub-agents, skills and prompt optimizers help only when they are measured against your own tasks.
- **Hype check:** Loop engineering, Ralph loops, OpenClaw-style always-on agents, multi-model "fusion" panels and agent swarms all multiply tokens. Anthropic's engineering team reports that multi-agent research systems "use about 15× more tokens than chats," and Fusion panels cost about 4–5× a single completion. They pay off only with strong verifiers, budgets and high-value tasks. Also, the O'Reilly *Harness Engineering* book does not publicly describe "six planes." Its themes appear as chapters.

## Key Findings

### 1. Existing harnesses to build on

| Harness | License / openness | Architecture | Strengths | Limitations for enterprise |
|---|---|---|---|---|
| **DeepSeek Harness (dsh)** | MIT, open source, developer preview (tested v0.1.1-rc.2)\[1\] | Built on the Cordis plugin framework. "Everything is a plugin," including the model adapter, tool registry, session log and the agent loop itself. Named swap points (session persistence JSONL/SQLite; local or E2B sandbox executor; bash/sandboxed bash/PowerShell; six sub-agent providers including Claude Code and Codex backends)\[1\] | Best-in-class observability: an append-only session log records every prompt, reasoning step, tool call/result, sub-agent handoff and context injection, viewable in a Trajectory view. Reads AGENTS.md/CLAUDE.md and existing Claude Code hooks.json. Per-model routing in settings.yaml\[1\]\[2\] | README warns of compatibility-breaking changes. "Workspace Write" sandbox fences writes only, so reads are unconfined (a reviewer's agent read an Obsidian vault outside the project unprompted). Sub-agent delegation is a cold start with no inherited context\[1\] |
| **OpenCode** | MIT; Anomaly (formerly SST)\[3\] | Persistent local server plus separate clients (TUI, desktop, web, IDEs via ACP, CI). Config-driven agents, skills, MCP, JS/TS plugins with lifecycle hooks such as `tool.execute.before`\[4\] | 75+ providers. Built-in sub-agents (general, explore, scout) plus markdown-defined custom agents with their own model, prompt, permissions and step limits.\[3\]\[4\] Large plugin ecosystem (e.g., worktree and background-delegation bundles)\[5\] | Plugins extend the harness but cannot rewrite its core (Pi allows deeper in-process control).\[4\] Under Harbor, no turn-budget flag is exposed, so runs are bounded only by wall time\[6\] |
| **Hermes Agent (Nous Research)** | MIT, self-hosted, released February 2026\[7\]\[8\] | Synchronous `AIAgent` loop shared by CLI, gateway, ACP and batch. SQLite sessions with FTS5. Profiles with SOUL.md identity. Self-authored skill library\[9\]\[10\] | Messaging gateways (Telegram, Slack, Discord, WhatsApp, email). Compression summarizes old turns at about 20% budget (2k floor, 12k ceiling) and rotates session lineage. Delegated children default-deny dangerous commands with capped recursion\[11\]\[12\]\[13\] | Arize notes child-run lifecycle ownership as the current weak point.\[11\] Self-modifying skills need governance. Optimized for personal/persistent assistants rather than enterprise coding |
| **Claude Code** | Proprietary. Source accidentally exposed via an npm source map in v2.1.88 (31 March 2026, ~512,000 lines)\[14\] | Async-generator query loop (`query.ts`, ~1,729 lines) with explicit continue sites; ~40+ tools behind default-deny permissions; 25+ bash validators including tree-sitter AST checks; multi-stage context-compaction cascade\[15\]\[16\] | Mature permissions, hooks, skills, sub-agents and worktree isolation. Forked sub-agents reuse the parent's prompt cache\[17\] | Not extensible at the core. Heavy default overhead (see §2). Leak gives attackers a map of its guardrails\[18\]\[19\] |
| **GitHub Copilot (CLI/SDK)** | Proprietary. SDK GA 2 June 2026 (Node, Python, Go, .NET, Rust)\[20\]\[21\] | One shared agentic harness powers Copilot CLI, the Copilot app, code review and SDK experiences\[22\]\[23\] | OpenTelemetry tracing across JSON-RPC, sessions and tools. Hooks at pre/post tool use and permission requests. BYOK for OpenAI, Anthropic, Foundry and others.\[20\] 20+ models. HyDRA/HydraFusion routing\[24\] | Closed source. GitHub's benchmark claiming parity with fewer tokens is a vendor self-report\[23\]\[25\] |

**Verdict:** For a harness you own, start from **OpenCode** (stable, broad surfaces, permission model). Copy **DeepSeek Harness's** design ideas: event-log-as-truth, plugin swap points, per-step model lines. Pilot dsh itself once it leaves preview. Wrap **Claude Code/Codex/Copilot** as delegation backends, as dsh already does.\[1\] A neutral harness's value is routing work to whichever vendor agent is cheapest and good enough.

Harness choice is a real variable, not a detail. In a research-lifecycle benchmark, the minimal Mini-SWE-Agent with Claude Opus 4.7 scored 68.3% overall versus 64.6% for Hermes with the same model. Hermes with DeepSeek-V4-Flash reached 57.1%.\[26\] A "Scaffold Effect" study likewise treats harness choice as a hidden evaluation variable.\[6\] Don't assume more harness features mean more quality.

### 2. Key problems, ranked by impact

1. **Context replay and token bloat (highest impact).** Agent cost tracks accumulated context, not task size. In one dsh test, a second round cost more than twice the first despite caching, because cache reads more than doubled as the session grew.\[1\] Measured overhead in Claude Code is about 14,000–17,600 tokens of system prompt plus tool definitions.\[27\] One practitioner cut a bloated configuration from about 25K to about 8K tokens by disabling unused built-in tools.\[28\] Claude Code itself warns when custom sub-agent descriptions exceed 15,000 tokens.\[17\] Claude Code issue #46526 complains that CLAUDE.md, rules, skill listings and MCP schemas are re-sent every turn, and that raw tool output accumulates in the parent.\[29\] **Fixes:** deferred tool loading, progressive-disclosure skills, observation masking or pruning of old tool output, cache-stable prefixes, programmatic/"code mode" tool calling\[30\] (dsh's PTC mode lets the model write one TypeScript program instead of a round trip per tool call).\[1\]
2. **Frontier-model dependency.** Gartner estimates agentic workflows need 5–30× more tokens per task, and McKinsey expects most enterprise workloads to move to open-weight models.\[31\] On the DeepInfra price sheet, running the main loop on DeepSeek V4-Pro and mechanical sub-tasks on V4-Flash is a 14× output-price difference.\[1\] Routing is the biggest controllable cost lever (see HyDRA below). Note: "Gemini Astra" did not appear in any source I found. Treat it as unverified naming.
3. **Weak verification and long-run degradation.** Quality drops as contexts fill (practitioners cite roughly 100k–150k tokens as a "dumb zone"), and compaction is lossy.\[32\] Loops with shallow tests learn to game them.\[33\] Anthropic's long-running-agent harness addresses this with an initializer agent, feature lists, one feature at a time, git commits, progress files and end-to-end tests, plus full context resets with structured handoff files rather than summary-only compaction.\[34\]\[35\]
4. **Cheaper models aren't token-efficient.** At matched ~82% accuracy on OckBench, DeepSeek-V4-Flash used 83.6k tokens versus 3.2k for GPT-5.4 (medium).\[36\] Harbor-Index found frontier models use only 42% of weaker-model tokens on the easiest tasks. Weaker models were still 2–3× cheaper per trial.\[37\] Per-token price is not per-task cost, so always measure cost per *solved* task.
5. **Sandbox and workspace boundaries.** Write-only fencing (dsh) leaves reads open.\[1\] Anthropic Engineering reports that its telemetry showed Claude Code users approved "roughly 93% of permission prompts," so manual gating decays into rubber-stamping. Ralph-style loops require bypassing approvals, which exposes credentials if unsandboxed.\[38\] Enforce read *and* write scopes, network egress policy and secrets isolation at the runtime, not in the prompt.
6. **Hidden observability.** Without a model-visible event log, you cannot tell whether a failure came from the model, a tool or harness config.\[39\] dsh's append-only log and Trajectory view, plus community plugins tracking steps, LLM failures, tool latency and slowest tools, are the template.\[40\] The Copilot SDK's OpenTelemetry propagation is the enterprise-grade equivalent.\[20\]
7. **Sub-agents and worktrees.** These are useful for isolating heavy reads (anything needing more than three or four large files is a good candidate), but they cost tokens (see §4).\[41\] Delegation is a cold start, and sub-agent results still accumulate in the parent unless summarized.\[1\]\[29\]
8. **Skill/plugin selection without evaluation.** See §5. Many skills give limited benefit and some degrade performance.\[42\]
9. **Model routing for different purposes.** Solved well enough to adopt now (HyDRA, OpenRouter Auto).
10. **Prompt improvement (DSPy).** High value for stable, repeated pipelines with metrics. Low value for one-off asks.
11. **Human-in-the-loop vs fire-and-forget, and loop engineering for corrections.** The evidence favors graduated autonomy: report-only, then assisted fixes with a verifier, then unattended. Escalation points should be explicit. METR's randomized controlled trial (Becker et al., arXiv 2507.09089; 16 experienced open-source developers, 246 tasks) found that early-2025 AI tools "actually increase[d] completion time by 19%," even though developers had predicted a 24% speedup. So don't assume autonomy equals productivity.

### 3. Latest techniques and research

- **HyDRA / HydraFusion (GitHub/Microsoft).** HyDRA predicts the capabilities a query needs, then picks the cheapest model whose YAML capability profile meets them. Over four months in Copilot, it absorbed six model additions and three removals with zero retraining. On SWE-Bench Verified, LiveCodeBench and BigCodeBench it held quality within a fraction of a point of the strongest single model while cutting cost by more than half. An A/B test with close to one million users per arm estimated a 7–20% serving-cost reduction for the routed segment.\[43\] HydraFusion (research preview, 4 September 2026) adds workflow selection: **Single**, **Cascade** (cheap draft, then a quality gate, then escalation) and **Critique** (a read-only critic from a different model family, then one revision).\[44\]\[45\] It reportedly matched or exceeded an Opus 5 baseline in *offline* evaluations.\[44\] **Adopt the pattern:** a capability-profile router plus cascade with a test-based gate.
- **OpenRouter.** Auto Router routes by aggregate community spend per task type over a trailing 7-day window, with a `cost_tier` (low through max) and `max_price` caps. You pay the routed model's rate.\[46\]\[47\] Fusion runs a 1–8 model panel plus a judge. OpenRouter's own estimate is about 4–5× the cost and 2–3× the latency of a single completion, despite a "$0" alias price.\[48\]\[49\] Use Auto for convenience. Reserve Fusion for high-stakes queries.
- **DSPy / GEPA.** GEPA (ICLR 2026 oral) reflects on execution traces and evolves prompts on a Pareto front. Reported results: +14% aggregate gain versus MIPROv2's +7%, prompts up to 9.2× shorter, and outperforming GRPO by 10% on average (up to 20%) with up to 35× fewer rollouts.\[50\]\[51\] It's available as `dspy.GEPA`, standalone, and in MLflow and Google ADK.\[52\] **Caveats:** it needs a metric and training examples. In multi-agent teams it converged to "extreme-deference" prompts that suppress deliberation.\[53\] MAS-PromptBench keeps optimized prompts only if they beat the seed on validation.\[54\] For "converting user asks into better prompts," use DSPy to optimize the *rewriter* module against task outcomes, not as a per-request magic step.
- **"JEV."** I found no established "Judge-Execute-Verify" method. The closest match is **Jev**, TypeSafe AI's "System One" judge model (in LangSmith Evals since 21 September 2026). It returns typed answers with probabilities rather than generated text.\[55\] In LangChain's test it matched the oracle on all 500 binary decisions, had 92–913× lower score variance than LLM judges, and cost $0.00035 per call ($0.34 total versus $28.17 for Claude).\[56\] An arXiv security-trace study found mean F1 of 77.8 but weaker results on MCPHunt (F1 61.1).\[57\] These are largely vendor or partner-reported. The underlying *pattern* (planner/maker, independent verifier, judge) is well supported, e.g., Prosecutor–Judge protocols and maker/checker loops.\[58\]\[59\]
- **Loop engineering.** Coined in early June 2026 (Osmani, Steinberger, Cherny). An academic working definition: triggered runs bounded by machine-checkable stop conditions, persistent state, independent verifiers, token budgets and defined human escalation.\[60\] A mining study of 36,710 repositories confirmed autonomous loops in 217 of 256 heuristic matches, but almost none committed the state files the discourse prescribes.\[60\]
- **Graph engineering.** Evidence is thin. Explicit DAG/graph orchestration appears in SemaClaw (DAG-driven agent-team dispatch), openJiuwen (one execution semantics reused across single agents, sub-agents and "Swarm Flow")\[61\]\[62\] and LangGraph. Use graphs where control flow is known. Keep the model loop for open-ended steps.
- **Context engineering best practices.** Anthropic recommends progressive disclosure, compaction, structured note-taking and sub-agent isolation.\[63\] JetBrains researchers (Lindenbauer et al., "The Complexity Trap," arXiv 2508.21433, NeurIPS '25 DL4C workshop) found on SWE-bench Verified that simple observation masking "halves cost relative to the raw agent while matching, and sometimes slightly exceeding, the solve rate of LLM summarization." Context files (AGENTS.md) showed mixed evidence. One study found lower token use. ETH Zurich's "Evaluating AGENTS.md" (Gloaguen et al., arXiv 2602.11988) found context files "do not generally improve task success rates, while increasing inference cost by over 20% on average." A "Harness Effect" study across six models reported −41% cost per task and −38% tokens from orchestration design alone.\[64\]
- **Worktrees and sub-agent orchestration.** Asynchronous SWE-agent research finds dependency-aware plans, isolated workspaces and test-based gates improve long-horizon outcomes.\[60\] A source study of eleven coding agents reports multi-agent patterns are used mostly for breadth-first exploration rather than parallel implementation.\[65\]

### 4. Shiny vs proven

| Technique | Verdict | Why |
|---|---|---|
| **OpenClaw always-on agents** | **Risky by default** | Community reports (secondary, not audited) cite workspace files (AGENTS.md, SOUL.md, USER.md) injected on every message, about 35,600 tokens or "93.5%" of budget (GitHub issue #9157).\[66\] Heartbeats replay fat histories while "idle."\[67\] One user cited 180M tokens (~$3,600) in a month.\[66\] Another blog reports Opus as the default model.\[68\] Fixable with routing and session hygiene, but the defaults encourage burn |
| **Loop engineering / Ralph loops** | **Proven only with verifiers** | Ralph (Huntley, July 2025) restarts fresh context per iteration, which is genuinely useful against context rot.\[32\] But skeptics call loops "a renamed cron job," and Orosz reports a "tokenmaxxing" suspicion that labs benefit from loop token use.\[60\] One Ralph guide caps runs at 20 iterations, and critics call verifier-less loops "an expensive way to burn tokens"\[33\]\[69\] |
| **Multi-agent swarms** | **High cost, task-dependent** | Anthropic's multi-agent research system beat single-agent Opus 4 by 90.2% on its internal eval. But Anthropic Engineering reports "agents typically use about 4× more tokens than chat interactions, and multi-agent systems use about 15× more tokens than chats," and Anthropic says tightly coupled tasks like coding fit poorly |
| **Fusion/panel models** | **Selective use only** | About 4–5× cost per call\[70\] |
| **Self-generated skills** | **Hype** | Per alphaXiv's summary of SkillsBench (arXiv 2602.12670), self-generated skills scored 8.1–11.5 pp *below* the no-skills baseline |
| **Routing + cascade** | **Proven** | HyDRA production A/B evidence\[43\] |
| **GEPA/DSPy** | **Proven for metric-backed pipelines** | Peer-reviewed gains. Overhead is not worth it for ad-hoc asks |
| **Context pruning, deferred tools, code-mode tools** | **Proven** | Direct token reductions, measurable in your traces |

### 5. Skill/plugin evaluation frameworks

- **SkillsBench (paired evaluation).** Each task runs with and without the skill. Across 18 model–harness configurations, curated skills raised pass rates from 33.9% to 50.5% (+16.6 pp). Focused bundles of 1–3 skills gained about +19.0 pp versus +10.1 pp for 4 or more. Smaller models with skills can match larger models without them.\[71\] Self-generated skills did worse than no skills: per alphaXiv's summary of the paper (arXiv 2602.12670), they scored 8.1–11.5 pp below the no-skills baseline, while curated skills gained 18.2–24.8 pp in the same configurations.
- **SWE-Skills-Bench** found many skills give limited benefit and some degrade performance when they conflict with project context.\[42\]
- **Per-skill and CI tooling.** ACES computes "Skill Lift" on the author's own tasks with decoy skills, runs in CI and adds trajectory metrics.\[72\] SkillAudit converts a SKILL.md into hidden-rubric tasks.\[73\] Shapley valuation (SkillSV) scores which *parts* of a skill earn their tokens.\[74\] OpenSkillEval runs rolling comparisons of community skills.\[75\] SkillReducer and SkillMOO trade effectiveness against token cost.\[42\] A survey also flags skill-security auditing, since malicious skills can exfiltrate data.\[76\]
- **Recommended leaderboard design:** maintain an internal task suite per task type (bug fix, refactor, docs, data extraction). Score every candidate skill/plugin by paired lift, tokens and dollars per solved task, latency, and safety findings. Rank by lift per dollar. Re-run on model changes. Use cheap judges (Jev-class or small models) for breadth and deterministic checks for gates.

### 6. O'Reilly *Harness Engineering* (Nicole Koenigstein)

The book is an early release, listed for December 2027 at about 350 pages, subtitled *Optimization, Coordination, and Adaptive Agentic Systems*.\[77\]\[78\] Only chapters 1–2 are released.\[77\] **No public source describes six "planes"** (identity & behavior, runtime, adaptation, verification, observability, governance & security). That framing appears to be a synthesis, not the author's published model. The themes do map to the provisional table of contents:

- **Identity & behavior:** Ch 5, "Agent Identity: The Durable Boundary"; Ch 3, "Skills, Instructions, and Runtime Scaffolding."\[78\]
- **Runtime:** Ch 2, "The Harness as the Stateful Agent System Substrate" (state movement, externalizing state); Ch 4, "Context-Scoped Skill Compilation" (a runtime context compiler); Ch 6, "The Action Surface: Tools, Sandboxes, and Capability Scoping"; Ch 7, "Coordination as State."\[77\]\[78\]
- **Observability:** Ch 8, "Observability, Traces, and Harness Telemetry"; Ch 9, optimization via tracing, pruning and retry discipline.\[77\]\[78\]
- **Adaptation:** Ch 10, "Learning the Harness: RL over Skills, Routes, and Signals"; Ch 11, "Skill Internalization and Latent Coordination."\[78\]
- **Verification:** no chapter title. Related O'Reilly live-event material covers deterministic checks plus judge-verifier patterns and judge pools.\[79\]
- **Governance & security:** Ch 12, "Governance, Trust Boundaries, and the Harness in Production" (permissions, identity boundaries, audit trails, human oversight).\[77\]\[78\]

A separate, unrelated open "Harness Books" series (agentway.dev) analyzes Claude Code and Codex control planes, query loops, permissions and recovery.\[80\]\[81\] It's useful companion reading for builders.

## Recommendations

1. **Architecture:** Start from an OpenCode-style core. Implement a dsh-style append-only event log as the source of truth, exported via OpenTelemetry. Make the model adapter, loop, sandbox and sub-agent provider swappable plugins.
2. **Token budget first:** set per-session and per-loop token/dollar caps. Load tools lazily. Mask old observations. Keep stable cached prefixes. Show a per-turn breakdown (system, tools, history, tool output, reasoning) in the UI.
3. **Route by capability:** adopt a HyDRA-style capability-profile router with a cascade gate (tests/linters). Default mechanical steps to cheap models. Escalate on failed gates. Measure cost per solved task, not per token.
4. **Verify independently:** require machine-checkable stop conditions for every autonomous run. Use a verifier from a different model family for critique. Use cheap judges for breadth.
5. **Graduated autonomy:** run report-only, then assisted with a verifier, then unattended, promoting per task type only when metrics justify it. Prefer check-ins at plan approval and pre-merge over constant prompts, which users rubber-stamp.
6. **Sandbox properly:** fence reads, writes, network and secrets at the runtime. Run unattended loops only in isolated containers or worktrees.
7. **Gate skills/plugins through paired evals** before they enter the registry. Cap active skills at about 1–3 per task.
8. **Use DSPy/GEPA** only on high-volume, metric-backed modules (intent rewriting, extraction, triage).

## Caveats

- Many sources are vendor blogs (GitHub, LangChain/TypeSafe, DeepInfra, OpenRouter) or practitioner posts. GitHub's harness parity and HydraFusion's Opus 5 results are self-reported and partly offline.\[23\]\[44\] OpenClaw cost figures are community anecdotes relayed by third-party sites.
- DeepSeek Harness is pre-1.0. Observations apply to v0.1.1-rc.2.\[1\]
- Several cited arXiv papers are recent preprints that have not been peer reviewed.
- "JEV as Judge-Execute-Verify," "Gemini Astra" and the "six planes" framing could not be verified as named methods or products.
- The Anthropic multi-agent figures (90.2%, about 15× chat tokens) come from Anthropic Engineering's "How we built our multi-agent research system" and are based on Anthropic's own internal eval.

## Sources

1. [DeepSeek Harness Review: Agent Loop & Plugin Architecture](https://deepinfra.com/blog/deepseek-harness-review)
2. [What DeepSeek’s Open-Source Agent Harness Gets Right](https://medium.com/@minhle_0210/what-deepseeks-open-source-agent-harness-gets-right-b85f57533802)
3. [OpenCode: Open-Source AI Harness for the Terminal](https://innfactory.ai/en/ai-harness/opencode/)
4. [Pi vs OpenCode: After 100 Hours, Which Open-Source Coding Agent Should You Use?](https://composio.dev/content/pi-vs-opencode)
5. [GitHub - kdcokenny/opencode-workspace: Bundled multi-agent orchestration harness for OpenCode. One install, complete control. · GitHub](https://github.com/kdcokenny/opencode-workspace)
6. [The Scaffold Effect in Coding Agents: Harness Choice as a Hidden Variable in Coding-Agent Evaluation](https://arxiv.org/pdf/2607.22585)
7. [What Is Hermes AI Agent? Inside Nous Research's Open-Source Agent Harness](https://www.width.ai/post/what-is-hermes-ai-agent)
8. [Hermes Agent Review 2026: Nous Research Setup + Best Models](https://www.heyuan110.com/posts/ai/2026-04-14-hermes-agent-guide/)
9. [Channel Fracture: Three Instances of Cross-Boundary Silent Delivery Reliability Failures in Multi-Agent Systems](https://arxiv.org/pdf/2606.04896)
10. [Hermes Agent: Nous Research's AI Agent Harness](https://innfactory.ai/en/ai-harness/hermes-agent/)
11. [How Hermes implements an open source agent harness architecture - Arize AI](https://arize.com/blog/how-hermes-implements-open-source-agent-harness-architecture/)
12. [What Is an Agent Harness? The Architecture Behind Claude Code, DeepSeek Harness, and Hermes Agent](https://www.freecodecamp.org/news/what-is-an-agent-harness/)
13. [Hermes Harness Architecture](https://x.com/aparnadhinak/article/2060406977357070522?lang=en)
14. [Claude Code Source Leak: Everything Found (2026)](https://claudefa.st/blog/guide/mechanics/claude-code-source-leak)
15. [Claude Code Source Leak: With Great Agency Comes Great Responsibility](https://www.straiker.ai/blog/claude-code-source-leak-with-great-agency-comes-great-responsibility)
16. [What Claude Code's Leaked Source Teaches About AI Agents](https://blog.kubesimplify.com/claude-code-leak-what-the-source-actually-teaches)
17. [Create custom subagents - Claude Code Docs](https://code.claude.com/docs/en/sub-agents)
18. [A Look Inside Claude's Leaked AI Coding Agent](https://www.varonis.com/blog/claude-code-leak)
19. [Claude Code Source Leak 2026: The Complete Guide to ...](https://decodethefuture.org/en/claude-code-source-leak-complete-guide/)
20. [Copilot SDK is now generally available - GitHub Changelog](https://github.blog/changelog/2026-06-02-copilot-sdk-is-now-generally-available/)
21. [GitHub Copilot: GitHub's Agent Harness Explained](https://innfactory.ai/en/ai-harness/github-copilot/)
22. [GitHub Copilot Matches Claude Code While Burning Fewer Tokens](https://alphasignal.ai/news/github-copilot-matches-claude-code-while-burning-fewer-tokens)
23. [GitHub Copilot Agentic Harness: Token Efficiency Guide for…](https://www.nxcode.io/resources/news/github-copilot-agentic-harness-token-efficiency-2026)
24. [Evaluating performance and efficiency of the GitHub Copilot agentic harness across models and tasks - The GitHub Blog](https://github.blog/ai-and-ml/github-copilot/evaluating-performance-and-efficiency-of-the-github-copilot-agentic-harness-across-models-and-tasks/)
25. [GitHub Copilot Agentic Harness Benchmark: What Developers…](https://www.nxcode.io/resources/news/github-copilot-agentic-harness-benchmark-2026)
26. [Act As a Real Researcher: A Suite of Benchmarks Evaluating Frontier LLMs and Agentic Harnesses in Research Lifecycle](https://arxiv.org/pdf/2606.07462)
27. [Inside Claude Code's System Prompt](https://www.claudecodecamp.com/p/inside-claude-code-s-system-prompt)
28. [Claude Code's system tools are SO BLOATED](https://daily.dev/posts/claude-code-s-system-tools-are-so-bloated-gvzyp3uz1)
29. [Token efficiency: system prompt overhead consumes too much of the context window · Issue #46526 · anthropics/claude-code](https://github.com/anthropics/claude-code/issues/46526)
30. [LOCA-bench: Benchmarking Language Agents Under Controllable and Extreme Context Growth](https://arxiv.org/pdf/2602.07962)
31. [Token bills to push most enterprise AI workloads onto open-weight models](https://www.computerweekly.com/news/366651239/Token-bills-to-push-most-enterprise-AI-workloads-onto-open-weight-models)
32. [The Ralph Loop: How Recursive AI Agents Actually Work](https://thomas-wiegold.com/blog/ralph-loop-how-recursive-ai-agents-work/)
33. [Ralph Wiggum is an expensive way to burn tokens. He needs a Marge](https://medium.com/@mpuig/ralph-wiggum-is-an-expensive-way-to-burn-tokens-he-needs-a-marge-811d81378ae4)
34. [Long-running Agents](https://addyosmani.com/blog/long-running-agents/)
35. [Effective harnesses for long-running agents](https://daily.dev/posts/effective-harnesses-for-long-running-agents-7clzunmmu)
36. [OckBench: Measuring the Efficiency of LLM Reasoning](https://arxiv.org/pdf/2511.05722)
37. [Harbor Adapters and Harbor-Index: Infrastructure and a Curated Meta-Dataset for Large-Scale Agentic Evaluation](https://arxiv.org/pdf/2609.04298)
38. [The Ralph Wiggum Agent Loop Is Really About Engineering Discipline](https://writing.alteredcraft.com/p/the-ralph-wiggum-agent-loop-is-really)
39. [DeepSeek Harness Explained: What It Is, When to Use It, and When Not To - DEV Community](https://dev.to/aditi_gupta_8d81622a592aa/deepseek-harness-explained-what-it-is-when-to-use-it-and-when-not-to-3la3)
40. [Building Session-Level Observability for DeepSeek Harness with a Community Plugin - DEV Community](https://dev.to/claven07/building-session-level-observability-for-deepseek-harness-with-a-community-plugin-19n6)
41. [Claude Code Token Optimization: Full System Guide (2026)](https://buildtolaunch.substack.com/p/claude-code-token-optimization)
42. [From Anatomy to Smells: An Empirical Study of SKILL.md in Agent Skills](https://arxiv.org/pdf/2607.01456)
43. [HyDRA: Hybrid Dynamic Routing Architecture for Heterogeneous LLM Pools](https://arxiv.org/pdf/2605.17106)
44. [Project HydraFusion: Frontier quality via multi-model orchestration - The GitHub Blog](https://github.blog/ai-and-ml/github-copilot/project-hydrafusion-frontier-quality-via-multi-model-orchestration/)
45. [HydraFusion and Fugu: AI Model Orchestration Is the Product](https://www.llmrumors.com/news/hydrafusion-sakana-fugu-model-routing-orchestration)
46. [Auto Router - API Pricing & Providers](https://openrouter.ai/openrouter/auto)
47. [Auto Router - Intelligent Model Selection](https://openrouter.ai/docs/guides/routing/routers/auto-router)
48. [OpenRouter Fusion: Features, Pricing & Alternatives](https://www.therundown.ai/tools/fusion)
49. [OpenRouter Fusion API Review: Cost, Latency, and Best Uses](https://aireiter.com/blog/openrouter-fusion-api-review)
50. [GEPA Prompt Optimization: Beat RL With 35x Fewer Rollouts](https://www.morphllm.com/gepa-prompt-optimization)
51. [DSPy Optimizers Explained in 2026: BootstrapFewShot, MIPROv2, COPRO, and GEPA](https://futureagi.com/blog/dspy-optimizers-explained/)
52. [GitHub - gepa-ai/gepa: Optimize prompts, code, and more with AI-powered Reflective Optimization · GitHub](https://github.com/gepa-ai/gepa)
53. [Multi-Agent Teams Hold Experts Back](https://arxiv.org/pdf/2602.01011)
54. [MAS-PromptBench: When Does Prompt Optimization Improve Multi-Agent LLM Systems?](https://arxiv.org/pdf/2606.23664)
55. [Jev is now available in LangSmith Evals](https://www.langchain.com/blog/jev-is-now-available-in-langsmith-evals)
56. [Jev-as-a-Judge for Agent Evals - @LangChain](https://x.com/LangChain/status/2101454284927959080)
57. [JEV as a Judge for Agent Trace Security:An Empirical Comparison with Generative LLM Judges](https://arxiv.org/html/2609.34862v1)
58. [SetupX: Can LLM Agents Learn from Past Failures in Functionality-Correct Code Repository Setup?](https://arxiv.org/pdf/2605.26186)
59. [What Is Loop Engineering?](https://www.ibm.com/think/topics/loop-engineering)
60. [Loop Engineering: Building Blocks, Adoption, and Impact](https://arxiv.org/pdf/2608.21884)
61. [openJiuwen: Beyond Static Harnesses for Long-Horizon Coding Agents](https://arxiv.org/pdf/2608.27969)
62. [SemaClaw: A Step Towards General-Purpose Personal AI Agents through Harness Engineering](https://arxiv.org/pdf/2604.11548)
63. [Effective context engineering for AI agents \\ Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
64. [The Harness Effect: How Orchestration Design Sets the Token Economics of Enterprise Agentic AI](https://arxiv.org/pdf/2607.06906)
65. [Harness Engineering: Anatomy, Architecture, and Evolution of Coding Agents -- A Source-Code Study of Eleven Systems](https://arxiv.org/pdf/2609.00006)
66. [Reduce Your OpenClaw AI Costs by 97% — Token Optimization Guide](https://openclawsearch.com/blog/token-optimization)
67. [My OpenClaw agent looked idle overnight and still burned through tokens - DEV Community](https://dev.to/lars_winstand/my-openclaw-agent-looked-idle-overnight-and-still-burned-through-tokens-4ikj)
68. [Why Does OpenClaw Burn Through Tokens So Fast? (And How to Cut Costs by 80%)](https://docs.bswen.com/blog/2026-03-27-openclaw-token-usage-costs/)
69. [2026 - The year of the Ralph Loop Agent - DEV Community](https://dev.to/alexandergekov/2026-the-year-of-the-ralph-loop-agent-1gkj)
70. [OpenRouter Fusion Pricing: Panel Size and Token Cost](https://aireiter.com/blog/openrouter-fusion-pricing-panel-token-cost)
71. [SkillsBench: Benchmarking How Well Agent Skills Work Across Diverse Tasks](https://www.alphaxiv.org/abs/2602.12670)
72. [Evaluating Skills, Not Just Agents: Agentic Continuous Evaluation of Skills](https://arxiv.org/pdf/2608.20614)
73. [SkillAudit: From Fixed-Suite Benchmarking to Skill-Centered Assessment](https://arxiv.org/pdf/2606.22613)
74. [What Is a Skill Worth? Structure-Aware Shapley Valuation of Agent Skills](https://arxiv.org/pdf/2608.04562)
75. [OpenSkillEval: Automatically Auditing the Open Skill Ecosystem for LLM Agents](https://arxiv.org/pdf/2605.23657)
76. [Agent Skill Evaluation and Evolution: Frameworks and Benchmarks](https://arxiv.org/pdf/2606.11435)
77. [Harness Engineering \[Book\]](https://www.oreilly.com/library/view/harness-engineering/0642572422783/)
78. [GitHub - Nicolepcx/harness\_engineering: This is the corresponding code for the O'Reilly book: Harness Engineering · GitHub](https://github.com/Nicolepcx/harness_engineering)
79. [Harness Engineering for Long-Running Agent Skills](https://www.oreilly.com/live-events/harness-engineering-for-long-running-agent-skills/0642572464714/0642572464707/)
80. [GitHub - wquguru/harness-books: 📚 Two books on harness engineering — the design philosophies behind Claude Code & Codex: constraints, query loops, context governance, multi-agent verification. harness-books.agentway.dev](https://github.com/wquguru/harness-books)
81. [Harness Books](https://harness-books.agentway.dev/en/)
