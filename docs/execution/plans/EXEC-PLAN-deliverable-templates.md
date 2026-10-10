# Deliverable Templates Execution Plan

## Approved Scope

The user approved the repository-native template recommendation on 2026-10-09
and requested fetching the latest code first. `git fetch origin` succeeded;
clean `main` already matched `origin/main` at `3ab504f` (0 ahead, 0 behind).
No merge, rebase, stash, branch creation or commit was needed.

## Alternatives

- Prompt-embedded skeletons: rejected because they duplicate content and cannot
  mechanically verify structure.
- Static template files alone: insufficient for overrides, provenance and
  missing-output checks.
- Bundled templates plus one manager and agent hooks: selected; reuses the
  repository's runtime packaging and cross-client export paths.

## Milestones

1. Defaults and manager: three versioned Markdown defaults, committed workspace
   config, safe paths, exclusive initialization, exact template hashes, ordered
   sections, placeholder checks and session registration.
2. Integration: package the manager/templates/skill; wire the four product
   authoring agents; preserve minimal/evaluator/specialist roles and app flow.
3. Verification and documentation: focused regression cases in template,
   extension and adapter tests; company-template guide; extension version 0.5.0.
4. Review: compile/build/package checks, fresh independent read-only review,
   followed by an explicit offer to execute the focused suites.

## Acceptance and Limits

- Bundled defaults resolve for all three types; custom relative sources replace
  only their configured types and never silently fall back on errors.
- Existing documents are not overwritten. Provenance drift and invalid required
  structure prevent a valid manager result.
- Explicit requested types and initialized outputs are checked per parent session.
  The keyword detector is deliberately limited; agent instructions register
  missed intent. Stop correction is bounded, not an indefinite loop.
- Exported clients receive the same assets through existing runtime/skill copying;
  no templates are loaded from installed Frontier/AgentX.
- Markdown is the output contract; DOCX/PDF export, remote template retrieval,
  content-quality certification and automatic generation of unrequested documents
  are out of scope. Structural checks do not certify approval or test execution.
- Test suites are authored during implementation; execution is offered separately
  under the governing test-consent rule. No tracker item is marked validated.

## Current Evidence

Python compilation and `extension/build.py` passed after the integration edits;
all 14 agent-referenced runtime scripts exist. The three template types resolve
through the real CLI. Initial CRLF parsing failure was fixed by normalizing text
for matching while retaining the raw-byte source hash. Final checks and review
will bind to the final worktree, not these earlier observations.