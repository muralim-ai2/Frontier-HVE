# Mission Control

Mission Control is the Frontier HVE sidebar. Click the **HVE icon in the Activity Bar** (the left edge of VS Code) to open it; **Frontier HVE: Open Mission Control** opens the larger dashboard in the editor. It ships inside the Frontier HVE extension from 0.19.0 — there is nothing else to install.

## What it shows

| Area | Shows | Source |
|---|---|---|
| Sidebar | The workspace's project, the open ask, its agent and lifecycle, and each feature marked passing | `.hve/project/`, `.hve/asks/active.json` |
| Overview | The next step, feature and review counts, the delivery stages and the last recorded decisions | the ask's `contract.json` |
| Evidence | Each feature's recorded check command, exit code and output, and the evidence files | `.hve/asks/<ask>/loop/prs/`, `attempts/`, `evidence/` |
| Approvals | Stages and tasks waiting for a human decision | the ask's checklist |
| Skills & packs, Setup | Selected skills, expertise packs, Python, loop guard mode and telemetry | the contract and existing **Frontier HVE** commands |

Viewing never writes files. Recorded results are what the loop stored, not a fresh test run, and the UI never runs a feature's check command. A feature marked passing without a recorded result is shown as such.

## What it does

| Action | What happens | Writes |
|---|---|---|
| **New task** | Asks for the outcome and a short identifier, shows where it lands (`lifecycle.py where`) and asks you to confirm the workspace | A direct-delivery ask for `HVE creator` (`lifecycle.py contract`); no agent starts |
| **Continue in Chat** | Puts a draft naming the exact ask into the Chat input | Nothing: pick the agent, review the draft and press **Send** |
| **Accept** / **Request changes** | Asks for your note, names the workspace and ask, and asks you to confirm | One human decision through the guarded review commands (see [Ways of working](Ways-of-Working.md)) |
| Setup, packs, telemetry buttons | Run the existing **Frontier HVE** commands after a confirmation | Whatever that command writes |

Accept needs finished work, a recorded passing check for feature tasks, and a synchronized plan. Edited plan checkboxes must be reconciled by the agent first. A changed ask, plan or evidence after the screen was drawn makes the action stop with "Workspace state changed"; refresh and try again. Accepting does not push, merge, advance a stage or mark a tracker item `validated`.

## Requirements and limits

- A trusted, local workspace folder, and Python 3.11+ on PATH (the same launcher the extension finds for its hooks).
- With several workspace folders, choose one with **Frontier HVE: Select Mission Control workspace**. The setup and pack buttons act on the first folder, so they refuse a different selection; open that folder in its own window.
- Evidence previews are limited to 8 MB per file, 500 files and eight folder levels. Linked folders (symlinks, junctions) inside `.hve/` and malformed state files are shown as errors.
- The guard is optimistic: it rejects stale screens, but it is not a lock against an agent editing the same ask at the same moment.

## Files

| File | Role |
|---|---|
| `extension/ui/mission-control.js` | Views, commands and confirmations |
| `extension/ui/workspace-state.js`, `file-access.js` | Read-only, bounded reads of `.hve/` state |
| `extension/ui/workflow.js`, `lifecycle-cli.js` | Task and review actions through the bundled `lifecycle.py` (allowlisted operations only) |
| `extension/ui/render.js`, `ui/media/` | Escaped HTML, styles and the webview script (strict content security policy) |
| `tests/mission-control/` | Unit and integration tests, and the release check |
