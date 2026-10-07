---
name: code-review
description: Review queued feature branches before pushing - correctness against acceptance criteria, hidden errors, size, security (OWASP), tests and dependencies - and return findings as JSON. Use before the pr-push skill.
---

# Code review

For each branch from `python <tools>/git/branch_workflow.py queue .` (`<tools>` is the harness tools folder named in your agent instructions):

1. Read the diff: `git diff <base_branch>..<branch> --stat`, then the changed hunks you need.
2. Check, in order:
   - **Correctness:** the feature's description and acceptance criteria (`design.json` if present) are met; edge cases (empty input, errors) are handled.
   - **Hidden errors:** no empty `catch {}`, silent `except`, default values that hide failures, or `TODO`/`FIXME`.
   - **Size and structure:** no file over 500 lines; one responsibility per module.
   - **Security (OWASP Top 10):** no injection (SQL, shell, HTML without escaping), no secrets in code, input validated at boundaries, no unsafe `eval`, safe defaults for auth and CORS.
   - **Tests:** the feature's check exercises the new behaviour.
   - **Dependencies:** every new package is needed; run the `prototype-guardrail` skill if any datastore, OCR, search, vector, LLM or infra component appears.
3. Write findings as JSON in your reply: `[{"branch", "severity": "blocking|major|minor", "file", "line", "issue", "fix"}]`.
4. Fix blocking findings on the branch (then `loop.py verify .` again if it is the current feature) before pushing. List the rest in the PR body.

On GitHub, Copilot code review gives a second pass on the opened PR; this review does not replace the human reviewer.
