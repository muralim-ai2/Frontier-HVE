---
name: ui-anti-slop
description: Spot and fix AI slop in UI - generic gradients, emoji icons, fake metrics, lorem copy, uneven spacing - and replace it with honest placeholders and one coherent design system.
---

# UI anti-slop

Check every generated screen for these tells before showing it to the user.

| Tell | Fix |
|---|---|
| Purple-to-blue gradients, glassmorphism and glow on everything | One brand color plus neutrals; effects only where they carry meaning |
| Emoji used as icons | One icon set (for example Lucide) at consistent size and stroke |
| Invented numbers ("10,000+ happy users", "99.9% uptime") | Remove, or an honest placeholder: `[metric - to be confirmed]` |
| Lorem ipsum or generic hero copy ("Unlock your potential") | Real copy from the feature description, or `[copy - to be written]` |
| Random spacing, radii and font sizes | A scale: spacing 4/8/12/16/24/32, two radii, a type scale of at most 5 sizes |
| Every section a card in a centered column | Layout chosen for the content: tables for data, lists for items |
| Fake logos, testimonials and avatars | Remove; never imply endorsements that do not exist |
| Decorative animation on load | Motion only for feedback and state changes; respect reduced motion |

Steps:
1. Define or reuse the design tokens (colors, spacing, type, radii) in one file; every component uses them.
2. Walk each screen against the table and fix each tell; list what you changed.
3. Placeholders must be visibly placeholders, so nobody ships them by mistake.
4. Take a screenshot after the fixes for the feature's evidence.
