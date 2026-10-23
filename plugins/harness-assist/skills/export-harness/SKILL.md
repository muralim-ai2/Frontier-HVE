---
name: export-harness
description: Install the Frontier HVE agents, skills and guard hooks for Copilot CLI, the Copilot cloud agent, Claude Code, Cursor or Codex, and connect Azure DevOps through Microsoft's Azure DevOps MCP server.
---

# Export the harness

Run from the workspace root; `<tools>` is the harness tools folder named in your agent instructions. The full guide (prerequisites, per-client start, Azure DevOps sign-in, guards per client, troubleshooting) is `<tools>/../docs/wiki/Adapters.md`; read it for any question this skill does not answer.

1. Ask with the ask-questions tool which harnesses to install for (Copilot, Claude Code, Cursor, Codex, Copilot cloud agent), at which scope (user: every workspace, nothing committed; project: this repository only), and whether to connect Azure DevOps (organization name).
2. For each harness run `python <tools>/adapters/export.py <copilot|claude|cursor|codex> --user` (user scope; `copilot` is user scope only) or `python <tools>/adapters/export.py <claude|cursor|codex|cloud> . [--ado <organization>]` (project scope; `cloud` writes `.github/` for the user to commit). To connect Azure DevOps in VS Code only, run `python <tools>/adapters/export.py vscode . --ado <organization>`.
3. Show each printed `invoke` line and `gaps` list verbatim. Existing files that Frontier HVE did not write are never overwritten; if the script stops on one, show its message and stop.
4. Tell the user the runtime is a copy of the harness (`~/.hve/runtime/` at user scope, `.hve/runtime/` or `.github/hve/runtime/` at project scope): rerun the export after updating the extension.
