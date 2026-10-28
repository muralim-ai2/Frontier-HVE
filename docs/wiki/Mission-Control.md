# Mission Control

Mission Control is the Frontier HVE sidebar. Click the **HVE icon in the Activity Bar** (the left edge of VS Code) to see what the agent is doing right now; any page link opens the dashboard in the editor (**Frontier HVE: Open Mission Control** does too). It ships inside the Frontier HVE extension; there is nothing else to install.

## Where the live view comes from

| Source | What it gives | Where |
|---|---|---|
| Copilot Chat's transcript of this window | The agent's status (working, waiting for your answer, idle), its current step, its to-do list, every file it reads or edits, every command with its explanation, its messages, failed tool calls | VS Code's workspace storage for this window, `GitHub.copilot-chat/transcripts/` (Settings shows the folder) |
| The harness files of the task | The task, its plan and sign-offs, stages, feature checks with recorded evidence, decisions, skills | `.hve/project/`, `.hve/asks/<task>/` |
| The harness run files of the session | The error guard's failed commands and pause, the skill load against the guideline, guard alerts | `.hve/runs/<session>.*` |
| Research telemetry, when on | Model calls, input, cached and output tokens per model, AI units for the session | the telemetry export (`.hve/runs/copilot-otel.jsonl`) |

Mission Control updates within a second of any of these files changing while a view of it is visible; a hidden view does no work and catches up when shown. Relative times ("2 min ago") keep ticking. It only reads these files: viewing never writes to the project, runs a check, or starts an agent.

## The sidebar

From top to bottom: the live status chip; the task card (project, a short title, agent, stage, to-do progress; click for the full activity); **Needs you** (the agent is waiting for an answer in Chat, the error guard paused it or the last commands failed, the plan is a draft or was changed, items are ready for sign-off, the skill load is over the guideline); **Now** (the current step with its command or file, and the agent's to-do list); **Recent** (the last six steps); links to the five pages with a short status each; the research telemetry switch; and **New task**.

## The dashboard

| Page | Shows | You can |
|---|---|---|
| Live | Needs you; the current step and to-do list; the session's turns, tool calls, commands, files changed and failed tool calls; model use and AI units when telemetry is on; the error guard's failed commands with their output; the files the agent changed; the whole activity, filterable (all, edits, commands, conversation, problems) | Open a changed file beside the dashboard |
| Plan | Where the plan stands (not written, draft, agreed, changed since agreed), the plan as formatted text (headings, lists with tick boxes, tables, code), the sign-off of each milestone and task, the options (output evaluation), and the generated skills and tools section | **Edit plan** opens `plan.md` in an editor beside the dashboard; the view updates when you save. **Accept** or **Request changes** with a note |
| Progress | Stages with their persona and status, feature checks with their recorded exit code, evidence files, recorded decisions | Open a check's output or an evidence file |
| Skills & packs | The task's skills with why each was chosen and its tokens against the guideline, the skills loaded in the latest chat, the always-on harness skills (for example `wow-uplift`), and the expertise packs installed for you | Open a skill's `SKILL.md`; **Install a pack…** and **Manage packs…** (each says what it does; the pack list refreshes afterwards) |
| Settings | The folder followed, the extension version, the Python launcher, the loop guard mode, where live activity comes from | Change folder; research telemetry switch; **Set up this workspace**; **Install for other tools** |

Accept needs finished work, a recorded passing check for feature tasks, and an agreed plan. Edited plan tick boxes must be recorded by the agent first. Sign-offs go through the guarded review commands (see [Ways of working](Ways-of-Working.md)): if the task, plan or evidence changed after the screen was drawn, the action stops with "Workspace state changed" and the screen refreshes. Accepting does not push, merge, advance a stage or mark a tracker item `validated`. **New task** asks for the outcome and a short name, says where the task lands, and creates it after you confirm; it opens on the Plan page and no agent starts until you write to one in Chat. Mission Control never writes into the Chat input.

## Research telemetry

The switch turns Copilot's telemetry export on (Frontier HVE first warns that it records full chat content) or off. The agents no longer ask about it. When on, Mission Control shows token use and AI units for each new chat, and the task report (`provenance.md`) measures cost, tokens, latency and cache, and reminds you to turn it off.

## Requirements and limits

- A trusted, local workspace folder. Python 3.11+ on PATH (`python`, `python3` or `py -3`) for New task, sign-offs and the pack list; the views work without it.
- Live activity reads Copilot Chat's transcript files. If their format changes in a Copilot update, the Live section shows "Mission Control cannot read the live activity" with the reason, and the task views keep working.
- With several workspace folders, choose one with **Frontier HVE: Select Mission Control workspace**. Set-up and pack buttons act on the first folder of the window, so they refuse another selection; open that folder in its own window.
- Evidence previews are limited to 8 MB per file, 500 files and eight folder levels. Linked folders (symlinks, junctions) inside `.hve/` and malformed state files are shown as errors.
- The sign-off guard is optimistic: it rejects stale screens, but it is not a lock against an agent editing the same task at the same moment.

## Files

| File | Role |
|---|---|
| `extension/ui/mission-control.js` | Views, file watchers, commands and confirmations |
| `extension/ui/activity.js` | Live activity from chat transcripts, run files and telemetry |
| `extension/ui/workspace-state.js`, `file-access.js` | Read-only, bounded reads of `.hve/` state and the plan |
| `extension/ui/workflow.js`, `lifecycle-cli.js` | New task, sign-offs and the pack list through the bundled tools (allowlisted operations only) |
| `extension/ui/media/` | The webview: `views.js` (sidebar), `pages.js` (dashboard), `markdown.js` (plan rendering), `vnode.js` (tags and attributes from an allowlist, text never parsed as markup), `app.js`, `app.css` |
| `tests/mission-control/` | Unit and integration tests (`node --test "tests/mission-control/*.test.js"`), the release check, and `preview.js` for a browser preview built from a workspace and its transcripts |
