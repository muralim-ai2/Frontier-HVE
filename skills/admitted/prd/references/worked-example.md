# Worked Example: "Intelligent Docs Search" PRD Content

> **Modified** by Frontier HVE on 2026-10-12 from AgentX `fc39b29` (Apache-2.0): numbered sections replaced with template-neutral content blocks; user stories removed (the backlog lives in the chosen tracker); requirement IDs added to acceptance criteria.

> **Parent skill**: [PRD](../SKILL.md)
> **Purpose**: Filled content for each PRD content block. Place each block in the configured template's matching section; the headings below are block names, not template sections.
> **Scope**: An illustrative example, not a real feature.

---

### Problem and evidence

Developers waste ~15 minutes per day searching for snippets across our 120-repo monorepo. Keyword search returns too many false positives; asking teammates on Slack has ~2h response latency. New-hire time-to-first-PR averages 9 days.

Sources: internal developer survey (n=140, Q2); search logs for 30 days; prior art compared: GitHub code search, Sourcegraph Cody, Glean (strengths, gaps and user complaints summarized in a comparison table with links).

### Users

**Primary**: Backend engineers (N=180), median 2 years tenure, comfortable with the CLI.
**Secondary**: New hires in their first 30 days (~8/month) who do not yet know the repository structure.

Journey: the engineer runs `docs-search "<query>"`, sees a loading indicator for up to 3s, then an answer with numbered citations. Alternatives: no confident match gives a list of related files; an ambiguous query gives a clarifying question.

### Goals and metrics

| Metric | Baseline | Target | Window |
|---|---|---|---|
| Median search-to-answer time | 15 min | <= 2 min | 30 days post-launch |
| New-hire time-to-first-PR | 9 days | <= 6 days | 90 days post-launch |
| Citation accuracy on eval set | n/a | >= 95% | From day 1 |
| p95 query latency | n/a | <= 3s | From day 1 |

### Scope and non-goals

In scope: natural-language search with citations over the 120 allowlisted repositories, with a fallback and a CI evaluation gate. Sequenced: retrieval and fallback first, clarification next, the CLI copy button later.

Non-goals:
- Search outside the 120 allowlisted repositories.
- Code generation or edit suggestions.
- An IDE plugin (tracked separately).
- Indexing issues, PRs or Slack history.

### Requirements

| ID | Priority | Requirement | Acceptance |
|---|---|---|---|
| FR-1 | P0 | Natural-language query endpoint | AC-1: POST `/search` accepts `{query}` and returns `{answer, citations[{path, line_start, line_end, score}]}` within 3s p95 for queries <=200 tokens |
| FR-2 | P0 | Grounded responses | AC-2: every answer has >=1 citation with `score >= 0.6`; otherwise it returns `"No confident match. Top 3 related files: ..."` |
| FR-3 | P0 | Evaluation gate in CI | AC-3: 50 held-out queries with expected citation paths; CI blocks merge when Citation Precision@3 < 95% or Faithfulness < 0.85 |
| FR-4 | P1 | Clarification for ambiguous queries | AC-4: when classifier confidence < 0.7, the response is `{clarification_question}` instead of an answer |
| FR-5 | P2 | Copy-to-clipboard in the CLI renderer | AC-5: the copy action puts the answer text on the clipboard |
| NFR-1 | P0 | Cost | AC-6: p95 cost per query <= $0.02; monthly inference spend capped at $500 by quota |

### AI product contract

| Field | Value |
|---|---|
| Primary AI Job | Answer natural-language questions about internal code and docs with citations to source files |
| Grounding Sources | Markdown under `docs/`, inline code comments and READMEs in the 120 allowlisted repos. No external web |
| Tool / Action Boundaries | MAY read indexed content and run retrieval queries. MUST NOT execute code, open PRs or write to any repo |
| Response Contract | Structured JSON `{answer, citations[]}`; citations always an array, possibly empty on fallback |
| Fallback Behavior | No citation >= 0.6: return the top-3 related paths with `"No confident match."` Never fabricate citations |
| Human Review Trigger | None at runtime (read-only). Weekly review of 20 sampled queries for drift |
| Quality Threshold | Citation Precision@3 >= 95%; Faithfulness >= 0.85; p95 latency <= 3s, on the held-out eval set |

### Dependencies and constraints

- A Microsoft Foundry project, reachable through managed identity (confirmed with the Platform team).
- The embedding index is refreshed nightly by the existing `repo-sync` job.
- Model and provider: `TBD`, resolved during design; the user stated no preference.

### Risks and open questions

| Risk | Impact | Probability | Mitigation |
|---|---|---|---|
| The model invents citations | High | Medium | Faithfulness gate in CI; a runtime check rejects answers whose cited lines lack the referenced terms |
| A stale index misleads users | Medium | Medium | Show `indexed_at` with every response; nightly and on-demand refresh |
| Query cost spikes | Medium | Low | Per-user rate limit of 60/min; budget alert at 80% of the monthly cap |

Open questions:
- Do we need access control on which repositories a user can query? (Owner: Security; needed before FR-1 ships.)
- Should clarification questions come from the same model or a smaller classifier? (Owner: data science.)

---

## What This Example Demonstrates

- **Every success metric is numeric and has a window.**
- **Every requirement has a stable ID and testable acceptance.**
- **Non-goals are explicit.**
- **The AI contract is product-facing**, so design can specify retrieval and prompting without guessing.
- **Unknowns are `TBD` or open questions with owners**, not invented constraints.
- **No backlog items appear in the PRD**; epics and stories go to the chosen tracker and reference FR/NFR/AC IDs.

Compare this to the vague equivalents in [requirements-quality.md](requirements-quality.md) to see the rewrite pattern in action.
