'use strict';
/** New ask: a title, an optional description, the harness's scope check, the ask's creation and its chat. */
const vscode = require('vscode');
const path = require('node:path');
const { listAsks, slugFor, askRequest, scopeText } = require('./asks');
const NAME = /^[a-z0-9][a-z0-9-]{0,40}$/;

/** @typedef {import('./mission-control').MissionControl} MissionControl */
/** @typedef {{title: string, description: string}} Brief */

/** Ask for the title, then the optional description; either box can start filled in.
 * @param {Partial<Brief>} [preset]
 * @returns {Promise<Brief | null>}
 */
async function askBrief(preset = {}) {
  const title = await vscode.window.showInputBox({ title: 'New ask (1 of 2): title', value: preset.title, placeHolder: 'Title', ignoreFocusOut: true,
    prompt: 'A short name for this piece of work, for example “Dog profile badges” or “Investor pitch deck”. You describe it in the next step.',
    validateInput: value => value.trim().length < 3 || value.trim().length > 80 ? 'Use 3-80 characters.'
      : /[\p{L}\p{N}]/u.test(value) ? null : 'Use at least one letter or digit.' });
  if (title === undefined) return null;
  const description = await vscode.window.showInputBox({ title: `New ask (2 of 2): what should “${title.trim()}” deliver?`, value: preset.description,
    placeHolder: 'For example: come up with 3 creative ideas for the feed and build them', ignoreFocusOut: true,
    prompt: 'Optional. One or two sentences about the outcome. You add detail, files and screenshots in the chat next. Press Enter to skip.',
    validateInput: value => value.length > 4000 ? 'Use at most 4,000 characters.' : null });
  if (description === undefined) return null;
  return { title: title.trim(), description: description.trim() };
}

/** Collect a brief, follow the harness's recommendation (continue the open ask, or a new ask after confirmation), then open a chat for it.
 * @param {MissionControl} mc
 * @returns {Promise<void>}
 */
async function newAsk(mc) {
  const root = mc.target().uri.fsPath;
  const flow = await mc.connect();
  const brief = await askBrief();
  if (!brief) return;
  const scope = await flow.describeAsk(root, scopeText(brief));
  const open = listAsks(root).find(ask => ask.active);
  if (scope.verdict === 'continue' && open) {
    const choice = await vscode.window.showWarningMessage(`“${brief.title}” looks like a follow-up to the open ask “${open.title}”.`, { modal: true,
      detail: 'Continue that ask (same folder, plan and evidence), or create a separate ask for this work. Earlier ask folders always stay on disk.' },
    'Continue the open ask', 'Create a separate ask');
    if (choice === 'Continue the open ask') return newChat(mc);
    if (choice !== 'Create a separate ask') return;
  }
  let slug = slugFor(brief.title);
  for (;;) {
    const choice = await vscode.window.showWarningMessage(`Create ask “${brief.title}” in ${path.basename(root)}?`, { modal: true, detail: [
      scope.verdict === 'new-workspace' ? `The harness recommends a separate workspace: ${scope.why}.` : `Where it lands: ${scope.why}.`,
      `Folder: .hve/asks/<UTC date-time>-${slug}/ with your request, the contract, the plan and the loop records. Features and progress stay shared across the project.`,
      open ? `The open ask “${open.title}” stays on disk, unfinished items included, but is no longer active.` : '',
      'A Copilot Chat then opens for it. No agent starts until you send a message.'].filter(Boolean).join('\n\n') }, 'Create ask', 'Change folder name…');
    if (choice === 'Create ask') break;
    if (choice !== 'Change folder name…') return;
    const name = await vscode.window.showInputBox({ title: 'Ask folder name', value: slug, ignoreFocusOut: true,
      prompt: 'Lowercase letters, digits and hyphens. The folder name starts with the UTC date and time.',
      validateInput: value => NAME.test(value) ? null : 'Use 1-41 lowercase letters, digits or hyphens.' });
    if (name === undefined) return;
    slug = name;
  }
  mc.target();
  await flow.createAsk(root, scope.revision, slug, askRequest(brief));
  await mc.view(null);
  await newChat(mc);
}

/** Open a new, empty Copilot Chat for the active ask and link the next chat that starts to it.
 * @param {MissionControl} mc
 * @returns {Promise<void>}
 */
async function newChat(mc) {
  const active = listAsks(mc.target().uri.fsPath).find(item => item.active);
  if (!active) throw new Error('No ask is active. Create one, or make an earlier ask active first.');
  await mc.context.workspaceState.update('pendingChat', { ask: active.id, at: new Date().toISOString() });
  await vscode.commands.executeCommand('workbench.action.chat.open');
  await vscode.commands.executeCommand('workbench.action.chat.newChat');
  mc.open('live');
  void vscode.window.showInformationMessage(`A new chat is open for "${active.title}". Pick an HVE agent and describe the next step; Mission Control links the chat to this ask when you send it.`);
}

module.exports = { askBrief, newAsk, newChat };
