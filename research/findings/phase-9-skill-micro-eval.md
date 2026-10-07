# Phase 9 findings: micro paired evaluation of the skill library (2026-10-07)

Evidence: [skills/evals/](../../skills/evals) (one JSON per skill, with per-task scores, judge reasons and token deltas), [skills/registry.json](../../skills/registry.json), task suites in [tests/skill_tasks/](../../tests/skill_tasks), runner [tools/skills/micro_eval.py](../../tools/skills/micro_eval.py), gate [tools/skills/onboard.py](../../tools/skills/onboard.py). Decisions D-037, D-038. Model responses are cached in `.hve/evals/micro/` (git-ignored).

**Scope clarification (2026-10-07):** "all 13 skills" means the locally authored batch, not all 134 AgentX source skills. Ten were admitted and three rejected. The original notes do not establish exhaustive source selection or coverage of all relevant capabilities. See the [selection and coverage audit](phase-9-skill-selection-coverage.md) for verified counts, the documented selection method, visibility distinctions and unassessed candidates across the six requested areas.

## 1. Question

Does adding a skill to the agent's instructions make its answers measurably better, and at what token cost? A skill only earns a place in the library (and in the agent's context) if the answer is yes.

## 2. Test method: micro paired evaluation

**Why not full sessions.** The session-level method (`eval_skill.py`) runs the whole creator benchmark with and without the skill: about 4 runs of about 15 minutes per skill, 52 runs for 13 skills, and each run must be started by hand in a chat. Too slow and too costly for a library-wide check.

**Design.** A paired A/B test on small tasks, so each comparison isolates the skill:

1. **Tasks.** Each skill has 5 small, realistic tasks in its own area (for example: write the empty-state text for a page; design the REST endpoints for orders; scrub a diff that contains a hardcoded key and a debug print). Each task lists 3-4 checks: what a good answer must contain. Answers are capped at about 250 words, so a call takes seconds.
2. **Two conditions, one variable.** Every task is answered twice by the same model with the same settings and system prompt. The only difference: in the "with" condition the full SKILL.md text is appended to the system prompt ("Follow this skill: ..."). No tools, no conversation history: one call per answer ("single agent").
3. **Blind judge.** A second model receives the task, its checks and the two answers labelled only "A" and "B". Which one is the "with" answer is decided by a hash of the task id: effectively random, but reproducible, so a re-run hits the cache. The judge does not know a skill exists. It scores each answer 0-5 against the checks and overall usefulness, lists the checks met, and gives a one-sentence reason, as JSON.
4. **Unblinding.** The runner maps A/B back to with/without and computes, per task, `delta = score_with - score_without`.
5. **Metrics per skill.**
   - **Quality lift** = mean delta over the 5 tasks as a share of the 5-point scale, in percentage points (pp). Example: +1.4 mean = 28 pp.
   - **Wins / ties / losses** across the 5 tasks.
   - **Worst task** = the most negative delta.
   - **Token overhead** = mean extra prompt tokens (the skill text) plus mean extra answer tokens, divided by a typical creator call of 50,000 prompt tokens. In a 300-token micro prompt the skill would look like a 100%+ overhead; what matters is its share of a real agent call, where it is loaded.
6. **Gate (admission).** A skill is admitted when all hold: lift >= 10 pp; token overhead < 20%; wins plus ties >= 3 of 5; no task lost by more than 1 point. Otherwise it is rejected with the reasons in the registry; rejected skills stay in `skills/authored/` but are not loaded.

**Models (Azure AI Foundry, keyless Entra auth through the Azure CLI).**

| Role | Model | Settings | Why |
|---|---|---|---|
| Answers (both conditions) | `gpt-5.4-mini` | reasoning effort low, up to 1,200 completion tokens | Cheap and fast; the skill must help a small model |
| Judge | `gpt-5.2-chat` | up to 600 completion tokens | Non-reasoning, about 400-500 tokens per verdict |
| Tried, dropped | `Kimi-K2.6` | up to 2,000 tokens | Spent the whole budget thinking and returned empty content; the deployment rejects a switch to turn thinking off |

Both answers in a pair come from the same model, so the judge's own style preferences cannot favour either condition.

**Cost control.** Every request is cached by a hash of its full body, so re-runs, resumes and re-scoring cost nothing; an empty reply raises instead of being cached; the gate reads the saved evals, so changing the gate needs no new model calls.

## 3. Results

Full run: 13 skills, 130 answers and 65 judgements in 144 s, 117,890 tokens; about 140K including the pilot and the failed Kimi judge attempt.

Scores are with/without per task (0-5). Token columns are mean extra tokens per answer.

| Skill | Task scores (with/without) | Lift (pp) | W/T/L | Worst | +prompt | +answer | Result |
|---|---|---|---|---|---|---|---|
| dreams | 5/1 5/1 5/3 3/0 5/4 | 56 | 5/0/0 | +1 | 419 | -67 | admitted |
| analyst | 5/1 5/5 5/2 5/4 4/1 | 44 | 4/1/0 | 0 | 342 | 144 | admitted |
| scrub | 5/5 5/2 4/2 4/1 5/3 | 40 | 4/1/0 | 0 | 365 | 18 | admitted |
| build-approach | 5/2 5/4 5/5 5/4 5/3 | 28 | 4/1/0 | 0 | 373 | 34 | admitted |
| ux-flows | 4/3 5/4 4/2 5/3 5/4 | 28 | 5/0/0 | +1 | 345 | 22 | admitted |
| web-research | 5/2 5/4 5/2 5/5 5/5 | 28 | 3/2/0 | 0 | 336 | 24 | admitted |
| prose-anti-slop | 5/1 5/5 5/1 5/5 4/5 | 28 | 2/2/1 | -1 | 359 | 11 | admitted (ties count, see 4) |
| api-design | 5/4 5/3 5/5 5/5 5/4 | 16 | 3/2/0 | 0 | 396 | -4 | admitted |
| architecture-options | 5/4 5/5 4/3 5/4 4/4 | 12 | 3/2/0 | 0 | 365 | 121 | admitted |
| ui-anti-slop | 5/4 5/5 5/5 5/5 4/2 | 12 | 2/3/0 | 0 | 375 | -3 | admitted (ties count, see 4) |
| code-hygiene | 5/3 5/2 5/5 3/5 3/4 | 8 | 2/1/2 | -2 | 339 | -23 | rejected |
| ui-content | 3/5 5/5 5/3 4/5 4/2 | 4 | 2/1/2 | -2 | 358 | -36 | rejected |
| accessibility | 5/5 5/5 4/5 5/4 5/5 | 0 | 1/3/1 | -1 | 395 | -6 | rejected |

Token overhead per real creator call was 0.6-1.0% for every skill: each skill adds about 340-420 prompt tokens, and answer length barely changed.

## 4. Gate change after the first run (user decision)

The gate was first run with "wins >= 3 of 5". That rejected prose-anti-slop (28 pp, 2 wins, 2 ties, 1 loss by 1 point) and ui-anti-slop (12 pp, 2 wins, 3 ties, no loss). The user decided that a tie counts as a win, because a tie means the skill did no harm, and both skills had enough lift. The rule became "wins plus ties >= 3 of 5" and was re-applied to the saved evals with no new model calls. Result: 10 admitted, 3 rejected.

This change was made after seeing the results, which weakens the claim for those two skills: a re-run with fresh tasks would confirm or overturn it.

## 5. What it shows

- **Skills that add a procedure or format the model would not choose on its own help most.** `dreams` (lessons as structured JSON with evidence and counts), `analyst` (weighted criteria, arithmetic, sensitivity) and `scrub` (diff-only scope, report vs fix) took baselines from 0-2 to 4-5.
- **Skills that restate what the model already does well add little.** Accessibility, UI copy and code clean-up baselines already scored 4-5. That is a ceiling effect: the checks leave no room for the skill to show. These skills may still help in a full session, where the model juggles more at once; the micro test cannot show that.
- **A skill can hurt a specific task.** In `code-hygiene-4` the skill's "simplify" push led the answer to change the function's input from a dict to a number (with 3, without 5); in `ui-content-1` the answer with the skill broke the requested length limit. Losses like these are why the gate caps the worst task.
- **Overhead is small where it matters.** About 400 tokens per skill is under 1% of a typical agent call; the cost risk is loading many skills at once, which the loadout budget (10 skills, 2,000 tokens) controls.

## 6. Limits

- **Selection coverage is unproven.** The 13 authored candidates were a curated batch; no complete source-by-source triage/exclusion ledger was found. Passing candidates in every requested category does not establish exhaustive coverage of relevant AgentX skills. The [coverage audit](phase-9-skill-selection-coverage.md) lists follow-up candidates and the evidence needed.
- **5 tasks and one judge pass per skill.** A one-point swing on a single task moves the lift by 4 pp. Treat results near the thresholds as provisional.
- **Same author.** The agent that wrote the skills also wrote the tasks and checks, which can favour the skills. Independent tasks (from users or real sessions) are the stronger test.
- **Micro tasks are not sessions.** They test whether a skill improves one answer, not whether it improves a multi-step build.
- **Single judge model, no human calibration yet.** Phase 2 showed an AI judge can miss differences a human sees. A human spot-check of a few pairs per skill would calibrate it.
- **No position-swap pass.** Each pair was judged once in one A/B order; judging again with the order swapped would control position bias, for about 30K more tokens.

## 7. Next

Before claiming complete source coverage, inventory the pinned upstream tree and record a disposition for every source skill, then evaluate additional relevant candidates as described in the [coverage audit](phase-9-skill-selection-coverage.md). This is separate from improving the existing 13:

1. Human spot-check: 2 pairs per admitted skill, compared with the judge's scores.
2. Revise code-hygiene (protect the input contract), ui-content (respect length limits) and accessibility (aim at what the model misses: testing, screen-reader announcements), then re-run only those (`python tools/skills/micro_eval.py <skill>`; the cached without-skill answers cost nothing, only the new with-skill answers and judgements do).
3. Optional: a swapped-order judge pass and a second, independent task set for the two skills admitted under the tie rule.
