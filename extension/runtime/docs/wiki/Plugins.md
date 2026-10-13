# Plugins

Plugins add an organization's agents, skills, deliverable templates, an optional SDLC flow and optional rubrics to Frontier HVE.
They are released separately from the core: install the core first, add plugins later. Sample:
[examples/plugins/oracle-offering](../../examples/plugins/oracle-offering/README.md). Design: `docs/execution/plans/EXEC-PLAN-plugin-architecture.md`.

## For users

| Task | How |
|---|---|
| Install | **Frontier HVE: Install plugin** (organization index, folder, `.hveplugin` file, or https git URL), or a wrapper extension from the Marketplace. You confirm the publisher, hash and tools unless the organization index verified the package and its tools did not grow. |
| Manage | **Frontier HVE: Manage plugins**: enable, disable, uninstall. Reload the window afterwards so agents appear or disappear. |
| Organization index | Setting `frontierHve.pluginIndex`: a path or https URL to `{"version": 1, "plugins": [{"name", "version", "url", "sha256", "revoked"?}]}`. Install with `index:<name>@<version>`. Revoked versions are disabled on the next start. |
| Command line | `python <runtime>/tools/plugins/plugin.py inspect\|install\|list\|enable\|disable\|uninstall\|reconcile\|resolve "<prompt>"\|requirements <workspace>` |
| Workspace requirements | Commit `frontier-hve.plugins.json` at the repository root: `{"version": 1, "plugins": [{"name", "range", "source"}]}` (source as for install, for example `index:oracle-offering@1.0.0`). Opening the workspace offers to install missing plugins; a global version outside the range is reported, never changed, since other workspaces share it. |
| Other clients | `export.py claude\|cursor\|codex <workspace>` also exports enabled plugins' agents as `<plugin>-<agent>`; re-export after installing, upgrading or removing a plugin. Cursor cannot show the plugin announcement or question, so name the plugin in the prompt there. |

Plugins install globally in `~/.frontier-hve` (or `HVE_PLUGIN_HOME`), like the core, and serve every workspace. Core updates keep them.

**How the core uses them.** On each prompt, `HVE creator`, `HVE creator-flow`, `HVE creator-github` and `HVE product-manager` match the
prompt against the plugins' task patterns and keywords:

- One plugin matches: its agents (`<plugin>:<agent>`), skills, templates, flow and rubrics are announced and used.
- Several match: the agent asks you which (question `select-plugin`, multi-select, or **Core only**). Until you answer, no plugin
  agent, skill or template is used. In the same chat the answer is kept unless a new plugin matches; a new chat asks again.
- Name a plugin to skip matching: `@oracle-offering`, `oracle-offering:oracle-db-architect`, or "use the oracle plugin". Naming a
  plugin id that is not installed (for example "use the mysql-offering plugin") stops the agent so you can install it.
- **SDLC flow**: in `HVE creator-flow`, a selected plugin's flow starts automatically when it is the only one (say "core flow" for
  the default); several flows are a `select-flow` question. Without a plugin flow the core flow runs. Benchmarks always use the core flow.
- **Rubrics**: the plugin's rubrics always apply, together with the core rubrics the agent selects as applicable before scoring.
  `evidence-verification` and `safety-maintainability` always apply; the report lists excluded core rubrics with reasons.

## For plugin authors

Start with `plugin.py init <repo> --name <name> --publisher <publisher> --display-name "<Name>"`: it creates `plugin/` (a valid package
with one agent, skill, template and routing test) and `.github/workflows/release-plugin.yml`, which validates, tests, packs and attaches
the package to a GitHub release on every `v*` tag (set the repository variables `FRONTIER_HVE_REPO` and `FRONTIER_HVE_REF` to the core
repository and tag). `plugin.py test plugin` validates the package and runs `tests/routing.json`
(`{"cases": [{"prompt", "routes": true|false}]}`). Editors validate `hve-plugin.json` against `schemas/hve-plugin.schema.json`.

Layout (Markdown and JSON only; no hooks, no scripts):

```
<name>/
  hve-plugin.json       manifest (below)
  README.md, LICENSE    required
  agents/<agent>.agent.md     frontmatter: name, description, tools (subset of the manifest tools); no hooks
  skills/<skill>/SKILL.md     listed in registry.json: {"skills": [{name, description, task_categories}]}
  categories.json             optional: {"categories": {<name>: {"task_pattern": <regex>}}}, used as <plugin>:<name>
  templates/*.md              hve-template / hve-section markers, as the core templates
  flows/*.flow.json           optional SDLC flow, plus its stage instruction files
  evaluation/*.eval.json      optional plugin rubrics
  tests/routing.json          routing cases for `plugin.py test`
```

`hve-plugin.json` keys: `name`, `publisher` (lowercase kebab-case; id is `<publisher>.<name>`; `core`, `hve`, `frontier-hve` reserved),
`displayName`, `version` (MAJOR.MINOR.PATCH), `description`, `harness` (`apiVersion: 1`, `frontierHve` range such as `">=0.8.0 <1.0.0"`),
`routing` (`domains`, `keywords`, `task_pattern`, `workspace_signals` globs or `file:text`), `agents` (`name`, `file`, `capabilities`),
`skills: "registry.json"`, `templates` (kind -> `file`, `version`, and `output` with one `{slug}` for kinds the core does not have),
`tools`, optional `flows` and `evaluation`. Every file under `agents/`, `templates/`, `flows/` and `evaluation/` must be declared.

**Skills** are trusted as vetted by the publishing organization: they load as admitted, within the normal loadout budget.

**Templates.** A new kind is used as `<plugin>:<kind>` (for example `oracle-offering:assessment`). To replace a core kind, a workspace
sets its source in `frontier-hve.templates.json` to `plugin:<plugin>/<kind>@<version>`.

**Flow** (`flows/*.flow.json`): `id`, `description`, `start`, `lockChecks: true`, `stages` (each `agent` is `core:builder` or
`<plugin>:<agent>` with `instructions`), `edges` (forward edges with `evidence`; back-edges with `back: true` and `cap` 1-3), optional
`evaluation`. Forward edges may not form a cycle; every stage must reach `done`. Evidence types: `json-fields`, `check` (a command
stored in a project file, locked once approved), `feature-checks`, `structure`, `no-code-growth`, `linked-list`, `template-valid`,
`artifacts` (files written after the flow started). The core flow uses the same format: `evaluation/flows/core.flow.json`.

**Rubrics** (`evaluation/*.eval.json`): the evaluation contract format without `council` and `maxRevisionPasses` (those come from the
core), plus `coreShare` (0.2-0.5, the core rubrics' share of the score). No `command` hooks; rubric and hook ids must not reuse core ids;
rubrics may reference core hooks such as `locked-feature-checks`; `minimumScore` and `councilPasses` at least the core values.

**Release.** `plugin.py validate <folder>`, then `plugin.py pack <folder> --out dist` writes a reproducible
`<name>-<version>.hveplugin` (with `SHA256SUMS`) and prints its sha256 for the organization index or the release notes. A wrapper
VS Code extension declares `"extensionDependencies": ["muralim-ai2.frontier-hve"]` and on activation calls
`(await vscode.extensions.getExtension('muralim-ai2.frontier-hve').activate()).installPlugin(<bundled .hveplugin>, <its id>)`;
removing the wrapper uninstalls the plugin on the next start.
