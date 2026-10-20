# Evaluation

After the feature loop, `HVE creator` (and the repository's `creator` mode) runs an output reflection loop on what it built. It runs again whenever the user asks to evaluate or improve the build; `prepare` refuses when no delivered file changed since the last evaluation. It has five layers. Each layer writes JSON to `.hve/evaluations/<run>/`, and the script enforces their order.

| Layer | What happens | Command (`reflection.py` = `python <tools>/evaluation/reflection.py`) | Output |
|---|---|---|---|
| 1. Contract | The JSON contract, the user's original request, the output kind and a fingerprint of the delivered files are snapshotted | `prepare <project> --contract <json> --request <file> --output-kind <ui\|cli\|api\|library\|document> [--revision-pass N]` | `contract.json`, `request.md`, `rubric-prompt.json` |
| 2. Rubrics | A fresh sub-agent scores each rubric from 0 to 1. Every score must cite existing project files | `record-scores <project> <run> <scores.json>` | `rubric-results.json` |
| 3. Validation | Hooks that fit the output kind run: `always` hooks every time, `below-warning` hooks only when a linked rubric scores below its warning threshold, every hook on a revision pass. Hooks re-run the locked feature checks, run a contract command, or collect files with SHA-256 | `validate <project> <run>` | `validation-results.json` |
| 4. Council | Three high-tier reviewers (`critical`, `balanced`, `constructive-coach`) each run on a model from a different vendor. They return markers (risk, miss or questionable design), each with a severity and evidence (`rubric:`, `validation:` or `file:`) | `council-prompts <project> <run>`, then `record-council <project> <run> <role> <verdict.json> --requested-model <model>` | `council-prompts.json`, `council/<role>.json` |
| 5. Decision | A weighted score plus deterministic markers (a score below its blocking threshold, a failed required hook) plus the council markers decide the outcome: `pass`, `revise` (another bounded pass) or `human-review` | `complete <project> <run>`; `check <project>` prints the latest decision | `report.json` |

`<tools>` is `tools` in this repository or `<installed-extension>/runtime/tools` for extension users. The default contract is `evaluation/frontier.eval.json` (shipped as `runtime/evaluation/frontier.eval.json`).

## Decision rules

- `pass`: no deterministic marker and no critical marker, a weighted score of at least `decision.minimumScore`, and at least `decision.councilPasses` council `pass` votes.
- `revise`: anything else while revision passes remain (`decision.maxRevisionPasses`), unless the council asks for a human. The creator fixes the critical and high markers, then runs `prepare --revision-pass N`. A revision pass needs the previous report's decision to be `revise`.
- `human-review`: the revision budget is spent, or enough council members ask for a human judgment. The creator shows the markers, asks the human to reflect on them, and records the answer with `record-human <project> <run> <verdict.json>` (`{"decision": "accept|revise|reject", "summary": "...", "disagree": [marker indexes]}`) in `human.json`. These verdicts are the data for calibrating the council later.
- A failed optional hook (`required: false`) adds no marker; its `recommendation` goes to the report's `recommendations` and reappears on every run until the evidence exists.

`check` exits 1 when no evaluation exists, a revision is due, or the human asked for a revision.

## Contract

The contract is JSON. The validator checks:
- `version: 1`;
- hooks of type `feature-checks`, `command` (needs `command`) or `artifacts` (needs `paths` globs), each with `required`, `trigger` (`always` or `below-warning`), `outputKinds` (from `ui`, `cli`, `api`, `library`, `document`) and `timeoutSeconds` (1-1800); an optional hook needs a `recommendation`; every hook must be used by a rubric;
- at least three rubrics with unique ids, positive weights that sum to 1, and `0 <= blocking <= warning <= 1`. Each rubric's `validationHooks` must name hooks that exist;
- exactly three council roles, all `modelTier: high`;
- `decision.councilPasses` within the council size and `decision.maxRevisionPasses` from 0 to 3.

A `command` hook gets the run folder in `HVE_EVALUATION_RUN`. The default contract always re-runs the locked checks, collects `.harness/evidence/**/*.png` for UI outputs when usability scores low (`visual-evidence`, required), and collects `.harness/evidence/**/*.log` for CLI and API outputs (`runtime-logs`, optional, because logs may live on a remote service). With an ask open, `.harness/` patterns resolve to the ask's `loop/` folder, and checks run with `HVE_EVIDENCE` pointing at its `evidence/`. So the creator makes each UI check save a screenshot and each CLI or API check save its output to `$HVE_EVIDENCE/<feature>/`.

## Council models

These follow the same rules as the [Product Manager](Product-Manager.md) council. The creator requests the strongest model it can from a different vendor for each role. If a model is refused, it picks another from the list in the refusal; if none is left, it records `host-selected`. `report.json` lists the requested model per role. A requested model is not confirmation of which model answered: only the Copilot OTel export confirms that.

## Files

`tools/evaluation/contract.py` (JSON contract validation), `tools/evaluation/workflow.py` (stages and decision), `tools/evaluation/reflection.py` (CLI), `extension/agents/hve-evaluation-reviewer.agent.md` and `.github/agents/evaluation-reviewer.agent.md` (read-only council member), `tests/test_evaluation.py`. `hooks/loop_guard.py` lets the agent write files to `.hve/evaluations/input/` that cite `.harness/` evidence; loop state stays locked.
