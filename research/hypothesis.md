# Research hypothesis

## H1 — Do more agents and more loop iterations beat a better-crafted single node?
- **Claim under test:** the full harness (`creator`: sub-agents, one-feature-per-session loop, verification gate) produces higher output quality than a single, well-crafted node on a stronger model (`single`: Claude Opus 5.5, high reasoning, engineered system prompt, tools).
- **Control:** `single` is always the baseline the harness is compared against.
- **Primary metric:** blind human score (1–5) against the spec; reviewer does not know which mode produced the output.
- **Reject H1 if:** `creator` quality ≤ `single` quality. Then the extra agents and loops are not justified, whatever they cost.
- **Status (2026-10-06, baseline n=1):** preliminary support. Blind human score creator 3.8 vs single 2.9, at 34% lower cost. Not yet conclusive: one run per mode, model confounded, creator used no sub-agents. See `research/findings/phase-2-baseline-blind-eval.md`.

## H2 — Minimal mode shows why context engineering, tools, and iteration matter
- **Claim under test:** without context engineering, tool calls, or iteration (`minimal`: GPT-6 Astra, no tools, one pass), a coding agent produces sub-standard output.
- **Measured as:** blind score gap `single` − `minimal`, plus spec items missed by `minimal`.
- **Status (2026-10-06, baseline n=1):** supported. minimal's 204-line inline app does not build (unclosed CSS block in its own output); human 0, AI 1.

## Method
- Same prompt for every mode: `tests/prompts/color-palette.md`.
- 3 runs per mode; metrics from `research/runs/<session_id>.jsonl` (hook + OTel, never model self-reports).
- Decision priority: Quality > Tokens > Latency > Cache hit ratio. A cheaper run with worse quality is a failed run.

## Known confounder
- Modes use different models (decision D-003), so mode differences mix harness effect with model effect. Report quality by mode **and** model; a same-model ablation is needed before attributing gains to the harness alone.
