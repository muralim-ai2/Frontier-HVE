---
name: clickable-infographic
description: "Create a clickable, theme-aware infographic (1920x1080 HTML plus PNG export) for any subject: app or repo flows, user journeys, processes, architectures, phases, timelines, comparisons or categories. Use when asked for an infographic, flow map, journey map, process poster, architecture picture, phase or timeline graphic, or a slide-ready visual summary."
argument-hint: "subject: a folder, document, or topic, plus the question it should answer"
---

# Clickable infographic

One 1920x1080 canvas that answers **one question** about a subject, built from facts in the source material. Every box can be clicked: it opens the subject's own page, a related document or image, or an in-page detail sheet. The same page exports to slide-ready PNGs in any theme.

Bundled assets (copy the template, then author only `data.js`, plus the token blocks in `styles.css` if you need them):

| File | Role |
|---|---|
| [template/index.html](./template/index.html) | Canvas shell. Do not edit. |
| [template/app.js](./template/app.js) | Engine: layouts, connectors, click targets, detail sheet, theme routes, budget warning. Do not edit. |
| [template/styles.css](./template/styles.css) | Engine styles. Only the `:root` and `[data-theme]` token blocks are meant to change. |
| [template/data.js](./template/data.js) | **All content.** A neutral sample using the `lanes` layout. |
| [examples/columns.data.js](./examples/columns.data.js) | The same shape using the `columns` layout. |
| [scripts/export.py](./scripts/export.py) | `python export.py <folder> light,dark [out]` writes `<folder>-<theme>.png` (headless Edge or Chrome). |

## Workflow

1. **Frame.** Write the one question as a single sentence. It becomes the subtitle. Name the audience: team, executives, users or a slide deck.
2. **Gather facts (read-only).** Read the source: README, docs, code entry points, process documents, data. Note every item you will draw, along with its evidence (file, section, line or route) and anything it can link to (a page, document, image, source file or URL).
3. **Choose the layout** (table below), then map the items onto the information model. Check them against the budget. If they don't fit, split into two infographics.
4. **Confirm** the question, the layout, the lanes or columns, and the output folder in one short message, unless the request says not to ask. Default output: `<subject>/docs/infographic/`, or the current task's working folder.
5. **Build.** Copy `template/` to the output folder. Write `data.js`, and set `kinds` to the subject's own vocabulary. Set the colour tokens from the subject's design system if it has one; otherwise keep the defaults. Add any missing icons in the same 24px, 1.8-stroke style.
6. **Self-check.** Open `index.html`. The footer turns into a warning if content spills. Export Light, Dark and High contrast, look at every image, and work through the quality bar. Click every node.
7. **Polish once.** Make up to three small, visible fixes from the uplift menu. No redesign.
8. **Deliver.** Export PNGs (Light and Dark by default). Report the file to open, the PNG paths, the click path to try first, what is placeholder, and two creative touches.

## Choose the layout

| Subject shape | Layout | Model |
|---|---|---|
| Movement between places: app screens, user journeys, request flows, architectures, decision paths | `lanes` | Rail of entry points, then a main node per lane, then one-hop targets, then an optional second hop |
| Ordered stages or side-by-side groups: phases, a timeline, a maturity model, a comparison, categories | `columns` | One column per stage or group: a header node with in-place items, child nodes, then a closing note. `sequence: true` draws arrows between headers |

If neither fits (a single metric story, a dense matrix), use another kind of visual. Don't force the subject into these layouts.

## Information model

| Element | Use for | Rule |
|---|---|---|
| Rail (`lanes`) | Ways in: navigation, channels, triggers, entry commands, user types | Real order; labels of 8 characters or fewer; one `start` tag at the natural beginning |
| Lane / column | One area, stage or group | Max 4 lanes or 5 columns |
| Main node | The anchor of an area | Lists things that happen **in place** (no movement) as `items`, max 6 |
| Target / child node | One hop away, or one member of the group | Title of about 18 characters or fewer; `via` line of about 26 characters or fewer saying what triggers it or what it is |
| Chain | A second hop | Max 1 per row |
| Note | The outcome and the way back, or why it matters | Max 2 lines, with the key verbs in **bold** |
| Side panel (optional) | One thing shared across many areas: settings, measures, policies, data stores, risks | One arrow in, with a short label; `nodes`, `image` and `facts` |

**Kinds** describe what a box means. Each kind maps to one of five encodings, and the legend is generated from them:

| Style | Looks like | Typical meaning |
|---|---|---|
| `accent` | Tinted tile and accent tag | Entry point, phase, primary screen |
| `bar` | Left inset bar | Step, output, pushed page |
| `dashed` | Dashed border, no shadow | Optional, overlay, conditional |
| `muted` | Filled, no shadow | Planned, placeholder, gate, external |
| `solid` | Plain card | Anything else (no tag) |

Use at most four kinds, and name them in the subject's words (`kinds: { primary: { label: 'Phase', style: 'accent' } }`).

## Click targets (resolved per node, in this order)

1. **The subject's own page.** If the subject has an `index.html` (a web app, site or prototype), set `app: { page: '<relative path>/index.html', themeParam: 'theme' }` and give each node a `route` (for example `'#/home'` or `'?tab=2'`). The previewed theme is passed along when the subject supports it; omit `themeParam` if it doesn't.
2. **Related material.** Otherwise set `href` to the most useful related item: a document section (`../docs/process.md#review`), an image or diagram, a source file, a spreadsheet, or a URL the user provided. Use paths relative to the output folder.
3. **Detail sheet.** If there is nothing to open, or the item needs explanation, set `detail: { text, image, alt, links: [[label, href]] }`. Clicking opens an in-page sheet with the text, an optional image and link chips. If you set both `href` and `detail`, the sheet shows and `href` becomes an **Open** chip.

A node with none of these still opens a sheet with its title and `via`, but every node should lead somewhere useful. Never invent links. If a related document doesn't exist, use a detail sheet that says `[to be written]`.

## Data schema (`window.INFOGRAPHIC`)

```js
{
  meta: { eyebrow, title, sub, mark /* icon name */, foot, exportFoot },
  layout: 'lanes' | 'columns',
  app: { page, themeParam },              // optional, see click targets
  kinds: { key: { label, style, legend } }, // style: accent | bar | dashed | muted | solid
  arrow: 'Leads to',                     // legend text for arrows
  icons: { name: '<svg path data>' },    // extra icons, 24px grid
  rail: { title, foot },                 // lanes only
  lanes: [{
    entries: [{ id, icon, label, to /* node id */, start /* optional tag */ }],
    main: { id, icon, title, via, kind, cap, items: [[icon, text]], route | href | detail },
    rows: [{ node: {...}, chain: {...} /* optional */, note }],
    // or, for entries that go straight to nodes with no main node:
    direct: [{ node: {...}, note }],
  }],
  columns: [{ main: {...}, nodes: [{...}], note }], sequence: true, // columns only
  panel: { icon, title, sub, from /* node id */, label, nodes, image: { src, alt, caption }, facts: [[icon, html]] },
}
```

Every `id` must be unique. Notes, facts and detail text accept simple inline HTML (`<b>`, `<code>`, `<span class="k">` to stop wrapping). Never put user-supplied or untrusted HTML in them.

## Design principles

### 1. One question, one canvas
- Every element answers the subtitle's question. Cut everything else, however true.
- The canvas is fixed at 1920x1080 with 56/64px padding and scales to fit any window, so PNGs and slides get identical pixels.

### 2. Alignment is the backbone
- Fixed columns, with shared left edges for target nodes and for notes. Each rail item is centred on its node, so its arrow is horizontal.
- 56px rows with 12px gaps on a 4/8px spacing scale (4, 8, 12, 16, 24, 32, 48, 64). Radii 8/12/16 only.
- Icons sit in 32px tiles and centre on their text block. Tags sit at the right edge on the title's centre line.

### 3. Meaning never relies on colour alone
- Kind = border style + inset bar + fill + tag text. The legend is generated from `kinds`, so it always matches.
- High contrast mode uses 1.5px borders and black edges, with no shadows.

### 4. Connectors that read at slide distance
- Orthogonal bus routing with 10px rounded corners, a 1.5px stroke and 7px arrowheads. Never diagonal spaghetti.
- Connectors use the **muted text colour**. Light grey lines vanish on bands and in dark mode.
- Put the trigger in the node's `via` line. Only the side-panel arrow gets a label.
- Hover or focus on a node highlights its connectors in the accent colour.

### 5. A five-step type scale
- 32 title / 20 anchors and panel title / 15 node titles / 13 notes / 12 metadata and tags. Weights 700/600/400.
- **No truncation and no shrinking.** If a line ellipsises, rewrite it shorter and move the detail into the note or detail sheet.

### 6. Restrained layers
- Canvas → band → surface node, with a hairline border and a soft shadow. Dashed and muted nodes have no shadow. No cards inside cards, no decorative gradients.
- One accent colour, used for anchors, the start tag, focus and the eyebrow.

### 7. Honest content
- Every name, step, count and claim comes from the source material. No invented metrics, users, logos or links.
- Mark unknowns visibly: `[target - to be confirmed]`, `[copy - to be written]`, or a `muted` kind labelled Planned or Placeholder.

### 8. Clickable and accessible
- Nodes are real links (`<a>`) or buttons (detail sheet) with descriptive `aria-label`s. Keyboard order follows reading order, and the focus ring is visible.
- The detail sheet is a modal `<dialog>`. Esc, the close button and a backdrop click all close it.
- Text contrast is at least 4.5:1 in every theme, and transitions are removed under reduced motion.

### 9. Themes are routes
- `#/light`, `#/dark`, `#/hc` and `#/system` preview the canvas. Append `/export` to hide the controls and use `exportFoot`, which is what the PNG export does.

### 10. Two creative touches, not features
- Add small, subject-specific details that carry meaning: a mark echoing the subject's brand, a start tag in the domain's language, an icon that tells a story. Report them under **Creative touches**.

## Budget

| Item | Max |
|---|---|
| Lanes / columns | 4 / 5 |
| Target rows per lane / in total | 4 / 12 |
| Nodes per column | 5 |
| In-place items per main node | 6 |
| Chain depth | 2 hops |
| Note | 2 lines (about 110 characters) |

When the footer warns *Over the canvas budget*, cut content or split it into two infographics. Never edit `app.js` or reduce sizes to make things fit.

## Quality bar (check every exported image)

- [ ] The question is clear from the title and subtitle alone. The legend fits on one line and matches the boxes.
- [ ] No ellipsis, overlap, wrapped rail label or clipped text anywhere.
- [ ] Rail arrows are horizontal, bus arrows end exactly at node edges, and every arrowhead is visible.
- [ ] Shared left edges hold within each lane or column. Bands are balanced, with no large empty band beside a crowded one.
- [ ] Light, Dark and High contrast all read clearly, and connectors stay visible in Dark.
- [ ] Every node opens something useful (page, document, image or detail sheet). Tab order works and the focus ring shows.
- [ ] Exported PNGs are 1920x1080 with no theme control visible. Placeholders are visibly marked.

## Uplift menu (pick at most three small, visible fixes)

Type hierarchy · alignment within elements · composition gaps · layer separation · focus or highlight borders · purposeful icons · one subject-specific detail · token refinement · dark appearance · meaning without colour. If nothing worthwhile remains, stop.

## Anti-patterns

- A box for every concept, diagonal arrows, or arrows to in-place actions. Use lanes or columns, buses, and `items`.
- Colour-only categories, faint connectors, emoji icons, or mixed icon families.
- Shrinking text, or growing the canvas, to fit more. Split instead.
- Generic marketing copy, invented numbers, or links to files that don't exist.
- External fonts, CDNs, trackers, `eval`, or editing the engine for a one-off tweak.
