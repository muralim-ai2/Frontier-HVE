# Frontier-HVE vs Same Model Without Frontier-HVE — Benchmark Plan

## 1. Purpose

This plan defines a lightweight, repeatable benchmark that answers one question:

> **Given the same model, the same task, the same prompt, the same environment and the same budget, how much measurable value does Frontier-HVE add?**

This is a **harness-value benchmark**, not another general coding benchmark. The goal is not to show that a model can solve coding tasks, but to show whether Frontier-HVE makes that model more correct, reliable, verifiable, disciplined and efficient.

The benchmark compares:

- **Baseline:** the model with only the minimum ability to read files, edit files and run commands.
- **Frontier-HVE:** the exact same model running with Frontier-HVE.
- **Ablations:** Frontier-HVE with one component removed at a time, to show which components create the value.

---

## 2. Core principle: isolate the harness

The only thing allowed to change between conditions is the harness.

| Held constant | Detail |
|---|---|
| Model | Same model identifier and version |
| Provider | Same provider and endpoint |
| Model settings | Same reasoning level, temperature (where controllable) and context limit |
| Task prompt | Identical text, delivered the same way |
| Repository | Identical fixture at the identical commit |
| Environment | Same devbox image, runtime versions and dependencies |
| Budget | Same wall-clock, token and tool-call limits |
| Network | Same access policy |
| Verification | Same hidden tests and checks, run after the session ends |

If any of these differ, the result is not a harness comparison and must not be reported as one.

The **served** model must be recorded for every run, not only the requested model. Any run where the served model differs from the requested model is invalid.

---

## 3. What is being measured

The original list of qualities is grouped into six scored dimensions plus a set of hard gates.

### 3.1 Scored dimensions

| Dimension | Covers | How it is measured |
|---|---|---|
| **Correctness** | Task is actually solved, nothing else broke | Hidden fail-to-pass tests and pass-to-pass regression tests |
| **Instruction and PRD fidelity** | Constraints, non-goals, acceptance criteria | Machine-checkable assertions per requirement; prohibited-change checks |
| **Verification and recovery** | Testing before claiming success, diagnosing failures, no repeated-error loops, improving after feedback | Test/build events in the run log, verification after the final edit, count of repeated identical failures, change of approach after failure |
| **Engineering quality** | Simplicity, brevity, maintainability, understandability, scope discipline | Changed lines of code, files touched, unrelated changes, new dependencies, lint/type results, complexity and duplication deltas |
| **Efficiency** | Token savings, cost, latency | Input/output/cached tokens, cost, wall-clock time, tool calls — credited only for passing runs |
| **Traceability** | Human can follow what was decided and why; collaborative decisions on architecture and stack | Presence and quality of plan, decision record, requirement-to-test mapping and evidence of completion |

### 3.2 Hard gates (run scores zero if any fail)

| Gate | Failure condition |
|---|---|
| Hidden fallback | Model, provider, library or implementation substituted without disclosure |
| Runaway loop | Three consecutive equivalent failures without a changed hypothesis, or budget/timeout exhausted |
| Unsupported success claim | Declares the task complete without the required verification evidence |
| Critical instruction violation | Breaks an explicit "must not" constraint |
| Benchmark integrity | Accesses hidden tests, gold answers or prohibited sources |
| Blocker failure | Fails any task-specific blocker requirement (for example, does not build) |

Behaviours such as hiding behind fallbacks or looping forever are treated as gates, not deductions, because a run that does them is not trustworthy regardless of its other scores.

### 3.3 Anti-vibe-coding as an auditable checklist

"Anti-vibe coding" is not scored subjectively. It is measured through observable behaviours in the run log and diff:

- Did it inspect the existing code before editing?
- Did it identify the stated constraints?
- Did it add or modify a test for the change?
- Does the new test **fail on the original code** and pass on the patched code?
- Did it run verification after its last edit?
- Did it claim success without evidence?
- Did it add unnecessary dependencies or abstractions?
- Did it rewrite unrelated code?
- Did it leave TODOs, stubs or mocks in production code?

Each item feeds the Verification, Engineering Quality or Traceability dimension.

### 3.4 Continuous improvement metric

Frontier-HVE aims to reach verified quality rather than stopping at the first answer. This is measured directly:

- Capture the **first executable candidate** (the first version of the code that builds/runs).
- Capture the **final candidate**.
- Score both against the hidden checks.

**Improvement Delta = final score − first-candidate score**

A strong harness should show a positive delta; the baseline is expected to show a smaller or zero delta because it tends to stop early.

---

## 4. Task suite (MVP: six tasks)

Tasks are small, private, deterministic and each targets specific dimensions. Every task has a public prompt and fixture, and a hidden verifier the model never sees.

### T1 — Constraint adherence bug fix
- **Setup:** Small package with an edge-case bug.
- **Prompt includes:** Do not change the public API; do not add dependencies; do not modify a named file.
- **Hidden checks:** Boundary inputs, public API signature hash, protected file unchanged, dependency list unchanged, regression suite.
- **Targets:** Instruction fidelity, correctness, scope.

### T2 — Multi-file feature
- **Setup:** Feature requiring coordinated changes across several layers (for example data model, service logic and command-line entry point).
- **Hidden checks:** End-to-end behaviour, backward compatibility, regression suite.
- **Targets:** Planning, correctness, maintainability.

### T3 — Verification trap
- **Setup:** The obvious fix passes the visible example but fails a hidden edge case. The prompt asks for a fix and a test.
- **Hidden checks:** Edge case behaviour; the model's new test must fail on the original code and pass on the fix.
- **Targets:** Verification, anti-vibe coding, improvement delta.

### T4 — Error recovery
- **Setup:** A misleading first failure masks a second, real root cause.
- **Hidden checks:** Correct final behaviour; run log analysed for repeated identical attempts, change of hypothesis and escalation.
- **Targets:** Recovery, loop control.

### T5 — Fallback trap
- **Setup:** The preferred library or tool is unavailable; an approved alternative is documented in the repo.
- **Hidden checks:** No silent stub or fake implementation; fallback is explicitly disclosed; behaviour preserved.
- **Targets:** No hidden fallback, instruction fidelity.

### T6 — Mini PRD to implementation
- **Setup:** Short PRD with functional requirements, acceptance criteria, constraints and non-goals.
- **Hidden checks:** One check per acceptance criterion; non-goals not implemented; requirement-to-test traceability.
- **Targets:** PRD fidelity, planning, traceability.

### Later additions (phase 2)
- **T7 — Architecture decision:** Two viable stack/design options with a hidden constraint; scripted second turn supplies the user's choice. Measures whether options and trade-offs are surfaced and the chosen option is implemented faithfully.
- **T8 — Refactor with restraint:** Improve a tangled module without behaviour change. Measures behavioural equivalence, complexity reduction and diff discipline.

### Task construction rules
- Each fixture is a fresh single-commit repository (no history to mine).
- Hidden tests are mounted only after the session ends.
- Every task is validated with a reference solution multiple times before freezing.
- At least two different correct solutions are used during validation to avoid over-specific tests.
- Task prompts, fixtures and verifiers are versioned and hashed before official runs.

---

## 5. Experimental conditions

### 5.1 MVP conditions

| ID | Condition | Purpose |
|---|---|---|
| C0 | Bare model (prompt only, basic file/shell access) | Baseline |
| C1 | Model + basic tools, no harness controls | Separates tool access from harness value |
| C2 | Full Frontier-HVE | Primary comparison |
| C3 | Frontier-HVE without skills | Value of skills |
| C4 | Frontier-HVE without active verification | Value of the verification loop |

### 5.2 Phase 2 ablations

| ID | Condition |
|---|---|
| C5 | Frontier-HVE without planning |
| C6 | Frontier-HVE without recovery/escalation |
| C7 | Guards only (no-fallback, loop and scope controls, no workflow) |
| C8 | Verification only |

### 5.3 Ablation rules
- Each ablation is a separate, committed configuration.
- Each configuration has a machine-readable list of enabled components.
- A check confirms that only the intended component differs from C2.
- The external post-run verifier is identical across all conditions — removing "active verification" removes the harness's in-session checking, not the benchmark's grading.

---

## 6. Run protocol

### 6.1 Volume
- MVP: **6 tasks × 5 conditions × 3 runs = 90 runs.**
- Phase 2: 8 tasks × 9 conditions × 3 runs = 216 runs.

### 6.2 Per-run procedure
1. Create a fresh workspace from the frozen fixture.
2. Start a fresh session with no prior conversation, memory or cache carried over.
3. Apply the condition's configuration.
4. Deliver the identical task prompt.
5. Enforce budgets: wall-clock, total tokens, tool calls.
6. Record all events, commands, edits, errors and usage to a run log.
7. On completion or termination, capture the diff, final response and environment manifest.
8. Destroy the session.
9. Run the hidden verifier against the captured result in a separate step.
10. Score and store the result.

### 6.3 Independence and ordering
- Each of the three runs is fully independent.
- Run order is randomised across conditions within each task to avoid time-of-day or provider-load bias.
- Temperature is set to 0 where supported; otherwise the setting is recorded and runs are treated as independent samples.

### 6.4 Termination rules
| Trigger | Outcome |
|---|---|
| Wall-clock limit reached | Terminated — gate failure |
| Token or tool-call limit reached | Terminated — gate failure |
| Three consecutive equivalent failures with no change of approach | Terminated — loop gate failure |
| Model declares completion | Normal end, proceed to verification |

### 6.5 What is frozen before official runs
- Benchmark version and commit
- Frontier-HVE version and commit
- Model identifier, provider and settings
- Devbox image and runtime versions
- Task prompts, fixtures and verifier hashes
- Scoring weights and thresholds

Nothing in this list changes during a benchmark round. Any change starts a new benchmark version.

---

## 7. Scoring

### 7.1 Gates first
If any hard gate fails, the run's overall score is **0**. The gate failure reason is still recorded and reported.

### 7.2 Run score (gate-passing runs)

$$
S_{run} = 100 \times (0.40C + 0.15I + 0.15V + 0.15Q + 0.10E + 0.05T)
$$

| Symbol | Dimension | Weight |
|---|---|---:|
| C | Correctness | 40% |
| I | Instruction and PRD fidelity | 15% |
| V | Verification and recovery | 15% |
| Q | Engineering quality | 15% |
| E | Efficiency | 10% |
| T | Traceability | 5% |

Each dimension is scored 0–1 against **fixed thresholds set per task before the runs**. Scores are never normalised against the other conditions, so adding or removing a condition does not change anyone's score.

Efficiency is credited only when correctness blockers pass — a cheap wrong answer earns no efficiency credit.

### 7.3 Aggregation across the three runs

Report all of:

| Metric | Definition |
|---|---|
| Mean score | Average of three run scores |
| Pass rate | Passing runs / total runs |
| Reliability | 3/3 = reliable, 2/3 = usually succeeds, 1/3 = unstable, 0/3 = fails |
| Spread | Range or standard deviation across runs |
| Resource medians | Median tokens, cost, time, tool calls |
| Improvement delta | Final vs first executable candidate |

**Best-of-three is never reported** — it rewards randomness rather than harness quality.

### 7.4 Harness value

The headline result is the **paired difference** between Frontier-HVE and the baseline on the same tasks:

$$
\text{Harness Value} = \text{Quality Gain} + \text{Reliability Gain} + \text{Efficiency Gain}
$$

subject to all gates passing.

Each ablation's contribution is:

$$
\text{Component Value} = S_{C2} - S_{\text{ablation}}
$$

Bootstrap confidence intervals are computed across tasks. With six tasks the intervals will be wide; they are shown rather than hidden.

### 7.5 How results are presented
Dimension scores are the headline. The composite is secondary.

```text
                    Bare (C0)   Frontier-HVE (C2)   Delta
Correctness            ..             ..              ..
Instruction fidelity   ..             ..              ..
Verification           ..             ..              ..
Engineering quality    ..             ..              ..
Efficiency             ..             ..              ..
Traceability           ..             ..              ..
-----------------------------------------------------------
Composite              ..             ..              ..
Pass rate              ../18          ../18
Reliable tasks (3/3)   ../6           ../6
Median tokens          ..             ..
```

Also include:
- Per-task breakdown (not only the aggregate).
- Score versus cost chart.
- Gate failure counts by reason.
- Component contribution chart from the ablations.

---

## 8. Automation outline

The runner is deliberately simple so it can be understood and extended.

```text
frontier-bench/
  tasks/
    T1/ task.yaml  prompt.md  fixture/  verifier/   (verifier hidden from runs)
    ...
  conditions/
    C0_bare.yaml  C1_tools.yaml  C2_full.yaml  C3_no_skills.yaml  C4_no_verify.yaml
  runner/
    run_matrix.py     # expands tasks x conditions x 3 runs, randomises order
    workspace.py      # creates and destroys fresh workspaces
    budget.py         # enforces time, token and tool-call limits
    monitor.py        # loop detection and termination
    capture.py        # diff, logs, usage, environment manifest
  verify/
    run_verifier.py   # hidden tests, regression, lint, scope, reverse-test check
  scoring/
    gates.py  dimensions.py  aggregate.py  report.py
  results/
    <benchmark_version>/<condition>/<task>/<run>/
```

### 8.1 Task definition

```yaml
id: T3
version: 1
title: Verification trap
prompt_file: prompt.md
fixture: fixture/
budgets:
  wall_seconds: 1200
  tokens: 120000
  tool_calls: 120
blockers:
  - hidden_edge_case_passes
  - regression_suite_passes
  - new_test_fails_on_base
dimensions: [correctness, verification, engineering_quality]
```

### 8.2 Run record

```json
{
  "benchmark_version": "1.0",
  "task_id": "T3",
  "condition": "C2_full",
  "run": 2,
  "model": {"requested": "...", "served": "...", "provider": "..."},
  "harness_commit": "...",
  "environment_hash": "...",
  "outcome": "completed",
  "usage": {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0, "wall_seconds": 0, "tool_calls": 0},
  "first_candidate_captured": true,
  "artefacts": {"diff": "...", "log": "...", "final_response": "..."}
}
```

### 8.3 Score record

```json
{
  "task_id": "T3",
  "condition": "C2_full",
  "run": 2,
  "gates": {"fallback": true, "loop": true, "evidence": true, "instructions": true, "integrity": true, "blockers": true},
  "dimensions": {"correctness": 1.0, "instruction": 0.9, "verification": 0.85, "quality": 0.8, "efficiency": 0.7, "traceability": 1.0},
  "first_candidate_score": 72,
  "final_score": 88.5,
  "improvement_delta": 16.5
}
```

Fields that only Frontier-HVE can report (for example skill activations or guard interventions) are stored separately and marked as harness-specific. Missing telemetry is recorded as **unavailable**, never as zero.

---

## 9. Execution plan

### Phase 0 — Preparation (week 1)
- [ ] Choose the single model and provider for all conditions.
- [ ] Confirm the served model can be captured for every run.
- [ ] Build the devbox image and pin all versions.
- [ ] Define C0–C4 configurations and the component check for each.

### Phase 1 — Task build (weeks 1–2)
- [ ] Write T1–T6 prompts and fixtures.
- [ ] Write hidden verifiers and regression suites.
- [ ] Write two reference solutions per task.
- [ ] Validate each task: reference solutions pass repeatedly; original code fails.
- [ ] Freeze and hash tasks, verifiers and scoring thresholds.

### Phase 2 — Runner and scoring (week 2)
- [ ] Implement workspace creation/teardown.
- [ ] Implement budget enforcement and loop detection.
- [ ] Implement first-candidate capture.
- [ ] Implement verifier execution and gate checks.
- [ ] Implement dimension scoring, aggregation and report.

### Phase 3 — Dry run (week 3)
- [ ] Run one task × all conditions × one run.
- [ ] Inspect every log manually for leakage, mis-scored gates and missing telemetry.
- [ ] Fix issues; if fixes affect scoring, re-freeze and bump version.

### Phase 4 — Official MVP run (week 3)
- [ ] Execute 90 runs in randomised order.
- [ ] Manually audit a sample of trajectories, including every gate failure and every top-scoring run.

### Phase 5 — Analysis and report (week 4)
- [ ] Paired Frontier-HVE vs baseline comparison.
- [ ] Ablation component contributions.
- [ ] Reliability, improvement delta and cost views.
- [ ] Write up findings with limitations.

### Phase 6 — Strengthen (later)
- [ ] Add T7 and T8.
- [ ] Add C5–C8 ablations.
- [ ] Add blinded, double-scored human review for understandability and decision quality.
- [ ] Refresh tasks periodically to limit contamination.
- [ ] Repeat on a second model to show the effect generalises.

---

## 10. Threats to validity and mitigations

| Threat | Mitigation |
|---|---|
| Model or provider differs between conditions | Pin and record served model; invalidate mismatched runs |
| Randomness | Three independent runs; report reliability and spread; no best-of-three |
| Small sample (six tasks) | Treat MVP as directional; show per-task results and confidence intervals |
| Prompt sensitivity | Freeze prompts; test paraphrases only as a separate study |
| Contamination or leakage | Private tasks, fresh single-commit repos, hidden verifiers, restricted network |
| Subjective quality judgements | Deterministic checks first; blinded double review only where necessary |
| Ablations changing more than intended | Component inventory and automated diff check per configuration |
| Benchmark gaming | Audit trajectories; independently check restricted access rather than trusting self-reports |
| Composite score hiding trade-offs | Lead with dimension scores, gates and reliability; composite is secondary |

---

## 11. Expected outcome

At the end of the MVP, the benchmark should support statements of the form:

> With the same model, Frontier-HVE raised reliable task completion from **X/6 to Y/6**, increased the mean score by **Z points**, reduced gate failures by **N**, and changed median token use by **M%**.

> Removing verification reduced the score by **A points**; removing skills reduced it by **B points**.

These are the claims that establish whether — and which parts of — Frontier-HVE add measurable value over the model alone.
