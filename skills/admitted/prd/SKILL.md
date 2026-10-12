---
name: "prd"
description: "Produce production-grade Product Requirements Documents (PRDs) that bridge business vision and technical execution, in whatever template the workspace configures. Use when writing, reading, reviewing, or extending a PRD, or when turning a PRD into backlog items for a local JSON backlog, Azure DevOps or GitHub."
user-invocable: false
metadata:
  author: "Frontier"
  version: "1.2.0"
  created: "2026-04-21"
  updated: "2026-10-12"
---
# Product Requirements Document (PRD)

> **Modified** by Frontier HVE on 2026-10-12 from AgentX `fc39b29` (Apache-2.0; `LICENSE` and `NOTICE` ship in `runtime/skills/licenses/agentx/`). Changes: made template- and tracker-neutral (no fixed section list, file paths or issue formats), added stable requirement IDs, moved the backlog out of the PRD, moved examples and the AI contract into references. The unmodified original is kept in the repository at `skills/imported/agentx/product/prd/`.

**Goal**: concrete, measurable, non-contradictory requirements that survive handoff to design, engineering and test. Use when authoring, amending, reviewing or consuming a PRD, or decomposing it into a backlog.

## Load Order

1. This file (conventions).
2. The configured PRD template, through the `deliverable-templates` skill (structure).
3. [references/requirements-quality.md](references/requirements-quality.md): vague vs concrete rewrites, the AI product contract and the consumer checklist.
4. [references/pbi-examples.md](references/pbi-examples.md): backlog item shape and tracker mapping, only when building a backlog.
5. [references/worked-example.md](references/worked-example.md): filled content blocks.

## Structure Comes From the Configured Template

This skill never defines sections; the configured template (bundled default or company) does. Read the initialized document's markers and headings and place each content block in the section whose purpose matches; if none matches, use the closest and say so. If a section does not apply, write why. Keep every template marker.

| Content block | What it holds |
|---|---|
| Problem and evidence | The problem, baseline numbers and cited research (prior art, standards, user evidence) |
| Users | Personas and their journeys |
| Goals and metrics | Each metric with baseline, target, window and measurement method |
| Scope and non-goals | What is in, what is explicitly out, what is sequenced later |
| Requirements | Functional and non-functional requirements with stable IDs and testable acceptance criteria |
| AI product contract | Only for AI-bearing requirements (see requirements-quality.md) |
| Dependencies and constraints | Only constraints the user or repository stated; unknowns are `TBD` |
| Risks and open questions | Risks with mitigations; open questions with owners |

## The Five Non-Negotiables

1. **Evidence**: the problem block cites sources; requirements resting on assumption alone are labelled as assumptions.
2. **Concrete, measurable requirements**: no "fast", "easy", "intuitive", "modern"; every requirement has a number, a rubric or a named standard and can be rewritten as a test.
3. **Intent preservation**: constraints never contradict the user's stated technology intent ("AI agent" is not quietly downgraded to rule-based). No stated stack means `TBD`, not an invented one.
4. **Explicit non-goals**: the PRD states what it is NOT building.
5. **Testable acceptance criteria**: "works well" is not a criterion; "returns HTTP 200 with schema X in <200ms for 10k records" is.

## Stable Requirement IDs

Give every requirement and acceptance criterion an ID that never changes once published: `FR-n` (functional), `NFR-n` (non-functional), `AC-n` (acceptance). Design documents, backlog items and tests refer to these IDs; never renumber, mark a removed requirement as withdrawn.

## Discovery Gate

Do not draft a PRD cold. Ask at least 2 clarifying questions (problem, success metric, hard constraints, persona, stack) and wait, or record `TBD` for every unknown as an open question with an owner. Never hallucinate constraints: "must use Postgres" is a requirement only if the user or the repository stated it.

## The Backlog Lives Outside the PRD

The PRD holds requirements, not backlog items. Epics, features and stories go to the tracker the user chooses (local JSON backlog, Azure DevOps or GitHub), each listing the PRD IDs it delivers. Item shape and tracker mapping: [references/pbi-examples.md](references/pbi-examples.md).

## AI-Bearing PRDs

If any requirement involves AI (LLM, agent, RAG, classification, generation), fill the product-facing AI contract in [references/requirements-quality.md](references/requirements-quality.md): job, grounding, tool boundaries, response contract, fallback, human review trigger and a numeric quality threshold.