# Three visible agents, top models, wow-uplift loop and the NorthStar presentation skill

- **Requests received:** 2026-10-21, after D-054 (two messages: the main request, then "the reflection layer ... should not stop at reflection but loop through that to improve, so that the uplift can be seen")
- **Decision:** D-055 in `research/decisions/decision_log.md`
- **Built in:** extension 0.15.0 (same unreleased version as D-054)

## User requests (verbatim in substance)

1. **Three visible agents.** The extension shows only Frontier E2E Delivery, Frontier BYOW (Bring your own way of working) and Frontier Prototype Creator. Creator, minimal, single, creator-flow and the other agents appear only among the research agents in this workspace.
2. **Top models.** All three default to the best model available (Astra, Gemini Argon, Claude Fable, Opus 5.5), with high reasoning.
3. **Wow uplift.** A small reflection with one of the highest models as judge, aimed especially at UI/UX:
   - two or three targeted things, about a 10% uplift, never a major overhaul;
   - examples: headings, themes, logos and grids for plain HTML; for decks, font alignment, placement, less text and more smart-art flows;
   - it runs every time, "like icing on a cake";
   - follow-up: it must loop, not stop after one reflection, so that the uplift can be seen.
4. **Presentation skill.** A detailed skill based on the user's NorthStar decks (`Harness_Engineering_Workshop_NorthStar_v2.pptx`) and the build scripts in `v-0--Self_Infographics_creator/src/multi-to-modal-to-ghcp-pptx`.
   - It is picked for every presentation or pptx.
   - It asks about the theme and the kind of deck (informational, analysis, pitch and so on), the level of text and smart art, and whether speaker notes are needed.
   - The aim is a wow factor.
5. **Scope.** Make minimal changes and inform the user.

## Sources studied

- The deck builders `_build_pptx.py`, `ppt-built/9/.py` (NorthStar), `ppt-built/10` (theme module plus builder) and `repo_presentation_builder_reference.md`.
- The NorthStar previews (`ppt-built/9/preview`).
- The SharePoint link was not opened, because it needs a sign-in. The local NorthStar build is the same family.
- **NorthStar grammar taken from those builders:**
  - Ink header band (1.02 in) with a 0.05 in accent rule, a letter-spaced eyebrow and a takeaway title.
  - Three colours plus tints, and Segoe UI.
  - Labels, cards with a left rule, chips, chevron flows, layered stacks and numbered kickers.
  - One takeaway bar per slide and a talk-track note per slide.

## What was built

| Request | Change |
|---|---|
| 1 | `user-invocable: false` on creator, creator-flow, creator-github, single, minimal, product-manager, skill-evaluator and azure-devops in `extension/agents/`. They still ship and run as sub-agents; product-manager remains the persona that E2E and BYOW delegate to. The research arms in `.github/agents/` are unchanged and stay user-invocable in this workspace. |
| 2 | E2E, BYOW and Prototype Creator get `model: ['GPT-6 Astra (copilot)', 'Gemini 4 Argon (copilot)', 'Claude Fable 5 (copilot)', 'Claude Opus 5.5 (copilot)']` (VS Code uses the first one available) and `reasoning-effort: high`. The Copilot export strips both fields, because model names differ outside VS Code. |
| 3 | New hidden agent `HVE uplift-judge`: read-only (read, view image, search), on the same top-model list, replying with JSON only (`verdict` `uplift` or `done`, two or three changes, what to keep). New plugin skill `wow-uplift`, which captures round 0, then loops up to 3 rounds; each round is described below the table. E2E runs it before each gate whose stage produced something the user sees. BYOW runs it before such persona hand-offs. Prototype Creator runs it before its sign-off. `check.py shots` takes an evidence subfolder for the rounds. |
| 4 | New plugin skill `presentation-deck`; its parts are listed below the table. The `document` lifecycle's draft stage lists the skill, and E2E and BYOW are told to use it for any deck. |

**Each wow-uplift round:**
1. The judge reviews the latest files and images.
2. Two or three targeted changes are applied.
3. Every check is re-run: feature verifies, prototype lint, deck lint.
4. The same views are captured into `loop/evidence/uplift/round-<n>/`, and the user is told what improved.

The loop stops when the judge says `done`, after round 3, or when every change in a round had to be dropped. The ask's `uplift.md` shows round 0 next to the last round.

**What the `presentation-deck` skill contains:**
- **`SKILL.md`**:
  - discovery form: kind of deck, audience, theme, text level, how visual, notes, length, logo;
  - a story spine for each kind of deck;
  - the visual grammar, and a table that turns text into smart art;
  - rules for speaker notes;
  - build, check and finish steps.
- **`scripts/deck_kit.py`**: a theme with any accent or hex code, plus cover, slide, label, card, highlight, pill, takeaway bar, flow, layers, metric tiles and notes; it adds footers when it saves.
- **`scripts/check_deck.py`**:
  - `lint` checks words per slide against the text level, fonts under 9 pt, shapes off the slide and missing notes;
  - `preview` exports PNG slide previews through PowerPoint COM on Windows.

## Verification

- A smoke deck and the skill's example deck were built with `python-pptx==1.0.2` in a temporary venv, linted, and exported to PNG through PowerPoint.
- The previews match the NorthStar look.
- All 12 test suites pass:
  - `test_extension` checks 23 agents and 15 plugin skills, that only the three Frontier agents are visible, and the model pin on them and the judge;
  - `test_flow_plugin` checks that 15 plugin skills pass the scan;
  - `test_loop` covers the prototype check.

## Decisions to surface (not settled)

1. **Model names are inferred.** "Gemini 4 Argon" and "Claude Fable 5" come from earlier council reports and model ids (`claude-fable-5`). Check them against the model picker: a name that does not match is skipped, and the next one in the list is used.
2. **`reasoning-effort: high` is set, but VS Code ignores it in agent files (D-020).** Set the effort in the model picker as well.
3. **Earlier decisions reversed.** Product agents used the picked model (D-050), and every working agent was visible. Now only three are visible and they pin models.
4. **Hidden agents have no workspace copies.** `HVE skill-evaluator` and `HVE azure-devops` are not reachable by users in other workspaces, and this repository has no research copies of them either.
5. **Nested sub-agents.** Prototype Creator running as a sub-agent may not be able to start the judge. BYOW then runs the uplift at the hand-off, and skips it when the persona's reply already shows rounds.
6. **Cost.** The uplift adds up to 3 top-model judge calls per deliverable, plus the edits and re-checks.
7. **Dependencies and platform.** `python-pptx` is a new pinned dependency for any deck, approved in the plan form. Previews need PowerPoint on Windows; without it the user reviews by hand.
8. **Not live-tested.** The judge, the loop and the forms have not been run in a live chat.
