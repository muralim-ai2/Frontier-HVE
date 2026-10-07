---
name: pr-push
description: Show verified feature branches as a checkbox list, push only the branches the user ticks, open stacked GitHub PRs, request Copilot code review, and report GitHub Actions checks. Unticked branches stay queued for a later session.
---

# PR push

Run from the project root; `<tools>` is the harness tools folder named in your agent instructions. Requires a GitHub remote and the GitHub Pull Requests extension.

1. `python <tools>/git/branch_workflow.py queue .` lists queued PRs: `branch`, `base_branch`, `lines_added`, `scope_creep`, `verify`.
2. Run the `code-review` skill on them first.
3. Ask with the ask-questions tool. Use exactly:
   - `header`: `push`
   - `question`: `Which branches should be pushed and opened as PRs now? [project: <project path relative to the workspace>]`
   - `multiSelect: true`, one option per queued branch, `label` = the branch name (`feature/...`), `description` = base branch, lines added, check command, and "SCOPE CREEP" if flagged.
   A plugin hook records the ticks across sessions. Pushes of unticked branches are denied by the harness.
4. For each ticked branch, in queue order (stacked branches build on each other):
   - `git push -u origin <branch>` (never force).
   - Open the PR with the GitHub Pull Requests create tool: `head` = branch, `base` = `base_branch`, title = feature name, body = description, check command and exit code, and review findings that remain.
   - `python <tools>/git/branch_workflow.py pushed . <feature> <pr url>`.
5. If the repository does not add Copilot code review automatically, ask the user to select "Request review from Copilot" on each PR.
6. Report each PR's GitHub Actions checks with the PR status-checks tool. Do not merge; merging is the human reviewer's decision.

At `guided` or `balanced` explanation depth, explain in one line what a PR is and what happens after the review (see `explain-walkthrough`).
