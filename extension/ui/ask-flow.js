'use strict';
/** New ask: a title, an optional description, the harness's scope check, the ask's creation and its chat. */
const vscode = require('vscode');
const fs = require('node:fs');
const path = require('node:path');
const { listAsks, slugFor, askRequest, scopeText, starterPrompt } = require('./asks');
const { claimsFrom, chatSessionUri } = require('./chats');
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
    if (choice === 'Continue the open ask') return pickChat(mc, open, 'follow-up', brief);
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
  const created = listAsks(root).find(ask => ask.active);
  if (!created) throw new Error('The new ask was created but is not active. Inspect .hve/asks/active.json.');
  await pickChat(mc, created, 'new', brief);
}

/** Ask which chat should work on the ask and open it; cancelling keeps the ask and says how to open a chat later.
 * @param {MissionControl} mc
 * @param {import('./types').AskSummary} ask
 * @param {'new' | 'follow-up'} kind
 * @param {Brief} brief
 * @returns {Promise<void>}
 */
async function pickChat(mc, ask, kind, brief) {
  const choice = await chooseChat(mc, ask, kind, brief);
  if (!choice) {
    void vscode.window.showInformationMessage(`No chat opened for “${ask.title}”. Open one any time with New chat for this ask on the Live page.`);
    return;
  }
  await startChat(mc, ask, kind, brief, choice);
}

/** Open a new chat for the active ask with a starter message, without asking which chat.
 * @param {MissionControl} mc
 * @returns {Promise<void>}
 */
async function newChat(mc) {
  const active = listAsks(mc.target().uri.fsPath).find(item => item.active);
  if (!active) throw new Error('No ask is active. Create one, or make an earlier ask active first.');
  await startChat(mc, active, 'resume', null, { target: 'new' });
}

/** @typedef {{target: 'new' | 'current' | 'own', chat?: import('./types').Chat}} ChatChoice */

/** Ask which chat should work on the ask: a new one, the chat in use, or the ask's own chat; with only one option, use it.
 * @param {MissionControl} mc
 * @param {import('./types').AskSummary} ask
 * @param {'new' | 'follow-up'} kind
 * @param {Brief} brief
 * @returns {Promise<ChatChoice | null>}
 */
async function chooseChat(mc, ask, kind, brief) {
  await mc.refresh();
  const chats = mc.state.activity?.chats || [];
  const own = chats.find(chat => chat.asks.some(link => link.ask === ask.id));
  /** @type {(vscode.QuickPickItem & ChatChoice)[]} */
  const options = [];
  const fresh = { label: '$(add) New chat session', target: /** @type {const} */ ('new'),
    detail: 'A fresh chat that starts from this ask. Best for unrelated work: the agent does not carry the earlier conversation.' };
  if (kind === 'new') {
    options.push({ ...fresh, description: 'recommended' });
    if (chats[0]) options.push({ label: '$(comment-discussion) This chat session', description: chats[0].title || 'Untitled chat', target: 'current', chat: chats[0],
      detail: 'Keep going in the chat you were using: the agent keeps its earlier conversation, and the chat is linked to the new ask.' });
  } else {
    if (own) options.push({ label: '$(history) The ask’s own chat', description: `recommended · ${own.title || 'Untitled chat'}`, target: 'own', chat: own,
      detail: 'Reopen the chat that worked on this ask, with its full history.' });
    options.push(fresh);
  }
  if (options.length === 1) return options[0];
  const picked = await vscode.window.showQuickPick(options, { title: `Which chat should work on “${brief.title}”?`, ignoreFocusOut: true,
    placeHolder: kind === 'new' ? 'A new ask unrelated to the earlier chat works best in a new chat session' : 'A follow-up works best in the ask’s own chat' });
  return picked ? { target: picked.target, chat: picked.chat } : null;
}

/** Open the chosen chat with the ask's agent, its request and plan attached and a starter message filled in but not sent, and link the chat to the ask.
 * @param {MissionControl} mc
 * @param {import('./types').AskSummary} ask
 * @param {'new' | 'follow-up' | 'resume'} kind
 * @param {Brief | null} brief
 * @param {ChatChoice} choice
 * @returns {Promise<void>}
 */
async function startChat(mc, ask, kind, brief, choice) {
  const root = mc.target().uri.fsPath;
  const query = starterPrompt(kind, ask, brief);
  const attachFiles = ['request.md', 'plan.md'].map(name => path.join(root, '.hve', 'asks', ask.id, name)).filter(file => fs.existsSync(file))
    .map(file => vscode.Uri.file(file));
  if (choice.target === 'new') {
    await mc.context.workspaceState.update('pendingChat', { ask: ask.id, at: new Date().toISOString() });
    await vscode.commands.executeCommand('workbench.action.chat.open');
    await vscode.commands.executeCommand('workbench.action.chat.newChat');
    await vscode.commands.executeCommand('workbench.action.chat.open', { query, isPartialQuery: true, mode: ask.agent, attachFiles });
  } else {
    const chat = /** @type {import('./types').Chat} */ (choice.chat);
    if (choice.target === 'own') await vscode.commands.executeCommand('vscode.open', vscode.Uri.parse(chatSessionUri(chat.id)));
    else if (!chat.asks.some(link => link.ask === ask.id)) {
      await mc.context.workspaceState.update('chatAsks', { ...claimsFrom(mc.context.workspaceState.get('chatAsks')), [chat.id]: { ask: ask.id, how: 'continued' } });
    }
    await vscode.commands.executeCommand('workbench.action.chat.open', { query, isPartialQuery: true, attachFiles });
  }
  mc.open('live');
  void vscode.window.showInformationMessage(`The chat for “${brief ? brief.title : ask.title}” has a starter message filled in, with the ask's request and plan attached. `
    + 'Add references (files, screenshots, links) or more detail, then send it.', 'Attach files…')
    .then(answer => answer === 'Attach files…' ? mc.execute({ action: 'attachReferences' }) : null);
}

/** Pick files and attach them to the chat that has focus.
 * @param {MissionControl} mc
 * @returns {Promise<void>}
 */
async function attachReferences(mc) {
  const files = await vscode.window.showOpenDialog({ canSelectFiles: true, canSelectFolders: false, canSelectMany: true, defaultUri: mc.target().uri,
    openLabel: 'Attach to the chat', title: 'References for the agent: designs, screenshots, documents or examples' });
  if (!files?.length) return;
  await vscode.commands.executeCommand('workbench.action.chat.open', { attachFiles: files });
}

module.exports = { askBrief, newAsk, newChat, chooseChat, startChat, attachReferences };
