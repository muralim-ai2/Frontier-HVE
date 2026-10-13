---
name: delivery-coach
description: Run AI-built work as a participatory, verified loop - plan, build and evaluate each feature with tests and screenshots, offer manual checks, use discovery sprints for complex features, and coach toward the right stack and experts.
---

# Delivery coach

Guards against vibe-coding a production application: nothing counts as done without evidence, and the user stays in the loop. Run from the project root; `<tools>` is the harness tools folder named in your agent instructions.

## 1. Coach first (guided or balanced explanation depth)
Before planning, follow `explain-walkthrough` section 2: what we will build, how the parts fit, and where we are (prototype, pilot or production). Then challenge, kindly and once per topic:
- **Production intent on a prototype stack**: if the user plans real users, real data, scale or compliance, run `prototype-guardrail` and name the experts (solution architect, security, backend) before building further.
- **Choices with hidden cost**: a self-built datastore, auth, search or hosting where a licensed service exists; storage that grows without bound; no tests "to go faster".
State the risk, the better option and what it costs in one line each. The user decides; record their choice in your summary.

## 2. Initializer: plan in files, not in chat
1. Use `feature-checklist` to write `feature_list.json` (3-8 features a user recognises, each with a real check).
2. For a UI feature, make its `verify` command also capture a screenshot into `.harness/evidence/<feature>/` (for example a script that starts the app, runs `npx playwright screenshot --full-page http://localhost:<port> .harness/evidence/<feature>/page.png`, stops the app, and exits non-zero if the file is missing). The check produces the evidence, so it cannot be faked.
3. Run `python <tools>/loop/loop.py init . --review <local|github>`. It writes `progress.txt` and `tracker.json` (status, attempts, check, evidence and manual check per feature). Show the user the tracker as a short table.

## 3. Generator and evaluator: one feature at a time
1. `loop.py next .`, then one fresh sub-agent builds the feature (description, check command, file paths only).
2. `loop.py verify .` runs the check (unit tests, plus the screenshot for UI features). On failure do exactly the printed `action`.
3. Evaluator: a second fresh sub-agent reviews the diff and any screenshot against the feature description (see `code-review`) and reports findings only. Fix HIGH findings before moving on.

## 4. Offer a manual check after each passing feature
Ask with the ask-questions tool (the user may skip; never insist):
- `header`: `check:<feature>`
- `question`: `<feature> passed its check. Want to try it yourself? <how to run it, in one line> [project: .]`
- options, `label` exactly: `looks right`, `needs changes`, `skip`; single choice.
A hook records the answer and `python <tools>/loop/loop.py status .` shows it in `tracker.json`. On `needs changes`, ask what is wrong; fix it within the next feature only if it belongs there, otherwise list it as a follow-up request in your summary.

## 5. Discovery sprint for complex features
When a feature has several viable designs, new technology or high risk, do not guess: follow `parallel-options` with 2-3 approaches. Each approach gets its own branch and worktree under `.hve/discovery/`, is built and run, and is reviewed with `code-review`. Show the user how each one behaves and what it costs to maintain, then let them tick the winner.

## 6. Close out
Report per feature: check command and exit code, evidence files, manual check result. Say plainly what is still a prototype and which experts to involve before production. Then follow `check-context-load` and include its warnings, if any, so skill and instruction bloat is caught as the project grows.
