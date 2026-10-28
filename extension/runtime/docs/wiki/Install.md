# Install

Frontier HVE ships as one VS Code extension (VSIX). Installing it is the only required step.

## Requirements

| Need | Why | If missing |
|---|---|---|
| VS Code with GitHub Copilot Chat | Runs the agents. Current VS Code includes it; on older versions install **GitHub Copilot Chat** | The extension and Mission Control still load; the HVE agents cannot run until Copilot Chat is enabled |
| Python 3.11+ on PATH as `python`, `python3` or `py -3` | Runs the guard hooks and the harness tools (feature loop, evaluation, templates) | Agents that need it show **(Needs Python)** and tell you so; a status bar item says *guards off* |
| Git | The feature loop commits each verified feature | `loop.py init` stops with an error |

## Install

1. Get `frontier-hve-<version>.vsix` (from a release, or build it, see below).
2. Extensions view → `...` → **Install from VSIX...**, or `code --install-extension frontier-hve-<version>.vsix`.
3. Click **Reload Window** when asked.
4. Open your project folder, open the Chat view, start a **new chat with Session Target: Local**, and pick an **HVE** or **Frontier** agent ([Agents](Agents.md)). How a piece of work then runs: [Ways of working](Ways-of-Working.md). The **HVE icon in the Activity Bar** opens [Mission Control](Mission-Control.md).
5. For other harnesses (Session Target **Copilot**, Copilot CLI, the Copilot cloud agent, Claude Code, Codex, Cursor), run **Frontier HVE: Install for other harnesses** ([Adapters](Adapters.md)).

On activation the extension finds Python, renders the agents and skills into its storage with that Python launcher and the runtime path, and registers them in `chat.pluginLocations`. It does this again after an update or when Python appears. The hooks create `<workspace>/.hve/` the first time they run.

Optional: **Frontier HVE: Set up** (Command Palette) asks how you prefer to build (assisted or pro mode), offers to add `.hve/` to `.gitignore`, and reports how many tokens load into every request.

## Without Python

Install Python 3.11+ (the warning links to python.org), make sure a new terminal runs `python --version`, `python3 --version` or `py -3 --version`, then run **Frontier HVE: Set up** and reload. Until then the agents run without guards and say so; nothing is skipped silently.

## Check that it works

After a chat, run from the workspace root:

```
python <extension>/runtime/tools/observe/provenance.py <agent file> latest --require skills templates
```

`<extension>` is the installed extension folder (`~/.vscode/extensions/<publisher>.frontier-hve-<version>`); the rendered agent files are in the extension's storage under `plugin/com.github.copilot/agents/`. It lists each harness component the agent declares as `verified`, `not-exercised` or `failed`, saves `.hve/runs/<session>.provenance.json` and exits 1 when a component failed or a required one did not run. Example: after asking `HVE product-manager` for a PRD, `templates` shows which template the PRD came from.

## Update

Install the newer VSIX and reload. The agents are re-rendered automatically.

## Build the VSIX (maintainers)

From the repository: `python extension/build.py`, then in `extension/`: `npx --yes @vscode/vsce package --skip-license --allow-missing-repository`. On Microsoft-managed devices set the npm registry first (see `AGENTS.md`).

Release check: `npm --prefix extension ci`, then set `HVE_VSCODE` to a VS Code executable and run `npm --prefix extension run test:release`. It type-checks Mission Control, builds and packages the VSIX into a temporary folder, checks the package keeps every agent, skill and runtime file and adds Mission Control, then installs it into a throwaway profile, starts VS Code with Copilot Chat disabled and checks that the extension activates by itself, renders its agents and opens Mission Control. Your own profile and extensions are not used. The check prints and keeps its run folder (`hve-release-*` in the temp folder, about 25 MB) for inspection; delete it when done. Mission Control's unit and integration tests: `node --test "tests/mission-control/*.test.js"`. For a visual check, `node tests/mission-control/preview.js <workspace> <transcripts folder> [telemetry export or -] [time]` writes a browser preview built read-only from a real workspace and its chat transcripts.

## Troubleshooting

| Symptom | Fix |
|---|---|
| No HVE agents in the picker | Reload the window; check `chat.pluginLocations` lists the extension's `plugin` folder. With Session Target Copilot, Claude or Codex, run **Frontier HVE: Install for other harnesses** |
| The agent says the session hooks are not running | In Local, start a new chat; in other harnesses, install them with **Frontier HVE: Install for other harnesses**. The ask contract commands work either way |
| Agents show **(Needs Python)** | Install Python 3.11+, run **Frontier HVE: Set up**, reload |
| Skills appear twice | Remove a repository `plugins/harness-assist` entry from `chat.pluginLocations` |
| Benchmark metrics needed | **Frontier HVE: Turn on research telemetry** (records full chat content; research workspaces only) |
