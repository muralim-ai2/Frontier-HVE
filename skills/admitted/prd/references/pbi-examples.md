# Product Backlog Item Examples

> **Modified** by Frontier HVE on 2026-10-12 from AgentX `fc39b29` (Apache-2.0): made tracker-neutral; added the shared item shape for a local JSON backlog, Azure DevOps and GitHub; PRD links use requirement IDs.

> **Parent skill**: [PRD](../SKILL.md)
> **Purpose**: How to write backlog items (epics, features, stories) that downstream design, engineering and test can act on without guessing, in whichever tracker the user chose.
> **Rule**: An item is ready only when a reader can see the user outcome, scope boundary, acceptance tests, dependencies and evidence expectation, and which PRD requirements it delivers.

---

## Item Shape (all trackers)

Every epic, feature and story has these fields. A local JSON backlog uses them as keys; the field mapping below shows where they go in Azure DevOps and GitHub.

| Field | Quality bar |
|-------|-------------|
| `id` | Stable within the backlog (`E1`, `F1`, `S1`) |
| `type` | `epic`, `feature` or `story` |
| `parent` | `null` for an epic; an epic for a feature; a feature for a story |
| `title` | Names the user-visible outcome, not the implementation task |
| `persona` | Who receives value |
| `problem` | Current pain, baseline or risk |
| `outcome` | The value created when the item is done |
| `scope` | What is included now |
| `non_goals` | At least one nearby capability intentionally left out |
| `acceptance` | Given/When/Then criteria, including at least one edge or failure case |
| `verification` | How completion is proven: test, metric, artifact, screenshot, eval result |
| `dependencies` | Ids of items that must be done first |
| `priority` | `P0`, `P1` or `P2` |
| `priority_rationale` | Why this priority: impact, risk, deadline or sequencing |
| `requirements` | The PRD IDs (`FR-n`, `NFR-n`, `AC-n`) this item delivers |

Avoid items that only say "build X" or "add Y". A good item explains why X matters, who benefits, how small the slice is, and what proof will close it.

## Field Mapping per Tracker

| Field | Local JSON | Azure DevOps | GitHub |
|---|---|---|---|
| `type` | `type` | Work item type of the project's process: Epic / Feature / User Story (Agile), Epic / Feature / Product Backlog Item (Scrum), Epic / Feature / Requirement (CMMI), Epic / Issue / Task (Basic, no Feature type); ask for inherited or custom processes | The repository's issue type if defined, otherwise an existing label; never create one |
| `title` | `title` | Title | Title |
| `persona` ... `scope`, `non_goals`, `verification`, `priority_rationale`, `requirements` | Keys | Description, as the body sections below | Body, as the body sections below |
| `acceptance` | `acceptance` list | Acceptance Criteria field (description if the type has none) | Body section "Acceptance Criteria" |
| `priority` | `priority` | Priority field (P0 = 1, P1 = 2, P2 = 3) | Existing priority label, otherwise a body line |
| `parent` | `parent` id | Parent link | Sub-issue of the parent |
| `dependencies` | Ids | Predecessor links | "Blocked by #n" lines in the body |

---

## Splitting Rules

Split an item when any of these are true:

- More than one persona receives distinct value.
- The acceptance criteria require different release gates or owners.
- The work spans UI, API, data, AI and DevOps in ways that cannot be completed in one sprint.
- A failure mode can be shipped independently from the happy path.
- The item depends on an unresolved architecture, UX or data-science decision.

Do not split by technical layer alone. Prefer vertical slices that users can validate:

```text
[FAIL] Add database table
[FAIL] Add API endpoint
[FAIL] Add React screen

[PASS] As a compliance analyst, I can upload the monthly exception file and see row-level validation errors before submitting it.
```

---

## Body Sections (Azure DevOps description, GitHub body)

```markdown
## User Outcome
As a <persona>, I want <capability>, so that <measurable value or decision improves>.

## Problem
<Current pain, evidence, baseline, or risk.>

## Scope
Included:
- <behavior or capability in this item>

Out of scope:
- <nearby capability intentionally deferred>

## Acceptance Criteria
- Given <precondition>, when <action>, then <observable result>.
- Given <edge or failure condition>, when <action>, then <safe or expected behavior>.

## Evidence Required
- <test command, metric target, artifact, screenshot, eval score, or review evidence>

## Dependencies
- PRD: <path> <FR/NFR/AC ids>
- Blocked by: <item ids or none>

## Priority Rationale
<Why now: user impact, compliance date, risk reduction, dependency unblock, or revenue impact.>
```

---

## Bad vs Good

### Weak item

```markdown
Title: Add dashboard filters

Description:
Users need better filtering on the dashboard.

Acceptance Criteria:
- Filters work.
- UI is easy to use.
```

Why this fails:

- Persona is missing.
- "Better" and "easy" are not testable.
- No baseline, failure case, dependency, PRD link or completion evidence.
- The engineer must guess which filters, which dashboard, and what counts as done.

### Strong item (local JSON)

```json
{
  "id": "S3", "type": "story", "parent": "F1",
  "title": "Filter the risk dashboard by region and control owner",
  "persona": "Compliance manager",
  "problem": "Monthly review prep takes 45 minutes because managers export all open risks and filter them in a spreadsheet.",
  "outcome": "Review packs are prepared in the dashboard in <=15 minutes.",
  "scope": "Region and control-owner filters on the existing dashboard; filters persist in the URL; empty state when nothing matches.",
  "non_goals": ["Saved filter presets", "New dashboard widgets", "Changes to risk scoring"],
  "acceptance": [
    {"given": "risks across several regions", "when": "I select EMEA", "then": "only EMEA risks are listed and the count updates"},
    {"given": "a filtered URL", "when": "I reopen it", "then": "the same filters are applied"},
    {"given": "filters that match nothing", "when": "the dashboard loads", "then": "'No risks match these filters' is shown with a clear-filters action"},
    {"given": "no access to a region", "when": "I open a shared URL for it", "then": "restricted risks are not shown and nothing about them leaks"}
  ],
  "verification": "Unit tests for filter parsing; browser test for select, share and clear; accessibility scan with zero High findings.",
  "dependencies": ["S1"],
  "priority": "P0",
  "priority_rationale": "Directly delivers the PRD metric of <=15 minutes review prep before the Q3 review cycle.",
  "requirements": ["FR-3", "NFR-2"]
}
```

---

## AI Item Example

Keep AI items product-facing; design and data science own the implementation.

```markdown
Title: Summarize support case history with cited source messages

## User Outcome
As a support lead, I want an AI-generated case summary with citations to source messages, so that I can review escalation context in <=2 minutes without reading the full thread.

## Problem
Escalation review takes 12 minutes median across 80 sampled cases because leads read long case histories manually.

## Scope
Included:
- Summaries from messages already visible to the support lead, with a citation per factual claim.
- A manual-review prompt when citation confidence is below threshold.

Out of scope:
- Auto-sending responses to customers.
- Reading private notes outside the lead's permissions.
- Training or fine-tuning a model.

## Acceptance Criteria
- Given a case with at least five messages, when the lead requests a summary, then the response includes summary, key events, open questions and citations.
- Given citation precision below 95% on the eval set, when CI runs the case-summary evaluation, then the build fails.
- Given retrieval confidence below 0.6, when the lead requests a summary, then "Summary unavailable. Review the case history directly." is shown and no citation is fabricated.
- Given the lead lacks permission for a private note, when the summary is generated, then that note is excluded.

## Evidence Required
- Eval dataset with >=50 held-out cases; citation precision >=95% and faithfulness >=0.85.
- Security test proving unauthorized notes are excluded.

## Dependencies
- PRD: docs/product/PRD-case-summary.md FR-2, FR-5, NFR-1
- Blocked by: none

## Priority Rationale
P0 because it validates the central AI value while keeping autonomous customer actions out of scope.
```

---

## Ready Checklist

- [ ] Persona, problem, outcome and priority rationale are present.
- [ ] Non-goals name at least one deferred nearby capability.
- [ ] Acceptance criteria are observable and include a failure, permission or edge case.
- [ ] Verification is concrete enough for a reviewer or tester.
- [ ] Every item lists the PRD IDs it delivers; dependencies point to real items.
- [ ] The item is small enough for one sprint or explicitly split.
- [ ] AI-bearing items include fallback behavior, grounding boundaries and quality thresholds.
