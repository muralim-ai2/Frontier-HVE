# Phase 9 findings: workspace skill evaluator and context-load guardrail (2026-10-07)

Decision D-039. Code: [tools/skills/evaluate.py](../../tools/skills/evaluate.py), [tools/skills/context_load.py](../../tools/skills/context_load.py), agents [extension/agents/hve-skill-evaluator.agent.md](../../extension/agents/hve-skill-evaluator.agent.md) (+ `HVE skill-worker`, `HVE skill-judge`), skill [check-context-load](../../plugins/harness-assist/skills/check-context-load/SKILL.md). Tests: `tests/test_skills.py` (context load, evaluator flow), `tests/test_extension.py` (runtime).

## 1. Why

- **Onboarding.** Before this, only this repository could evaluate and admit a skill (`micro_eval.py`, `onboard.py`). An extension user adding their own skill had no way to measure whether it helps or to keep it out of every chat.
- **Bloat.** Every discoverable skill puts its name and description into every request of every chat; always-on instruction files and MCP tool schemas do the same. A workspace with hundreds of skills, large instruction files and several MCP servers can start every request with tens of thousands of tokens before the user types. Nobody sees this number today. No fixed token limit is set: the right size depends on the model's window and the task. The guardrail measures and reports instead.

## 2. Skill evaluator: how it works

| Step | Command | What happens |
|---|---|---|
| 1. Static check (free) | `python <runtime>/tools/skills/evaluate.py static <skill folder>` | Security scan, structure, category fit, size and description limits, Python-only scripts, overlap with library skills (shared word stems >= 50%), and cost: tokens per request if the skill sat in a skill folder vs tokens when loaded |
| 2. Tasks | agent writes `.hve/evals/<name>/tasks.json` | 5 small tasks with 3-4 checks each, drafted from what the skill claims; the user approves or edits them before any model call |
| 3a. Answers, in chat (default, no keys) | sub-agent `HVE skill-worker`, twice per task | Same chat model for both; "with" gets the full SKILL.md in the message. The worker is a custom agent with no tools and its own short prompt, so it does not inherit the evaluator's instructions |
| 3b. Answers, on Foundry (optional) | `evaluate.py foundry <skill folder>` | When `.env.local` defines `AZURE_OPENAI_ENDPOINT` and the user agrees: the micro-eval runner (keyless `az` login, cached responses) |
| 4. Blind judging | `evaluate.py blind <name>`, then sub-agent `HVE skill-judge` per prompt | The script orders A/B by a hash of the task id and writes the judge prompts; the judge never learns which answer used the skill |
| 5. Record and admit | `evaluate.py record <skill folder>` | Unblinds, computes lift, wins/ties/losses, worst task and overhead; applies the same gate as the harness library (lift >= 10 pp, wins or ties on 3 of 5, no task lost by more than 1 point, overhead < 20%); writes `.hve/skills-registry.json`; copies admitted skills to `.hve/skill-library/` |
| 6. Context load | `context_load.py` | Reports what the workspace now loads up front (section 3) |

Admitted workspace skills are ranked and loaded per task by the HVE creator agents together with the harness library, within the loadout budget (up to 10 skills and 2,000 tokens), and are never added to every chat.

**Trust.** In-chat answers and verdicts pass through the evaluator agent, which writes them to files; the agent is told never to edit them, and the judge is a separate sub-agent with no tools. This is weaker than the Foundry path, where the script makes every call itself. The eval records `eval_method: in-chat` or `micro` so the difference stays visible.

## 3. Context-load guardrail: how it works

**What it counts** (estimated tokens, 4 characters per token):
- every skill VS Code can discover: workspace `.github/skills`, `.claude/skills`, `.agents/skills`; the user's `~/.copilot/skills`, `~/.claude/skills`, `~/.agents/skills`; every enabled plugin (`chat.pluginLocations` in VS Code user settings and marketplace-installed agent plugins). Each skill costs its name, description and path in every request;
- always-on instruction files: `.github/copilot-instructions.md`, `AGENTS.md`, `CLAUDE.md`, and `*.instructions.md` with `applyTo: **` in the workspace and the user prompts folder (scoped `applyTo` files are not counted);
- the agent prompt, when `--agent "<name>"` is given;
- MCP tool schemas, as an estimate per configured server (workspace and user `mcp.json`; real schemas are known only at runtime).

Not counted: VS Code's own system prompt and built-in tool schemas.

**What it reports:** total always-on tokens; share of the model's context window (`--context-tokens`, or 128K, 200K and 1M when unknown); the split by kind; the 10 largest contributors; duplicate skills (same name, or descriptions sharing at least half their word stems); skills never measured with a paired evaluation. Saved to `.hve/context_load.json`.

**When it warns:** when the total grew at least 20% since the last check, or takes at least 10% of the (smallest given) context window. Both are relative and live in `skills/categories.json` (`context_load`). The warning states the cost per request and the fixes: move rarely used skills into the HVE library (loaded per task, evaluated first), merge duplicates, narrow `applyTo`, disable unused plugins or MCP servers. It never changes anything itself.

## 4. When it runs and how to invoke it

| Trigger | How | Runs |
|---|---|---|
| On demand, any HVE agent | type `/check-context-load` in chat | context load |
| On demand, onboarding a skill | pick agent `HVE skill-evaluator` (Session Target: Local) and give the skill folder | static check, tasks, paired answers, blind judging, admission, then context load |
| Setup | Command Palette: **Frontier HVE: Set up** | context load; a notification shows the total, the share and any warnings, with "Show report" |
| Delivery close-out | automatic in `delivery-coach` section 6 (HVE creator agents, participatory delivery) | context load; warnings are part of the final report |
| Terminal | `python <runtime>/tools/skills/context_load.py [--agent "<name>"] [--context-tokens <n>]` or `python <runtime>/tools/skills/evaluate.py static|blind|record|foundry ...` | either tool directly |

`<runtime>` is the extension's runtime folder; HVE agent instructions name `<runtime>/tools` as the harness tools folder (`<tools>` in the skills). In this repository use `tools/skills/...` directly.

## 5. First measurement (this development window)

`context_load.py --agent "HVE creator"` in this repository: 11,632 always-on tokens (9.1% of 128K, 5.8% of 200K) from 42 discoverable skills (6,238 tokens), instructions (910), the agent (1,484) and two MCP servers (3,000, estimated). It found 9 duplicate skills: the harness-assist plugin is registered here both from the repository and through the installed extension, so every plugin skill is announced twice. Remove the repository entry from `chat.pluginLocations` in windows where the extension is installed. 33 of the 42 skills have never been measured (mostly the Azure skills plugin and our own plugin skills).

## 6. Limits

- Token counts are estimates (characters / 4); MCP cost is a flat estimate per server.
- Skill discovery follows the documented folders; settings in other VS Code profiles or editors are not read.
- The in-chat evaluation costs the user's Copilot quota (about 15 sub-agent calls per skill) and depends on the chat model chosen.
- Duplicate detection is lexical; two skills can overlap in purpose with different words.
