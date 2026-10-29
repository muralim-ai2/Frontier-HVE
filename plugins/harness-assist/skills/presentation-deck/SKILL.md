---
name: presentation-deck
description: Build any presentation, deck, slides or PowerPoint (pptx) - discovery questions on format (editable NorthStar pptx or animated web slides through frontend-slides), purpose, theme, text level, smart art and speaker notes, a takeaway storyline, build, lint and slide previews. Use for every deck.
---

# Presentation deck (NorthStar)

Use this skill whenever the deliverable is a presentation: a deck, slides, a pitch, a briefing pack, a workshop or a `.pptx`. It builds an editable PowerPoint, or routes to the `frontend-slides` skill when the user picks web slides (section 1); do not hand-write slides any other way. The look comes from the NorthStar decks built with `python-pptx` (editorial ink header band, one accent colour, cards, chips, chevron flows and one takeaway bar per slide). The aim is a deck that makes people say "wow": clean, visual, little text, every slide with one clear point.

`<skill>` below is the folder holding this `SKILL.md`; its `scripts/` has `deck_kit.py` (theme and slide primitives) and `check_deck.py` (lint and previews).

**The NorthStar style is built in.** `deck_kit.py` and section 3 encode it completely, so you never need a NorthStar reference deck. When a request links or names one (a SharePoint, OneDrive or web link, or a file name such as `Harness_Engineering_Workshop_NorthStar_v2.pptx`), read it as "use this style": do not fetch, download, open or ask for it, and do not wait on it or list it as missing. Content the user wants in the deck comes from the request, the workspace and its repository, and files the user has put in the workspace.

## 1. Discovery (one form, before any outline)

Ask once with the ask-questions tool as one form; skip any question the request already answers, and as a sub-agent use your brief instead of asking. Recommend the option in bold.

| Question | Options |
|---|---|
| Format | **Editable PowerPoint (.pptx) in the NorthStar style**, or web slides: one animated HTML file that runs in the browser, with style previews to pick from (`frontend-slides` skill) |
| What kind of deck is it? | Informational (explain), Analysis (answer a question with evidence), Pitch (persuade and ask), Decision (options and a recommendation), Status update, Workshop or training |
| Who is in the room? | Executives, technical leads, mixed, customer or partner |
| Theme | **NorthStar: ink with one accent** (green, blue, teal, orange, purple or red), your brand colours (hex codes), or a template `.pptx` already in the workspace (never a link to fetch) |
| How much text? | **Minimal**: headline plus visual, under 45 words a slide; Balanced: under 80; Detailed reading deck: under 120 |
| How visual? | **Mostly smart art** (flows, layers, card grids, timelines, metric tiles), mixed, or mostly tables and text |
| Speaker notes? | **Full talk track per slide**, key points only, none |
| Length | Number of slides (default 6-10; one message per slide) |
| Logo or brand assets? | A file path, or none (never download one) |

Record the answers in the ask folder's `deck/brief.md` (six lines: format, kind, audience, theme, text level, notes).

**Web slides.** When the user picks web slides, do section 2 here, then follow the `frontend-slides` skill from its Phase 2 (style previews) instead of sections 3 and 5: its Phase 1 questions are already answered by this form (purpose is the kind, density is the text level). Save previews in `<evidence folder>/deck/previews/` instead of `.frontend-slides/` and the deck as `presentation/<slug>/index.html`, keep speaker notes as its HTML comments, then finish with section 6 here.

## 2. Storyline (outline first)

Write `deck/outline.md`: one line per slide with eyebrow (topic, 1-3 words), title (the takeaway as a full sentence, not a topic) and the visual it uses. Get it approved before building. Story spines by kind:

| Kind | Spine |
|---|---|
| Pitch | Problem, why now, the idea, how it works, proof, plan, the ask |
| Analysis | The question, the answer first, the evidence (2-3 slides), what it means, recommendation |
| Informational | Context, what it is, how it works, what changes, next steps |
| Decision | Decision needed, options, criteria, comparison, recommendation, risks, the ask |
| Status | Headline, progress against plan, risks and blockers, decisions needed |
| Workshop | Agenda, concept, worked example, exercise, recap |

Open with a cover slide and close with the ask or the next steps. Every number needs a source in the notes; never invent figures, customers or quotes.

## 3. Visual grammar

- 16:9 (13.333 x 7.5 in). Content left edge 0.56 in, content starts at 1.26 in, 0.20 in gaps on a column grid (`Deck.columns`).
- Header band: ink, 1.02 in, a 0.05 in accent rule under it, letter-spaced eyebrow (9 pt), takeaway title (23 pt bold white, one line).
- Three colours only: ink for structure, one accent for emphasis, slate for text, plus their tints. Exactly one element per slide gets the accent tint (`Deck.highlight` or a `strong` pill).
- Type scale (Segoe UI unless the brand says otherwise): title 23, lead 14-17 bold, card heads 12.5-15 bold, body 9.5-11.5, labels 9.5, never under 9.
- Every content slide ends with a takeaway bar (`Deck.bar`): the one sentence the audience should repeat.
- Numbered kickers (`01`, `02`) in the accent over card heads; rules on the left of cards; chips for short lists.
- Turn text into smart art:

| Content | Visual (`deck_kit.Deck`) |
|---|---|
| A sequence or process | `flow`: numbered steps with chevrons, the outcome inked |
| A stack, architecture or hierarchy | `layers`: tagged bands, top layer in the accent |
| Three to eight parallel ideas | `card` grid with numbered kickers |
| Short items, criteria, domains | `pill` row with sub-lines |
| Numbers | `metrics`: big accent figure over a caption |
| Two sides (today vs target, problem vs fix) | two `card` columns, one with the accent rule |
| One key statement | `highlight` card |
| Phases or a timeline | stage cards with kickers (`WEEKS 1-3`) and an `OUTPUT` line |

- Text discipline: at most six items in a group, card bodies under 25 words, no paragraphs, numbers over adjectives, cut every word that does not change the meaning.

## 4. Speaker notes

When notes are on, every slide gets them (`Deck.notes`): the opening line to say, what to point at, the one thing the audience must take away, and the objection to pre-empt. Write them as talk, not as the slide's text repeated. Key-points mode: three short lines.

## 5. Build

1. Dependency: `python-pptx==1.0.2` (pinned). It goes in the dependency list of the plan form; install it into the project's environment only after the user approves.
2. Copy `<skill>/scripts/deck_kit.py` to `presentation/deck_kit.py` and write `presentation/build_deck.py` next to it; the deck saves to `presentation/<slug>.pptx`. Keep data (titles, cards, steps) in lists at the top of each slide block so edits stay local, and keep the script under 500 lines (split per section if needed).

```python
from pathlib import Path
from pptx.util import Inches
from deck_kit import Deck, theme

d = Deck("Leave portal - sprint 1 review", theme("teal"))
d.notes(d.cover("Leave requests in two clicks", "Sprint 1 review", "leave portal"), "Open with the user problem.")
s = d.slide("the flow", "Requesting leave now takes two steps, not seven")
d.label(s, Inches(1.26), "the new request flow")
d.flow(s, Inches(1.58), [("Balance", "see days left"), ("Request", "pick dates"), ("Approved", "manager notified")])
d.bar(s, Inches(5.9), "Fewer steps, fewer emails, faster approvals.")
d.notes(s, "Point at step 2: this is where the old form lost people.")
d.save(Path("presentation/leave-sprint-1.pptx"))
```

3. Run it, then check it:
   - `python <skill>/scripts/check_deck.py lint presentation/<slug>.pptx <minimal|balanced|detailed> [--notes]` must exit 0 (density per slide, fonts under 9 pt, shapes off the slide, missing notes).
   - `python <skill>/scripts/check_deck.py preview presentation/<slug>.pptx <evidence folder>/deck/` exports one PNG per slide with PowerPoint on Windows (`<evidence folder>` is the ask's `paths.evidence`). Look at every image: fix wrapped titles, overlaps, crowded cards and empty space before showing the user. Without PowerPoint it says so; then ask the user to look at the deck.

## 6. Finish

- Then self-check the deck once against the `ui-ux-uplift` skill: for decks usually fewer words, a list turned into a flow or cards, better alignment and spacing.
- Hand over: the `.pptx` (or web slides `index.html`) path, the preview folder, the slide count and the words per slide from the lint, and whether notes are in.
