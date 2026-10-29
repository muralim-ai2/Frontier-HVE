# Skills

## Where skills live

| Kind | Location | Loaded |
|---|---|---|
| Plugin skills (`/check-context-load`, `/recommend-skills`, `delivery-coach`, ...) | `plugins/harness-assist/skills/`, shipped in the extension | Discoverable in every chat |
| Harness library | `skills/admitted/` with `skills/registry.json`, shipped in the runtime | Per task by `skill_loader` and the ask contract: every relevant skill is shortlisted, ranked by relevance. Over 10 skills or 32,000 tokens, the agent scores the shortlist 0-10 for the ask (`lifecycle.py skills score`), shows you the suggested top 10 with scores, and you pick suggested, all or named (`lifecycle.py skills`) |
| Workspace library | `.hve/skill-library/` with `.hve/skills-registry.json` | Per task, like the harness library |

Library skills are copied to `.hve/skills/` for the session that loads them; other library skills are blocked so they cannot leak into context.

## Pathways for adding a skill

Pick the pathway by who should get the skill and how much evidence you have. Every pathway runs the security and structure scan first (`tools/skills/scan.py`), and a skill loads only when one of its categories in `skills/categories.json` matches the task or its rare words match the request; a skill that matches no category is rejected.

| Pathway | For | How | Gate | Lands in | Loads |
|---|---|---|---|---|---|
| 1. Workspace, evaluated in chat | One project or team, no Azure needed | `HVE skill-evaluator` with the skill folder (below) | Scan, then blind with/without pairs: lift at least 10 points, token overhead under 20%, at most one task lost | `.hve/skill-library/<name>/`, `.hve/skills-registry.json` | Per task, like the harness library |
| 2. Workspace, evaluated on Foundry | As 1, faster and with a fixed model pair | `HVE skill-evaluator`, answer yes to Foundry (needs `AZURE_OPENAI_ENDPOINT` in `.env.local` and `az login`), or `python <tools>/skills/evaluate.py foundry <skill_dir>` after writing `tasks.json` | As 1 | As 1 | As 1 |
| 3. Harness library, provisional | Every user of the extension, small skills | `python tools/skills/onboard.py <skill_dir> "<source>" provisional`, then rebuild and release the extension | Scan, a category match, at most 800 tokens, description at most 200 characters, Python-only scripts | `skills/admitted/<name>/`, `skills/registry.json` (`provisional`) | Per task for agents whose floor is `provisional` (all working agents) |
| 4. Harness library, admitted | Every user, with measured lift | Micro paired evaluation to `skills/evals/<name>.json` (`tools/skills/micro_eval.py`), then `onboard.py <skill_dir> "<source>" eval` | Lift and overhead thresholds (`skills/categories.json` → `thresholds`) | As 3 (`admitted`) | Per task for every agent |
| 5. Bulk import from a repository | Many skills from one licensed source | `python tools/skills/import_eval.py untested <clone>` (copied verbatim with `LICENSE` and `NOTICE`, evaluation pending) or `import_eval.py eval <clone>` (strict: must win every task) | Scan and category; `eval` adds the strict gate | `skills/imported/` and `skills/admitted/` | As 3 or 4 |
| 6. Plugin skill | Workflow skills every chat should discover (`/recommend-skills`, `feature-checklist`) | Add `plugins/harness-assist/skills/<name>/SKILL.md`, rebuild | Scan (`tests/test_flow_plugin.py`); `check-context-load` for its always-on cost | Extension `skills/` | Always discoverable: its description costs tokens on every request |
| 7. Required by a lifecycle | Skills a team's way of working always needs | Name the skill in a stage's `skills` in `.hve/lifecycles/<name>.json` (workspace) or `plugins/<plugin>/lifecycles/` | The skill must already be in a library (pathways 1-5) | - | Required for that stage, ahead of ranked skills |

After any pathway, check it with `python <tools>/skills/recommend.py provisional "<a task it targets>"`: the skill should be listed with a reason. If it never shows up, its category does not match the tasks you expect; add or widen a category's `skill_pattern` and `task_pattern` in `skills/categories.json` (harness) and re-run the gate.

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

Ask `Frontier Lite` (or another agent with `skill_loader`) for a task the skill targets. The session's loadout is in `.hve/runs/<session>.skills.json`; `/recommend-skills` shows the ranking. `provenance.py <agent file> latest --require skills` ([Install](Install.md#check-that-it-works)) confirms the loader ran.

## Ship a skill in the harness library (maintainers)

`python tools/skills/onboard.py <skill_dir> <source label> provisional|eval|untested` admits a skill to `skills/admitted/` as `provisional` (static gate) or `admitted` (paired evaluation clears both thresholds) and updates `skills/registry.json`. Rebuild the extension to ship it. Method and past results: `research/findings/phase-9-skill-micro-eval.md`.
