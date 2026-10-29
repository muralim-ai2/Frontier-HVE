'use strict';
/** Check the sidebar and dashboard pages built from a real-shaped project and a live chat transcript. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { workspace, removeWorkspace, json, EXTENSION } = require('./helpers');
const { mission } = require('./vscode-stub');
const { project, ASK } = require('./fixtures');
const { snapshot } = require('../../extension/ui/workspace-state');
const { activity } = require('../../extension/ui/activity');
const { listAsks, askTree } = require('../../extension/ui/asks');
const { chatList } = require('../../extension/ui/chats');
const { text } = require('../../extension/ui/media/vnode');
const { sidebar } = require('../../extension/ui/media/views');
const { dashboard } = require('../../extension/ui/media/pages');
const START = Date.parse('2026-10-28T20:07:35.000Z');
const NOW = START + 60_000;

/** Return every view node matching a test.
 * @param {import('../../extension/ui/types').VNode | string} node
 * @param {(node: import('../../extension/ui/types').VNode) => boolean} match
 * @returns {import('../../extension/ui/types').VNode[]}
 */
function find(node, match) {
  return typeof node === 'string' ? [] : [...(match(node) ? [node] : []), ...node.children.flatMap(child => find(child, match))];
}

/** Return the buttons with an action.
 * @param {import('../../extension/ui/types').VNode} tree
 * @param {string} action
 * @returns {import('../../extension/ui/types').VNode[]}
 */
function actions(tree, action) { return find(tree, node => node.attrs['data-action'] === action); }

/** Build a model from a project with a working chat session opened for its ask.
 * @param {import('node:test').TestContext} t
 * @returns {import('../../extension/ui/types').Model}
 */
function model(t) {
  const root = workspace();
  const storage = workspace();
  t.after(() => { removeWorkspace(root); removeWorkspace(storage); });
  project(root);
  const transcripts = path.join(storage, 'transcripts');
  fs.mkdirSync(transcripts);
  const at = seconds => new Date(START + seconds * 1000).toISOString();
  const row = (type, seconds, data) => JSON.stringify({ type, data, timestamp: at(seconds) }) + '\n';
  fs.writeFileSync(path.join(transcripts, 'session-1.jsonl'), row('session.start', 0, { startTime: at(0) })
    + row('user.message', 1, { content: 'Build the onboarding workspace' }) + row('assistant.turn_start', 2, {})
    + row('tool.execution_start', 3, { toolCallId: 'a', toolName: 'manage_todo_list', arguments: { todoList: [{ title: 'Policy checks', status: 'completed' }, { title: 'Report', status: 'in-progress' }] } })
    + row('tool.execution_complete', 4, { toolCallId: 'a', success: true })
    + row('tool.execution_start', 5, { toolCallId: 'b', toolName: 'run_in_terminal', arguments: { command: 'npm test', explanation: 'Run the policy checks' } })
    + row('tool.execution_complete', 9, { toolCallId: 'b', success: false })
    + row('tool.execution_start', 10, { toolCallId: 'c', toolName: 'create_file', arguments: { filePath: path.join(root, 'policy.js') } }));
  json(root, '.hve\\runs\\session-1.errors.json', { failures: [{ command: 'npm test', output: '1 failing' }], paused: false });
  const asks = listAsks(root);
  const { chats } = chatList(transcripts, root, asks.map(ask => ask.id), { 'session-1': { ask: ASK, how: 'started' } }, null, NOW);
  return { now: new Date(NOW).toISOString(), surface: 'sidebar', busy: false, error: null, workspace: { name: 'policy', path: root }, workspaceMessage: null,
    connection: { version: '0.20.0', python: 'python', guard: 'advise' }, telemetry: { enabled: false, file: null }, transcripts,
    asks, asksError: null, snapshot: snapshot(root), snapshotError: null, activity: { ...activity(root, path.join(transcripts, 'session-1.jsonl'), null, NOW), chats },
    activityError: null, pending: null, files: askTree(root, ASK), filesError: null, packs: null, packsError: null, evaluations: [], map: null, outputsError: null,
    models: null, modelsError: null, analysis: null, insights: null, handoff: null, handoffError: null,
    navigate: { page: 'live', seq: 0 } };
}

/** @type {import('../../extension/ui/types').UiState} */
const UI = { page: 'live', filter: 'all', open: {}, seq: 0 };

test('the sidebar shows live status, the ask, what needs you, the current step and its to-do list', t => {
  const tree = sidebar(model(t), UI, NOW);
  const shown = text(tree);
  assert.match(shown, /Working/);
  assert.match(shown, /Build the onboarding workspace/);
  assert.match(shown, /Frontier Lite · deliver: done · started .* · 1 chat/);
  assert.match(shown, /2 items ready for your sign-off/);
  assert.match(shown, /The last command failed/);
  assert.match(shown, /Created policy\.js/);
  assert.match(shown, /1 of 2 to-dos done/);
  assert.match(shown, /Research telemetry/);
  assert.equal(find(tree, node => node.attrs.role === 'switch')[0].attrs['aria-checked'], 'false');
  assert.deepEqual(actions(tree, 'go').map(node => node.attrs['data-page']).filter((page, index, all) => all.indexOf(page) === index), ['live', 'plan', 'progress', 'files', 'others', 'telemetry', 'visuals', 'skills', 'settings']);
  assert.doesNotMatch(shown, /Continue in Chat/);
});

test('text from the project and the chat never becomes markup', t => {
  const data = model(t);
  data.snapshot.ask.title = '<img src=x onerror=alert(1)>';
  data.activity.session.events[0].title = '<script>alert(1)</script>';
  const trees = [sidebar(data, UI, NOW), dashboard({ ...data, surface: 'editor' }, UI, NOW)];
  for (const tree of trees) assert.deepEqual(find(tree, node => ['img', 'script'].includes(node.tag)), []);
  assert.match(text(trees[0]), /<img src=x onerror=alert\(1\)>/);
});

test('the Live page shows the session numbers, failures, files changed and a filterable timeline', t => {
  const data = { ...model(t), surface: 'editor' };
  const all = dashboard(data, UI, NOW);
  assert.match(text(all), /Tool calls3/);
  assert.match(text(all), /Failed commands in a row \(error guard\)/);
  assert.match(text(all), /1 failing/);
  assert.deepEqual(actions(all, 'openFile').map(node => node.attrs['data-path']), ['policy.js']);
  assert.match(text(all), /Token use and cost appear here/);
  const commands = dashboard(data, { ...UI, filter: 'commands' }, NOW);
  const events = find(commands, node => node.tag === 'li' && /\bevent\b/.test(node.attrs.class || ''));
  assert.deepEqual(events.map(node => text(node).replace(/\d+s ago$/, '')), ['Run the policy checksfailednpm test']);
  data.activity.tokens = { models: [{ model: 'claude-opus-5.5', calls: 12, failed: 1, input: 503677, output: 15387, cached: 466746 }], aiu: 63.04 };
  const used = text(dashboard(data, UI, NOW));
  assert.match(used, /claude-opus-5\.512 \(1 stopped\)504k467k15k/);
  assert.match(used, /63\.0 AI units/);
});

test('the Plan page shows the formatted plan, where it stands, Edit, and sign-offs tied to the exact revision', t => {
  const data = { ...model(t), surface: 'editor' };
  const tree = dashboard(data, { ...UI, page: 'plan' }, NOW);
  assert.ok(find(tree, node => node.tag === 'h2' && text(node) === 'Workspace policy').length);
  assert.match(text(tree), /Agreed/);
  assert.equal(actions(tree, 'editPlan').length, 1);
  const accept = actions(tree, 'review').filter(node => node.attrs['data-value'] === 'accepted');
  assert.equal(accept.length, 2);
  assert.ok(accept.every(node => node.attrs['data-revision'] === data.snapshot.revision && !('disabled' in node.attrs)));
  data.snapshot.planState = 'unsynced';
  const held = dashboard(data, { ...UI, page: 'plan' }, NOW);
  assert.ok(actions(held, 'review').filter(node => node.attrs['data-value'] === 'accepted').every(node => 'disabled' in node.attrs));
  assert.match(text(held), /Evaluation: not answered/);
});

test('the Progress, Skills and packs, and Settings pages explain what each action does', t => {
  const data = { ...model(t), surface: 'editor' };
  const progress = text(dashboard(data, { ...UI, page: 'progress' }, NOW));
  assert.match(progress, /Deliver.*Deliver the workspace policy/);
  assert.match(progress, /exit 0/);
  data.packs = [{ id: 'oracle', name: 'oracle-offering', version: '1.2.0', enabled: true, disabledReason: null, source: 'index:oracle-offering@1.2.0',
    agents: ['Oracle architect'], lifecycles: ['oracle-delivery'], knowledge: [], templates: ['prd'] }];
  const skills = dashboard(data, { ...UI, page: 'skills' }, NOW);
  assert.match(text(skills), /ux-flows.*382 tokens/);
  assert.match(text(skills), /wow-uplift/);
  assert.match(text(skills), /oracle-offering 1\.2\.01 agent · 1 lifecycle · 1 template · 0 knowledge documents/);
  assert.deepEqual(actions(skills, 'command').map(node => node.attrs['data-name']), ['installPack', 'managePacks']);
  assert.match(text(skills), /You see its source, hash and tools before it installs/);
  const settings = dashboard(data, { ...UI, page: 'settings' }, NOW);
  assert.match(text(settings), /Advisory: warns in chat, does not block/);
  assert.match(text(settings), /full content/);
  assert.deepEqual(actions(settings, 'command').map(node => node.attrs['data-name']), ['setup', 'installHarnesses']);
  assert.equal(actions(settings, 'telemetry')[0].attrs['data-value'], 'on');
});

test('the webview loads only bundled scripts under a strict content security policy', t => {
  const fixture = mission(t);
  const view = fixture.controls.view();
  fixture.controls.provider.resolveWebviewView(view);
  assert.match(view.webview.html, /default-src 'none'/);
  assert.match(view.webview.html, /script-src 'nonce-[a-f0-9]+'/);
  assert.doesNotMatch(view.webview.html, /unsafe-inline|unsafe-eval|https?:\/\/(?!local\.test)/);
  const css = fs.readFileSync(path.join(EXTENSION, 'ui', 'media', 'app.css'), 'utf8');
  for (const rule of [/focus-visible/, /prefers-reduced-motion/, /vscode-high-contrast/]) assert.match(css, rule);
  for (const file of ['app.js', 'views.js', 'pages.js', 'markdown.js', 'vnode.js']) {
    assert.doesNotMatch(fs.readFileSync(path.join(EXTENSION, 'ui', 'media', file), 'utf8'), /innerHTML|insertAdjacentHTML|eval\(|new Function/, file);
  }
});
