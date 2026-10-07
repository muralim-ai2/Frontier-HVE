# Agent Instructions

## Wiki

How-to pages for users and agents are in `docs/wiki/` (start at `Home.md`). For using the harness in Claude Code, Cursor or Codex CLI, or connecting Azure DevOps, read `docs/wiki/Adapters.md`.

## npm registry on Microsoft-managed devices

Direct access to `https://registry.npmjs.org/` is blocked. Before installing
npm packages:

1. Check for a repository `.npmrc`.
2. Run `npm config get registry`.
3. If `.npmrc` configures an Azure Artifacts feed, preserve and use it.
4. If no repository-specific registry is configured, run:
   `npm config set registry https://packagefeedproxy.microsoft.io/npm/`
5. Run `npm config get registry` again and confirm the effective registry
   before installing dependencies.

Do not overwrite a repository or team-specific Azure Artifacts registry with
the general Microsoft Central Feed Services proxy.
