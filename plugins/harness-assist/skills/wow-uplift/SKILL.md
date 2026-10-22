---
name: wow-uplift
description: Finishing loop on every deliverable a user sees - a top-model judge picks two or three small, targeted UI/UX or presentation improvements per round, you apply and re-check them, and the loop repeats on the new version (up to 3 rounds) so the uplift shows before and after.
---

# Wow uplift

The icing on the cake. Run it on every finished deliverable a user sees (a UI, a prototype, a deck, a document) before you show it for sign-off. There is always something that can be better: each round finds the two or three changes that lift the experience most for the least change, applies them, and looks again at the result. Small targeted steps, never an overhaul or new scope.

`<tools>` is the harness tools folder named in your agent instructions; `<evidence>` is the ask's `paths.evidence`; `<n>` is the round (1, 2, 3).

## 1. Before

Capture what the user would see now, in `<evidence>/uplift/round-0/`:
- Static HTML (a prototype, a page): `python <tools>/prototype/check.py shots <folder with index.html> "<route,route>" uplift/round-0`.
- An app with its own checks: copy the screenshots its feature checks saved under `<evidence>/<feature>/`.
- A deck: `python <presentation-deck skill>/scripts/check_deck.py preview <deck.pptx> <evidence>/uplift/round-0`.
- A document: the file itself.

## 2. Improve in a loop (at most 3 rounds)

For round `<n>`:
1. **Judge.** Run sub-agent `HVE uplift-judge` (it runs on a top model). Its prompt: the output of `lifecycle.py brief "HVE uplift-judge"` when an ask is open, then the user's request verbatim, the output kind (`ui`, `deck` or `document`), the files to read, the latest images (`<evidence>/uplift/round-<n-1>/`) and the changes made in earlier rounds. It replies with JSON only: `verdict` (`uplift` or `done`), two or three `changes` (what, where, why) and what to keep. Save it to `<evidence>/uplift/round-<n>/judge.json`. On `done`, stop the loop.
2. **Apply.** Make exactly those changes, yourself or with one fresh sub-agent, and nothing else:
   - Keep the agreed scope, content, facts and data; no new dependencies, network calls, external fonts, scripts or images from the web.
   - UI examples: proper heading hierarchy and a page title, a cohesive theme (colour tokens, spacing scale, one accent), a simple text or SVG wordmark as the logo, a better grid or card layout instead of a plain list, clearer empty and error states, focus and hover states.
   - Deck examples: fewer words, a bullet list turned into a flow, cards or metric tiles, aligned edges and even spacing, one highlighted element, a sharper takeaway bar.
   - Document examples: a summary up front, scannable headings, a table instead of a dense paragraph.
3. **Re-check.** Everything that passed before must still pass: every feature's `verify` command from the feature list (the `run-tests` regression), a prototype's `check.py lint`, a deck's `check_deck.py lint`. If a change breaks a check, fix it within the change or drop that change; never leave a check failing.
4. **Capture and show.** Take the same views into `<evidence>/uplift/round-<n>/`, look at them, and tell the user one line per change with the image paths, so each round's uplift is visible.

The loop ends when the judge says `done`, after round 3, or when every change of a round had to be dropped (say so). Never restart it for the same version.

## 3. Close

- If the feature loop committed the features, commit the uplift as one commit `[uplift] <change titles>` (git hooks run; never `--no-verify`).
- Write the ask's `uplift.md`: one row per change (round, change, why, before image, after image), the checks re-run with exit codes, and why the loop stopped.
- Inside an ask, run `lifecycle.py used "HVE uplift-judge" - "none"`.
- In the sign-off, show round 0 next to the last round.
