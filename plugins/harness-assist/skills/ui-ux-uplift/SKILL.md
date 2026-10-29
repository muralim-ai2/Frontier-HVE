---
name: ui-ux-uplift
description: "UI and UX quality bar for every app screen, prototype, deck and document a user sees: alignment, adaptive navigation, type tokens, surfaces and depth, theme modes, contrast and layering, white space and icons. Apply while building and self-check once."
---

# UI/UX uplift

This guide outlines the core competencies and architecture principles required to uplift legacy interfaces, translate design tokens, and build highly adaptive applications across **Web**, **iOS**, **Android**, and **Desktop** platforms. It balances Google's **Material Design 3 (M3)** logic with Apple's **Human Interface Guidelines (HIG)**.

**Order of priority:**
1. **The brief wins.** An explicit requirement, such as a phone frame, light theme only, a fixed geometry or a time limit, overrides any default in this guide.
2. **Readability and accessibility come next.** No other rule may reduce legibility, contrast, hit-target size or keyboard and screen-reader access.
3. **Within those limits, alignment comes first** (Section 0). It is followed by layering and contrast (Sections 6–7), then white space and icons (Sections 8–9). All other sections build on these.

Treat the rules below as strong defaults, not absolutes. When you depart from one, do it on purpose and give the reason in one line.

---

## 0. Alignment Everywhere (the top principle)
### Skill Definition
Hold alignment to a very high standard at every level of the interface. Grids line up with each other. Elements line up within each grid. Text and icons line up within each element. Good alignment and layering are what make an interface legible and smooth. Misalignment is the fastest way to make a product feel unfinished. Alignment never overrides readability or accessibility. Never shrink text, clip content or reduce a hit target just to land on a line.

### The Four Levels of Alignment
1. **Between grids:** page columns, cards, sheets and bars all use the same outer margins (for example 16px on mobile and 24px or more on desktop). Content edges form one continuous vertical line from the top bar to the bottom bar.
2. **Within a grid:** sibling elements use the same gutter and share baselines, top edges or centers. Never mix these anchors in one row. Rows that repeat have the same height.
3. **Within an element:** padding is the same on every side unless an optical correction is needed. Icon-and-label pairs are centered vertically on the text's x-height, not on its line box. Leading icons in a list share one column, and their labels share another.
4. **Within text:** headings, body text and metadata share a left edge. Numbers use tabular figures (`font-variant-numeric: tabular-nums`) so columns of counts line up. Truncated text is cut at the same edge across siblings.

### Rules
* **One spacing scale, as a design aid.** Use a 4px base (4, 8, 12, 16, 24, 32, 48, 64) for gaps, padding and margins by default. The scale is a tool, not a law. Required geometry keeps its true values: a hexagon's height is width × 2/√3, an aspect ratio is exact, and a hairline is 0.5px. Never distort a shape or required layout to round to the scale.
* **One baseline grid.** Body line-heights are multiples of 4px, so mixed text blocks keep a shared rhythm.
* **Optical alignment.** Mathematical centering is only the starting point. Nudge play triangles, chevrons and rounded glyphs so they *look* centered. Hang punctuation and bullets outside the text edge.
* **Fixed icon boxes.** Every icon sits in a square box of the same size (for example a 24px glyph in a 40px or 44px hit target). That way, rows of icons align on their centers even when the glyphs have different visual weights.
* **Edge consistency.** Inside a container, an image, a divider or a button either runs full-bleed or sits on the content inset. Never stop it at an arbitrary in-between offset.
* **Hairlines on the pixel grid.** Borders (0.5px or 1px) land on whole or half pixels so they don't blur.

### Implementation Checklist
- [ ] Overlay a column and baseline grid on every screen and confirm each edge snaps to it.
- [ ] Check every row of icons and labels at 200% zoom for vertical centering.
- [ ] Confirm the left edges of the top bar title, content, cards and list text form one line.
- [ ] Confirm that numbers in stats, tables and counters use tabular figures and are right- or center-aligned consistently.
- [ ] Review spacing values that are not on the 4px scale, and keep only those that are required geometry or optical corrections.
- [ ] Compare sibling components (cards, tiles, chips) for identical padding, radius and height.

---

## 1. Adaptive Navigation Architecture
### Skill Definition
The ability to restructure an application's information architecture (IA) dynamically based on viewport size, platform ergonomics, and hardware inputs.

### Core Principles
* **Android / Mobile Web:** Utilize top app bars, search anchors, and persistent or modal navigation drawers (hamburger menus).
* **iOS / Mobile Web:** Implement a bottom tab bar (`UITabBar` equivalent) limited to 3–5 high-priority destinations. Contextual or secondary actions live in the top navigation bar.
* **Responsive Desktop / Web:** Refactor bottom tabs or drawers into a sticky left-hand navigation rail or a fully expanded sidebar layout. *Exception:* when the brief requires a phone frame or a mobile-only experience, keep the mobile navigation at every viewport size. Never convert it to a desktop sidebar.

### Implementation Checklist
- [ ] Map high-level views to a platform-conditional navigation wrapper.
- [ ] Strip Floating Action Buttons (FAB) when rendering on iOS platforms, embedding them instead as a prominent header action.
- [ ] Incorporate safe-area insets dynamically to clear physical hardware obstacles like display notches, dynamic islands, and home indicator bars.

---

## 2. Design Token Translation & Cross-Platform Typography
### Skill Definition
Establishing a centralized, platform-agnostic design token pipeline (JSON/W3C format) that maps primitive values to platform-specific system defaults.

### Core Typography Matrix

| Metric / Attribute | Material Design 3 (Android/Web) | Human Interface Guidelines (iOS) | Desktop Web Standard |
| :--- | :--- | :--- | :--- |
| **System Font Stack** | Roboto, Google Sans | SF Pro (Text/Display), New York | Inter, Segoe UI, system-ui |
| **Heading Casing** | Sentence case or Sentence case | Title Case | Mixed / Brand dependent |
| **Button Casing** | Title Case / Sentence Case | Title Case | Sentence Case |
| **Base Scale (Body)** | 16px / 1rem | 17pt (Dynamic Type Baseline) | 16px / 1rem |
| **Letter Spacing** | Tracking varies by scale (looser) | Tightened for Display scales | Standard tracking |

### Implementation Checklist
- [ ] Separate token values into global primitives (`color-blue-500`) and semantic aliases (`sys-color-primary`).
- [ ] Utilize system font stacks over heavy web-font files to ensure zero-layout shift during platform loading.
- [ ] Enforce accessible contrast ratios: WCAG AA at minimum, and AAA for primary body text, in every theme the brief ships.

---

## 3. Surface, Depth, and Materiality
### Skill Definition
Engineering spatial relationships and visual hierarchy on flat screens using realistic physics, lighting models, and material characteristics peculiar to each operating system.

```
[Material Design 3 Layering]            [Apple HIG Layering]
┌───────────────────────────┐         ┌───────────────────────────┐
│     Z-Index Elevation     │         │ Visual Effects Materials  │
│  (Drop Shadows & Shading) │    VS   │ (Translucency & Blurring) │
│       Card Layers         │         │     Vibrancy Layers       │
└───────────────────────────┘         └───────────────────────────┘
```

### Technical Approaches
* **The Material Model:** Relies heavily on surface color shifts and distinct shadow profiles to communicate elevation levels (0dp to 5dp).
* **The Apple HIG Model:** Leans on **translucency, background blurring, and material vibrancy**. Surfaces do not float; they sit on top of each other separated by ultra-thin borders (`0.5pt`) or distinct spatial fills.

---

## 4. Micro-interactions, Gestures & Physics Engine Controls
### Skill Definition
Designing and implementing fluid, interactive states that react seamlessly to user touch, mouse, or trackpad gestures while respecting platform-native kinetic behaviors.

### Interaction Models
* **Kinetic Physics:** Use platform-specific interpolation curves. Material uses fast acceleration with gradual easing (Standard Easing). iOS demands spring physics engines with customizable damping ratios (`bounciness`).
* **Gesture Mapping:**
  * **Swipe-to-Dismiss / Edge Swipe:** Treat edge-swiping as a destructive modal dismiss or a structural back navigation on iOS, matching system behaviors.
  * **Context Menus:** Support desktop right-click, Android long-press overlays, and iOS haptic context menus seamlessly on a single web element.
* **Haptics Pipeline:** Trigger subtle tactile feedback cycles matching user behaviors—sharp ticks for picker wheels and heavy double-pulses for validation failures.

---

## 5. Component Translation Mapping
When migrating architectures or standardizing cross-platform codebases, utilize this strict pattern mapping guide:

| General Intent | Material Design 3 Component | Apple HIG Component | Web / Desktop Component |
| :--- | :--- | :--- | :--- |
| **Primary Action** | Floating Action Button (FAB) | Top Navigation Right Bar Button | Fixed Action Header / Button |
| **Content Container** | Elevated Card | Grouped Inset Row / Platter | Box Container |
| **Binary Toggle** | M3 Switch | UIKit Switch | Custom CSS Toggle Track |
| **Multi-option Choice**| Segmented Button | Segmented Control | Tabbed Radio Group |
| **Contextual Menu** | Dropdown Menu / Bottom Sheet | Context Menu / Action Sheet | Custom Floating Popover |

---

## 6. Theme Modes
### Skill Definition
Build colors as a theme system, not a hard-coded palette. The default is **Light**, with **Dark** and **High Contrast** recommended. They follow the system setting and the user can override them. **When the brief says light only, extra themes are not mandatory.** Light must be complete and polished on its own and must be what loads by default. Other modes are optional and opt-in. Never remove a mode the user has already asked for or accepted, unless they explicitly say to.

### Rules
* Components read only semantic tokens (`--sys-surface`, `--sys-on-surface`, `--sys-primary`). Each mode swaps primitives behind the same semantic names. Components never contain mode-specific colors.
* When more than one mode ships, respect `prefers-color-scheme` and `prefers-contrast`. Persist the user's choice and apply it before first paint so the theme doesn't flash.
* Dark mode is not inverted light mode. Use near-black surfaces (for example `#0f1115`), raise elevated layers by making them lighter, and lower the saturation of accent colors.
* High Contrast mode removes translucency and blur, thickens hairlines to 1.5–2px and moves text to the strongest available contrast pair.
* Animate theme switches with a short cross-fade of 150–200ms. Never animate every color property separately.

### Implementation Checklist
- [ ] Confirm which modes the brief allows before building any of them.
- [ ] Define a token set for each shipped mode, all sharing the same semantic names.
- [ ] If more than one mode ships, make the switcher reachable in two taps and show which mode is active.
- [ ] Screenshot every built screen in every shipped mode before sign-off.

---

## 7. Color Palette, Contrast and Layering
### Skill Definition
Choose a clean, restrained palette whose contrast is deliberate, so that each layer (background, surface, elevated surface, overlay) is clearly separate from the next.

### Palette Structure
| Role | Count | Guidance |
| :--- | :--- | :--- |
| **Neutrals** | 8–10 steps | Carry roughly 90% of the UI: background, surfaces, borders and text. Tint them slightly toward the brand hue so they don't look dull. |
| **Primary accent** | 1 hue, 5 steps | Use it for the main action, selection and links only. Never use it for decoration. |
| **Secondary accent** | 0–1 hue | Optional. Use it for a single brand moment, such as a story ring or a highlight. |
| **Semantic** | 4 hues | Success, warning, danger and info. Use them only for meaning. |

### Layering Ladder (Light mode)
1. **Canvas:** pure white `#ffffff`.
2. **Grouped background:** `#f5f6f8`, used behind inset groups and sheets' grouped lists.
3. **Surface or card:** white, separated from the canvas by a 0.5–1px border (`#e4e6eb`) *or* a soft shadow. Never use both at full strength.
4. **Elevated or overlay:** white with a shadow at levels 2–3 and a scrim of `rgba(0,0,0,.4)` behind it.
5. **Selected or active:** a primary tint at 8–12% opacity, plus a 2px primary indicator.

### Rules
* The contrast between neighboring layers must be noticeable but quiet. Use a luminance step of at least 3–6% between canvas and surface, or a border.
* Text must meet WCAG AA at least: 4.5:1 for body text and 3:1 for large text and icons. Aim for AAA (7:1) on primary body text.
* Limit each screen to one accent color. Two accents fighting for attention break the hierarchy.
* Color never carries meaning alone. Pair it with an icon, a label or a change in weight.

---

## 8. Professional Use of White Space
### Skill Definition
Use white space as structure. It groups related things, separates unrelated things and gives the eye a place to rest.

### Rules
* **Proximity groups content:** the space inside a group is smaller than the space between groups, for example 8px inside and 24px between.
* **Generous outer margins:** at least 16px on mobile and 24–32px on desktop. Content never touches the edge of a container.
* **One idea per block:** separate sections with space first. Add a hairline divider only when space alone doesn't make the separation clear.
* **Breathing room around primary actions:** leave at least 16px of clear space around the main call to action.
* **Readable line length:** 45–75 characters for body text, with line-height between 1.4 and 1.6.
* Don't fill empty space with decoration. Leaving it empty is a deliberate choice.

---

## 9. Iconography
### Skill Definition
Icons are one family. They are drawn to the same grid, stroke and corner logic, and they are aligned as carefully as text.

### Rules
* **One family:** use one style (outline *or* filled), one stroke weight (1.5–2px at 24px) and one corner radius throughout. The filled variant is reserved for the selected or active state.
* **One grid:** use a 24px artboard with a 2px safe zone. Render at 16, 20, 24 or 28px only.
* **Pair icons with labels** wherever the meaning isn't universal. Space icons and labels 4–8px apart, centered vertically.
* **Use inline SVG** with `currentColor`, so icons inherit the theme in every mode. Never use emoji as UI icons.
* **Purposeful only:** every icon must help the user scan or recognize something. Remove icons that only decorate.
* **Hit targets:** at least 44×44pt on iOS and 48×48dp on Android, even when the glyph is 20–24px.

---

## 10. Presentation Surfaces (Decks, Reports, Showcases)
### Skill Definition
When the output is a presentation, a report or a design-review showcase, white is the background. A cleaner palette and exact alignment carry the quality.

### Rules
* **White background** (`#ffffff`) on every slide or page. Use color in accents, charts and a single highlight, not in full-bleed fills.
* **A clean palette:** neutral text (a near-black heading color, mid-grey supporting text), one primary accent and one optional secondary accent. Avoid gradients except for one deliberate brand moment.
* **One master grid** for every slide: the same margins, title position, column count and baseline. Titles never shift from one slide to the next.
* **Alignment everywhere:** text boxes, icons, images and charts snap to the grid. Icons line up with the first line of their text. Charts line up with the text columns.
* **Layering with restraint:** use thin borders, subtle tints or a single soft shadow to separate panels. Don't pile up boxes.
* **Purposeful icons:** use the same family as the product, at a consistent size, always with a label.
* **White space over density:** one message per slide, with large margins. If it doesn't fit, split the slide.

---

## 11. Creative Touches (two per build, required)
### Skill Definition
On every build, add **two small creative touches of your own** that lift the experience beyond the brief. An example is turning a generic like heart into a paw that fits the product. These are touches, not features. Each one refines something that already exists in a small way.

### What Qualifies
* **Creative visuals:** a smart-art arrangement, a fitting icon swap, or a small illustration in an empty state.
* **Better alignment or layering:** a detail that makes a block noticeably cleaner.
* **Better text:** clearer microcopy, friendlier wording or more useful labels.
* **A little helper:** a one-time hint, a coach mark or a gentle nudge that teaches a gesture.
* **Smoother motion:** smoother scrolling, such as tapping the active tab to glide to the top, or a calmer transition.
* **Eye-level placement:** key information or actions moved to where the eye and thumb already are.

### Guardrails
* Don't add a new screen, a new data model or a new flow. If it needs its own spec, it's a feature, not a touch.
* Never break a brief requirement, a test hook or accessibility. Respect `prefers-reduced-motion`.
* Keep each touch small enough to remove in one edit.

### Report It
Always name the creative part in the chat summary, under a **Creative touches** heading. For each touch, give one line on what it is and why it helps.

---

## 12. Final Design QA Gate
Before any screen, flow or deck is called done:
- [ ] **Brief first:** no default in this guide overrode an explicit brief requirement (phone frame, single theme, geometry).
- [ ] **Alignment:** every grid, element, icon and text edge snaps to the shared grid. Spacing uses the 4px scale except for required geometry (Section 0).
- [ ] **Readability and accessibility:** nothing was shrunk, clipped or made harder to reach for the sake of alignment.
- [ ] **Themes:** every mode the brief ships has a token set and has been checked (Section 6).
- [ ] **Palette and layers:** one accent per screen, clear layer separation, and WCAG AA contrast at minimum (Section 7).
- [ ] **White space:** spacing inside groups is smaller than spacing between them, and margins are generous (Section 8).
- [ ] **Icons:** one family, one stroke, on the grid, labeled where needed (Section 9).
- [ ] **Presentations:** white background, a clean palette, and one master grid (Section 10).
- [ ] **Creative touches:** two small touches have been added, and both are named in the chat summary (Section 11).

---

## 13. Verification and Design QA Tools
Maintain continuous quality assurance over the transformed interfaces using these specialized evaluation frameworks:
* Use the [W3C Design Tokens Framework](https://www.w3.org/community/design-tokens/) to maintain synchronization between Figma, Style Dictionary, and production build targets.
* Audit your layout semantics using Apple’s official [Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines/) paired alongside Google’s [Material Design 3 Documentation](https://m3.material.io/).