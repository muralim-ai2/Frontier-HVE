# Copilot Instructions — Code Style

## Project context

- This repo is the enterprise AI harness. Original request and design rules: `reference/initial_request.md`. Background: `reference/Enterprise AI Harness Blueprint v3.md`, `reference/Implementation Plan Enterprise AI Harness v3.md`.
- Current status and open work: `tracker.json` (`next_actions` first). Decisions: `research/decisions/decision_log.md`. Hypothesis: `research/hypothesis.md`.
- Never mark a tracker item `validated`; only the user does.

## npm registry on Microsoft-managed devices

- Direct access to `https://registry.npmjs.org/` is blocked.
- Before installing npm packages, check for a repository `.npmrc` and run
  `npm config get registry`.
- If the repository configures an Azure Artifacts feed, preserve and use that
  feed. Do not replace it with the general proxy.
- If no repository-specific registry is configured, use the Microsoft Central
  Feed Services proxy:
  `npm config set registry https://packagefeedproxy.microsoft.io/npm/`
- Verify the effective registry with `npm config get registry` before running
  npm install commands.

## Brevity

- Prefer few, cohesive modules. Split only when a module clearly outgrows one
  responsibility.
- Write the fewest lines that stay clear. No clever one-liners that obscure intent.
- No dead code, unused parameters, speculative options, or wrapper functions
  that only forward calls.
- No premature abstraction. Add a layer only when a second real caller exists.
- No comments that restate the code.

## No fallbacks

- Fail fast. Let errors surface with a clear message and useful context.
- No `try/catch`/`try/except` that swallows, logs-and-continues, or returns a default.
- No silent defaults for missing config, env vars, inputs, or files.
- No retry loops, alternate code paths, or "if X fails use Y" logic unless
  explicitly asked.
- Catch an error only to add context and re-throw.

## Types

- **Python**: type-hint every parameter and return value. Use precise types
  (`list[str]`, `dict[str, int]`, `Path`, `TypedDict`, `Literal`) over `Any` or
  bare containers. Use built-in generics and `X | None`.
- **TypeScript**: explicit types on every parameter and exported function return.
  Use precise types (unions, literal types, interfaces) over `any`; prefer `unknown`
  when the type is truly unknown.
- **JavaScript**: use JSDoc `@param {Type}` and `@returns {Type}` tags.
- Other languages: follow the language's native static typing if it has one;
  otherwise skip this section.

## Docstrings

- Every public function, class, and module gets a docstring in the language's
  native form (Python `"""..."""`, JS/TS `/** ... */`, etc.).
- One sentence or less, descriptive only: state what it does or returns.
- No opinions, reasoning, design notes, or usage commentary.

  Good: `"""Return the total price of items in the cart."""`
  Bad:  `"""Calculates the total, which is better than the old approach because..."""`
