---
name: run-tests
description: Run the project's checks the harness way - the current feature through loop.py verify, or every feature check as a regression run - and report exact commands and exit codes.
---

# Run tests

- **Current feature:** run `python <tools>/loop/loop.py verify .` from the project root (`<tools>` is the harness tools folder named in your agent instructions). It runs the locked check, commits on success, and on failure prints a `rule` and `action`. Do exactly the action. If it prints `escalated: true`, stop and ask the user the printed question.
- **Regression (all features):** for every entry in `feature_list.json`, run its `verify` command from the project root. Report a table: feature, command, exit code, `HARNESS_CHECKS` line if printed.
- **Project test script:** if `package.json` has `test` or `pyproject.toml` configures pytest, run it once in the foreground and report the exit code.

Rules: run commands in the foreground and never leave servers running; never claim a check passed without its exit code; never edit `feature_list.json` to make a check pass.
