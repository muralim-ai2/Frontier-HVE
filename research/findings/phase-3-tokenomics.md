# Phase 3 findings: tokenomics (status 2026-10-06)

Evidence comes from the Copilot OTel export (`research/runs/copilot-otel.jsonl`) and the hook-built session JSONL, never from model write-ups. No benchmark run exists yet (Phase 2 deferred, D-012), so every number below comes from smoke or invalid sessions and is indicative only.

## 1. Tool-call token explosion: what we have now

### Observed (per chat call, from OTel)

| Session | Mode / model | Calls | Prompt tokens per call | Session cache share | Completion | Cost (AI units) |
|---|---|---|---|---|---|---|
| 5f9d682c (smoke) | single / claude-opus-5.5 | 3 | 24,987 → 26,826 → 26,972 | 65.8% | 1,806 | 18.1 |
| a187413b (invalid) | single / gpt-5.6-sol, main | 5 | 25,162 → 25,335 → 25,791 → 26,133 → 27,975 | 58.5% | 772 | 31.7 |
| a187413b (invalid) | its execution_subagent / gpt-5.6-luna | 4 | 1,928 → 2,020 → 2,056 → 2,785 | 66.5% | 1,047 | 0.2 |
| 91dd46e1 (invalid) | minimal / gpt-6-astra | 9 | 18,255 … 18,460 (8 tool_search calls), then 28,043 | 62.9% | 11,281 | 148.6 |

Cost = sum of `copilot_chat.copilot_usage_nano_aiu` / 10^9.

### What this shows
- **A fixed floor dominates each call.** ~18k tokens (minimal) and ~25k (single) are sent before any task content: Copilot's built-in agent prompt, tool schemas, repo instructions (`copilot-instructions.md`, `AGENTS.md`), environment context. Only ~600 tokens are our agent body.
- **The floor is cached after the first call.** Calls 2..n are ~99.9% cache reads; the session-level share is ~60–66% because the first call is uncached. (Correction: an earlier chat answer called the cache rate ~99.9% overall; that holds only for calls after the first.)
- **Tool output growth was small in these sessions** (+150 to +1.8k tokens per tool call). They were smoke tests. A full color-palette build (npm install/build logs, many file reads) has not been measured.
- **`context_tokens` (our cumulative sum of prompt tokens) grows linearly with call count** because each call resends the full floor. The number of calls, not the size of one call, drives total input.
- **Sub-agents keep tool output out of the parent.** In a187413b the terminal work ran in `execution_subagent` on ~2k-token prompts at 0.2 AI units, while the parent grew only 2.8k tokens over 5 calls. This is the mechanism `hooks/compaction.py` builds on.
- **Hidden tool loops cost real tokens.** minimal (no tools) called Copilot's built-in `tool_search` 8 times across 2 requests, ~146k prompt tokens, before producing any code. Now visible: minimal has PreToolUse/PostToolUse hooks (D-009).
- **Output can dominate cost.** minimal's code-producing call wrote 10.5k completion tokens; minimal's session cost was ~8x the single smoke session's.

### Mechanisms in place
| Mechanism | Where | Status |
|---|---|---|
| Explicit tool lists (fewer schemas, no `executionSubagent`) | single, creator agent files | built |
| Deferred tool schemas via Copilot's `tool_search` | native | observed in 91dd46e1 |
| Sub-agent return cap (< 2,000 tokens, summarize tool output) | `hooks/compaction.py`, SubagentStart | built, not seen live |
| Graph queries instead of file reads | Graphify MCP for creator (section 3) | built, not seen live |
| Per-call cost field `cost_nano_aiu` | `hooks/metrics.py` | built |
| Sub-agent rows and tool-to-conversation join | `hooks/metrics.py` (D-006, D-011) | built |

### Not possible with VS Code Local hooks
- Rewriting a tool result already in history (observation masking proper): `PostToolUse` can only add context or block.
- Editing or stripping the system prompt or tool schemas: no hook can.

### Next measurement (when Phase 2 resumes)
Per mode: fixed floor (first-call prompt), growth per tool call, number of calls, cache share, cost per task, and sub-agent share of tokens. Compare creator with and without each mechanism.

## 2. Headroom: evaluated, not adopted (D-015)

- **Package:** the real project is `headroom-ai` (headroomlabs-ai/headroom, Apache-2.0). The plan's `headroom` is a different PyPI package.
- **How it works with VS Code Copilot:** `headroom wrap vscode` writes `github.copilot.advanced.debug.overrideCapiUrl` and `overrideProxyUrl` into VS Code User settings. All Copilot chat and completion traffic, in every chat and mode, then goes through a local proxy at 127.0.0.1:8787. Copilot fails closed while the proxy is stopped, until `headroom unwrap vscode`.
- **Auth:** it needs its own `headroom copilot-auth login`, which stores a reusable Copilot OAuth refresh token in a plaintext file.
- **Telemetry, three separate switches:**
  - the beacon (counters and model names to Headroom Labs, on by default; `HEADROOM_BEACON=off`);
  - local stats (`HEADROOM_TELEMETRY`, off);
  - its own OTel metrics (`HEADROOM_OTEL_*`, opt-in).
  - It does not touch Copilot's OTel export; our token counts would reflect the compressed prompt. `HEADROOM_OFFLINE=1` blocks all egress.
- **What it would compress here:** tool output and history, not the cached ~25k floor, which it keeps stable for prompt caching. Expected effect is near zero for minimal and limited to the growing part for single/creator. Unmeasured.
- **Risks:**
  - lossy compression of code and JSON the agent edits (reversible retrieval inside VS Code Copilot is unverified);
  - output shaping would override our reasoning-effort pins;
  - a global proxy failure breaks every chat;
  - plaintext credential and on-disk originals (`HEADROOM_CCR_BACKEND=memory` avoids the latter).
- **Decision:** not implemented. The user does not want regular chat affected, and the VS Code integration cannot be scoped to one agent.
- **Revisit if:** Headroom can be scoped per agent, or the MCP-only mode (`headroom_compress`/`headroom_retrieve` tools in creator, no proxy) is worth testing.

## 3. Graphify: adopted for creator (D-016)

- **Package:** `graphifyy` 0.9.71 (Graphify-Labs/graphify, Apache-2.0), installed as an isolated uv tool from the Microsoft PyPI proxy. Upstream is at 0.9.77; the proxy lags. The plan's `graphify-cli` is unaffiliated.
- **Local only:** `graphify extract <project> --code-only` parses with tree-sitter (no LLM, no network). Graphify has no telemetry; its query log is disabled with `GRAPHIFY_QUERY_LOG_DISABLE=1`.
- **Wiring:**
  - `hooks/graph_refresh.py` (creator SessionStart + PostToolUse) rebuilds the graph of `tests/outputs/harness/current/` when its files change. Change detection uses a fingerprint of paths, mtimes and sizes, excluding `node_modules`, `.next`.
  - It publishes the graph atomically to `tests/outputs/harness/graph/graph.json`, and an empty graph while there is no code, so the MCP server always starts.
  - Nothing is written into the agent's project.
  - `.vscode/mcp.json` runs `graphify-mcp` on that file; the server hot-reloads it.
  - creator gets four tools: `query_graph`, `get_node`, `get_neighbors`, `shortest_path`. minimal and single list tools explicitly, so they do not get them.
- **Expected value on the color-palette benchmark is low:** the project starts empty, so early calls query an empty graph while the four tool schemas cost tokens on every call. Value should rise in later turns of a long build and in Phase 5 sessions that resume existing code. Measure creator with and without Graphify.
- **Contamination guard:** only the current run's folder is indexed; finished runs are never in the graph.
