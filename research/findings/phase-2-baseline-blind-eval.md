# Phase 2 findings: baseline run and blind evaluation (2026-10-06)

Evidence: `research/runs/<session_id>.jsonl` and `.run.json` (hooks and Copilot OTel, not model write-ups), `research/blind/round-20261006T193232Z/` (screenshots, `scores.json`, `key.json`), `research/comparisons/comparison.json`. One run per mode (baseline, D-011), 10-minute budget (D-018).

## 1. Result

| rank | mode | model | runs | human_score | ai_score | prompt_tokens | completion_tokens | cache_ratio | cost_aiu | model_calls | tool_calls | subagent_calls | wall_clock_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | harness (creator) | gpt-5.6-sol | 1 | 3.8 | 4 | 584,919 | 14,735 | 0.93 | 73.1 | 17 | 16 | 0 | 1,014 |
| 2 | single | claude-opus-5.5 | 1 | 2.9 | 4 | 645,314 | 32,454 | 1.0* | 110.8 | 13 | 36 | 0 | 482 |
| 3 | minimal | gpt-6-astra | 1 | 0 | 1 | 13,718 | 11,843 | 0.0 | 76.4 | 1 | 0 | 0 | 224 |

\* `cache_ratio` counts cache reads plus cache writes, so it overstates the hit rate for Claude; to be fixed in `compare.py`.

Sessions: creator `fcd288c9`, single `6a754bb3`, minimal `392cc6ec`. Blind labels: A = minimal, B = creator, C = single (revealed after human scoring).

## 2. What it shows

- **The harness run scored highest with humans and cost the least.** creator (GPT-5.6 Sol) scored 3.8 vs single (Claude Opus 5.5) 2.9, at 73.1 vs 110.8 AI units (34% less). It used 9% fewer prompt tokens and 55% fewer completion tokens. This is preliminary support for H1 and for the claim that a cheaper model in a better harness can beat a more expensive model in a simpler setup.
- **minimal produced code that does not build.** Its own `globals.css` has an unclosed `@media` block; our extraction copied the reply verbatim. Human 0, AI 1. This supports H2: no tools means no feedback loop, so syntax errors ship.
- **The AI judge did not separate creator from single (4 vs 4); the human did (3.8 vs 2.9).** A screenshot-only judge cannot see behavior (copy, lock, save), and it missed sections below the fold. Human scores stay the primary quality signal; the AI judge needs calibration against human scores before it can rank close runs (see §4, judge alignment).

### Why this is not yet proof
- **n = 1 per mode.** Run-to-run variance in agent output is large; a 0.9-point gap on one run is not significant. The plan calls for 3+ runs per mode before claiming a winner.
- **Model and harness are confounded (D-003).** Each mode uses a different model family, so the gap mixes harness effect with model effect. A same-model ablation (single vs creator on one model) is needed to attribute the gain to the harness.
- **creator did not use its sub-agents (0 sub-agent calls).** The harness features that were active: explicit tool list, Graphify (1 query), profile, compaction and budget hooks, and the creator instructions. The sub-agent part of H1 is untested.
- **creator ran past its budget.** Its Stop hook fired at 12.2 min. A background terminal command then finished, Copilot injected a terminal-notification turn, and creator kept working until a second Stop at 16.9 min. The budget hook can only block new tool calls; it cannot end a running command or an injected turn. Its final `npm test` exited 1. single finished in 8.0 min within budget.
- **Scale use.** The human score for minimal is 0, outside the rubric's 1–5 scale. Treat it as "does not build".

## 3. Method used (blind protocol)

1. Same prompt for every mode (`tests/prompts/color-palette.md`, sha256 recorded in each `.run.json`), one new Local chat per run, metrics from hooks and OTel.
2. `tools/observe/blind.py prepare` shuffled the collected runs behind random labels (A–C) with `secrets.SystemRandom`; `key.json` (operator only) holds the mapping.
3. Each app was served with `next dev` and captured as full-page screenshots, desktop (1440 px) and mobile (390 px), into neutral `A/`, `B/`, `C/` folders.
4. Human scored 1–5 per label from screenshots against `tests/prompts/color-palette.rubric.json` (15 spec checks), before reading the AI fields.
5. AI judge: Claude Sonnet 5.5, a model family different from all three runs, screenshots plus rubric only, no access to the key or code. Per-check pass/fail/unknown plus a 1–5 score.
6. `tools/observe/compare.py` joins scores through the key and ranks Quality (human, then AI) > Tokens > Latency > Cache.

**Leaks found in this round:**
- **App branding is not neutral.** Some apps named themselves (for example "Chromakit").
- **Folder names leaked mode.** Dev-server terminals ran inside `tests/outputs/<mode>/` paths.
- **Screenshots are static.** They hide behavior, so interactive features were judged on presence only.

## 4. Human blind testing in harness engineering (background)

Summary of the user's notes:
- **Purpose.** A human blind test measures whether a harness change (prompts, tools, hooks, feedback loops) really improved an agent, without the evaluator knowing which variant produced which output. It guards against confirmation bias, which is easy to fall into because agent output is non-deterministic and developers want their change to win.
- **Protocol.**
  - Two or more system variants get identical tasks.
  - Outputs (code, traces, responses) are stripped of identifying metadata.
  - Expert humans grade them on correctness, safety, and efficiency, or pick the better one.
- **Benefits.**
  - Separates real harness value from lucky runs.
  - Quantifies the claim that a smaller, cheaper model in a strong harness can beat a larger model in a weak one.
  - Calibrates LLM-as-judge pipelines against human standards.

### Key reference: TaoLive "Training Agents to Evolve with Their Harness" (arXiv 2608.15763v2)
An industrial report on a live-commerce avatar agent with an evolvable harness (Skills, Hooks, prompt pipeline, tool registry). Relevant evaluation practice:

- **Human blind test (§5.6).** 100 real requests, stratified by scenario with a fixed random seed. Both systems ran on the same input; outputs were randomly assigned to "Model A"/"Model B" with identity hidden.
  - **Labels:** Harness better / ReAct better / tie. Every non-tie needed a short written reason, and all 100 labels were reviewed for consistency afterwards.
  - **Result:** harness 35, tie 64, ReAct 1. That is a 97.2% non-tie win rate, with a two-sided binomial test p < 0.001.
  - **Attribution:** wins were categorized from the rationales — input understanding 34%, output reliability 23%, scenario behavior 23%, response quality 14%, tool use 6%.
- **Judge calibration (App. C.3, D.1).** The automatic judge is a 3-model majority-vote panel calibrated against 482 human-labeled items. Accuracy agreement rose from 81.5% to 90.5% as the judge's rubric and tools were revised. Judge roles are kept independent: the RL reward judge shares no model with the evaluation panel.
- **Harness evolution has diminishing and negative returns (App. C.2).**
  - Evolution 2 was the best checkpoint.
  - Adding more long-tail rules in Evolutions 3–4 regressed both accuracy and effectiveness, so they stopped early.
  - This matches our anti-bloat rules.
- **Same harness edits help a harness-aware model more (§5.5).** On a held-out set, identical harness edits cut detected errors by 51.7% for the harness-aware model vs 18.1% for a fixed-harness fine-tune.

### What we should adopt
1. **Pairwise preference with ties and required reasons**, not only 1–5 scores. It is easier for raters and supports a binomial test.
2. **Many more cases, stratified.** The one-task, one-run setup above cannot reach significance.
3. **Randomized A/B position per item** and a consistency review pass.
4. **Calibrate the AI judge on human-labeled items** before using it to rank. Keep judge models disjoint from the models under test, and consider a multi-model panel.
5. **Attribute wins from rater rationales.** Tell us which harness feature mattered.

## 5. Open: blind testing interactive apps (to research)

Screenshots are not enough for apps whose quality is in behavior (for example a Minecraft-style game, or the palette app's lock, copy and save flows). Ideas to research before Phase 9/10 evaluations:

- **Neutral delivery.** Build each app into an anonymized folder (`run-7f3a/`) with neutral package names and window titles. Serve on random ports from a launcher the rater uses, so terminal paths, branding, and generated `AGENTS.md`/`CLAUDE.md` files never show mode.
- **Scripted task walkthroughs.** Give raters a fixed task script (for example "generate, lock card 2, regenerate, export Tailwind, save, reload"), or record Playwright videos of the same script per app, so behavior is compared under identical steps.
- **Pairwise sessions** (A vs B side by side, randomized position) with tie allowed and a reason required, as in the TaoLive protocol.
- **Multiple raters and agreement.** Report inter-rater agreement (Cohen's or Fleiss' kappa) and use it to calibrate the AI judge.
- **Hybrid scoring.** Automatic functional checks (does it build, do tests pass, does each scripted step succeed) for objective items; humans for experience and polish.
