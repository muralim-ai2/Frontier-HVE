'use strict';
/** Verify the chat that starts an ask: the session the user picks, a starter message filled in but never sent, the ask's agent, its files attached, references offered, and the link. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { mission } = require('./vscode-stub');
const { listAsks, starterPrompt } = require('../../extension/ui/asks');
const { chatSessionUri } = require('../../extension/ui/chats');
const ASK = { id: '20261029-0329-dog-profile-badges', title: 'Dog profile badges' };

/** Return the chat commands run so far.
 * @param {{calls: unknown[][]}} controls
 * @returns {any[][]}
 */
function chatCalls(controls) {
  return controls.calls.filter(call => /^workbench\.action\.chat\./.test(String(call[0])) || call[0] === 'vscode.open');
}

/** Write a chat transcript with the given rows, recently active.
 * @param {string} folder
 * @param {string} id
 * @param {object[]} rows
 * @returns {void}
 */
function chat(folder, id, rows) {
  fs.mkdirSync(folder, { recursive: true });
  const at = new Date(Date.now() - 60_000).toISOString();
  fs.writeFileSync(path.join(folder, `${id}.jsonl`), rows.map(row => JSON.stringify({ timestamp: at, ...row }) + '\n').join(''));
}

/** Create an ask through New ask with no earlier chat, so the new chat opens without a question.
 * @param {ReturnType<typeof mission>} fixture
 * @param {string} title
 * @param {string} description
 * @returns {Promise<import('../../extension/ui/types').AskSummary>}
 */
async function create(fixture, title, description) {
  fixture.controls.inputs.push(title, description);
  fixture.controls.confirmations.push('Create ask');
  await fixture.controls.commands.get('frontierHve.newAsk')();
  return listAsks(fixture.root).find(ask => ask.active);
}

test('the starter message names the ask, carries the description, says not to create another ask and asks for references first', () => {
  const fresh = starterPrompt('new', ASK, { title: 'Dog profile badges', description: 'Come up with 3 creative badge ideas and build them' });
  assert.match(fresh, /^New ask: Dog profile badges\n\nCome up with 3 creative badge ideas and build them\n\n/);
  assert.match(fresh, /already created and active in \.hve\/asks\/20261029-0329-dog-profile-badges\//);
  assert.match(fresh, /do not create another one/);
  assert.match(fresh, /ask me for any references \(files, screenshots, links, examples\) or constraints/);
  assert.doesNotMatch(starterPrompt('new', ASK, { title: 'Dog profile badges', description: '' }), /\n\n\n/);
  const follow = starterPrompt('follow-up', ASK, { title: 'Walk streaks', description: 'Add a streak counter' });
  assert.match(follow, /^Follow-up for the ask “Dog profile badges” \(\.hve\/asks\/20261029-0329-dog-profile-badges\/, its request and plan are attached\): Walk streaks/);
  assert.match(starterPrompt('resume', ASK, null), /^Continue the ask “Dog profile badges”/);
  assert.match(starterPrompt('resume', ASK, null), /whether I have references to add/);
  assert.throws(() => starterPrompt('new', ASK, null), /needs a title/);
});

test('a chat session id becomes the address VS Code opens it by', () => {
  assert.equal(chatSessionUri('29069519-94b9-4e4f-9a48-f46b3af1f2d2'), 'vscode-chat-session://local/MjkwNjk1MTktOTRiOS00ZTRmLTlhNDgtZjQ2YjNhZjFmMmQy');
  assert.throws(() => chatSessionUri('../x'), /Invalid chat session id/);
});

test('with no earlier chat, a new ask opens a new chat session with the starter filled in, the ask\'s agent, and its request and plan attached', async t => {
  const fixture = mission(t);
  const ask = await create(fixture, 'Dog profile badges', 'Come up with 3 creative badge ideas and build them');
  assert.ok(!fixture.controls.calls.some(call => call[0] === 'pick'));
  const calls = chatCalls(fixture.controls);
  assert.deepEqual(calls.map(call => call[0]), ['workbench.action.chat.open', 'workbench.action.chat.newChat', 'workbench.action.chat.open']);
  assert.deepEqual(calls.slice(0, 2).map(call => call.length), [1, 1]);
  const options = calls[2][1];
  assert.equal(options.isPartialQuery, true);
  assert.equal(options.mode, 'HVE creator');
  assert.equal(options.query, starterPrompt('new', ask, { title: 'Dog profile badges', description: 'Come up with 3 creative badge ideas and build them' }));
  assert.deepEqual(options.attachFiles.map(uri => path.relative(fixture.root, uri.fsPath)),
    [path.join('.hve', 'asks', ask.id, 'request.md'), path.join('.hve', 'asks', ask.id, 'plan.md')]);
  assert.equal(fixture.context.workspaceState.get('pendingChat').ask, ask.id);
  const notice = fixture.controls.calls.find(call => call[0] === 'information');
  assert.match(notice[1], /“Dog profile badges” has a starter message filled in/);
  assert.match(notice[1], /Add references \(files, screenshots, links\)/);
  assert.equal(notice[2], 'Attach files…');
  assert.equal(fixture.controls.commands.get('frontierHve.missionControlModel')().navigate.page, 'live');
});

test('with an earlier chat, a new ask asks which session: a new one first, or this one, which is then linked to the ask', async t => {
  const fixture = mission(t);
  chat(fixture.transcripts, 'earlier', [{ type: 'user.message', data: { content: 'Build: Pawstagram, a social photo app for dogs' } }]);
  fixture.controls.picks.push(1);
  const ask = await create(fixture, 'Dog profile badges', 'Add breed badges to the dog profile');
  const pick = fixture.controls.calls.find(call => call[0] === 'pick');
  assert.equal(pick[2].title, 'Which chat should work on “Dog profile badges”?');
  assert.deepEqual(pick[1].map(item => [item.label, item.description]), [['$(add) New chat session', 'recommended'],
    ['$(comment-discussion) This chat session', 'Build: Pawstagram, a social photo app for dogs']]);
  const calls = chatCalls(fixture.controls);
  assert.deepEqual(calls.map(call => call[0]), ['workbench.action.chat.open']);
  assert.equal(calls[0][1].isPartialQuery, true);
  assert.equal(calls[0][1].mode, undefined);
  assert.match(calls[0][1].query, /^New ask: Dog profile badges/);
  assert.deepEqual(fixture.context.workspaceState.get('chatAsks'), { earlier: { ask: ask.id, how: 'continued' } });
  assert.equal(fixture.context.workspaceState.get('pendingChat'), undefined);
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.deepEqual(model.activity.chats.find(row => row.id === 'earlier').asks, [{ ask: ask.id, how: 'continued' }]);
  assert.equal(model.activity.session.id, 'earlier');
});

test('a follow-up offers the ask\'s own chat first and reopens it with its history, with the follow-up filled in', async t => {
  const fixture = mission(t);
  const ask = await create(fixture, 'Pawstagram', 'Build Pawstagram, a social photo app for dogs with a home feed, dog profiles and a pack hive');
  chat(fixture.transcripts, '29069519-94b9-4e4f-9a48-f46b3af1f2d2', [{ type: 'user.message', data: { content: 'Build the Pawstagram feed' } },
    { type: 'tool.execution_start', data: { toolCallId: 'o', toolName: 'run_in_terminal', arguments: { command: `python lifecycle.py open ${ask.id}` } } }]);
  chat(fixture.transcripts, 'other', [{ type: 'user.message', data: { content: 'Which image formats are allowed?' } }]);
  fs.utimesSync(path.join(fixture.transcripts, 'other.jsonl'), new Date(), new Date());
  const before = fixture.controls.calls.length;
  fixture.controls.inputs.push('Walk streaks', 'Add a walk streak counter to the dog profile');
  fixture.controls.confirmations.push('Continue the open ask');
  await fixture.controls.commands.get('frontierHve.newAsk')();
  assert.deepEqual(listAsks(fixture.root).map(row => row.id), [ask.id]);
  const pick = fixture.controls.calls.slice(before).find(call => call[0] === 'pick');
  assert.deepEqual(pick[1].map(item => item.label), ['$(history) The ask’s own chat', '$(add) New chat session']);
  assert.match(pick[1][0].description, /^recommended · Build the Pawstagram feed$/);
  const calls = chatCalls({ calls: fixture.controls.calls.slice(before) });
  assert.deepEqual(calls.map(call => call[0]), ['vscode.open', 'workbench.action.chat.open']);
  assert.equal(calls[0][1].toString(), 'vscode-chat-session://local/MjkwNjk1MTktOTRiOS00ZTRmLTlhNDgtZjQ2YjNhZjFmMmQy');
  assert.match(calls[1][1].query, /^Follow-up for the ask “Pawstagram” .*: Walk streaks\n\nAdd a walk streak counter to the dog profile/);
  assert.equal(calls[1][1].isPartialQuery, true);
});

test('cancelling the session question keeps the ask, opens no chat and says how to open one later', async t => {
  const fixture = mission(t);
  chat(fixture.transcripts, 'earlier', [{ type: 'user.message', data: { content: 'Earlier work' } }]);
  fixture.controls.picks.push(null);
  const ask = await create(fixture, 'Dog profile badges', '');
  assert.ok(ask);
  assert.deepEqual(chatCalls(fixture.controls), []);
  assert.match(fixture.controls.calls.filter(call => call[0] === 'information').at(-1)[1], /No chat opened for “Dog profile badges”.*New chat for this ask/);
});

test('New chat for this ask opens a new session straight away with a starter to pick the ask up again', async t => {
  const fixture = mission(t);
  const ask = await create(fixture, 'Dog profile badges', '');
  const before = fixture.controls.calls.length;
  chat(fixture.transcripts, 'earlier', [{ type: 'user.message', data: { content: 'Earlier work' } }]);
  await fixture.controls.provider.execute({ action: 'newChat' });
  const later = fixture.controls.calls.slice(before);
  assert.ok(!later.some(call => call[0] === 'pick'));
  const calls = chatCalls({ calls: later });
  assert.deepEqual(calls.map(call => call[0]), ['workbench.action.chat.open', 'workbench.action.chat.newChat', 'workbench.action.chat.open']);
  assert.equal(calls[2][1].query, starterPrompt('resume', ask, null));
  assert.equal(calls[2][1].mode, 'HVE creator');
});

test('Attach files… adds the picked references to the chat, and the starter is never sent', async t => {
  const fixture = mission(t);
  fixture.controls.notices.push('Attach files…');
  fs.writeFileSync(path.join(fixture.root, 'brand.pdf'), 'brand');
  fixture.controls.dialogs.push([{ fsPath: path.join(fixture.root, 'brand.pdf'), scheme: 'file', toString: () => 'file:///brand.pdf' }]);
  await create(fixture, 'Dog profile badges', '');
  await new Promise(resolve => setTimeout(resolve, 50));
  const dialog = fixture.controls.calls.find(call => call[0] === 'dialog');
  assert.equal(dialog[1].canSelectMany, true);
  assert.equal(dialog[1].openLabel, 'Attach to the chat');
  const attach = chatCalls(fixture.controls).at(-1);
  assert.deepEqual(Object.keys(attach[1]), ['attachFiles']);
  assert.equal(attach[1].attachFiles[0].fsPath, path.join(fixture.root, 'brand.pdf'));
  assert.ok(chatCalls(fixture.controls).every(call => !call[1] || call[1].isPartialQuery !== false));
});
