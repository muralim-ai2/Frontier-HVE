---
name: scrub
description: Scrub changed files before commit - stale or restating comments, AI filler, debug leftovers, commented-out code, empty catches, secrets and PII; fix the safe ones, report the rest.
---

# Scrub

Scope is only what changed: `git diff --name-only HEAD` plus untracked files from `git status --porcelain`. Never sweep the whole repository.

| Find | Action |
|---|---|
| Comments that restate the code, narrate edits or address a reviewer | Delete |
| Stale comments that no longer match the code | Fix or delete |
| AI filler in docstrings and docs ("This robust function seamlessly...") | Rewrite to one plain sentence |
| Debug leftovers: `print`/`console.log` used for debugging, `debugger`, temporary files | Delete |
| Commented-out code | Delete (git keeps history) |
| Empty `catch {}` / `except: pass`, errors swallowed or turned into defaults | Report: needs a real decision (re-throw with context, or handle) |
| `TODO`/`FIXME` in shipped code | Report: resolve or turn into a tracked follow-up |
| Secrets (keys, tokens, connection strings) and PII (emails, phone numbers, names in fixtures) | Report immediately; move secrets to environment config, replace PII with synthetic data |

Steps:
1. List the changed files; scan each against the table.
2. Apply only the safe fixes (delete, reword); re-run the feature's check.
3. Run the harness pre-commit scan by committing normally; never bypass it.
4. Report per file: fixed items, reported items with line numbers, and the check's exit code.
