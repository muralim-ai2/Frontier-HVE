# Evaluation review, agent variants and distribution (2026-10-13)

Discussion between the user and the agent on 2026-10-13, recorded as agreed. Decisions: D-047. Follow-ups: tracker `N30`-`N33`.

## 1. Is the five-layer output evaluation sound?

Mostly. The stage order, the contract snapshot, grounded citations, non-overridable deterministic markers, capped revisions and a different model vendor per council role hold up. Gaps found:

| # | Gap | Resolution |
|---|---|---|
| S1 | Validation ran only for rubrics scored below warning, so an inflated score skipped the checks | Hooks now have `trigger: always` or `below-warning`; the locked feature checks always run |
| S2 | The output grades itself: the builder authors the feature checks and a sub-agent of the same harness scores the rubrics | Accepted for in-session reflection; harness comparison needs task assertions independent of the harness (`N32`) |
| S3 | The council is uncalibrated against human judgment | `record-human` stores the human verdict and per-marker disagreement as calibration data |
| S4 | Human review was a handoff with nothing recorded | `record-human` → `human.json`; `check` reports it |
| S5 | `visual-evidence` was required for every output, so CLI/API outputs got an unfixable marker | Hooks have `outputKinds`; screenshots are UI-only; CLI/API logs are optional and keep reappearing as a recommendation (logs may be remote) |
| S6 | No live creator run yet | Deferred (`N30`) |

Code size: about 630 non-blank Python lines, of which a hand-written YAML-subset parser was about 110 and duplicated helpers about 25. Decision: switch the contract to JSON and remove both.

## 2. Output evaluation vs harness evaluation

They answer different questions and stay separate. The output reflection judges one delivered output in one session (pass, revise or human review). The harness evaluation (`reference/Harness Evaluation Layer.md`; `tools/observe/`) compares harness versions across tasks, runs and user levels (promote, hold or reject). A reflection `report.json` can become one run's gate and quality record in `compare.py`, provided every arm is scored the same way after the run and against task assertions independent of the harness, and the reflection's own cost counts as verification spend. Deferred to `N32`.

## 3. When the evaluation runs

| Level | Runs? |
|---|---|
| Every interaction | No: hooks only |
| Every feature | No: `loop.py verify` already checks each feature |
| Loop finished (milestone) | Yes, automatically |
| User asks to evaluate or improve | Yes |
| Before PR push (creator-github) | Yes, once creator-github inherits the reflection (`N31`) |
| Harness release | Separate harness evaluation, never inside a user session |

`prepare` refuses when no delivered file changed since the last evaluation.

## 4. Many agents as variants of creator

Agent files have no inheritance, so every harness agent copies about 50 lines of hooks and shared sections; a fix to creator reaches none of the copies. Proposal: a base (`_base/harness.md` with the hook profile and the shared sections) that variants extend with `extends`, `replace`, `add` and `omit`, merged at build time; variants differ only in role, tools, domain skills, evaluation contract, templates, hook parameters and declared section overrides. A test fails when a variant drops a base hook it did not omit, and a snapshot test shows every agent a base change touches. Plugin-wide hooks were rejected because they would fire in the `minimal` and `single` baselines and in the user's default agent. Deferred to `N31`; first step: migrate the four existing harness agents with identical rendered output, then add an Architecture agent.

## 5. Which agents and skills are the real ones

| Layer | Edit? |
|---|---|
| Repository code: `hooks/`, `tools/`, `skills/admitted/`, `plugins/harness-assist/skills/` | Yes: the source |
| `extension/agents/hve-*.agent.md` | Yes: shipped product agents (`{{RUNTIME}}` templates) |
| `.github/agents/*.agent.md` | Yes: research benchmark arms; they differ on purpose (time budget, metrics, Graphify, output folder) |
| `extension/runtime/`, `extension/skills/` | Never: `build.py` output, not in git |
| `<globalStorage>/plugin/` | Never: rendered on install |

Other users get changes through a new VSIX version, which re-renders on activation. Locally, the same: `build.py`, package, reinstall, reload; a dev loop without packaging is not built yet.

## 6. Install that works for anybody

Problems: a manual Set up command, hooks calling bare `python` (`python3` on macOS and Linux, a Store stub on Windows), a winget-only install hint, OTel offered to every user although it records full chat content, hooks silently not running outside the Local session target, and a profile that only existed after Set up.

Agreed:
- The extension renders and registers the agents on install, update or a change of Python; Set up becomes optional (build preference, `.gitignore`, context-load report).
- It finds `python`, `python3` or `py -3` (3.11+) and writes that launcher into hook and tool commands.
- Without Python: agents that need it are shown with "(Needs Python)" and a warning instead of hooks, and a status bar item stays until Python is installed (user choice: warn, not hide).
- Hooks create `.hve/` state on first use.
- OTel moves to a separate research command with a modal warning.
- Agents with session hooks tell the user to switch to Session Target Local when the hook context line is missing.
- Distribution: VSIX (user choice).
