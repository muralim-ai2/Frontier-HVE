# Skills

## Where skills live

| Kind | Location | Loaded |
|---|---|---|
| Plugin skills (`/check-context-load`, `/recommend-skills`, `delivery-coach`, ...) | `plugins/harness-assist/skills/`, shipped in the extension | Discoverable in every chat |
| Harness library | `skills/admitted/` with `skills/registry.json`, shipped in the runtime | Per task by `skill_loader`, within the loadout budget (10 skills, 2,000 tokens) |
| Workspace library | `.hve/skill-library/` with `.hve/skills-registry.json` | Per task, like the harness library |

Library skills are copied to `.hve/skills/` for the session that loads them; other library skills are blocked so they cannot leak into context.

## Onboard a skill with `HVE skill-evaluator`

Pick `HVE skill-evaluator` in a Local chat and give it the skill folder (the one holding `SKILL.md`). It runs `<tools>/skills/evaluate.py` through these steps:

| Step | What happens | You do |
|---|---|---|
| 1. Static check | Security and structure scan, overlap with existing skills, token cost per request and when loaded. Stops on any finding | Fix and retry if it stops |
| 2. Tasks | Writes 5 small tasks with 3-4 checks each to `.hve/evals/<name>/tasks.json` | Approve or edit them |
| 3. Paired answers | `HVE skill-worker` answers each task with and without the skill (or Foundry, if `.env.local` sets `AZURE_OPENAI_ENDPOINT` and you agree) | — |
| 4. Blind judging | `HVE skill-judge` scores each pair as anonymous A and B | — |
| 5. Record and admit | Admits when quality lift is at least 10 points, token overhead at most 20% and at most one task lost (`skills/categories.json` → `thresholds`); otherwise records the rejection with reasons | Read lift, wins/ties/losses, worst task |
| 6. Context load | Reports always-on tokens and warnings | Act on warnings |

Five tasks are a small sample, and in-chat answers come from the model you picked; treat the result as a gate, not a benchmark.

## Check the skill is used

Ask `HVE creator` (or another agent with `skill_loader`) for a task the skill targets. The session's loadout is in `.hve/runs/<session>.skills.json`; `/recommend-skills` shows the ranking. `provenance.py <agent file> latest --require skills` ([Install](Install.md#check-that-it-works)) confirms the loader ran.

## Ship a skill in the harness library (maintainers)

`python tools/skills/onboard.py <skill_dir> <source label> provisional|eval|untested` admits a skill to `skills/admitted/` as `provisional` (static gate) or `admitted` (paired evaluation clears both thresholds) and updates `skills/registry.json`. Rebuild the extension to ship it. Method and past results: `research/findings/phase-9-skill-micro-eval.md`.
