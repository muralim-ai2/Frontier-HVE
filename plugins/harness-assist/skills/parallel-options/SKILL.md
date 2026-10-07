---
name: parallel-options
description: Build two or more approaches to one feature in separate git worktrees, let the user run each and tick the winner, then adopt only the ticked option. Use when a feature has genuinely different implementations.
---

# Parallel options

Run from the project root; `<tools>` is the harness tools folder named in your agent instructions.

1. `python <tools>/git/parallel_options.py create . <feature> <approach-a> <approach-b>` (slugs: lowercase and `-`). Give each printed worktree folder to its own sub-agent with the feature description and the approach.
2. `python <tools>/git/parallel_options.py compare . <feature>` checks and ranks every option (passes, then share of `HARNESS_CHECKS`, then smallest diff). In benchmark loops (`--review local`) it adopts the best passing option itself; you are done. For GitHub loops it keeps the worktrees and prints a `preview` list.
3. Show the user, per option: what is different in plain words, its check result, lines added, and how to try it (open the folder with `code -n "<folder>"`, then the printed `npm install` and `npm run dev -- --port <port>` in that window's terminal). Do not start the servers yourself.
4. Ask with the ask-questions tool. Use exactly:
   - `header`: `choose:<feature>`
   - `question`: `Which option should <feature> use? [project: <project path relative to the workspace>]`
   - one option per approach, `label` = the approach slug, `description` = check result, lines added, and "recommended" for the top-ranked one; single choice.
   A plugin hook records the tick; you cannot write it yourself.
5. Run `python <tools>/git/parallel_options.py choose . <feature> <ticked approach>`, then `loop.py verify .`.

Losing branches stay in git as evidence; their worktrees are removed.
