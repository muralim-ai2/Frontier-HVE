---
name: ui-content
description: Write UI copy for usability - labels, buttons, empty states, errors, confirmations and onboarding - in clear, short, inclusive wording that tells users what to do next.
---

# UI content

1. **Buttons say the action and object**: "Save palette", not "Submit" or "OK". Keep the same verb through the flow (Save, then "Saved").
2. **Labels are nouns, hints are examples**: label "Email", hint "name@company.com". Never use the placeholder as the only label.
3. **Empty states** answer three things: what this area is for, why it is empty, and the one action to fill it ("No palettes yet. Generate your first palette.").
4. **Errors** say what happened, in the user's terms, and how to fix it: "That email is missing an @." Never blame the user, never show raw codes or stack traces, never say only "Something went wrong" when the cause is known.
5. **Confirmations** for destructive actions name the object and the consequence: "Delete 'Spring' palette? This cannot be undone." Offer undo instead where possible.
6. **Length budget**: button 1-3 words, label up to 4, error and empty-state text up to 2 short sentences. Front-load the important word.
7. **Tone**: plain, calm, direct; sentence case; no exclamation marks in errors; no jargon or internal names; inclusive and gender-neutral.
8. **Numbers and dates** in the user's locale; units always shown.

Review every string on a screen together: inconsistent verbs and tone across screens confuse users more than any single weak string.
