# Phase 10: client adapters (Claude Code, Cursor, Codex CLI) and Azure DevOps

Date: 2026-10-07. Branch: `adapters/mm-1007`. Decision: D-042. Open issues: tracker `N27`, `N28`.

## 1. What was asked

- Keep the existing VS Code / GitHub Copilot path unchanged; add Azure DevOps, Cursor, Claude Code and Codex CLI.
- Prefer established tools (MCP servers) where they exist; otherwise build a lighter version. Give each target agents and skills the user can invoke.
- Nothing is accepted without a test that checks it, with the results recorded here.

## 2. Options considered

| Target | Options | Chosen | Why |
|---|---|---|---|
| Azure DevOps | (a) copy the source project's ADO agents, 8 ADO instruction files and 8 prompts (about 41K characters); (b) Microsoft's official Azure DevOps MCP server `@azure-devops/mcp` (MIT, 2K stars, 64 contributors, v2.10.0) | (b) plus one `HVE azure-devops` agent | Established, maintained by the product team, supports every client asked for, and its `-d` domain filter limits the tool list (context load). The source instructions would add tens of thousands of tokens and duplicate the server's tool descriptions; they stay a candidate for the skill gate later. |
| Claude Code, Cursor, Codex | (a) copy the source project's TypeScript adapter setup (`adapterSetup.ts`, 17K) into the extension; (b) a Python exporter plus one hook-protocol shim | (b) | The harness runtime is Python and already ships with the extension; the three clients read the open Agent Skills format and Claude-style hook JSON, so one exporter (229 lines) and one shim (103 lines) cover all three. |
| Agents per client | Plan text: Cursor `.cursor/rules/`, Claude `CLAUDE.md` + `hooks.json` | Claude: subagent files with frontmatter hooks; Cursor and Codex: agents exported as explicitly invoked skills | Rules and `CLAUDE.md` are always-on: they would load the creator prompt into every request (bloat, D-039). Claude subagent hooks are scoped to the agent like VS Code agent hooks. Cursor and Codex skills that are not auto-invoked cost only their description. |

OpenCode (in the plan's adapter table) was not built; it reads the same skill format and is a small follow-up if needed.

## 3. Design

- **`tools/adapters/export.py <claude|cursor|codex|vscode> <workspace> [--ado <organization>]`**, shipped in the extension runtime and invoked through the new `/export-harness` skill.
  - Copies the runtime into `<workspace>/.hve/runtime` (hooks, loop tools, skill library, source licenses) and creates `.hve/runs` and an empty user profile.
  - Copies the plugin skills except `pr-push` (needs the VS Code GitHub Pull Requests extension) and `export-harness` into `.claude/skills`, `.cursor/skills` or `.agents/skills`.
  - Renders `HVE creator`, `HVE single` and `HVE azure-devops` from the same VS Code agent templates. Hooks are parsed from `hve-creator.agent.md`, so the clients cannot drift from VS Code.
    - **Claude Code:** `.claude/agents/hve-*.md`. Hooks sit in the subagent frontmatter (exec form, `${CLAUDE_PROJECT_DIR}`). Run with `claude --agent hve-creator`.
    - **Cursor:** skills with `disable-model-invocation: true`, invoked as `/hve-creator` or kept as a Custom Mode. Hooks go in `.cursor/hooks.json` (native format).
    - **Codex:** skills with `agents/openai.yaml` `allow_implicit_invocation: false`, invoked as `$hve-creator`. Hooks go in `.codex/hooks.json`.
  - `--ado` adds the `ado` server, scoped to `core work work-items repositories pipelines`, to `.mcp.json`, `.cursor/mcp.json`, `.codex/config.toml` or `.vscode/mcp.json`.
    - The organization name is validated (letters, digits, hyphens), so it cannot inject into the configs.
    - Existing MCP files are merged.
    - Hook files the harness did not write are never overwritten.
- **`hooks/agent_compat.py <client> <script> [KEY=VALUE ...] [-- args]`** runs any existing hook unchanged. Payload mapping:
  - **Tool names:** `Bash`/`PowerShell`/`Shell` become `run_in_terminal`; `Write` becomes `create_file`; `Edit` becomes `replace_string_in_file`; `Read` becomes `read_file`; `AskUserQuestion` becomes `vscode_askQuestions`. Codex `apply_patch` keeps its name and the module guard reads its patch text.
  - **Fields:** `file_path` becomes `filePath`.
  - **Cursor events:** `conversation_id` becomes `session_id`. `preToolUse`, `postToolUse`, `beforeSubmitPrompt`, `stop` and `sessionStart` become `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop` and `SessionStart`. `tool_output` becomes `tool_response`.
  - **Stop:** adds `timestamp`; Cursor's `loop_count` becomes `stop_hook_active`.
  - **AskUserQuestion answers:** Claude's answers keyed by question text are re-keyed to headers.
  - **Working directory:** the hook runs from `CLAUDE_PROJECT_DIR`, `CURSOR_PROJECT_DIR` or Codex's `cwd`.

  Output mapping:
  - **Stop decision:** VS Code's nested decision moves to the top level for Claude and Codex.
  - **Codex PreToolUse:** `continue`/`stopReason` are dropped, because Codex fails such a hook open and would let the tool run.
  - **Cursor:** gets its native `permission`, `user_message`, `agent_message`, `additional_context` and `followup_message` fields.
  - **Codex Stop:** always answers JSON.

  Environment that VS Code sets per hook (`HARNESS_PROJECT`, `HARNESS_STOP_POLICY`, `HARNESS_SKILLS_MIN_STATUS`) is passed as `KEY=VALUE` arguments, because Claude frontmatter hooks have no per-hook `env`.
- **`HVE azure-devops` agent** (all four clients).
  - Turns `feature_list.json` into work items, syncs `tracker.json` status, proposes linked pull requests for ticked branches, and summarizes builds.
  - Every write is listed and asked with an `ado-write` question; only ticked changes are made.
  - It never deletes work items, abandons pull requests or edits pipelines.

Sources read for the formats (fetched 2026-10-07):
- Claude Code: hooks reference and subagents.
- Cursor: hooks, third-party hooks and skills.
- Codex: hooks, build skills and config reference.
- Azure DevOps MCP: README and getting started.

## 4. Test results

Command: `python tests/test_adapters.py` → `test_adapters: OK`, exit 0. The full regression run (`adapters, skills, extension, flow_plugin, loop, hooks, metrics, collect, trajectory`, `node --check extension/extension.js`) all exit 0.

Each test builds the extension, exports all four targets into a fresh temp workspace, and runs the **exported** hook commands (Claude: the frontmatter `args`; Cursor and Codex: the `hooks.json` command strings through the shell) with payloads shaped as each client's documentation specifies.

| Test | What it proves | Result |
|---|---|---|
| `test_export_structure` | Runtime and licenses copied; 9 skills per client without `pr-push`/`export-harness`, each `name` matches its folder; 3 Claude agents; the 7 hook scripts exist in the runtime and the guardrail keeps `--hook`; no `{{RUNTIME}}` left; Cursor native events (5); Cursor creator skill not auto-invoked; Codex events (6) and `allow_implicit_invocation: false`; `ado` server in all 4 MCP files with the 5 domains | pass |
| `test_export_refuses_foreign_files_and_bad_organizations` | Re-export is idempotent (one `[mcp_servers.ado]`); a hand-written `.cursor/hooks.json` is kept and the export fails with a clear message; organization `x; rm -rf /` is rejected | pass |
| `test_claude_code_hooks` | SessionStart profile context (Delivery line); UserPromptSubmit loadout; first PreToolUse announces `.hve/skills/`; `Write` to `feature_list.json` denied; `git push -f` denied; 600-line `Write` blocked by the module guard (top-level `decision`); `AskUserQuestion` answer recorded to `.harness/checks/login.json`; Stop victory check top-level; escalation sends `continue: false` | pass |
| `test_cursor_hooks` | `sessionStart` → `additional_context`; `beforeSubmitPrompt` → `continue: true`; `Write` to `progress.txt` → `permission: deny` with `agent_message`; a harmless `Read` is not denied; 600-line `Write` → `additional_context`; `stop` → `followup_message`, and none once `loop_count` > 0 | pass |
| `test_codex_hooks` | Stop with all features passing answers `{}`; `apply_patch` touching `progress.txt` during an escalation is denied **without** `continue` (Codex would otherwise fail it open); Stop victory check top-level; `SubagentStart` context delivered | pass |

## 5. What is not verified (honest limits)

- **No live client run.** `claude`, `cursor`, `cursor-agent` and `codex` are not installed on this machine. The tests prove that the exported files are well formed and that the hooks answer correctly to documented payloads. They do not prove that each client loads the files and honours every field.
- **Azure DevOps server not started.** `npm view @azure-devops/mcp` failed with `ECONNRESET` through the npm proxy (same network problem as N26). The package name, arguments and domains come from the official README and getting-started guide, not from a run.
- **Assumptions to confirm live:**
  - Claude's `AskUserQuestion` PostToolUse `tool_response` carries `answers` keyed by question text. This is documented for PreToolUse `updatedInput`, not for the response.
  - Cursor accepts an empty response from `preToolUse` as "no objection". The harness deliberately does not send `permission: allow`, which could skip Cursor's own approval.
  - The VS Code agent tool id `ado/*` selects the `ado` server's tools.
- **Known gaps by design** (printed by the exporter):
  - Cursor and Codex hooks are project-wide, not agent-scoped.
  - Cursor has no context channel on prompt submit or before a tool, so the skill loadout notice and harness challenges do not reach the model there.
  - Cursor's `subagentStart` cannot add context, so the sub-agent context hook is not exported.
  - Codex cannot stop the agent from PreToolUse.
  - `pr-push` is VS Code only.

## 6. Cost

- **Always-on tokens:** the new `export-harness` plugin skill adds one discoverable skill (about 60 tokens per request) in VS Code. The exported skills cost the same per request in each client as the plugin skills do in VS Code. The agents exported as skills add only their descriptions.
- **Code size:** 103 + 229 lines of runtime code and 214 lines of tests. No model tokens were spent.
