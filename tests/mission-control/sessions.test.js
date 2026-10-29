'use strict';
/** Verify chats and asks: one ask has many chats, each chat is linked to the asks it created, reopened, edited or was opened for, and New ask opens a fresh chat. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { workspace, removeWorkspace } = require('./helpers');
const { mission } = require('./vscode-stub');
const { realAsks } = require('./fixtures');
const { chatList, shownChat, claimsFrom, pendingFrom } = require('../../extension/ui/chats');
const { slugFor, listAsks } = require('../../extension/ui/asks');
const { text } = require('../../extension/ui/media/vnode');
const { dashboard } = require('../../extension/ui/media/pages');
const PAWS = '20261028-2015-pawstagram-dog-app';
const OLD_PAWS = '20261027-0900-pawstagram-dog-app';
const ONBOARDING = '20261028-1200-onboarding';
const REPORTING = '20261028-1300-reporting';
const ASKS = [PAWS, OLD_PAWS, ONBOARDING, REPORTING];
const UI = { page: 'live', filter: 'all', open: {}, seq: 0 };
const LIFECYCLE = '"c:/Users/me/.vscode/extensions/muralim-ai2.frontier-hve-0.20.0/runtime/tools/loop/lifecycle.py"';

/** Return a transcript event.
 * @param {string} type
 * @param {string} at
 * @param {Record<string, unknown>} data
 * @returns {object}
 */
function row(type, at, data = {}) { return { type, data, timestamp: at }; }

/** Return a started tool call.
 * @param {string} at
 * @param {string} id
 * @param {string} toolName
 * @param {Record<string, unknown>} args
 * @returns {object}
 */
function tool(at, id, toolName, args) { return row('tool.execution_start', at, { toolCallId: id, toolName, arguments: args }); }

/** Write a chat transcript one JSON event per line and return its path.
 * @param {string} folder
 * @param {string} id
 * @param {object[]} rows
 * @returns {string}
 */
function write(folder, id, rows) {
  fs.mkdirSync(folder, { recursive: true });
  const file = path.join(folder, `${id}.jsonl`);
  fs.writeFileSync(file, rows.map(value => JSON.stringify(value) + '\n').join(''));
  return file;
}

/** Create a workspace and transcript folder removed after the test.
 * @param {import('node:test').TestContext} t
 * @returns {{root: string, transcripts: string}}
 */
function setup(t) {
  const root = workspace();
  const storage = workspace();
  t.after(() => { removeWorkspace(root); removeWorkspace(storage); });
  return { root, transcripts: path.join(storage, 'transcripts') };
}

test('a chat is linked to the ask its contract created, the asks it reopened and the asks whose files it edited; one ask has many chats', t => {
  const { root, transcripts } = setup(t);
  write(transcripts, 'created', [row('session.start', '2026-10-28T20:15:00.000Z', { startTime: '2026-10-28T20:15:00.000Z' }),
    row('user.message', '2026-10-28T20:15:01.000Z', { content: 'Build: Pawstagram, a social photo app for dogs' }),
    tool('2026-10-28T20:15:40.000Z', 'c', 'run_in_terminal', { command: `python ${LIFECYCLE} contract direct pawstagram-dog-app "Frontier Prototype Creator" .hve/asks/request.md +ux-flows` })]);
  write(transcripts, 'follow-up', [row('user.message', '2026-10-29T09:00:00.000Z', { content: 'Add a dog profile page' }),
    tool('2026-10-29T09:00:05.000Z', 'o', 'run_in_terminal', { command: `$L=${LIFECYCLE}; python $L open ${PAWS} | Select-Object -Last 1; python $L open 20261028-0000-unknown` })]);
  write(transcripts, 'edited', [row('user.message', '2026-10-29T10:00:00.000Z', { content: 'Tidy the onboarding plan' }),
    tool('2026-10-29T10:00:05.000Z', 'r', 'read_file', { filePath: path.join(root, '.hve', 'asks', REPORTING, 'plan.md') }),
    tool('2026-10-29T10:00:09.000Z', 'e', 'replace_string_in_file', { filePath: path.join(root, '.hve', 'asks', ONBOARDING, 'plan.md'), oldString: 'a', newString: 'b' })]);
  write(transcripts, 'late-contract', [row('user.message', '2026-10-28T19:00:00.000Z', { content: 'Earlier attempt' }),
    tool('2026-10-28T19:00:05.000Z', 'c', 'run_in_terminal', { command: `python ${LIFECYCLE} contract direct pawstagram-dog-app "HVE creator" request.md` })]);
  write(transcripts, 'plain', [row('user.message', '2026-10-29T11:00:00.000Z', { content: 'What does this repo do?' })]);
  const { chats, claimed } = chatList(transcripts, root, ASKS, {}, null, Date.parse('2026-10-29T12:00:00Z'));
  assert.equal(claimed, null);
  const links = Object.fromEntries(chats.map(chat => [chat.id, chat.asks]));
  assert.deepEqual(links, { created: [{ ask: PAWS, how: 'created' }], 'follow-up': [{ ask: PAWS, how: 'opened' }], edited: [{ ask: ONBOARDING, how: 'edited' }],
    'late-contract': [], plain: [] });
  assert.deepEqual(chats.map(chat => chat.id), ['plain', 'edited', 'follow-up', 'created', 'late-contract']);
  assert.equal(chats.find(chat => chat.id === 'created').title, 'Build: Pawstagram, a social photo app for dogs');
  assert.equal(shownChat(chats, PAWS, null).id, 'follow-up');
  assert.equal(shownChat(chats, PAWS, 'created').id, 'created');
  assert.equal(shownChat(chats, PAWS, 'plain').id, 'follow-up');
  assert.equal(shownChat(chats, REPORTING, null), null);
  assert.equal(shownChat(chats, null, null).id, 'plain');
});

test('a pending new chat claims the first chat that starts after it, never an older one, and lapses after an hour', t => {
  const { root, transcripts } = setup(t);
  const at = '2026-10-29T09:00:00.000Z';
  write(transcripts, 'older', [row('session.start', '2026-10-29T08:50:00.000Z', { startTime: '2026-10-29T08:50:00.000Z' }),
    row('user.message', '2026-10-29T09:01:00.000Z', { content: 'Still talking here' })]);
  write(transcripts, 'second-new', [row('session.start', '2026-10-29T09:03:00.000Z', { startTime: '2026-10-29T09:03:00.000Z' })]);
  write(transcripts, 'first-new', [row('session.start', '2026-10-29T09:00:30.000Z', { startTime: '2026-10-29T09:00:30.000Z' }),
    row('user.message', '2026-10-29T09:00:40.000Z', { content: 'Plan the onboarding checker' })]);
  const now = Date.parse('2026-10-29T09:05:00Z');
  const pending = pendingFrom({ ask: ONBOARDING, at }, now);
  const result = chatList(transcripts, root, ASKS, {}, pending, now);
  assert.deepEqual(result.claimed, { chat: 'first-new', ask: ONBOARDING });
  assert.deepEqual(result.chats.find(chat => chat.id === 'first-new').asks, [{ ask: ONBOARDING, how: 'started' }]);
  assert.deepEqual(result.chats.find(chat => chat.id === 'older').asks, []);
  const saved = claimsFrom({ 'first-new': { ask: ONBOARDING, how: 'started' } });
  assert.deepEqual(chatList(transcripts, root, ASKS, saved, pending, now).claimed, { chat: 'second-new', ask: ONBOARDING });
  assert.equal(pendingFrom({ ask: ONBOARDING, at }, Date.parse('2026-10-29T10:00:01Z')), null);
  assert.equal(pendingFrom(undefined, now), null);
  assert.throws(() => pendingFrom({ ask: '../x', at }, now), /Invalid saved new chat/);
  assert.throws(() => claimsFrom({ 'first-new': { ask: ONBOARDING, how: 'guessed' } }), /Invalid saved chat link/);
  assert.deepEqual(claimsFrom(undefined), {});
});

test('transcripts are read incrementally: new lines update a chat, a half-written line waits, and a malformed line fails with its place', t => {
  const { root, transcripts } = setup(t);
  const file = write(transcripts, 'live', [row('session.start', '2026-10-29T09:00:00.000Z', { startTime: '2026-10-29T09:00:00.000Z' }),
    row('user.message', '2026-10-29T09:00:01.000Z', { content: 'Build the feed' }), row('assistant.turn_start', '2026-10-29T09:00:02.000Z')]);
  const now = Date.parse('2026-10-29T09:01:00Z');
  assert.equal(chatList(transcripts, root, ASKS, {}, null, now).chats[0].status, 'working');
  const question = JSON.stringify(tool('2026-10-29T09:00:30.000Z', 'q', 'vscode_askQuestions', { questions: [{ header: 'Screens' }] })) + '\n';
  fs.appendFileSync(file, question.slice(0, 25));
  assert.equal(chatList(transcripts, root, ASKS, {}, null, now).chats[0].status, 'working');
  fs.appendFileSync(file, question.slice(25));
  const chat = chatList(transcripts, root, ASKS, {}, null, now).chats[0];
  assert.equal(chat.status, 'waiting');
  assert.equal(chat.lastAt, '2026-10-29T09:00:30.000Z');
  fs.appendFileSync(file, JSON.stringify(row('tool.execution_complete', '2026-10-29T09:00:50.000Z', { toolCallId: 'q', success: true })) + '\n');
  assert.equal(chatList(transcripts, root, ASKS, {}, null, now).chats[0].status, 'working');
  write(transcripts, 'broken', [row('user.message', '2026-10-29T09:00:00.000Z', { content: 'ok' })]);
  fs.appendFileSync(path.join(transcripts, 'broken.jsonl'), '{"type":\n');
  assert.throws(() => chatList(transcripts, root, ASKS, {}, null, now), /Invalid chat event on line 2 of broken\.jsonl/);
  assert.deepEqual(chatList(null, root, ASKS, {}, null, now), { chats: [], claimed: null });
});

test('a new ask is named from its request in a few lowercase words', () => {
  assert.equal(slugFor('Build: Pawstagram, a social photo app for dogs'), 'pawstagram-social-photo-app');
  assert.equal(slugFor('Please could you create a new dashboard for quarterly revenue'), 'dashboard-quarterly-revenue');
  assert.equal(slugFor('Café menu for the week'), 'cafe-menu-week');
  assert.equal(slugFor('x'.repeat(60)), 'x'.repeat(41));
  assert.equal(slugFor('!!!'), 'ask');
  assert.match(slugFor('Write the onboarding policy checker for new joiners'), /^[a-z0-9][a-z0-9-]{0,40}$/);
});

test('New ask opens a fresh chat, links the next chat that starts to the ask, and shows its live activity', async t => {
  const fixture = mission(t);
  const before = new Date(Date.now() - 10 * 60_000).toISOString();
  write(fixture.transcripts, 'earlier', [row('session.start', before, { startTime: before }), row('user.message', before, { content: 'Earlier question' })]);
  fixture.controls.inputs.push('Onboarding policy checker', 'Build an onboarding policy checker', 'onboarding');
  fixture.controls.confirmations.push('Change folder name…', 'Create ask');
  await fixture.controls.commands.get('frontierHve.newAsk')();
  const [ask] = listAsks(fixture.root).map(row => row.id);
  assert.match(ask, /^\d{8}-\d{4}-onboarding$/);
  const asked = fixture.controls.calls.filter(call => call[0] === 'confirmation');
  assert.match(asked[0][1], /Create ask “Onboarding policy checker”/);
  assert.match(asked[0][2].detail, /\.hve\/asks\/<UTC date-time>-onboarding-policy-checker\//);
  assert.match(asked[0][2].detail, /A Copilot Chat then opens for it/);
  assert.equal(fixture.context.workspaceState.get('pendingChat').ask, ask);
  let model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.equal(model.pending.ask, ask);
  assert.equal(model.activity.session, null);
  assert.match(text(dashboard(model, UI, Date.now())), /A new chat is open for this ask/);
  const started = new Date().toISOString();
  write(fixture.transcripts, 'fresh', [row('session.start', started, { startTime: started }), row('user.message', started, { content: 'Plan the onboarding checker' }),
    row('assistant.turn_start', started), tool(started, 'w', 'create_file', { filePath: path.join(fixture.root, 'policy.js') })]);
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.deepEqual(fixture.context.workspaceState.get('chatAsks'), { fresh: { ask, how: 'started' } });
  assert.equal(fixture.context.workspaceState.get('pendingChat'), null);
  assert.equal(model.pending, null);
  assert.equal(model.activity.session.id, 'fresh');
  assert.equal(model.activity.session.current.title, 'Created policy.js');
  assert.deepEqual(model.activity.chats.find(chat => chat.id === 'earlier').asks, []);
  const live = dashboard(model, UI, Date.now());
  assert.match(text(live), /Chats for this ask \(1\)/);
  assert.match(text(live), /Plan the onboarding checkeropened for it here · working/);
  assert.match(text(live), /Chats not linked to any ask \(1\)/);
});

test('a follow-up request continues the open ask in a new chat instead of creating another folder', async t => {
  const fixture = mission(t);
  fixture.controls.inputs.push('Onboarding policy checker', 'Build an onboarding policy checker');
  fixture.controls.confirmations.push('Create ask');
  await fixture.controls.commands.get('frontierHve.newAsk')();
  const [ask] = listAsks(fixture.root).map(row => row.id);
  fixture.controls.inputs.push('Policy checker messages', 'Tighten the onboarding policy checker messages');
  fixture.controls.confirmations.push('Continue the open ask');
  await fixture.controls.commands.get('frontierHve.newAsk')();
  assert.deepEqual(listAsks(fixture.root).map(row => row.id), [ask]);
  const follow = fixture.controls.calls.filter(call => call[0] === 'confirmation').at(-1);
  assert.equal(follow[1], '“Policy checker messages” looks like a follow-up to the open ask “Onboarding policy checker”.');
  assert.deepEqual(follow.slice(3), ['Continue the open ask', 'Create a separate ask']);
  assert.equal(fixture.controls.calls.filter(call => call[0] === 'workbench.action.chat.newLocalChat').length, 2);
  assert.equal(fixture.context.workspaceState.get('pendingChat').ask, ask);
});

test('chats can be chosen and an unlinked chat linked by hand; a new chat needs an active ask', async t => {
  const fixture = mission(t);
  await assert.rejects(fixture.controls.provider.execute({ action: 'newChat' }), /No ask is active/);
  const [first, second] = await realAsks(fixture.root, fixture.storage, [['onboarding', 'Build an onboarding policy checker'], ['reporting', 'Write the quarterly revenue report']]);
  const recent = new Date(Date.now() - 60_000).toISOString();
  const later = new Date(Date.now() - 30_000).toISOString();
  write(fixture.transcripts, 'reopen', [row('user.message', recent, { content: 'Back to onboarding' }),
    tool(recent, 'o', 'run_in_terminal', { command: `python ${LIFECYCLE} open ${first}` })]);
  write(fixture.transcripts, 'loose', [row('user.message', later, { content: 'A question about onboarding' })]);
  await fixture.controls.provider.execute({ action: 'selectAsk', ask: first });
  let model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.equal(model.activity.session.id, 'reopen');
  assert.ok(!find(dashboard(model, UI, Date.now()), node => node.attrs['data-action'] === 'newChat').length);
  const links = find(dashboard(model, { ...UI, open: { 'other-chats': true } }, Date.now()), node => node.attrs['data-action'] === 'linkChat');
  assert.deepEqual(links.map(node => node.attrs['data-chat']), ['loose']);
  await fixture.controls.provider.execute({ action: 'linkChat', chat: 'loose' });
  model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.deepEqual(fixture.context.workspaceState.get('chatAsks'), { loose: { ask: first, how: 'linked' } });
  assert.equal(model.activity.session.id, 'loose');
  assert.match(text(dashboard(model, UI, Date.now())), /Chats for this ask \(2\)/);
  await fixture.controls.provider.execute({ action: 'selectChat', chat: 'reopen' });
  assert.equal(fixture.controls.commands.get('frontierHve.missionControlModel')().activity.session.id, 'reopen');
  await assert.rejects(fixture.controls.provider.execute({ action: 'selectChat', chat: 'unknown' }), /not listed/);
  await fixture.controls.provider.execute({ action: 'selectAsk', ask: second });
  model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.equal(model.activity.session, null);
  assert.equal(find(dashboard(model, UI, Date.now()), node => node.attrs['data-action'] === 'newChat').length, 1);
});

/** Return every view node matching a test.
 * @param {import('../../extension/ui/types').VNode | string} node
 * @param {(node: import('../../extension/ui/types').VNode) => boolean} match
 * @returns {import('../../extension/ui/types').VNode[]}
 */
function find(node, match) {
  return typeof node === 'string' ? [] : [...(match(node) ? [node] : []), ...node.children.flatMap(child => find(child, match))];
}
