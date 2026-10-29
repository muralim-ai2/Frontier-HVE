# Mission Control

Mission Control is the Frontier HVE sidebar (marked **Early release**: features may change). Click the **HVE icon in the Activity Bar** (the left edge of VS Code) to see what the agent is doing right now, with the **Harness files** pane below it; any page link opens the dashboard in the editor (**Frontier HVE: Open Mission Control** does too). It ships inside the Frontier HVE extension; there is nothing else to install.

## Asks and chats

An **ask** is one distinct piece of work within the project, not one chat. Its folder `.hve/asks/<YYYYMMDD-HHMM>-<slug>/` (UTC time, lowercase hyphenated name) holds `request.md`, `contract.json`, `plan.md` and `loop/`, and its evidence and other artifacts accumulate there. `active.json` points to the ask agents, hooks and guards currently work on. Features, progress, tracker and state stay shared across the project under `.hve/project/`; a new ask does not start a new project.

One ask can have many chats. Mission Control links a chat to an ask when the chat:

| How | Shown as |
|---|---|
| Ran `lifecycle.py contract …` and the ask with that name was created within minutes | created it |
| Ran `lifecycle.py open <ask-id>` (a follow-up that reuses the folder) | reopened it |
| Edited a file in the ask's folder | edited its files |
| Was the first chat started after **New ask** or **New chat for this ask** | opened for it here |
| Was the chat in use when you chose **This chat session** for a new ask | continued here |
| Was linked by you (**Link to this ask**) | linked by you |

Links made here are kept in this window's Mission Control state; they never change the harness files. Chats with no link are listed under **Chats not linked to any ask**.

## Where the live view comes from

| Source | What it gives | Where |
|---|---|---|
| Copilot Chat's transcripts of this window | Each chat's status (working, waiting for your answer, idle), its current step, its to-do list, every file it reads or edits, every command with its explanation, its messages, failed tool calls, and the asks it created, reopened or edited | VS Code's workspace storage for this window, `GitHub.copilot-chat/transcripts/` (Settings shows the folder); the 30 most recent chats, read incrementally |
| The harness files of the ask | The ask, its plan and sign-offs, stages, decisions, skills, its folder; the project's feature checks with recorded evidence | `.hve/project/`, `.hve/asks/<ask>/` |
| The harness run files of the chat | The error guard's failed commands and pause, the skill load against the guideline, guard alerts | `.hve/runs/<chat>.*` |
| Research telemetry, when on | Model calls, input, cached and output tokens per model, AI units for the chat | the telemetry export (`.hve/runs/copilot-otel.jsonl`) |

Mission Control updates within a second of any of these files changing while a view of it is visible; a hidden view does no work and catches up when shown. A tool call whose result Copilot never records (it happens, for example with `view_image`) shows as stopped once the agent answers or you write again, so **Now** moves on to the next step instead of sticking on it. A read, view, edit or search that reports nothing for a minute also shows as stopped (commands, sub-agents and questions can run longer), and a chat with no activity for five minutes is idle. Relative times ("2 min ago") keep ticking. Viewing never writes to the project, runs a check, or starts an agent.

## The sidebar

From top to bottom: the live status chip; **New ask**; an ask carried over from another workspace, if any; the **ask dropdown** (every ask of the project, newest first, the active one marked "active"); when you view an ask that is not active, a notice with **Make active**; the ask card (project, a short title, agent, stage, how many chats, to-do progress; click for the full activity); **Needs you** (the agent is waiting for an answer in Chat, the error guard paused it or the last commands failed, the plan is a draft or was changed, items are ready for sign-off, the skill load is over the guideline); **Now** (the current step of the ask's latest chat, and its to-do list); **Recent** (the last six steps); links to the nine pages with a short status each; and the research telemetry switch.

Choosing an ask in the dropdown only changes what Mission Control shows. **Make active** asks you to confirm, then runs `lifecycle.py open <ask-id>`: agents, hooks and guards then work on that ask, and the ask you leave stays on disk with its unfinished items. Sign-off is available only for the active ask.

## The Harness files pane

Below Mission Control in the same sidebar, **Harness files** shows everything under the workspace's `.hve/` and `.harness/` folders as a normal VS Code tree: drag the divider to resize it, collapse it, or use **Collapse All**. `.hve/`, `.hve/asks/` and the active ask's folder open by themselves; ask folders are listed newest first with the ask's title, and the active one is marked "active". Every file and folder is listed, including asks without a contract, loose files an agent left in `.hve/asks/`, run records in `.hve/runs/`, skills, project state and loop evidence in `.harness/`. Click a file to open it. The pane updates when these folders change, even while Mission Control is hidden. Links (symlinks, junctions) are listed but never opened. A folder with more than 500 entries shows the first 500 and a note. If an ask's `contract.json` cannot be read, the pane says so at the top and the files stay browsable. With no `.hve/` or `.harness/` yet, the pane explains that and offers **New ask**.

It only shows files: it does not create an ask for work an agent did without one.

## New ask

1. **Title** (box 1 of 2): a short name such as "Dog profile badges" or "Investor pitch deck", 3 to 80 characters. It names the ask's folder and is what Mission Control shows.
2. **What it should deliver** (box 2 of 2, optional): one or two sentences, for example "Come up with 3 creative ideas for the feed and build them". They help the harness tell a follow-up from new work or a different project; with only a title it cannot tell a different project. Detail, files and screenshots go in the chat afterwards.
3. The harness checks where it lands (`lifecycle.py where`), as the agents do:

| The harness finds | Mission Control asks | Then |
|---|---|---|
| A different project, for example a trading platform or a Facebook-style app in the Pawstagram workspace | **Start in a new workspace…** (recommended) or **Keep it in this project**, with the harness's reason | A new workspace: pick an empty folder or make one with **New folder** (it must be outside this workspace). It opens in a new window, whose Mission Control offers **Start the ask** with your title and description filled in. Nothing is created here |
| A follow-up to the open ask | **Continue the open ask** or **Create a separate ask** | Continue: no new folder; the chat opens with a follow-up message |
| New work in this project, or a first ask | **Create ask**, or **Change folder name…** | The harness writes `.hve/asks/<UTC date-time>-<name>/` and the ask becomes active; the open ask stays on disk. A name already used in the same minute fails instead of overwriting |

4. **Which chat**: for a new ask, **New chat session** (recommended for unrelated work; the agent does not carry the earlier conversation) or **This chat session** (keep going in the chat you were using; it is linked to the new ask). For a follow-up, **The ask's own chat** (recommended; it reopens with its full history) or **New chat session**. With only one option there is no question.
5. The chat opens with the **Frontier HVE Collab** agent selected (a new chat is a **Local** session), the ask's `request.md` and `plan.md` attached, and a short starter message filled in: the title, your description, "if you are an HVE agent, use this ask and do not create another; otherwise ignore this", and to ask you for references first. **The message is not sent**: edit it, add detail, drag in files or screenshots, then send it. A notification offers **Attach files…** to pick references.

If an ask's files were deleted while the project still lists it, Mission Control says so and New ask first offers **Forget and continue**: the harness (`lifecycle.py forget`) removes it from the project record and as the active ask, and removes its folder if empty. It refuses an ask that still has its contract or owns features.

A carried-over ask waits in the new folder's sidebar (**Start the ask** or **Not now**) for a day. **New chat for this ask** (on Live, for the active ask) opens a new chat session straight away with a message to pick the ask up again. A new chat session is linked to its ask when you send the first message (within an hour).

VS Code starts a new chat in the chat view that last had focus, and first asks to keep or undo the previous chat's unaccepted edits; if you cancel that, the earlier chat stays and Mission Control keeps waiting for the new one.

## The dashboard

| Page | Shows | You can |
|---|---|---|
| Live | Needs you; the chats of the ask (how each is linked, status, last activity) and the chats not linked to any ask; for the chosen chat: the current step and to-do list, turns, tool calls, commands, files changed and failed tool calls, model use and AI units when telemetry is on, the error guard's failed commands, the files the agent changed, and the whole activity, filterable (all, edits, commands, conversation, problems) | Choose a chat; **New chat for this ask**; **Link to this ask**; open a changed file beside the dashboard |
| Plan | Where the plan stands (not written, draft, agreed, changed since agreed), the plan as formatted text (headings, lists with tick boxes, tables, code), the sign-off of each milestone and task, the options (output evaluation), and the generated skills and tools section | **Edit plan** opens `plan.md` in an editor beside the dashboard; the view updates when you save. **Accept** or **Request changes** with a note (active ask only) |
| Progress | The ask's stages with their persona and status; the project's feature checks with their recorded exit code and the ask each came from; evidence files; recorded decisions; evaluation reports (`.hve/evaluations/`); the contract, `provenance.md`, plan and request. **Experimental:** a model summarizes where the ask stands in three bullets | Open any of these files; Summarize |
| Files | The ask's folder as a tree: folders first, what each harness file is, size and last change; top folders open, your open and closed folders remembered | Open any file beside the dashboard; **Show in Explorer** |
| Other asks | Every ask of the project besides the one on screen, with only its chat status (waiting, working, idle) and last activity. One ask is active at a time; asks that must run at the same time need their own workspace or git worktree | **Track** shows that ask's details on Live |
| Telemetry | One chat at a time, picked from a list grouped by ask: its agent, execution mode (Local) and model from VS Code's own session record; turns, tool calls, skills used and their tokens, prompt and chat tokens, thinking tokens (research telemetry only); total tokens and AI units only for chats recorded with research telemetry on. **Experimental:** pick a Copilot model and a standard question (did it start sub-agents to explore different paths, where it looped, where it got stuck, what it decided without asking, which errors it worked around, what filled its context, whether it followed the plan) or your own; it reads the activity log and answers in three bullets. **What fills the context window:** files read (sized from the files), skills, images, edits, commands, searches, sub-agents, web pages, questions, messages and thinking, largest first | Pick a chat; analyze with a model; turn research telemetry on |
| Visuals | The solution map (built when, by the bundled map tool in seconds) and the clickable infographic | **Build** or **Refresh the map**, **Open the map** in its own tab; **Make an infographic** opens a Local chat with the skill and your subject filled in |
| Skills & packs | The ask's skills with why each was chosen and its tokens against the guideline, the skills loaded in the chat shown on Live, the always-on harness skills (for example `wow-uplift`), and the expertise packs installed for you | Open a skill's `SKILL.md`; **Install a pack…** and **Manage packs…** (each says what it does; the pack list refreshes afterwards) |
| Settings | The folder followed, the extension version, the Python launcher, the loop guard mode, where live activity comes from | Change folder; research telemetry switch; **Set up this workspace**; **Install for other tools** |

Accept needs finished work, a recorded passing check for feature tasks, and an agreed plan. Edited plan tick boxes must be recorded by the agent first. Sign-offs go through the guarded review commands (see [Ways of working](Ways-of-Working.md)): if the ask, plan or evidence changed after the screen was drawn, the action stops with "Workspace state changed" and the screen refreshes. Accepting does not push, merge, advance a stage or mark a tracker item `validated`. Mission Control never writes into the Chat input.

## Research telemetry

**Prune data…** (under the switch, when the export has data) archives the export to a compressed `otel-archive-<time>.jsonl.gz` beside it and empties it, or deletes all records, after you confirm. The switch turns Copilot's telemetry export on (Frontier HVE first warns that it records full chat content) or off. The agents no longer ask about it. When on, Mission Control shows token use and AI units for each new chat, and the ask report (`provenance.md`) measures cost, tokens, latency and cache, and reminds you to turn it off.

## Requirements and limits

- A trusted, local workspace folder. Python 3.11+ on PATH (`python`, `python3` or `py -3`) for New ask, Make active, sign-offs and the pack list; the views work without it.
- Live activity reads Copilot Chat's transcript files. If their format changes in a Copilot update, Needs you shows "Mission Control cannot read the live activity" with the reason, and the ask views keep working.
- Chat links come from what the chat ran or edited. A chat that works on an ask without creating, reopening or editing it, or that ran the lifecycle script through a variable set in an earlier command, is listed as not linked until you link it.
- With several workspace folders, choose one with **Frontier HVE: Select Mission Control workspace**. Set-up and pack buttons act on the first folder of the window, so they refuse another selection; open that folder in its own window.
- The dropdown lists up to 200 asks. The Files page shows up to 400 entries and six folder levels and says when it stops; use **Show in Explorer** for the rest. Links (symlinks, junctions) inside an ask are listed but never opened. Evidence previews are limited to 8 MB per file and 500 files. Malformed state files are shown as errors.
- The sign-off guard is optimistic: it rejects stale screens, but it is not a lock against an agent editing the same ask at the same moment.

## Files

| File | Role |
|---|---|
| `extension/ui/mission-control.js` | Views, file watchers, refresh, the ask on screen, commands |
| `extension/ui/ask-flow.js` | New ask (title, description, scope check, new-workspace handoff), choosing and opening the chat with its starter message |
| `extension/ui/actions.js` | Make active, linking chats, sign-offs, opening files, harness commands, with their confirmations |
| `extension/ui/asks.js` | The project's asks, an ask's folder tree, the folder name, saved request, scope text and starter message of a new ask, the carried-over ask |
| `extension/ui/chats.js` | This window's chats, read incrementally, and the asks each one is linked to |
| `extension/ui/activity.js` | Live activity of one chat from its transcript, run files and telemetry |
| `extension/ui/insights.js`, `analysis.js`, `media/telemetry.js` | The Telemetry tab: the summary, what fills the context, the experimental chat review and progress summary |
| `extension/ui/extras.js` | Pruning research telemetry, building and opening the solution map, the infographic chat |
| `extension/ui/harness-tree.js` | The Harness files pane: `.hve/` and `.harness/` as a native tree |
| `extension/ui/workspace-state.js`, `file-access.js` | Read-only, bounded reads of `.hve/` state and the plan of the ask on screen |
| `extension/ui/workflow.js`, `lifecycle-cli.js` | Creating and reopening asks, sign-offs and the pack list through the bundled tools (allowlisted operations only) |
| `extension/ui/media/` | The webview: `views.js` (sidebar and ask dropdown), `pages.js` (dashboard pages), `markdown.js` (plan rendering), `vnode.js` (tags and attributes from an allowlist, text never parsed as markup), `app.js`, `app.css` |
| `tests/mission-control/` | Unit and integration tests (`node --test "tests/mission-control/*.test.js"`), the release check, and `preview.js` for a browser preview built from a workspace and its transcripts |
