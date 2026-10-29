'use strict';
/** Verify the current step follows the latest step when Copilot drops a tool call's completion, as it did for a view_image call in a real Pawstagram chat. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { workspace, removeWorkspace } = require('./helpers');
const { activity } = require('../../extension/ui/activity');
const { chatList } = require('../../extension/ui/chats');
const START = Date.parse('2026-10-29T00:20:49.000Z');

/** Return an ISO time a number of seconds after the start.
 * @param {number} seconds
 * @returns {string}
 */
function at(seconds) { return new Date(START + seconds * 1000).toISOString(); }

/** Return a transcript event.
 * @param {string} type
 * @param {number} seconds
 * @param {Record<string, unknown>} data
 * @returns {object}
 */
function row(type, seconds, data = {}) { return { type, data, timestamp: at(seconds) }; }

/** Return Copilot's order of a turn: tool calls of the previous answer, the next answer with its requests, the turn's end and the next start.
 * @param {string} root
 * @returns {object[]}
 */
function dropped(root) {
  const slide = name => ({ filePath: path.join(root, 'presentation', 'previews', name) });
  return [row('session.start', 0, { startTime: at(0) }), row('user.message', 0, { content: 'Build me 5 slides for an investor' }),
    row('assistant.turn_start', 1, { turnId: '13' }),
    row('assistant.message', 18, { content: '', toolRequests: [{ toolCallId: 'a' }, { toolCallId: 'b' }, { toolCallId: 'c' }] }),
    row('assistant.turn_end', 18, { turnId: '13' }), row('assistant.turn_start', 18, { turnId: '14' }),
    row('tool.execution_start', 20, { toolCallId: 'a', toolName: 'view_image', arguments: slide('Slide3.PNG') }), row('tool.execution_complete', 21, { toolCallId: 'a', success: true }),
    row('tool.execution_start', 24, { toolCallId: 'b', toolName: 'view_image', arguments: slide('Slide2.PNG') }), row('tool.execution_complete', 24, { toolCallId: 'b', success: true }),
    row('tool.execution_start', 26, { toolCallId: 'c', toolName: 'view_image', arguments: slide('Slide1.PNG') })];
}

/** Write a chat transcript and return its workspace, folder and file, removed after the test.
 * @param {import('node:test').TestContext} t
 * @param {(root: string) => object[]} rows
 * @returns {{root: string, transcripts: string, file: string}}
 */
function setup(t, rows) {
  const root = workspace();
  const storage = workspace();
  t.after(() => { removeWorkspace(root); removeWorkspace(storage); });
  const transcripts = path.join(storage, 'transcripts');
  fs.mkdirSync(transcripts);
  const file = path.join(transcripts, 'live.jsonl');
  fs.writeFileSync(file, rows(root).map(value => JSON.stringify(value) + '\n').join(''));
  return { root, transcripts, file };
}

test('a call still waiting for its result is the current step until the conversation moves on', t => {
  const { root, file } = setup(t, dropped);
  const { session } = activity(root, file, null, START + 60_000);
  assert.equal(session.status, 'working');
  assert.equal(session.current.title, 'Read presentation/previews/Slide1.PNG');
  assert.equal(session.events[0].state, 'running');
});

test('a call whose result never arrived shows as stopped once the agent answers, and Now follows the next step', t => {
  const { root, file } = setup(t, root => [...dropped(root),
    row('assistant.message', 162, { content: '', toolRequests: [{ toolCallId: 'd' }] }), row('assistant.turn_end', 162, { turnId: '0' }),
    row('assistant.turn_start', 162, { turnId: '1' }),
    row('tool.execution_start', 163, { toolCallId: 'd', toolName: 'read_file', arguments: { filePath: path.join(root, 'presentation', 'build_deck.py') } })]);
  const { session } = activity(root, file, null, START + 170_000);
  assert.equal(session.status, 'working');
  assert.equal(session.current.title, 'Read presentation/build_deck.py');
  const slide = session.events.find(event => event.title === 'Read presentation/previews/Slide1.PNG');
  assert.equal(slide.state, 'stopped');
  assert.equal(session.failures, 0);
  assert.equal(session.events.filter(event => event.state === 'running').length, 1);
});

test('between steps the chat is thinking, not stuck on a dropped call', t => {
  const { root, file } = setup(t, root => [...dropped(root), row('assistant.message', 162, { content: 'All five slides are ready.', toolRequests: [] }),
    row('assistant.turn_end', 162, { turnId: '0' }), row('assistant.turn_start', 162, { turnId: '1' })]);
  const { session } = activity(root, file, null, START + 170_000);
  assert.equal(session.status, 'working');
  assert.equal(session.current, null);
  assert.equal(session.events[0].title, 'All five slides are ready.');
});

test('a new message from you also settles calls left without a result', t => {
  const { root, file } = setup(t, root => [...dropped(root), row('user.message', 200, { content: 'Use darker slide backgrounds' })]);
  const { session } = activity(root, file, null, START + 205_000);
  assert.equal(session.current, null);
  assert.equal(session.events.find(event => event.title === 'Read presentation/previews/Slide1.PNG').state, 'stopped');
});

test('the chat list status follows the same rule, and an open question still means waiting for you', t => {
  const { root, transcripts, file } = setup(t, root => [...dropped(root), row('assistant.message', 162, { content: 'Done.', toolRequests: [] }),
    row('assistant.turn_end', 162, { turnId: '0' })]);
  const now = START + 170_000;
  assert.equal(chatList(transcripts, root, [], {}, null, now).chats[0].status, 'idle');
  fs.appendFileSync(file, JSON.stringify(row('assistant.turn_start', 163, { turnId: '1' })) + '\n'
    + JSON.stringify(row('tool.execution_start', 164, { toolCallId: 'q', toolName: 'vscode_askQuestions', arguments: { questions: [{ header: 'Theme' }] } })) + '\n');
  assert.equal(chatList(transcripts, root, [], {}, null, now).chats[0].status, 'waiting');
  assert.equal(activity(root, file, null, now).session.status, 'waiting');
});

test('a read or view with no result after a minute shows as stopped, while a long command stays current', t => {
  const { root, file } = setup(t, dropped);
  const stale = activity(root, file, null, START + 26_000 + 61_000).session;
  assert.equal(stale.current, null);
  assert.equal(stale.events[0].state, 'stopped');
  assert.equal(stale.status, 'working');
  assert.equal(activity(root, file, null, START + 26_000 + 6 * 60_000).session.status, 'idle');
  fs.appendFileSync(file, JSON.stringify(row('tool.execution_start', 30, { toolCallId: 'r', toolName: 'run_in_terminal', arguments: { command: 'npm test', explanation: 'Run the deck checks' } })) + '\n');
  const long = activity(root, file, null, START + 30_000 + 3 * 60_000).session;
  assert.equal(long.current.title, 'Run the deck checks');
  assert.equal(long.status, 'working');
});
