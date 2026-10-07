---
name: dreams
description: Dreams - self-learning between sessions. Consolidate interventions, escalations, failed checks and manual-check results into lessons learned in .hve/learnings.json, then apply them next time.
---

# Dreams

Run at the end of a delivery session, or when the user asks what went wrong or what was learned. Read only; the single file you write is `.hve/learnings.json`.

## Gather (from the workspace)
- `.hve/runs/*.interventions.jsonl`: hook denials, victory checks, budget and guard events.
- `.hve/blindspots/`: blindspot-coded interventions.
- `.harness/attempts/*.jsonl`: failed checks, the rule that fired (R0-R7) and escalations.
- `tracker.json`: features with many attempts, and manual checks marked `needs changes`.
- `progress.txt`: what passed and how many attempts it took.

## Consolidate
Group repeated events into patterns. A lesson needs at least two occurrences or one escalation. For each, write:
`{"lesson": "<one sentence rule to follow next time>", "kind": "pitfall" | "convention" | "environment", "evidence": ["<file>:<line or id>", ...], "seen": <count>, "last_seen": "<date>"}`

Examples of good lessons: "Start the dev server on a free port before the screenshot step; port 3000 is often taken." "This project's tests need `npm ci` first."

## Write
Merge into `.hve/learnings.json` (`{"lessons": [...]}`): update `seen` and `last_seen` for existing lessons, add new ones, and drop lessons not seen in the last 20 sessions. Keep at most 30 lessons, most frequent first.

## Apply
At the start of the next task, read `.hve/learnings.json` and follow the lessons that match the task. Never store secrets, personal data or the user's prompts verbatim.
