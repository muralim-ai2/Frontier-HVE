'use strict';
/** Verify live activity from chat transcripts, harness run files and research telemetry. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { workspace, removeWorkspace, json } = require('./helpers');
const { activity, describe } = require('../../extension/ui/activity');
const SESSION = '42699ac7-2882-4c23-83a4-5b7ef4a73106';
const START = Date.parse('2026-10-28T20:07:35.000Z');

/** Return an ISO time a number of seconds after the session start.
 * @param {number} seconds
 * @returns {string}
 */
function at(seconds) { return new Date(START + seconds * 1000).toISOString(); }

/** Create a workspace and a transcript folder removed after the test.
 * @param {import('node:test').TestContext} t
 * @returns {{root: string, transcripts: string, write: (rows: object[], id?: string) => string}}
 */
function setup(t) {
  const root = workspace();
  const storage = workspace();
  t.after(() => { removeWorkspace(root); removeWorkspace(storage); });
  const transcripts = path.join(storage, 'GitHub.copilot-chat', 'transcripts');
  fs.mkdirSync(transcripts, { recursive: true });
  return { root, transcripts, write: (rows, id = SESSION) => {
    const file = path.join(transcripts, `${id}.jsonl`);
    fs.writeFileSync(file, rows.map(row => JSON.stringify(row) + '\n').join(''));
    return file;
  } };
}

/** Return a transcript event.
 * @param {string} type
 * @param {number} seconds
 * @param {Record<string, unknown>} data
 * @returns {object}
 */
function row(type, seconds, data = {}) { return { type, data, id: `${type}-${seconds}`, timestamp: at(seconds), parentId: null }; }

/** Return a started tool call.
 * @param {number} seconds
 * @param {string} id
 * @param {string} toolName
 * @param {Record<string, unknown>} args
 * @returns {object}
 */
function tool(seconds, id, toolName, args) { return row('tool.execution_start', seconds, { toolCallId: id, toolName, arguments: args }); }

/** Return a finished tool call.
 * @param {number} seconds
 * @param {string} id
 * @param {boolean} success
 * @returns {object}
 */
function done(seconds, id, success = true) { return row('tool.execution_complete', seconds, { toolCallId: id, success }); }

/** Return a busy session: a prompt, an agent message, a file, a to-do list, a failed command and an edit still running.
 * @param {string} root
 * @returns {object[]}
 */
function busy(root) {
  return [row('session.start', 0, { sessionId: SESSION, startTime: at(0) }),
    row('user.message', 1, { content: '# Build: Pawstagram, a social photo app for dogs\r\n\r\nThree screens.' }),
    row('assistant.turn_start', 2, { turnId: '0' }),
    row('assistant.message', 3, { content: 'Creating the ask and checking the workspace first.', toolRequests: [] }),
    tool(4, 't1', 'create_file', { filePath: path.join(root, 'index.html'), content: '<!doctype html>' }), done(5, 't1'),
    tool(6, 't2', 'manage_todo_list', { todoList: [{ id: 1, title: 'Home feed', status: 'completed' }, { id: 2, title: 'Dog profile', status: 'in-progress' },
      { id: 3, title: 'Pack hive', status: 'not-started' }] }), done(7, 't2'),
    tool(8, 't3', 'run_in_terminal', { command: 'npm test', explanation: 'Run the checks' }), done(20, 't3', false),
    tool(30, 't4', 'replace_string_in_file', { filePath: path.join(root, 'index.html'), oldString: 'a', newString: 'b' })];
}

test('without a chat session the activity says so instead of guessing', t => {
  const { root, transcripts } = setup(t);
  fs.rmSync(transcripts, { recursive: true });
  const result = activity(root, transcripts, null, START);
  assert.equal(result.session, null);
  assert.match(result.reason, /No Copilot Chat session/);
  assert.equal(activity(root, null, null, START).session, null);
});

test('a working session shows its current step, to-do list, files changed, failures and newest-first timeline', t => {
  const { root, transcripts, write } = setup(t);
  write(busy(root));
  const { session, sessions } = activity(root, transcripts, null, START + 60_000);
  assert.equal(sessions, 1);
  assert.equal(session.status, 'working');
  assert.equal(session.title, 'Build: Pawstagram, a social photo app for dogs');
  assert.equal(session.current.title, 'Edited index.html');
  assert.deepEqual(session.todos.map(todo => todo.status), ['completed', 'in-progress', 'not-started']);
  assert.deepEqual(session.files, [{ path: 'index.html', count: 2, last: at(30) }]);
  assert.equal(session.failures, 1);
  assert.equal(session.commands, 1);
  assert.equal(session.events[0].title, 'Edited index.html');
  assert.equal(session.events[0].state, 'running');
  assert.equal(session.events.find(event => event.kind === 'run').state, 'failed');
  assert.equal(session.events.at(-1).title, 'Build: Pawstagram, a social photo app for dogs');
  assert.equal(session.events.at(-1).kind, 'prompt');
});

test('an open question means the agent is waiting for you', t => {
  const { root, transcripts, write } = setup(t);
  write([...busy(root).slice(0, -1), tool(31, 'q1', 'vscode_askQuestions', { questions: [{ header: 'Screens', question: 'Confirm?' }, { header: 'Skills', question: 'Which?' }] })]);
  const { session } = activity(root, transcripts, null, START + 40 * 60_000);
  assert.equal(session.status, 'waiting');
  assert.equal(session.current.kind, 'ask');
  assert.equal(session.current.detail, 'Screens · Skills');
});

test('ten quiet minutes make a session idle and unfinished calls show as stopped', t => {
  const { root, transcripts, write } = setup(t);
  write(busy(root));
  const { session } = activity(root, transcripts, null, START + 11 * 60_000);
  assert.equal(session.status, 'idle');
  assert.equal(session.current, null);
  assert.equal(session.events[0].state, 'stopped');
});

test('the session error guard, skill load and guard alerts come from the harness run files', t => {
  const { root, transcripts, write } = setup(t);
  write(busy(root));
  json(root, `.hve\\runs\\${SESSION}.errors.json`, { failures: [{ command: 'python check.py', output: 'Usage: check.py' }], paused: true });
  json(root, `.hve\\runs\\${SESSION}.skills.json`, { skills: ['a', 'b'], tokens: 51162, over_budget: true, budget: { max_skills: 10, max_tokens: 32000 } });
  fs.writeFileSync(path.join(root, '.hve', 'runs', `${SESSION}.interventions.jsonl`),
    JSON.stringify({ ts_ms: START + 25_000, session_id: SESSION, hook: 'loop_guard.py', kind: 'advise', detail: 'Edited the feature list' }) + '\n');
  const result = activity(root, transcripts, null, START + 60_000);
  assert.deepEqual(result.errors, { paused: true, failures: [{ command: 'python check.py', output: 'Usage: check.py' }] });
  assert.deepEqual(result.loadout, { skills: 2, tokens: 51162, overBudget: true, maxSkills: 10, maxTokens: 32000 });
  const guard = result.session.events.find(event => event.kind === 'guard');
  assert.equal(guard.title, 'Guard: loop guard advise');
  assert.equal(guard.at, at(25));
});

test('research telemetry tokens are summed per model for this session only', t => {
  const { root, transcripts, write } = setup(t);
  write(busy(root));
  const span = (session, model, input, output) => JSON.stringify({ name: `chat ${model}`, attributes: { [model === 'gpt-4o-mini'
    ? 'copilot_chat.parent_chat_session_id' : 'gen_ai.conversation.id']: session,
    'gen_ai.response.model': model, 'gen_ai.usage.input_tokens': input, 'gen_ai.usage.output_tokens': output,
    'gen_ai.usage.cache_read.input_tokens': 100, 'copilot_chat.copilot_usage_nano_aiu': 500000000 } }) + '\n';
  const file = path.join(root, '.hve', 'runs', 'copilot-otel.jsonl');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, span(SESSION, 'claude-opus-5.5', 1000, 50) + span(SESSION, 'claude-opus-5.5', 2000, 70)
    + span(SESSION, 'gpt-4o-mini', 300, 5) + span('another-session', 'claude-opus-5.5', 9999, 999) + JSON.stringify({ body: 'log record' }) + '\n'
    + JSON.stringify({ name: 'chat claude-opus-5.5', status: { code: 2, message: 'The operation was aborted' },
      attributes: { 'gen_ai.conversation.id': SESSION, 'gen_ai.request.model': 'claude-opus-5.5' } }) + '\n');
  const { tokens } = activity(root, transcripts, file, START + 60_000);
  assert.deepEqual(tokens.models[0], { model: 'claude-opus-5.5', calls: 3, failed: 1, input: 3000, output: 120, cached: 200 });
  assert.equal(tokens.models[1].model, 'gpt-4o-mini');
  assert.equal(tokens.aiu, 1.5);
  assert.equal(activity(root, transcripts, path.join(path.dirname(root), 'elsewhere.jsonl'), START).tokens, null);
});

test('an unfinished last line is read once complete and malformed lines fail explicitly', t => {
  const { root, transcripts, write } = setup(t);
  const file = write(busy(root));
  const partial = JSON.stringify(row('assistant.message', 40, { content: 'Almost there.' }));
  fs.appendFileSync(file, partial.slice(0, 20));
  assert.ok(!activity(root, transcripts, null, START).session.events.some(event => event.title === 'Almost there.'));
  fs.appendFileSync(file, partial.slice(20) + '\n');
  assert.equal(activity(root, transcripts, null, START).session.events[0].title, 'Almost there.');
  fs.writeFileSync(file, '{"type":\n' + JSON.stringify(row('assistant.turn_start', 1)) + '\n');
  assert.throws(() => activity(root, transcripts, null, START), /Invalid JSON on line 1/);
});

test('the most recently written transcript is the current session', t => {
  const { root, transcripts, write } = setup(t);
  const older = write([row('user.message', 0, { content: 'Earlier work' })], 'older-session');
  fs.utimesSync(older, new Date(START - 3_600_000), new Date(START - 3_600_000));
  write(busy(root));
  const result = activity(root, transcripts, null, START + 60_000);
  assert.equal(result.sessions, 2);
  assert.equal(result.session.id, SESSION);
});

test('tool calls are described in plain words with every edited file', () => {
  const root = path.join(path.sep, 'work', 'app');
  const patch = describe('apply_patch', { input: '*** Begin Patch\n*** Update File: /work/app/a.js\n*** Add File: /work/app/b.js\n*** End Patch' }, root, at(0));
  assert.equal(patch.title, 'Edited 2 files');
  assert.equal(patch.files.length, 2);
  assert.equal(describe('read_file', { filePath: path.join(path.sep, 'ext', 'skills', 'ux-flows', 'SKILL.md') }, root, at(0)).title, 'Read ux-flows/SKILL.md');
  assert.equal(describe('runSubagent', { agentName: 'HVE engineer', description: 'Build feed' }, root, at(0)).title, 'Handed off to HVE engineer');
  assert.equal(describe('mcp_graphify_query_graph', {}, root, at(0)).title, 'Used graphify query graph');
  assert.equal(describe('run_in_terminal', {}, root, at(0)).title, 'Ran a command');
  const harness = describe('run_in_terminal', { command: 'python "c:/Users/me/.vscode/extensions/muralim-ai2.frontier-hve-0.19.0/runtime/tools/loop/lifecycle.py" where .hve/asks/request.md',
    explanation: 'Check for an existing project or open ask.' }, root, at(0));
  assert.equal(harness.title, 'Check for an existing project or open ask');
  assert.equal(harness.detail, 'python lifecycle.py where .hve/asks/request.md');
});
