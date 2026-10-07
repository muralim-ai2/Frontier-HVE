---
name: export-harness
description: Export the Frontier HVE agents, skills and guard hooks to Claude Code, Cursor or Codex, and connect Azure DevOps through Microsoft's Azure DevOps MCP server.
---

# Export the harness

Run from the workspace root; `<tools>` is the harness tools folder named in your agent instructions. The full guide (prerequisites, per-client start, Azure DevOps sign-in, guards per client, troubleshooting) is `<tools>/../docs/wiki/Adapters.md`; read it for any question this skill does not answer.

1. Ask with the ask-questions tool which clients to export to (Claude Code, Cursor, Codex) and whether to connect Azure DevOps (organization name).
2. For each client run `python <tools>/adapters/export.py <claude|cursor|codex> . [--ado <organization>]`. To connect Azure DevOps in VS Code only, run `python <tools>/adapters/export.py vscode . --ado <organization>`.
3. Show each printed `invoke` line and `gaps` list verbatim. Existing files that Frontier HVE did not write are never overwritten; if the script stops on one, show its message and stop.
4. Tell the user that `.hve/runtime/` is a copy of the harness: rerun the export after updating the extension.
