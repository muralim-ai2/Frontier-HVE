<!-- hve-document: {"kind": "technicalDesign", "sha256": "153f72ea2af41bad985e5e58a3e7d3b3cc8cd4d3f5a29725fa56dce348f49b73", "slug": "solution-map", "source": "builtin:technical-design@1"} -->
<!-- hve-template: technicalDesign@1 -->
# Technical Design Specification

<!-- hve-section: context -->
## Context and Requirements

**System:** Frontier HVE solution map (working name), a layered, meaning-carrying graph of an application that agents read instead of re-exploring the repository. **Owner:** muralim-ai2. **Status:** draft for review, 2026-10-22; nothing built. **Linked PRD:** none; the requirements below come from the user's request of 2026-10-22 and the Graphify review the same day (decision D-016, findings `phase-3-tokenomics.md`).

**Problem.** A new chat on an existing AI-built app spends most of its first turns re-reading the repository to learn how it fits together, and does so again in every session. Graphify, the current code graph, does not solve this: it is wired only to the research `creator` agent, its graph holds the colour-palette benchmark (195 nodes), it extracts syntax only (files, functions, calls, imports), answers by label match ("No matching nodes" for a plain-language question), has no layers, summaries or owners, and was never measured with and without (1 query in the baseline run).

**Goal.** For medium and large apps, give every session a compact map from paradigm to module to symbol, with a one-line purpose per node, typed relationships and the expertise each part needs, so that the agent (a) knows where to start a feature and what it touches, (b) can tell the user which experts to involve, and (c) spends fewer tokens. Every claim of saving is measured and shown in the provenance report.

**Token hypothesis (to be measured, not assumed).** Session-start exploration of a mid-size app (15-40 files read, roughly 25-60k prompt tokens, repeated per session) would drop to roughly 10-15k (map overview 2-3k, impact result 1-2k, 3-6 targeted files). These figures are estimates from typical file sizes; this design exists partly to measure them.

| Id | Requirement |
|---|---|
| FR-1 | Classify each ask's app as small, medium or large from the workspace and the request; build and use the map only for medium and large, recorded as a flag in the contract and shown in `plan.md`. |
| FR-2 | Build a layered map: system, views (requirements, solution design, stack design, frontend, API/backend, middleware, data, identity, integration/APIM, infra/DevOps, observability, ML), modules, symbols. |
| FR-3 | Each node carries a one-to-two-line purpose and usage note, its interface, source paths with line ranges, the expertise role that owns it, and the commit it was taken from. |
| FR-4 | Edges carry the nature of the relationship: calls, imports, injects, routes-through, authenticates-with, reads, writes, exposes, consumes, deploys-to, configured-by, implements, decided-in, tested-by, owned-by. |
| FR-5 | Answer `overview`, `impact "<feature>"` (touchpoints, start point, dependency chain, roles to involve), `path <a> <b>`, `node <id>` and `status` (staleness) within a token budget. |
| FR-6 | Refresh on demand, on a release tag, when an ask closes, and when the session's context passes 25% of the model's context window (the compaction checkpoint). |
| FR-7 | At every checkpoint record the context size, the map refresh, and the tokens the map answers replaced; the provenance report shows them per session and per ask. |
| FR-8 | Route impact results to expertise packs (a data and APIM impact offers the matching packs) and name the roles to involve. |
| NFR-1 | Code facts are extracted without an LLM and without network calls; only node summaries use the session's own model, and only for nodes whose content hash changed. |
| NFR-2 | A stale map is never presented as current: every answer states the map's commit and how many mapped files changed since. |
| NFR-3 | `overview` stays under 3,000 tokens and `impact` under 2,000 tokens by default. |
| NFR-4 | No new runtime dependency is required; Graphify is used for the symbol layer when it is installed. |
| NFR-5 | Python modules stay under 500 lines, fail fast, and follow the repository code style. |
| AC-1 | On a medium sample app, `impact` lists the touched views, modules and roles for a new authenticated API endpoint, and each item cites a source path. |
| AC-2 | A session that passes 25% of its window writes a checkpoint event and the provenance report shows it with tokens before and after. |
| AC-3 | A with/without-map benchmark on the same model and task reports prompt tokens to the first correct change, files read and the check result. |
| AC-4 | A small app (below the thresholds) records `map: off` with the reason and builds nothing. |

<!-- hve-section: constraints -->
## Constraints and Assumptions

**Confirmed:**
- Agents run in VS Code Copilot Chat (Local harness, agent-scoped hooks) and are exported to other harnesses; hooks cannot rewrite chat history (D-013) and cannot trigger compaction. They can add context on `UserPromptSubmit`, `PreToolUse`, `PostToolUse` and `SubagentStart`, and `PreCompact` is notification only, with `trigger: "auto"` when the conversation exceeds the prompt budget (VS Code Local hooks reference; GitHub Copilot hooks reference).
- Hook payloads do not carry the context size. Measured prompt tokens exist only in metrics rows (research arms) or the Copilot OTel export when research telemetry is on (`ask_report.measures`).
- `.hve/` holds workspace state and is usually git-ignored; asks already record requests, features, stages, PRDs and designs (`contract.json`, `feature_list.json`, template registry).
- Graphify (`graphifyy` 0.9.71) extracts a code-only graph locally with tree-sitter (D-016) but must be installed separately with `uv`; extension users usually do not have it.
- The skill loader, compaction hook and provenance report already exist and are the places to add map context and evidence.

**Assumptions (unverified):**
- A-1: The model's context window can be read from a per-model table kept in `skills/categories.json` (`context_load`), defaulting to its first reference window (128,000) when the model is unknown; 25% is therefore 32,000 tokens by default.
- A-2: A running estimate of the session's context (prompts, tool inputs and results seen by hooks, plus the measured always-on load) is within about 20% of the real prompt size; the estimate is calibrated against OTel when telemetry is on.
- A-3: The session's model writes adequate one-line summaries when given the node's source lines; summaries cite their lines so a reviewer can check them.
- A-4: Thresholds for medium (50 source files or 5,000 lines) and large (300 files or 50,000 lines) are a reasonable starting point and are tuned from measurements.

<!-- hve-section: architecture -->
## Architecture and Components

```mermaid
flowchart TD
    REQ[Request + workspace] --> SIZE[size.py: classify small, medium, large]
    SIZE -->|small| OFF[contract map: off, reason]
    SIZE -->|medium or large| BUILD
    subgraph BUILD[map build]
      EX[extract.py: symbols and code edges<br/>Graphify graph.json when installed, else built-in extractors]
      FW[frameworks.py: routes, DI registrations, middleware, ORM models, IaC, OpenAPI]
      ASK[asks: requirements, PRD, TDS, features -> implements and decided-in edges]
      VIEW[views.py: assign nodes to views and roles]
      SUM[summaries: changed nodes only, written by a sub-agent, cite lines]
    end
    EX --> VIEW
    FW --> VIEW
    ASK --> VIEW
    VIEW --> SUM --> MAP[.hve/map/map.json + overview.md]
    MAP --> Q[solution_map.py overview, impact, path, node, status]
    Q --> AG[E2E, BYOW, sub-agent briefs]
    METER[context_meter hook: running context estimate] -->|"over 25% of window"| CP[checkpoint: refresh changed nodes, inject overview, log event]
    CP --> MAP
    CP --> EV[.hve/runs/session.map.jsonl]
    Q --> EV
    EV --> PROV[provenance.md and provenance.json: Solution map section]
    REL[release tag, ask close, on demand] --> BUILD
```

| Component | Responsibility | Depends on |
|---|---|---|
| `tools/map/size.py` | Classify the app: counts source files and lines by language (skipping dependencies and build output), detects views present (frontend, backend, data, infra, identity, integration), reads request signals ("enterprise", "microservice", number of components named); returns `small`, `medium` or `large` with the reasons | workspace, request |
| `tools/map/extract.py` | Symbol layer: functions, classes, endpoints, tables, resources and their `calls`, `imports`, `contains` edges; reads Graphify's `graph.json` when present, otherwise Python `ast`, and import and export scanning for JS/TS, C# and Java | Graphify (optional) |
| `tools/map/frameworks.py` | Meaning-bearing edges from conventions: routes and controllers (`exposes`), dependency-injection registrations (`injects`), middleware chains (`routes-through`), auth decorators and policies (`authenticates-with`), ORM models and migrations (`reads`, `writes`), IaC and pipeline files (`deploys-to`, `configured-by`), API specs and APIM policies (`exposes`, `routes-through`) | extract output |
| `tools/map/views.py` | Assign every node to a view and a module; map views to expertise roles through `skills/map_roles.json` (extendable by expertise packs) | extract, frameworks |
| `tools/map/solution_map.py` | CLI and store: `build [--changed]`, `summaries prepare\|record`, `overview`, `impact`, `path`, `node`, `status`, `diff`, `snapshot`; keeps the map, the overview and snapshots, and logs every answer's tokens | all of the above |
| `hooks/context_meter.py` | Keep a running estimate of the session's context; at 25% of the window run the checkpoint once per crossing band (25%, 50%, 75%); log `PreCompact` events | session events |
| `tools/loop` additions | `size` and `map` flag in the contract, an `impact` step in the E2E and BYOW prompts, map lines in briefs, a Solution map section in the provenance report | solution_map |

Principal flows:
1. **Contract:** `lifecycle.py contract` calls `size.classify`; medium or large sets `map.enabled` and, when the workspace has code, builds or refreshes the map before planning. A new project with a medium or large request builds its first map when the first milestone with code is done.
2. **Feature request in an existing app:** the agent reads `overview`, runs `impact "<feature>"`, shows touchpoints, start point and roles in the plan, and offers the packs and personas the impact names. It reads only the files the impact cites.
3. **Checkpoint:** when the estimate passes 25% of the window, `context_meter` refreshes changed nodes, adds the overview and the current task's impact to the context with a note that earlier exploration output can be dropped, and logs the event.
4. **Release:** a release tag (or `solution_map.py snapshot <name>`) writes an immutable snapshot; `diff` shows architecture drift between snapshots.

<!-- hve-section: data -->
## Data Design

**Map file** (`.hve/map/map.json`, one per workspace, JSON only):

```json
{
  "version": 1,
  "commit": "705f275",
  "built": "2026-10-22T18:00:00+00:00",
  "size": {"class": "medium", "files": 142, "lines": 18350, "views": ["frontend", "api", "data", "identity", "infra"], "why": ["142 source files", "5 views"]},
  "nodes": [
    {"id": "api:orders.create_order", "level": "symbol", "view": "api", "module": "api:orders", "kind": "endpoint",
     "name": "POST /orders", "purpose": "Creates an order for the signed-in customer and reserves stock.",
     "interface": "body OrderIn -> 201 OrderOut; 401, 409", "source": "src/api/orders.py:40-88", "role": "backend-engineer",
     "hash": "9f2c...", "summary_by": "session model, cites src/api/orders.py:40-88"}
  ],
  "edges": [
    {"from": "api:orders.create_order", "to": "middleware:auth.require_user", "type": "routes-through", "evidence": "src/api/orders.py:39"},
    {"from": "api:orders.create_order", "to": "data:orders_table", "type": "writes", "evidence": "src/repo/orders.py:22"},
    {"from": "req:FR-3", "to": "api:orders.create_order", "type": "implements", "evidence": "docs/product/PRD-shop.md#FR-3"}
  ],
  "files": {"src/api/orders.py": "sha256..."}
}
```

- **Levels:** `system`, `view`, `module`, `symbol`. Ids are `<view>:<module>[.<symbol>]`, stable across builds for unchanged code.
- **Every edge has evidence** (a source line or document anchor); edges without evidence are not written.
- **Roles** (`skills/map_roles.json`): view to roles, for example `data` to `db-engineer`, `infra` to `devops`, `identity` to `security`, `integration` to `platform-apim`, `ml` to `data-scientist`, `requirements` to `product-manager`. Expertise packs may add roles and views for their domain.
- **Snapshots:** `.hve/map/snapshots/<release-or-utc-stamp>.json`, never edited. A team that wants the map in review commits `docs/architecture/solution-map.json` from a snapshot (open question Q-3).
- **Events** (`.hve/runs/<session>.map.jsonl`), one line per event: `{"ts", "event": "checkpoint"|"query"|"build"|"precompact", "context_estimate", "window", "share", "map_commit", "changed_files", "answer_tokens", "cited_file_tokens", "measured_prompt"}`.
- **Retention:** the map and snapshots stay with the workspace; events follow the `.hve/runs` retention. The map holds code structure and summaries, no secrets: files matched by `.gitignore` and secret patterns from `tools/skills/scan.py` are skipped.

<!-- hve-section: interfaces -->
## Interfaces and Contracts

**CLI** (`python <tools>/map/solution_map.py`, JSON or Markdown out, non-zero exit on error):

| Command | Returns |
|---|---|
| `size <request-file>` | `{class, files, lines, views, why}` |
| `build [--changed]` | Nodes and edges added, changed, removed; summaries pending |
| `summaries prepare` / `summaries record <file>` | A batch of changed nodes with their source lines for a sub-agent; records its summaries after checking each cites lines inside the node |
| `overview [--budget N]` | Views, modules with one-line purposes, key flows and roles, the map commit and staleness, within the budget (default 3,000) |
| `impact "<feature>" [--budget N]` | Touched views and modules, start point, dependency chain with edge types, roles to involve, packs to offer, files to read; within the budget (default 2,000) |
| `path <a> <b>`, `node <id>` | The typed path between two nodes; one node with its edges |
| `status` | Map commit, files changed since, nodes affected, whether a refresh is due |
| `snapshot <name>`, `diff <a> <b>` | Immutable snapshot; added, removed and changed nodes and edges between two snapshots |

**Contract additions** (`contract.json`): `map: {enabled, size, why, commit, path}`; the plan's generated block shows the size class, the map's age and staleness.

**Hook contract** (`context_meter.py`): on `UserPromptSubmit`, `PostToolUse` and `SubagentStart` it adds the text it saw to the session estimate (`.hve/runs/<session>.context.json`); when the estimate crosses a band (25%, then 50% and 75%) it runs `build --changed`, returns `additionalContext` with the overview and the current impact, and writes a `checkpoint` event. On `PreCompact` it writes a `precompact` event with the estimate. It never blocks a tool call.

**Agent contract:** E2E and BYOW read `overview` after `where` when `map.enabled`; for a feature on existing code they run `impact` before choosing the lifecycle and show touchpoints and roles in the plan; briefs carry the impact's files for the stage. Errors: a missing map when enabled builds it; a stale map is refreshed with `--changed` before use; extractor failures stop the build with the file and reason.

**Versioning:** `map.json` has `version: 1`; a breaking change rebuilds the map rather than migrating it.

<!-- hve-section: security -->
## Security and Access

- **No new network access:** extraction is local; summaries are written by the session's own model inside the chat, so no code leaves through a new channel.
- **Sensitive content:** the build skips `.gitignore`d files, `.env*`, key and certificate files, and lines matching the secret rules of `tools/skills/scan.py`; summaries describe behaviour and must not quote secrets.
- **Trust boundary:** the map is input to the model, not an authority: answers name their evidence lines, and the agent reads the cited file before editing it.
- **Access:** the map lives in the workspace with the same access as the code; committing a snapshot is a team decision (Q-3).
- **Prompt injection:** summaries are generated from code that may contain hostile comments; the `summaries record` step rejects summaries that contain instructions to the agent (the scan's prompt-injection rule) and keeps them as plain descriptive text.

<!-- hve-section: operations -->
## Reliability and Observability

**Failure modes:**

| Failure | Effect | Handling |
|---|---|---|
| Map stale (code changed since its commit) | Agent trusts old structure | Every answer states commit and changed files; checkpoint and ask close refresh with `--changed` |
| Context estimate wrong | Checkpoint too early or too late | Calibrated against OTel when telemetry is on; the event records estimate and measured value so the error is visible |
| Wrong summary | Agent starts in the wrong place | Summaries cite lines; the agent reads cited files before editing; reviewers can spot-check in `overview.md` |
| Extractor misses a framework convention | Missing edge | `status` lists modules with no inbound or outbound edges; packs can add conventions for their stack |
| Build too slow on large repos | Delay at contract or checkpoint | `--changed` hashes files and rebuilds only changed modules; full builds run on release or on demand |

**Performance budgets:** a changed-only refresh under 10 s for 50 changed files; `overview` under 3,000 tokens; `impact` under 2,000 tokens.

**Evidence of token saving (the point of FR-7):** the provenance report gets a **Solution map** section per session and ask:

| Measure | Source |
|---|---|
| Size class and why; map enabled or off | contract |
| Checkpoints: time, context estimate, share of window, files refreshed | `map.jsonl` checkpoint events |
| Compactions the harness ran (`PreCompact`) and the estimate at that moment | `map.jsonl` precompact events |
| Map answers: count and tokens | `map.jsonl` query events |
| Tokens of the files those answers cited (the reads the answer stands in for) | sum of cited files' tokens, an estimate labelled as such |
| Files actually read in the session, before and after the first map answer | skill loader and tool log |
| Measured prompt tokens: first, peak, at each checkpoint | metrics rows or OTel (research telemetry) |

The saving shown per session is an **estimate** (cited file tokens minus answer tokens). The **measurement** is the A/B benchmark (AC-3): the same model and task ("add an authenticated endpoint to an existing medium app") with the map on and off, comparing prompt tokens to the first correct change, files read and the check result, run through `tools/observe/bench.py` and reported in `research/comparisons/`.

<!-- hve-section: delivery -->
## Deployment and Rollback

**Rollout in milestones** (each ends with its tests and the user's review):
1. M1 Size flag: `size.py`, contract `map` field, plan line; no map yet. Shows how often asks are medium or large.
2. M2 Map build: extractors, framework conventions for the stacks we ship (Python FastAPI or Flask, Node Express, Next.js, .NET minimal APIs, Bicep and GitHub Actions), views and roles, `overview`, `node`, `status`.
3. M3 Impact and agent use: `impact`, `path`, E2E and BYOW steps, briefs carrying cited files, pack routing from impact.
4. M4 Checkpoint and evidence: `context_meter` hook, events, provenance section.
5. M5 Measurement: the A/B benchmark on a medium sample app; the result decides whether the map becomes default for medium apps.
6. M6 Releases: snapshot on tag, `diff`, optional committed snapshot.

**Compatibility:** existing asks without a `map` field behave as `map: off`. The map is additive: no current flow depends on it.

**Rollback:** set `map.enabled` off in the contract (or remove the `context_meter` hook from an agent); the agents fall back to their current exploration. Deleting `.hve/map/` removes all state.

<!-- hve-section: alternatives -->
## Alternatives, Risks and Decisions

| Option | For | Against | Decision |
|---|---|---|---|
| Keep Graphify as is | Installed, local, no LLM | Syntax only, label search, creator-only, no evidence of saving | Rejected as the solution; kept as an optional symbol source |
| Graphify full mode (LLM extraction of docs and code) | Richer semantics | Sends content to an external model configuration we do not control; no views, roles or evidence edges | Rejected for now |
| Language server only (usages, symbols) | Accurate, no install | Per query, no persistence, no meaning, no views | Used by agents as today; not a map |
| Hand-written architecture docs (C4, ADRs) | High quality | Go stale; not machine-queryable | Linked as `decided-in` evidence when present |
| **Layered solution map (this design)** | Views, purposes, typed edges, roles, refresh points, measured saving | Build effort; summaries can be wrong; must stay fresh | **Chosen, subject to the M5 measurement** |

**Risks:** a stale or wrong map misleads more than no map (mitigated by commit stamps, cited lines and refresh points); small apps gain nothing (mitigated by the size flag); the context estimate may be off (calibrated and recorded); the 25% band may refresh too often on large sessions (bands at 25, 50 and 75% only, at most once each).

**Decisions made (user, 2026-10-22):** build the map only for medium and larger apps, decided by a flag from the request and workspace; refresh at the compaction checkpoint when the context passes 25% of the window; record each checkpoint and the saving in the provenance report.

**Open questions:**
- Q-1 (user): the exact size thresholds; start with A-4 and tune after M1 data.
- Q-2 (user): whether the 25% checkpoint should also tell the agent to start a fresh sub-agent with the overview for the remaining work, since hooks cannot compact the chat themselves.
- Q-3 (user): commit release snapshots to `docs/architecture/` or keep them in `.hve/`.
- Q-4 (engineering): which stacks get framework conventions first.
- Q-5 (engineering): where the per-model context window table lives and who maintains it.

<!-- hve-section: traceability -->
## Verification and Traceability

| Requirement | Component | Planned check |
|---|---|---|
| FR-1, AC-4 | `size.py`, contract | Unit tests on sample workspaces below, between and above the thresholds; `map: off` recorded with why |
| FR-2, FR-3, FR-4 | extract, frameworks, views | Golden-map tests on small fixture apps per stack: expected views, modules, typed edges with evidence |
| FR-5, NFR-3, AC-1 | `solution_map.py` | Budget tests on `overview` and `impact`; AC-1 fixture for an authenticated endpoint |
| FR-6, AC-2 | `context_meter.py` | Hook tests feeding events past 25%, 50% and 75%; one checkpoint per band; `precompact` logged |
| FR-7 | provenance, `ask_report.py` | Report test showing the Solution map section with checkpoints, answers and cited-file tokens |
| FR-8 | impact to pack routing | Test that a data plus APIM impact offers the matching sample packs |
| NFR-1, NFR-4 | build | Test that a build runs with network disabled and without Graphify installed |
| NFR-2 | every answer | Test that a changed file makes `status` and every answer report staleness |
| AC-3 | benchmark | A/B run with and without the map on one medium sample app, same model and effort; results in `research/comparisons/` |

No test strategy document exists yet; one is needed before M2. **Review status:** draft, not reviewed; nothing in this design is implemented or validated.