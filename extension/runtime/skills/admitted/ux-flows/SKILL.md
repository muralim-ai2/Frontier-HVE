---
name: ux-flows
description: Design UI user flows, screens and states before code - primary task path, empty, loading and error states, responsive layout and accessible defaults.
---

# UX flows

Use before building any screen. Output goes into the feature descriptions, not a separate document.

1. **Users and task**: name the primary user and the one task the screen must make easy. Everything else is secondary.
2. **Flow**: list the steps of that task as screen -> action -> result, at most 7 steps. Remove any step that does not move the user forward.
3. **States per screen**: for each screen define what the user sees when it is empty (first use), loading, in error, partially filled and complete. Missing states are the most common UI defect.
4. **Layout**: one primary action per screen, visually dominant; secondary actions quieter. Group related fields. Mobile first: a single column at 360 px, then widen.
5. **Defaults**: semantic HTML elements (button, nav, main, label), visible focus, text contrast at least 4.5:1, touch targets at least 44 px, no information carried by color alone.
6. **Feedback**: every action gives a visible response within 100 ms (pressed state, spinner, toast); destructive actions ask for confirmation or offer undo.
7. **Turn into checks**: each state from step 3 becomes something a feature check can assert (a test renders the empty state, the error message appears on a failed request).

Keep the flow small: if the task needs more than one primary screen, split it into features.
