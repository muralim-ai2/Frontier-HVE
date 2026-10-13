# Harness Evaluation Layer

## How to prove that an AI harness improves outcomes

A practical, plain-language framework for comparing a **baseline AI system** with a **specialized harness**.

### Evaluation pillars

| Pillar | Recommended weight |
|---|---:|
| Quality | **40%** |
| Reliability | **30%** |
| Cost per successful task | **20%** |
| Token efficiency | **5%** |
| Latency | **5%** |

> **Central idea:** Do not ask only, “Did the harness create a better-looking answer?” Ask whether it creates a **correct, repeatable and policy-compliant outcome**, for different user levels, at an acceptable cost.

---

# 1. What is an AI harness?

An AI model generates responses. A **harness** is the engineered system around the model that controls how the work is performed.

### The model

Interprets the request, reasons about the task, and generates content or decisions.

### The harness

Supplies instructions, knowledge, tools, memory, controls, verification and stopping conditions.

### Baseline harness

A typical baseline may include:

- Agent or persona
- Reusable skills
- Minimal hooks
- Tool connections such as MCPs
- Plugins

### Specialized harness

A specialized harness can add:

- Domain-specific templates
- Curated skills and tools
- Skill evaluation
- Deterministic hooks
- Verification loops
- Model routing
- Business-domain skills
- Evaluation outputs
- Graph or multi-agent orchestration
- Context management
- Memory management
- Self-learning or multi-turn adaptation as a stretch capability

## Why evaluation must isolate the harness

A fair evaluation keeps the **task, model and budget stable**, then changes the harness. Otherwise, an apparent improvement may come from a stronger model, a different task, more time or additional retries.

> **Evaluation question:** With the same model and the same task, does the specialized harness produce better and more dependable business outcomes than the baseline harness?

### What success looks like

- Higher-quality outcomes, especially for novice users.
- Fewer invalid, incomplete or non-compliant results.
- Lower cost per **successful** task, not merely lower cost per attempt.
- Stable token usage and acceptable response time.
- Evidence showing which harness components caused the uplift.

---

# 2. The six-layer evaluation framework

The framework separates test design, evidence collection, scoring and decision-making.

| Layer | Purpose |
|---|---|
| **6. Decision and uplift** | Release decision, overall uplift, regression checks and feature attribution. |
| **5. Human and AI judgement** | Blind comparison, rubric scoring and calibration of automated judges. |
| **4. Pillar scorecard** | Quality, reliability, cost per successful task, token efficiency and latency. |
| **3. Evidence and telemetry** | Tests, traces, hooks, tool calls, token usage, costs, time and memory events. |
| **2. Controlled experiments** | Same task and model, repeated runs, user-level variants and component ablations. |
| **1. Evaluation foundation** | Versioned tasks, datasets, rubrics, accepted baselines and reports. |

## How the layers work together

1. Tasks and rubrics define what will be tested.
2. Controlled experiments create comparable runs.
3. Telemetry captures objective evidence.
4. Pillar metrics translate the evidence into scores.
5. Humans and calibrated automated judges assess aspects that cannot be reduced to deterministic tests.
6. The decision layer determines whether the specialized harness should be promoted.

---

# 3. Layer 1: Evaluation foundation

The foundation is a version-controlled evaluation package. It makes results **reviewable, repeatable and comparable across releases**.

## Evaluation contract

Defines:

- Task
- Model
- Harness configuration
- Budgets
- Number of runs
- Required checks
- Scoring rules

## Task datasets

Maintain separate collections for:

- Benchmark scenarios
- Regression scenarios
- Adversarial or edge cases
- User-level parity cases

## Rubrics

Define:

- What “good” looks like
- How failures are classified
- How human reviewers score outputs
- How automated judges score outputs

## Accepted baseline

Store the most recently approved results and thresholds for regression comparison.

A baseline should be updated only after review.

## Evidence reports

Preserve:

- Run-level traces
- Task-level summaries
- Pillar scorecards
- Uplift reports

## Minimum information for every evaluation case

| Field | What to capture |
|---|---|
| Task | Input, expected outcome and business scenario. |
| User level | Novice, intermediate or expert formulation. |
| Controls | Required tools, skills, hooks, templates and mandatory steps. |
| Assertions | Functional tests and pass/fail conditions. |
| Budgets | Token, cost, time and retry limits. |
| Repetition | Number of independent runs and randomisation settings. |
| Scoring | Quality rubric, reliability rules and judge protocol. |

---

# 4. Layer 2: Controlled experiments

A controlled experiment should answer **one question at a time**. The primary comparison changes only the harness.

## Recommended experiment variants

| Variant | Purpose |
|---|---|
| **Baseline** | The standard harness currently in use. |
| **Specialized harness** | The full set of domain templates, curated skills, controls and verification. |
| **Incremental build-up** | Add skills, hooks, loop, context, memory and routing one step at a time. |
| **Ablation** | Remove one feature from the full harness to determine how much that feature contributes. |
| **User-level parity** | Run equivalent novice, intermediate and expert prompts for the same underlying task. |
| **Robustness** | Run regression, edge, adversarial and tool-failure cases. |

## Core experimental rules

1. **Pin the same model** and model settings for baseline and harness arms.
2. Use the same tasks, budgets, tools and success criteria.
3. Run each task multiple times to expose variation and lucky successes.
4. Randomise run order.
5. Blind human reviewers to which system produced each output.
6. Record failed attempts rather than excluding them from cost calculations.
7. Use ablation testing to explain why the complete harness won or lost.

### Suggested starting point

Use a representative task set that includes novice and expert formulations and multiple independent runs per task. Increase the sample when the decision requires stronger statistical confidence.

---

# 5. Layer 3: Evidence and telemetry

Scoring should be based on **observable evidence**, not on the model's description of its own work.

## Product evidence

Examples:

- Build result
- Unit and integration test results
- Functional assertions
- Scripted user journey
- Regression checks
- Accessibility checks, where applicable

**Purpose:** Confirm that the result actually works.

## Harness evidence

Examples:

- Skill selected
- Tool selected
- Required hook execution
- Verification-loop iterations
- Stop-condition result
- Routing decision
- Context-compaction events
- Memory read/write events

**Purpose:** Show whether the harness behaved as designed.

## Resource evidence

Examples:

- Input tokens
- Output tokens
- Cached tokens
- Model cost
- Tool cost
- Retries
- Failed calls
- Context size
- Wall-clock time

**Purpose:** Explain efficiency and economics.

## Human evidence

Examples:

- Blind preference
- Tie
- Written rationale
- Failure category
- Rater confidence
- User-level appropriateness

**Purpose:** Measure useful quality that deterministic tests may not capture.

---

# 6. Critical pass/fail gates

Critical gates should run **before weighted scoring**.

A task that fails a critical gate is not a successful task, even if some aspects of the output appear strong.

| Gate | Example pass condition |
|---|---|
| Executable | Output builds, opens or runs. |
| Tests | Mandatory tests complete successfully. |
| Instruction adherence | Required steps and tools are confirmed in traces or hook logs. |
| Budget compliance | Time, token, cost and retry limits are respected. |
| Safety and policy | No disallowed tools, data exposure or writes outside approved boundaries. |
| Verification | Required final validation ran before completion. |

This creates an important distinction:

- **Gate:** Is the result valid enough to count as a successful outcome?
- **Score:** How good was that valid outcome?

---

# 7. Layer 4: Pillar scorecard

For a client-facing harness, **quality and reliability should dominate** the evaluation.

## Recommended weighting

| Pillar | Weight | Primary question | Primary metric |
|---|---:|---|---|
| **Quality** | **40%** | Is the outcome correct, useful and suitable for the user? | Blind preference + functional/specification quality. |
| **Reliability** | **30%** | Does the harness repeatedly deliver a valid result and obey controls? | Successful completion + repeated-run consistency. |
| **Cost per successful task** | **20%** | What does a valid business outcome cost? | Total cost / successful tasks. |
| **Token efficiency** | **5%** | Does the harness use context and generation efficiently? | Tokens per successful task. |
| **Latency** | **5%** | Does it deliver within acceptable time? | p50/p95 time to successful completion. |

The weights should be confirmed with stakeholders. The suggested distribution intentionally prioritizes quality and reliability.

---

# 8. Quality metrics

Quality should combine objective correctness with human judgement.

## Functional and specification pass rate

Measure the percentage of explicitly testable requirements that succeed.

Examples:

- Required feature exists.
- Produced artifact follows the required structure.
- Application behavior works.
- Required business rule is satisfied.

## Blind human preference

Compare baseline and harness outputs anonymously.

Report:

- Harness wins
- Baseline wins
- Ties
- Reasons for preference
- Reviewer agreement

## Human rubric score

Possible rubric dimensions:

- Correctness
- Completeness
- Relevance
- Business/domain fit
- Usability
- Clarity
- Output quality

## User-level parity

The north-star question is not merely whether the harness creates a good average result.

The harness should produce similar outcome quality when a task is expressed by:

- A novice user
- An intermediate user
- An expert user

Measure both:

- Mean quality across user levels
- The **quality floor**, or the lowest quality observed across user levels

> **North-star metric:** Quality floor = minimum quality score across user levels.

A high average should not hide weak performance for novice users.

## Automated-judge score

Use an AI judge as a supporting quality signal only after the judge has been calibrated against human-labelled examples.

---

# 9. Reliability metrics

Quality asks **how good the result is**.

Reliability asks **whether the system produces a valid result repeatedly and follows the required process**.

## Successful task completion rate

```text
Successful tasks / attempted tasks
```

A successful task should satisfy all required gates.

## Repeated-run success

For reliability, repeat the same task under equivalent conditions.

### pass@k

Measures whether **at least one** of `k` attempts succeeds.

This is useful when retries are an intentional part of the system.

### pass^k

Measures whether **all** of `k` repeated runs succeed.

This is a stronger measure of operational consistency for a client-facing harness.

## Instruction-adherence rate

```text
Mandatory actions completed / mandatory actions expected
```

Evidence should come from traces and hooks rather than from the agent's own summary.

Examples of mandatory actions:

- Required validation ran.
- Approved template was applied.
- Required tool was called.
- Final verification executed.
- Stop condition was honored.

## Run-to-run variation

Track dispersion across comparable runs for:

- Quality
- Cost
- Token usage
- Latency
- Number of retries

A system with a strong best run but large variation should not be described as reliable.

## Additional reliability indicators

- Budget-overrun rate
- Failed-tool-call rate
- Retry rate
- Loop-limit or kill-switch activation
- Recovery success after tool or model failure

---

# 10. Cost per successful task

Raw cost per run can reward a cheap failure.

The primary economic metric should therefore be:

```text
Cost per successful task =
Total cost of all attempts / Number of tasks clearing every required gate
```

This means a failed or retried attempt remains part of the economics.

## Supporting cost metrics

### Failed-attempt cost

Spend associated with attempts that produced no valid outcome.

### Retry cost

Cost caused by rework or unreliable runs.

### Cost relative to baseline

```text
Harness cost per successful task / Baseline cost per successful task
```

### Quality-adjusted cost

A useful diagnostic measure is:

```text
Cost per successful task / Normalized quality score
```

This helps distinguish “cheaper” from “better value.”

### Cost attribution

Where possible, split cost into:

- Main model
- Sub-agents
- Automated judges
- Retrieval
- Tools
- Verification
- Retries

---

# 11. Token efficiency

Token efficiency is an important diagnostic pillar because context management, routing, memory and verification decisions affect token consumption.

Useful metrics include:

- Input tokens per successful task
- Output tokens per successful task
- Cached-input utilization
- Context growth per turn
- Tokens spent in failed or discarded work
- Verification-token share
- Tool-result compression or offloading ratio

## Cache metric

Prefer a **true cache-read ratio** rather than combining cache reads and cache writes into one number.

A general form is:

```text
Cache-read ratio =
Cached input tokens read / Eligible input tokens
```

The exact formula should be aligned with the telemetry supplied by the model or platform being evaluated.

---

# 12. Latency

Total elapsed time is useful, but it does not explain where time is spent.

Track:

- Time to first useful action
- Time to first valid intermediate result
- Time to successful completion
- Model latency
- Tool latency
- Verification latency
- p50 completion time
- p95 completion time
- Budget-overrun rate

For interactive solutions, also measure the user's end-to-end scripted journey rather than only the agent's execution time.

---

# 13. Layer 5: Human blind evaluation

Human review remains important for close quality decisions.

## Recommended protocol

1. Present two anonymous outputs side by side.
2. Randomise which output appears first.
3. Do not expose system names, model names, folder names or other identifiers.
4. Allow the reviewer to choose:
   - Output A
   - Output B
   - Tie
5. Require a short reason for every non-tie decision.
6. For interactive outputs, let the reviewer perform a scripted interaction rather than relying on screenshots alone.
7. Use multiple reviewers for consequential decisions.
8. Measure reviewer agreement.

## Reason categories

Tag human preference reasons to possible sources of harness uplift:

- Better domain understanding
- Better template compliance
- Better instruction adherence
- Better tool use
- Better functional correctness
- Better output consistency
- Better novice-user support
- Better error recovery
- Better clarity or presentation

This allows the evaluation to explain not just **whether the harness won**, but **why**.

---

# 14. Automated judges

Automated judges are useful for scaling evaluations, but they should not automatically become the ground truth.

Calibrate an automated judge against a human-labelled evaluation set.

Track:

| Judge metric | Meaning |
|---|---|
| Human agreement | Percentage of decisions matching human reviewers. |
| Score correlation | Relationship between judge scores and human rubric scores. |
| False-positive rate | Weak outputs incorrectly accepted. |
| False-negative rate | Strong outputs incorrectly rejected. |
| Agreement by scenario | Categories in which the judge is more or less dependable. |

### Practical division of responsibility

- **Deterministic tests:** facts and behaviors that can be directly verified.
- **Human reviewers:** consequential or subjective quality.
- **Calibrated automated judges:** large-scale repeatable screening.

---

# 15. Layer 6: Measuring harness uplift

The evaluation should first report uplift **pillar by pillar**.

## Higher-is-better metrics

For metrics such as quality and reliability:

```text
Uplift % =
(Harness score - Baseline score) / Baseline score x 100
```

## Lower-is-better metrics

For metrics such as cost, tokens and latency:

```text
Improvement % =
(Baseline value - Harness value) / Baseline value x 100
```

## Overall harness uplift index

After normalizing each pillar onto a common scale, a summary index can be calculated as:

```text
Harness Uplift Index =
0.40 x Quality
+ 0.30 x Reliability
+ 0.20 x Cost efficiency
+ 0.05 x Token efficiency
+ 0.05 x Latency
```

The aggregate should **never be shown by itself**.

Always show the five component scores so that an efficiency gain cannot hide a quality or reliability regression.

---

# 16. Feature attribution

A full harness can improve overall performance without showing which component created the benefit.

Two methods help explain uplift.

## Incremental build-up

Evaluate:

```text
Baseline
→ + Curated skills
→ + Deterministic hooks
→ + Verification loop
→ + Context management
→ + Memory
→ + Model routing
```

This shows the marginal effect of each addition.

## Ablation testing

Start with the full specialized harness and remove one component at a time.

Examples:

- Full harness without curated skills
- Full harness without hooks
- Full harness without verification
- Full harness without context management
- Full harness without memory
- Full harness without routing

If removing a capability materially reduces quality or reliability, that capability has stronger evidence of contribution.

---

# 17. Release and promotion rules

A harness revision should be promoted only when agreed acceptance criteria are met.

A practical starting policy is:

1. No critical gate fails.
2. Quality does not regress.
3. Reliability does not regress.
4. The quality floor across user levels meets the agreed threshold.
5. Cost per successful task remains within budget.
6. Overall weighted uplift is positive.
7. No scenario category contains a material hidden regression.
8. The accepted baseline is updated only after review.

Thresholds should be agreed with the relevant business and engineering stakeholders before the evaluation is run.

---

# 18. Recommended evaluation output

The final evaluation should be understandable without requiring a reviewer to read detailed traces.

## Executive verdict

- Promote
- Hold
- Reject

Include the principal reason.

## Pillar scorecard

Report:

- Baseline score
- Specialized-harness score
- Absolute difference
- Percentage uplift or improvement

for all five pillars.

## Gate results

Show passed and failed gates by task.

## Human blind test

Show:

- Harness wins
- Baseline wins
- Ties
- Reasons
- Reviewer agreement

## Reliability report

Show:

- Successful completion rate
- Repeated-run reliability
- Variation
- Failure categories

## Economics

Show:

- Cost per successful task
- Failed-attempt cost
- Retry cost
- Cost attribution

## Feature attribution

Show incremental and ablation results for the harness capabilities being tested.

## Regressions

Explicitly identify scenarios where the specialized harness performs worse.

## Evidence links

Link each result back to its supporting:

- Trace
- Test result
- Telemetry
- Human evaluation
- Anonymous output artifact

---

# 19. Suggested evaluation sequence

## Step 1: Define

Choose representative tasks, user levels, critical gates and pillar weights.

## Step 2: Establish the baseline

Run the standard harness using the fixed model and approve the reference results.

## Step 3: Compare

Run the specialized harness with the same model, tasks and budgets.

## Step 4: Repeat

Perform multiple comparable runs and measure consistency.

## Step 5: Judge

Combine:

- Deterministic tests
- Blind human review
- Calibrated automated judging

## Step 6: Attribute

Use incremental testing and ablation to identify where the uplift came from.

## Step 7: Decide

Apply the release rules and update the accepted baseline only after review.

---

# 20. Key takeaways

### Evaluate the harness, not a model change

Keep the model, task and budget fixed when measuring harness uplift.

### Use gates before scores

An attractive answer is not successful if the result does not run, pass required checks, follow mandatory controls or stay within policy.

### Prioritize quality and reliability

These should carry most of the decision weight for a client-facing harness.

### Measure cost per successful task

Failed and retried attempts are part of the true economics.

### Test the north star directly

Compare novice, intermediate and expert task formulations and report the lowest user-level quality, not only the average.

### Explain where uplift came from

Use incremental build-up and ablation testing to tie improvements to skills, hooks, verification, context, memory or routing.

### Keep human judgement, but make it blind

Pairwise comparison, written reasons and reviewer agreement make subjective evaluation more defensible.

---

## In one sentence

> **A strong harness evaluation proves that the specialized system produces better, more repeatable outcomes for different users, at a known cost, with evidence that explains why.**
