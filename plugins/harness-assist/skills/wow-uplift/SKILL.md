---
name: wow-uplift
description: "Finishing loop for UIs, prototypes, decks and documents: inspect ten quick polish opportunities in typography, alignment, material layers, emphasis, icons, creativity and accessible themes; apply up to three meaningful improvements per round with before/after evidence, never a redesign."
---

# Wow uplift

Run this on every finished deliverable a user sees (a UI, a prototype, a deck, a document) before sign-off. Inspect ten opportunities, then apply one to three worthwhile changes per round. Each change should be small enough to implement and re-check in roughly 5-10 minutes. Ten candidates are not ten mandatory edits. Say `done` when there is no meaningful improvement; do not manufacture work or promise a percentage uplift.

Keep the existing structure, navigation, slide order, content, facts, data and brand. Improve their execution, not their replacement. Material design here means clear surfaces, hierarchy and states, not installing a framework. Preserve intentional whitespace; more cards, shadows, colour or icons do not automatically mean better design.

`<tools>` is the harness tools folder named in your agent instructions; `<evidence>` is the ask's `paths.evidence`; `<n>` is the round (1, 2, 3).

## Ten quick uplift candidates

| # | Candidate | Small, visible change |
|---|---|---|
| 1 | Type hierarchy | Make equivalent headings use consistent size, weight and spacing; separate title, section, body and metadata levels. Fix cramped wrapping without shrinking essential text. Different semantic roles need not have identical sizes. |
| 2 | Alignment within elements | Align icons with labels, headings with body text, values with units, and content with shared inner edges. Match padding and baselines across repeated cards or deck elements. Do not blindly left-align or centre everything. |
| 3 | Composition and focal balance | Correct overlaps, accidental gaps, crowded text clusters and uneven spacing within the existing layout. Centre a focal object such as a Hive within its content region, balance surrounding elements and preserve useful breathing room. |
| 4 | Material layers | Clarify canvas, content surfaces, navigation and overlays with restrained elevation, borders, surface contrast or a scrim. Make the foreground distinguishable without creating extra cards or nesting cards inside cards. |
| 5 | Focus and highlight borders | Give a selected, expanded or newly foregrounded element a clear accent outline or subtle surface highlight. Distinguish persistent selection from keyboard focus; preserve focus visibility. Use outlines or reserved border space so emphasis does not move the layout. |
| 6 | Purposeful icons, especially in decks | Add a consistent existing icon beside a section heading, process step or key metric when it improves scanning. Match optical size, stroke, spacing and baseline. Keep essential text labels; do not scatter icons as filler or replace a meaningful chart with decoration. |
| 7 | Domain-specific creativity | Add one coherent, recognisable detail such as a paw-shaped like control, a themed empty-state illustration using existing assets, or a more intentional relationship motif. Preserve action meaning, accessible names and existing behaviour; novelty alone is not an uplift. |
| 8 | Contained theme refinement | Adjust existing semantic colour tokens, accent usage or deck theme colours consistently while preserving the brand and structure. Improve hierarchy and contrast rather than swapping the entire visual language or recolouring isolated elements inconsistently. |
| 9 | Dark appearance | Refine an existing dark mode, or add one only when tokenised styles and the agreed scope make a complete, small implementation possible. Check text, surfaces, controls, charts and overlays in both modes. If this requires a new settings flow or extensive restyling, defer it as a feature, not a polish change. |
| 10 | Colourblind-safe treatment | Give status, selection and chart series meaning through labels, symbols, patterns or outlines as well as colour. Refine an existing colourblind mode when present; do not introduce a mode switch solely to tick a box or claim accessibility from a palette swap alone. |

For decks, prioritise type, alignment, composition, emphasis and purposeful icons; apply theme changes through consistent native styles and keep objects editable. For documents, use the relevant type, spacing, emphasis and information-grouping opportunities; do not add UI controls or cosmetic icons without a reader benefit.

## 1. Before

Capture what the user would see now, in `<evidence>/uplift/round-0/`:
- Static HTML (a prototype, a page, web slides): `python <tools>/prototype/check.py shots <folder with index.html> "<route,route>" uplift/round-0`.
- An app with its own checks: copy the screenshots its feature checks saved under `<evidence>/<feature>/`.
- A deck: `python <presentation-deck skill>/scripts/check_deck.py preview <deck.pptx> <evidence>/uplift/round-0`.
- A document: the file itself.

Record the views, viewport sizes, theme and selected states so after captures are comparable. Use full, uncropped images, plus readable detail views when needed. Record missing assets as evidence limitations; distinguish a failed image load from a design defect before proposing a change. Note the existing tokens, icon family and assets that can be reused.

## 2. Improve in a loop (at most 3 rounds)

For round `<n>`:
1. **Judge.** Run sub-agent `HVE uplift-judge` (it runs on a top model). Its prompt: the output of `lifecycle.py brief "HVE uplift-judge"` when an ask is open, then the user's request verbatim, the output kind (`ui`, `deck` or `document`), this skill's ten-candidate checklist, the files and reusable styles/assets to inspect, the latest images (`<evidence>/uplift/round-<n-1>/`) and earlier changes. It replies with JSON only: `verdict` (`uplift` or `done`), up to three `changes` (`title`, `where`, `what`, `why`) and `keep`. Each change identifies the file and element, exact bounded edit, observed issue or opportunity, and expected visible benefit. Prioritise legibility, overlap and alignment before decoration; include creative or layered polish when it provides a real benefit, not to fill a quota. Save the actual response to `<evidence>/uplift/round-<n>/judge.json`. On `done`, stop. If the judge cannot run, report the pass as blocked; do not silently substitute self-review or record a completed independent review. Explicitly authorised self-review must be labelled as such.
2. **Apply.** Make exactly those changes, yourself or with one fresh sub-agent, and nothing else:
   - Keep the agreed scope, content, facts and data; no new dependencies, network calls, external fonts, scripts or images from the web.
   - Reuse the established design tokens, components and icon library. Keep deck icons and diagrams editable where the existing tooling supports it. Do not change data to make a chart look better or remove required content to create whitespace.
   - A small palette adjustment is allowed; a new visual identity, layout system, navigation flow or settings subsystem is not. Defer mode work that cannot be completed and checked within this pass.
3. **Re-check.** Everything that passed before must still pass: every feature's `verify` command from the feature list (the `run-tests` regression), a prototype's `check.py lint`, a deck's `check_deck.py lint`. If a change breaks a check, fix it within the change or drop that change; never leave a check failing.
   - Inspect the changed elements at the original desktop/mobile sizes or slide aspect ratio: heading levels, wrapping, overlaps, internal alignment, icon/label baselines, layer separation and focus/selection visibility. For theme work, inspect all affected surfaces and states in both appearances; status must remain understandable without colour alone. Automated lint is not proof of improved visual quality.
4. **Capture and show.** Take the same views into `<evidence>/uplift/round-<n>/`, inspect before and after, and tell the user one line per retained change with the image paths and the visible benefit. A subtle preference with no meaningful improvement is not a successful uplift. Correct or drop changes that introduce visual regressions, and record dropped changes rather than counting them as improvements.

The loop ends when the judge says `done`, after round 3, or when every change of a round had to be dropped (say so). Never restart it for the same version.

## 3. Close

- If the feature loop committed the features, commit the uplift as one commit `[uplift] <change titles>` (git hooks run; never `--no-verify`).
- Write the ask's `uplift.md`: one row per change (round, candidate, change, why, before image, after image, retained/dropped), checks with exit codes, reviewer identity and whether it actually ran, deferred ideas, and why the loop stopped. A blocked or no-change pass is not an applied improvement.
- Inside an ask, run `lifecycle.py used "HVE uplift-judge" - "none"` only if that reviewer actually ran.
- In the sign-off, show round 0 next to the last round.
