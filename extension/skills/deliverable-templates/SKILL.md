---
name: deliverable-templates
description: Create or update PRDs, technical design specifications and test strategies using configured Frontier HVE templates; validate structure and provenance before handoff.
---

# Deliverable Templates

## When to Use

Use when authoring a Product Requirements Document (PRD), Technical Design
Specification (TDS), or Test Strategy. Do not generate all three for unrelated
coding requests. `<tools>` is the harness tools folder in the agent instructions.
Python 3.11+ is required.

## Decision Tree

- No workspace configuration: use the bundled versioned defaults.
- Company templates: run `python <tools>/templates/manage.py configure`, then
  edit `frontier-hve.templates.json`; sources MUST be committed relative paths.
- Existing generated document: fill/revise it in place, then use `register`
  instead of `init`. Existing unrelated documents are not overwritten.

## Core Rules

1. Use the template session ID from hook context. Before delegating or authoring,
   run `python <tools>/templates/manage.py request <types> --session <id>`.
   Types are `prd`, `technicalDesign`, `testStrategy`. Register all explicitly
   requested outputs, including requests the keyword hook did not recognize.
   The parent runs manager commands serially; workers edit assigned documents,
   not session state. A busy registry update fails explicitly, without retries.
2. For each requested type, run `python <tools>/templates/manage.py resolve <type>`
   and `python <tools>/templates/manage.py init <type> --slug <name> --session <id>`.
   Read the created file and fill its sections. Preserve all `hve-*` comments.
   Names MUST use lowercase letters/digits separated by hyphens.
3. Keep requirements traceable: PRD FR/NFR/AC IDs -> design decisions/components
   -> test coverage/evidence. Read linked upstream documents. Unknowns MUST be
   explicit open questions with owners; never fabricate sources or approvals.
   Explain non-applicability instead of leaving required sections empty.
4. Validate with `python <tools>/templates/manage.py validate <type> --slug <name>`.
   For an existing valid document, run `register <type> --slug <name> --session <id>`.
   Finish with `python <tools>/templates/manage.py check --session <id>` and report
   the result and output paths. A Test Strategy records planned tests, not proof
   of execution. Structural validation does not certify content correctness.

## Error Handling

Missing configured files, malformed config, changed template hashes or unsafe
paths MUST surface as errors, never fall back to another template. Do not delete
the session registry, change `enforce`, or remove markers to pass validation.
If an existing document uses an older template, obtain approval to migrate its
content into a new initialized document with a new slug; do not rewrite provenance.
The Stop hook asks once for correction and reports remaining failures on reentry;
it is not an indefinite retry loop or a host-level security boundary.
Cursor cannot receive the reentry diagnostic: its first Stop follow-up instructs
the agent to report unresolved errors, then permits no additional repair loop.

## Checklist

- Every requested deliverable is registered in the parent session.
- Configured templates and required sections are retained.
- Placeholders are filled with evidence or explicit unresolved questions.
- Linked requirements and planned test evidence are consistent across documents.
- Validation exits 0; approval and executed test claims have independent evidence.