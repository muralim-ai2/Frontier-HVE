---
name: solution-map
description: Explain how part of a codebase works from its solution map - the concept, its modules, files and functions, connections, dependencies and a plain explanation - and open the interactive explorer filtered to it. Use when the user asks to understand, explain or locate an implementation (for example "help me understand the telemetry implementation", "how do plugins work here") or types /solution-map <topic>.
---

# Solution map

`<tools>` is the harness tools folder named in your agent instructions (`tools/` in the harness repository, `runtime/tools` in the installed Frontier HVE extension). Run every command from the workspace root.

1. **Create or refresh on request.** If the user asks to create, build, refresh or publish the map (for example `/solution-map create`), run `python <tools>/map/solution_map.py build` (add `--snapshot` to publish it to `docs/architecture/` for committing), report the size class and counts in two lines, run `python <tools>/map/solution_map.py open`, and stop. When the build reports derived concepts, offer to propose named concepts for `docs/architecture/solution-map.config.json`.
2. **Ask first, unless invoked.** If the user typed `/solution-map` (or named this skill), go on. Otherwise ask once with the ask-questions tool: "Explain this from the solution map?" with options `Yes, use the solution map` (recommended) and `No, just answer`. On no, answer normally and stop.
2. **Map ready.** Run `python <tools>/map/solution_map.py status`. If it fails with no map, or shows `"stale": true`, run `python <tools>/map/solution_map.py build` (writes `.hve/map/`; a few seconds) and say in one line that the map was built or refreshed, with its size class.
3. **Explain.** Run `python <tools>/map/solution_map.py explain "<the user's words>"`. It prints Markdown: the concept, its explanation, the file to start at, modules with files and the functions that match the question, connections to other concepts, external dependencies, tests, docs, decisions, and an explorer link.
4. **Answer** in this order, compact and grounded only in that output (read a cited file only when the user asks for detail, and cite paths):
   - **Concept:** name, then 3-5 sentences in your own words.
   - **Where:** modules › files › key functions (at most 8 files; one line each).
   - **Connections and dependencies:** one line each.
   - **Start at:** the start file and why.
5. **No concept matched:** show the closest files it lists, then offer to add a concept: draft `{"id", "name", "keywords", "members": [path regexes], "start", "explain"}` from those files' purposes, show it, and with the user's yes add it to `concepts` in `docs/architecture/solution-map.config.json` and run `build` again.
6. **Offer the explorer** with the ask-questions tool: `Open the explorer filtered to <concept>`, `Show what a change here would touch`, `No thanks`.
   - Explorer: run `python <tools>/map/solution_map.py open "concept=<concept id without the concept: prefix>"` (or `open "<topic>"` when nothing matched). It opens the page with Force, Tree and Circles views, the filter banner, Back and Show whole map.
   - Change: pick 1-4 start nodes from the output (`file:<path>` ids), run `python <tools>/map/solution_map.py impact --seeds <ids>`, and list what it touches, the tests to run and the roles to involve.
7. **Tell the user once** how to ask again: "Ask any time with `/solution-map <topic>` in Copilot Chat or Claude Code, or `$solution-map <topic>` in Codex; or just say help me understand <topic>."

Never edit code in this skill: it explains. The map states its commit; when files changed since, say so with the count.
