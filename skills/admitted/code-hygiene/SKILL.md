---
name: code-hygiene
description: De-slop code after AI generation - remove over-engineering, dead code, speculative options and comments that restate the code; simplify without changing behavior.
---

# Code hygiene

Run on the files a feature changed, after its check passes. Behavior must not change: re-run the check after every pass.

## Pass 1: over-engineering
- Abstractions with one implementation, factories that build one thing, interfaces nobody else implements: inline them.
- Configuration options, flags and parameters no caller uses: delete them.
- Wrappers that only forward a call: call the target directly.
- Retry loops, fallbacks and default values nobody asked for: remove them and let errors surface.

## Pass 2: dead and duplicated code
- Unused imports, variables, functions, files and commented-out code: delete (git keeps history).
- The same logic in two places: keep one, call it from both, only if both callers exist today.

## Pass 3: comments and names
- Delete comments that restate the next line, narrate the change ("now we..."), or address a reviewer.
- Keep comments that say why, not what: a constraint, a workaround with its reason, a non-obvious invariant. One short line each.
- Rename vague names (`data`, `handle`, `util`, `temp`) to what they hold or do.

## Report
List what was removed or simplified per file with the line delta, and confirm the check still exits 0. If a simplification would change behavior, do not make it: note it as a question.
