---
name: accessibility
description: Check UI against WCAG 2.2 AA with a POUR checklist - semantics, keyboard, focus, contrast, motion and labels - and verify with an automated axe run where possible.
---

# Accessibility (WCAG 2.2 AA)

Apply while building UI and again before a UI feature's check runs.

## Perceivable
- Text contrast at least 4.5:1 (3:1 for large text and UI component borders); never color alone to convey meaning.
- Every image has meaningful `alt` text, or `alt=""` when decorative. Icons that act as buttons have an accessible name.
- Content reflows at 320 px width and 200% zoom without horizontal scrolling.

## Operable
- Everything works with the keyboard alone, in a logical tab order; no keyboard traps.
- Focus is always visible and not hidden behind sticky headers.
- Respect `prefers-reduced-motion`: no auto-playing or parallax motion for those users.
- Targets are at least 24x24 CSS px; dragging has a single-pointer alternative.

## Understandable
- Every input has a visible `<label>`; errors name the field and how to fix it, next to the field.
- The page language is set; the same component behaves the same everywhere.

## Robust
- Use native elements before ARIA; when ARIA is needed, roles, states and names match behavior.
- Headings form an outline (one `h1`, no skipped levels); landmarks (`header`, `nav`, `main`, `footer`) are present.

## Verify
Add to the UI feature's check an automated audit (for example `@axe-core/playwright` against the running page) that fails on serious or critical violations, plus a keyboard-only walk through the primary flow. Automated tools find roughly a third of issues: offer the user a manual screen-reader or keyboard check.
