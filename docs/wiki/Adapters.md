# Adapters: Frontier HVE in Claude Code, Cursor, Codex and Azure DevOps

Use the Frontier HVE agents, skills and guard hooks outside VS Code. Connect Azure DevOps through Microsoft's Azure DevOps MCP server.

> **Status:** built and protocol-tested (`tests/test_adapters.py`). Nobody has run it in a live Claude Code, Cursor or Codex session yet, and the Azure DevOps server has not been started from this setup. Report what fails under tracker issue `N27`. Decision: `D-042`. Research note: `research/findings/phase-10-adapters.md`.

## At a glance

| Client | What you get | Start the creator agent | Hooks live in | Hook scope |
|---|---|---|---|---|
| Claude Code | `.claude/agents/hve-*.md`, `.claude/skills/`, `.mcp.json` | `claude --agent hve-creator` | the agent file | only while that agent runs |
| Cursor | `.cursor/skills/` (agents as skills), `.cursor/hooks.json`, `.cursor/mcp.json` | `/hve-creator` in Agent chat | `.cursor/hooks.json` | every agent in the project |
| Codex CLI | `.agents/skills/` (agents as skills), `.codex/hooks.json`, `.codex/config.toml` | `$hve-creator` | `.codex/hooks.json` | every session in the project |
| VS Code | `.vscode/mcp.json` (Azure DevOps only; agents come from the extension) | pick **HVE azure-devops** | the agent file | only while that agent runs |

Every client gets three agents:
- **hve-creator:** the verified feature loop with guards.
- **hve-single:** one agent, no sub-agents.
- **hve-azure-devops:** work items, pull requests and builds.

It also gets the harness skills: `delivery-coach`, `feature-checklist`, `run-tests`, `code-review`, `parallel-options`, `explain-walkthrough`, `prototype-guardrail`, `recommend-skills` and `check-context-load`. `pr-push` stays in VS Code because it needs the GitHub Pull Requests extension.

## Before you start

- **Frontier HVE extension 0.4.0 or later:** installed in VS Code. Cursor can install the same VSIX. The exporter and the harness runtime ship inside it, at `<extension folder>/runtime/` (for example `~/.vscode/extensions/muralim-ai2.frontier-hve-<version>/runtime/`). In this repository, run `python extension/build.py` first and use `extension/runtime/`.
- **Python:** 3.11 or newer on `PATH` as `python`. Every hook runs `python`.
- **For Azure DevOps:**
  - Node.js 20 or newer.
  - An account with access to the organization.
  - On Microsoft-managed devices, an npm registry that works. Check `npm config get registry`; the general proxy is `https://packagefeedproxy.microsoft.io/npm/`.

## Export

**From chat:** pick an HVE agent in VS Code and type `/export-harness`. The agent asks which clients to export to and the Azure DevOps organization, runs the exporter and shows how to start each client.

**From a terminal**, in the project root:

```powershell
$ext = Get-ChildItem "$HOME/.vscode/extensions/muralim-ai2.frontier-hve-*" | Sort-Object LastWriteTime | Select-Object -Last 1
$hve = "$($ext.FullName)/runtime/tools/adapters/export.py"
python $hve claude . --ado contoso     # Claude Code (+ Azure DevOps)
python $hve cursor . --ado contoso     # Cursor
python $hve codex  . --ado contoso     # Codex CLI
python $hve vscode . --ado contoso     # Azure DevOps for VS Code only
```

`--ado` is optional for `claude`, `cursor` and `codex`, and required for `vscode`. The exporter prints a JSON report with these fields:
- `written`: every file and folder it created or updated.
- `invoke`: how to start the agents.
- `gaps`: what does not work in that client.
- `guide`: this page inside the copied runtime.

What it writes:
- **`.hve/runtime/`:** a copy of the harness (hooks, loop tools, skill library, licenses). Every client's hooks run from here.
- **`.hve/runs/` and `.hve/user_profile.json`:** the state the hooks read. An existing profile is kept.
- **The client's agent, skill, hook and MCP files**, as listed in the table above.

Safety rules:
- A hooks file that Frontier HVE did not write is never overwritten. The export stops and names the file; merge it by hand.
- MCP files are merged: only the `ado` entry is added or replaced.
- The organization name must be letters, digits and hyphens.
- Running the export again is safe.

## Use the agents

### Claude Code
1. Run `claude --agent hve-creator`. The header shows `@hve-creator`.
2. Accept the workspace trust prompt. Until you do, Claude Code skips the agent's hooks.
3. To delegate to the other agents, use `@"hve-single (agent)"` or `@"hve-azure-devops (agent)"`. Skills appear under `/`.
4. To make the creator the default for this project, add `"agent": "hve-creator"` to `.claude/settings.json`.

### Cursor
1. Type `/hve-creator` in Agent chat for one message. To keep it on for the whole session, press **Alt+Enter** on it (Custom Mode).
2. The hooks in `.cursor/hooks.json` apply to every agent chat in this project. Check them in **Customize → Hooks**; the Hooks output channel shows errors.
3. If you also exported for Claude Code, Cursor loads `.claude/skills/` as well and lists each skill twice. Keep one export per project, or turn off **Settings → Agents → Third-Party Imports**.

### Codex CLI
1. Start `codex` from the project root. Project hooks run in the session directory and use `.hve/runtime/...` relative paths.
2. Trust the project. Then open `/hooks`, then review and trust the Frontier HVE hooks. Codex skips untrusted hooks.
3. Type `$hve-creator`, `$hve-single` or `$hve-azure-devops`, or pick them from `/skills`. These skills are never invoked automatically.

## Azure DevOps

The adapter uses Microsoft's official server, [`@azure-devops/mcp`](https://github.com/microsoft/azure-devops-mcp) (MIT). It loads only the `core`, `work`, `work-items`, `repositories` and `pipelines` tool groups, which keeps the tool list and its context cost small.

**Connect:**
1. Export with `--ado <organization>` for your client.
2. Start the `ado` server:
   - **VS Code:** MCP view.
   - **Claude Code:** `/mcp`.
   - **Cursor:** **Settings → Tools & Integrations**.
   - **Codex:** restart; check with `codex mcp list`.
3. The first tool call opens a browser to sign in with a Microsoft account that can access the organization.

**Other sign-in methods:** add them to the `ado` server's `args` in the client's MCP file. Never put tokens in a config file.
- `"--authentication", "azcli"` uses your `az login` session.
- `"--authentication", "env"` uses the Azure credential chain.
- `"--authentication", "pat"` reads `PERSONAL_ACCESS_TOKEN` from the environment.

Microsoft also offers a hosted remote server (`https://mcp.dev.azure.com/<organization>`, type `http`). The exporter does not configure it, because the remote server cannot be limited to tool groups.

**The HVE azure-devops agent:**
- **Feature list to work items:** one work item per feature in `feature_list.json`. The check command becomes the acceptance criterion.
- **Status sync:** state updates from `tracker.json`, with the check command and its exit code as a comment.
- **Pull requests:** for feature branches you ticked, linked to their work items. It never pushes.
- **Builds:** latest pipeline result, failing stage and first error line.

Every write is listed first and asked with an `ado-write` question; only ticked changes are made. It never deletes work items, abandons pull requests or edits pipelines.

Example prompts:
- `List ADO projects`
- `Create work items for the features in feature_list.json in project Contoso`
- `Sync the tracker status to the work items`
- `Why did the last build on feature/login fail?`

## What the guards do in each client

| Harness behaviour | VS Code | Claude Code | Cursor | Codex |
|---|---|---|---|---|
| Block edits of `feature_list.json`, `progress.txt`, `tracker.json`, `.harness/` | yes | yes | yes | yes (also `apply_patch`) |
| Block force pushes, unticked pushes and git-hook bypass | yes | yes | yes | yes |
| Module-size feedback (files over 500 lines) | yes | yes | yes, as context | yes |
| Victory check when the agent stops with failing features | yes | yes | yes, as a follow-up message | yes |
| Escalation stops the agent | yes | yes | denies tools only | denies tools only |
| Skill loadout notice (which library skills to read) | yes | yes | no | yes |
| User profile at session start | yes | yes | yes | yes |
| Harness challenges on wasteful prompts | yes | yes | no | yes |
| Context for sub-agents | yes | yes | no | yes |
| Ticks in ask-questions recorded (manual checks, choices) | yes | yes (assumed answer format) | no | no |
| Prototype guardrail after edits | yes | yes | yes | yes |

## Update, re-export, remove

- **After updating the extension:** run the export again. `.hve/runtime/` is a copy and does not update itself.
- **Share with your team:** commit the agent, skill and hook files if you like. They point to `.hve/runtime/`, which is git-ignored, so each clone runs the export once.
- **Remove:** delete `.hve/runtime/`, the paths listed in `written`, and the `ado` entry in the MCP file.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Claude Code ignores the hooks | Folder not trusted, or Claude was not started with `--agent` | Accept the trust prompt; start `claude --agent hve-creator` |
| `python` not found in hook errors | Python is not on `PATH` for the client | Install Python 3.11+ and restart the client |
| Hook error `...skills.json missing: the UserPromptSubmit skill_loader hook did not run` | The hooks were added mid-session | Send a new prompt, or start a new session |
| Cursor blocks every tool call | Cursor may treat an empty `preToolUse` response as invalid (unverified) | Report under `N27`; meanwhile remove the `preToolUse` entries from `.cursor/hooks.json` |
| Codex runs no hooks | Hooks not trusted, or Codex was started in a subfolder | `/hooks` → trust; start Codex in the project root |
| Export stops: `... was not written by Frontier HVE` | You already have your own hooks file | Merge the entries from a scratch export by hand |
| Export stops: `... is not a Frontier HVE extension folder` | It was run from `.hve/runtime/` | Run the copy in the installed extension, or `extension/runtime/` after `python extension/build.py` |
| No `ado` tools | Server not started, sign-in not completed, or npm cannot reach the registry | Start the server; sign in; check `npm config get registry` |
| `npm error ... ECONNRESET` | Network or proxy | Fix the registry or network, then start the server again |
| Every skill listed twice in Cursor | Both the Claude Code and Cursor exports are in one project | Keep one export, or turn off Cursor's third-party imports |

## How it works (maintainers)

- **`tools/adapters/export.py`** reads the VS Code agent templates in `extension/agents/`, including their hooks, so all clients share one definition. It then writes each client's native files.
- **`hooks/agent_compat.py <client> <script> [KEY=VALUE ...] [-- args]`** runs any harness hook unchanged in another client:
  - **Tool names:** `Bash`/`PowerShell`/`Shell` → `run_in_terminal`, `Write` → `create_file`, `Edit` → `replace_string_in_file`, `Read` → `read_file`, `AskUserQuestion` → `vscode_askQuestions`.
  - **Fields:** `file_path` → `filePath`.
  - **Cursor:** event names and `conversation_id` are mapped.
  - **Stop:** a timestamp is added.
  - **Responses:** mapped back to each client's format. Claude and Codex get a top-level Stop `decision`. Codex gets no `continue` on PreToolUse, because Codex would let the tool run. Cursor gets `permission`, `agent_message`, `additional_context` and `followup_message`.
  - **Environment:** what VS Code sets per hook (`HARNESS_PROJECT`, `HARNESS_STOP_POLICY`, `HARNESS_SKILLS_MIN_STATUS`) is passed as `KEY=VALUE` arguments.
- **Tests:** `python tests/test_adapters.py` exports all four targets into a temp folder. It then runs the exported hook commands with each client's documented payloads.
- **New client:** add its skill folder to `SKILL_DIRS`, its event names, its hook file format in `hooks_file`, its payload and response mapping in `agent_compat.py`, and a test with that client's documented payloads.
