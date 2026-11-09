'use strict';
/** Verify the Agent Trajectory tab: the OTel span adapter, the tab and its states, the synced graph, timeline and details, and the filters. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { workspace, removeWorkspace, EXTENSION } = require('./helpers');
const fx = require('./trajectory-fixtures');
const { mission } = require('./vscode-stub');
const { activity } = require('../../extension/ui/activity');
const { trajectory, redact } = require('../../extension/ui/trajectory');
const { text } = require('../../extension/ui/media/vnode');
const { dashboard } = require('../../extension/ui/media/pages');
const { PAGES } = require('../../extension/ui/media/views');
const views = require('../../extension/ui/media/trajectory');
/** @type {import('../../extension/ui/types').UiState} */
const UI = { page: 'trajectory', filter: 'all', open: {}, seq: 0 };

/** Return every view node matching a test.
 * @param {import('../../extension/ui/types').VNode | string | import('../../extension/ui/types').Child[]} node
 * @param {(node: import('../../extension/ui/types').VNode) => boolean} match
 * @returns {import('../../extension/ui/types').VNode[]}
 */
function find(node, match) {
  if (Array.isArray(node)) return node.flatMap(child => child && typeof child === 'object' ? find(/** @type {any} */ (child), match) : []);
  return typeof node === 'string' ? [] : [...(match(node) ? [node] : []), ...node.children.flatMap(child => find(child, match))];
}

/** Return the trajectory page drawn for a model and view state.
 * @param {import('../../extension/ui/types').Model} model
 * @param {Partial<import('../../extension/ui/types').TrajectoryUi>} [traj]
 * @returns {import('../../extension/ui/types').VNode}
 */
function page(model, traj = {}) {
  return dashboard(model, { ...UI, traj: { ...views.uiState(UI), ...traj } }, fx.T0 + 120_000);
}

/** Register Mission Control with the multi-agent export as research telemetry and the main chat on screen; return its model.
 * @param {import('node:test').TestContext} t
 * @param {Record<string, unknown>[] | null} [rows] Null leaves research telemetry off.
 * @returns {Promise<{fixture: ReturnType<typeof mission>, model: () => import('../../extension/ui/types').Model}>}
 */
async function host(t, rows = fx.multiAgentRun()) {
  const fixture = mission(t);
  if (rows) {
    fixture.controls.settings.set('github.copilot.chat.otel.enabled', true);
    fixture.controls.settings.set('github.copilot.chat.otel.outfile', fx.writeExport(fixture.root, rows));
  }
  fx.writeTranscript(fixture.transcripts);
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  await fixture.controls.provider.execute({ action: 'selectChat', chat: fx.CHAT });
  return { fixture, model: () => fixture.controls.commands.get('frontierHve.missionControlModel')() };
}

/** Return a disposable workspace with the multi-agent export and transcript, and the main chat's session.
 * @param {import('node:test').TestContext} t
 * @param {Record<string, unknown>[]} [rows]
 * @returns {{root: string, file: string, session: import('../../extension/ui/types').Session}}
 */
function setup(t, rows = fx.multiAgentRun()) {
  const root = workspace();
  t.after(() => removeWorkspace(root));
  const file = fx.writeExport(root, rows);
  const transcript = fx.writeTranscript(path.join(root, 'transcripts'));
  const session = /** @type {import('../../extension/ui/types').Session} */ (activity(root, transcript, null, fx.T0 + 3600_000).session);
  return { root, file, session };
}

/** Return the event of a span id.
 * @param {import('../../extension/ui/types').Trajectory} run
 * @param {string} id
 * @returns {import('../../extension/ui/types').TrajectoryEvent}
 */
function event(run, id) {
  const found = run.events.find(item => item.id === id);
  if (!found) throw new Error(`no event ${id}`);
  return found;
}

test('adapter: builds the span tree from out-of-order lines, numbers steps depth-first and keeps parallel calls as sibling branches', t => {
  const { root, file, session } = setup(t);
  const run = /** @type {import('../../extension/ui/types').Trajectory} */ (trajectory(root, file, session));
  assert.equal(run.source, 'telemetry');
  assert.deepEqual(run.roots, ['a1', 'o1']);
  assert.deepEqual(run.events.map(item => item.id), ['a1', 'm1', 't1', 't2', 'm2', 't3', 't4', 't5', 'a2', 'm3', 'm4', 'm5', 't6', 'o1']);
  assert.deepEqual(run.events.map(item => item.seq), run.events.map((_, index) => index + 1));
  assert.deepEqual(event(run, 'a1').children, ['m1', 't1', 't2', 'm2', 't3', 't4', 't5', 'm5', 't6']);
  assert.deepEqual([event(run, 't2').depth, event(run, 'a2').depth, event(run, 'm3').depth], [1, 2, 3]);
  assert.ok(event(run, 't2').start < /** @type {number} */ (event(run, 't1').end), 't1 and t2 overlap');
  assert.deepEqual([event(run, 'a2').kind, event(run, 'a2').agent, event(run, 'a2').parentId], ['handoff', 'Explore', 't5']);
  assert.deepEqual([event(run, 'a1').kind, event(run, 'm1').kind, event(run, 't5').kind, event(run, 't5').name], ['agent', 'model', 'tool', 'runSubagent']);
  assert.ok(!run.events.some(item => item.id === 'x1'), 'spans of another chat and trace stay out');
});

test('adapter: settles status, retries, duplicates and orphans without failing the whole run', t => {
  const { root, file, session } = setup(t);
  const run = /** @type {import('../../extension/ui/types').Trajectory} */ (trajectory(root, file, session));
  assert.deepEqual(['t1', 't3', 'm3', 'm5', 't6'].map(id => event(run, id).status), ['ok', 'failed', 'timeout', 'cancelled', 'running']);
  assert.equal(event(run, 't3').statusMessage, 'Command exited 1');
  assert.deepEqual(['t3', 't4', 'm3', 'm4', 'm1', 'm2'].map(id => event(run, id).retry), [0, 1, 0, 1, 0, 0]);
  assert.equal(run.events.filter(item => item.id === 't1').length, 1);
  assert.deepEqual([event(run, 'o1').orphan, event(run, 'o1').parentId, run.orphans], [true, 'lost-parent', 1]);
  assert.equal(event(run, 't1').durationMs, 200);
  assert.equal(event(run, 't6').end, null);
  assert.deepEqual([run.end, run.running, run.lastUpdate], [null, 1, fx.T0 + 60000]);
});

test('adapter: sums agents, calls, errors and tokens and keeps trace context', t => {
  const { root, file, session } = setup(t);
  const run = /** @type {import('../../extension/ui/types').Trajectory} */ (trajectory(root, file, session));
  assert.deepEqual(run.agents, ['Frontier HVE Collab', 'Explore']);
  assert.deepEqual([run.modelCalls, run.toolCalls, run.handoffs, run.errors], [5, 7, 1, 2]);
  assert.deepEqual([run.input, run.output, run.cached], [35000, 875, 17500]);
  assert.ok(Math.abs(/** @type {number} */ (run.aiu) - 0.035) < 1e-9);
  assert.deepEqual([run.traceIds, run.start, run.durationMs], [[fx.TRACE], fx.T0, 60000]);
  const m1 = event(run, 'm1');
  assert.deepEqual(m1.tokens, { input: 12000, output: 300, cached: 6000, reasoning: 0, aiu: 0.012 });
  assert.deepEqual([m1.traceId, m1.spanId, m1.parentId, m1.model, m1.session], [fx.TRACE, 'm1', 'a1', 'claude-opus-5.5', fx.CHAT]);
  assert.deepEqual(m1.resource, [['session.id', 'window-1'], ['service.name', 'copilot-chat']]);
});

test('adapter: clips large content, omits system instructions and redacts secrets before anything reaches the view', t => {
  const { root, file, session } = setup(t);
  const run = /** @type {import('../../extension/ui/types').Trajectory} */ (trajectory(root, file, session));
  const result = event(run, 't1').content.find(item => item.label === 'Tool result');
  assert.deepEqual([result?.chars, result?.text.length, result?.truncated, result?.side], [5000, 1500, true, 'output']);
  const args = event(run, 't4').content[0];
  assert.equal(args.redacted, true);
  assert.ok(!args.text.includes(fx.SECRET) && args.text.includes('[redacted]'));
  assert.match(/** @type {[string, string]} */ (event(run, 'm1').attributes.find(([key]) => key === 'gen_ai.system_instructions'))[1], /^omitted from the viewer \(7,200 characters\)$/);
  assert.ok(!JSON.stringify(run).includes(fx.SECRET));
  assert.deepEqual(redact('Authorization: Bearer abcdefghijklmnop1234 and api_key="s3cretValue99" and max_tokens: 160000'),
    { text: 'Authorization: Bearer [redacted] and api_key="[redacted]" and max_tokens: 160000', redacted: true });
});

test('adapter: with telemetry off or no spans for the chat, the transcript gives a reduced trajectory', t => {
  const { root, session } = setup(t);
  const run = /** @type {import('../../extension/ui/types').Trajectory} */ (trajectory(root, null, session));
  assert.equal(run.source, 'transcript');
  assert.deepEqual(run.events.map(item => [item.kind, item.status]), [['user', 'ok'], ['tool', 'ok'], ['tool', 'failed'], ['handoff', 'ok'], ['response', 'ok']]);
  assert.deepEqual([run.traceIds, run.modelCalls, run.handoffs, run.errors], [[], 0, 1, 1]);
  assert.equal(new Set(run.events.map(item => item.id)).size, run.events.length);
  const other = setup(t, [fx.span('z', null, 'invoke_agent Other', 0, 10, { 'copilot_chat.chat_session_id': 'someone-else' })]);
  assert.equal(/** @type {import('../../extension/ui/types').Trajectory} */ (trajectory(other.root, other.file, other.session)).source, 'transcript');
  assert.equal(trajectory(root, null, null), null);
});

test('adapter: a large run keeps the latest 1,000 spans and says how many it left out', t => {
  const { root, file, session } = setup(t, fx.largeRun(1200));
  const run = /** @type {import('../../extension/ui/types').Trajectory} */ (trajectory(root, file, session));
  assert.equal(run.events.length, 1000);
  assert.equal(run.truncated, 201);
  assert.ok(run.orphans > 0 || run.roots.length >= 1);
});

test('adapter: an export outside the workspace is not read', t => {
  const { root, session } = setup(t);
  const outside = workspace();
  t.after(() => removeWorkspace(outside));
  const file = fx.writeExport(outside, fx.multiAgentRun());
  assert.equal(/** @type {import('../../extension/ui/types').Trajectory} */ (trajectory(root, file, session)).source, 'transcript');
  assert.ok(fs.existsSync(file));
});

test('tab: Mission Control lists Agent Trajectory, loads its script and opens it on the dashboard', async t => {
  assert.deepEqual(PAGES.find(([id]) => id === 'trajectory'), ['trajectory', 'Agent Trajectory', 'route']);
  const fixture = mission(t);
  const view = fixture.controls.view();
  fixture.controls.provider.resolveWebviewView(view);
  assert.match(view.webview.html, /trajectory\.js[\s\S]*pages\.js/);
  await fixture.controls.provider.execute({ action: 'openDashboard', page: 'trajectory' });
  await fixture.controls.provider.execute({ action: 'openDashboard', page: 'visuals' });
  assert.equal(fixture.controls.commands.get('frontierHve.missionControlModel')().navigate.page, 'visuals');
  const tabs = find(dashboard(fixture.controls.commands.get('frontierHve.missionControlModel')(), UI, Date.now()), node => node.attrs.class === 'tab');
  assert.ok(tabs.some(node => text(node) === 'Agent Trajectory' && node.attrs['aria-current'] === 'page'));
  assert.doesNotMatch(fs.readFileSync(path.join(EXTENSION, 'ui', 'media', 'trajectory.js'), 'utf8'), /innerHTML|insertAdjacentHTML|eval\(|new Function/);
});

test('tab: the host builds the trajectory of the chat on screen from the telemetry export and watches that file', async t => {
  const { fixture, model } = await host(t);
  const run = /** @type {import('../../extension/ui/types').Trajectory} */ (model().trajectory);
  assert.deepEqual([run.source, run.chat, run.events.length, model().trajectoryError], ['telemetry', fx.CHAT, 14, null]);
  fixture.controls.provider.bindWatchers();
  assert.ok(fixture.controls.watchers.some(watcher => watcher.pattern.pattern === 'copilot-otel.jsonl' && watcher.pattern.base.fsPath === path.join(fixture.root, '.hve', 'runs')));
});

test('tab: the summary bar shows identity, live state, counts, tokens, AI units, IDs and actions', async t => {
  const { model } = await host(t);
  const shown = text(page(model()));
  for (const part of ['Agent trajectory · one chat', 'Show me the trajectory of this run', 'Live', '2 errors', 'from research telemetry spans', 'Model calls5', 'Tool calls7',
    'Handoffs1', 'Errors2', 'Input tokens35k', 'Output tokens875', 'Cached tokens18k', 'AI units0.04', 'Agents2 · Frontier HVE Collab, Explore', 'Active agentFrontier HVE Collab',
    `Trace ID${fx.TRACE}`, `Run (chat) ID${fx.CHAT}`, 'Pause live updates', 'Open raw export', 'Partial telemetry: 1 step still running or not yet exported.',
    '1 span whose parent was not exported is shown as roots.', 'Duration1 min 0 s so far']) assert.ok(shown.includes(part), part);
  const tree = page(model());
  assert.deepEqual(find(tree, node => node.attrs['data-action'] === 'openFile').map(node => node.attrs['data-path']), ['.hve/runs/copilot-otel.jsonl']);
  assert.match(text(page(model(), { paused: true })), /Live updates paused\. Telemetry keeps arriving\.Resume/);
});

test('tab: telemetry off gives the reduced transcript view with the switch; no chat, no events and read errors each say what to do', async t => {
  const off = await host(t, null);
  const reduced = page(off.model());
  assert.match(text(reduced), /Reduced view from the chat transcript: research telemetry is off/);
  assert.equal(find(reduced, node => node.attrs.role === 'switch').length, 1);
  assert.match(text(reduced), /from the chat transcript \(reduced\)/);
  const none = mission(t);
  await none.controls.commands.get('frontierHve.refreshMissionControl')();
  assert.match(text(page(none.controls.commands.get('frontierHve.missionControlModel')())), /No chat selectedPick a chat of this window/);
  const run = /** @type {import('../../extension/ui/types').Trajectory} */ (off.model().trajectory);
  assert.match(text(page({ ...off.model(), trajectory: { ...run, events: [], roots: [] } })), /No trajectory events recorded/);
  const broken = await host(t, [...fx.multiAgentRun(), { ...fx.tool('bad', 'a1', 'read_file', 0, 1), startTime: 'yesterday' }]);
  assert.match(String(broken.model().trajectoryError), /Telemetry span time: expected \[seconds, nanoseconds\]/);
  assert.equal(broken.model().activityError, null);
  const failed = page(broken.model());
  assert.match(text(failed), /cannot read this chat's trajectory: Telemetry span time/);
  assert.equal(find(failed, node => node.attrs['data-action'] === 'refresh' && text(node) === 'Retry').length, 1);
});

test('views: the graph draws one keyboard-reachable node per step with labelled handoff and retry edges and the saved zoom', async t => {
  const { model } = await host(t);
  const tree = page(model(), { zoom: { k: 0.5, x: 10, y: 20 } });
  const nodes = find(tree, node => node.tag === 'g' && node.attrs['data-action'] === 'trajSelect');
  assert.equal(nodes.length, 14);
  assert.deepEqual(nodes.filter(node => node.attrs.tabindex === '0').map(node => node.attrs['data-id']), ['a1']);
  assert.match(nodes[5].attrs['aria-label'], /^Step 6: Tool call run_in_terminal, failed, 3\.9 s$/);
  assert.match(nodes[9].attrs.class, /status-timeout/);
  assert.deepEqual([nodes[8].attrs['data-parent'], nodes[8].attrs['data-child']], ['t5', 'm3']);
  assert.deepEqual(find(tree, node => node.attrs.class === 'tedge-label').map(text), ['retry 1', 'handoff', 'retry 1']);
  assert.equal(find(tree, node => node.attrs.class === 'tviewport')[0].attrs.transform, 'translate(10 20) scale(0.5)');
  assert.match(text(nodes[13]), /#14 · Tool call · orphan/);
  assert.equal(text(find(nodes[1], node => node.tag === 'title')[0]), nodes[1].attrs['aria-label']);
  const { at } = views.layout(/** @type {import('../../extension/ui/types').Trajectory} */ (model().trajectory).events);
  const a1 = /** @type {{x: number, y: number}} */ (at.get('a1'));
  assert.deepEqual([a1.x, at.get('a2')?.x, at.get('m3')?.x], [0, 2 * views.NODE.dx, 3 * views.NODE.dx]);
  assert.equal(a1.y, ((at.get('m1')?.y || 0) + (at.get('t6')?.y || 0)) / 2);
});

test('views: the timeline nests steps, collapses branches, switches clock and elapsed time and pages long runs', async t => {
  const { model } = await host(t);
  const rows = find(page(model(), { view: 'timeline' }), node => node.tag === 'li' && /\btrow\b/.test(node.attrs.class));
  assert.equal(rows.length, 14);
  assert.match(rows[9].attrs.class, /depth-3/);
  assert.match(text(rows[5]), /^#6\+5\.1 sTool callrun_in_terminal/);
  assert.match(text(rows[6]), /retry 1/);
  const clock = new Date(fx.T0 + 5100).toLocaleTimeString('en-GB', { hour12: false });
  assert.ok(text(find(page(model(), { view: 'timeline', time: 'clock' }), node => /\btrow\b/.test(node.attrs.class || ''))[5]).includes(clock));
  const folded = find(page(model(), { view: 'timeline', collapsed: { a2: true } }), node => /\btrow\b/.test(node.attrs.class || ''));
  assert.deepEqual(folded.length, 12);
  assert.equal(find(folded, node => node.attrs['data-action'] === 'trajToggle' && node.attrs['data-id'] === 'a2')[0].attrs['aria-expanded'], 'false');
  const large = await host(t, fx.largeRun(1200));
  const long = page(large.model(), { view: 'timeline' });
  assert.equal(find(long, node => /\btrow\b/.test(node.attrs.class || '')).length, views.PAGE_ROWS);
  assert.match(text(long), /Show 300 more of 700 remaining steps/);
  const graph = page(large.model());
  assert.equal(find(graph, node => node.tag === 'g' && node.attrs['data-action'] === 'trajSelect').length, 400);
  assert.match(text(graph), /Showing the first 400 of 1000 steps/);
  assert.match(text(graph), /The oldest 201 spans are left out; the latest 1,000 are shown\./);
});

test('views: one selection drives the graph, the timeline and the details panel, which shows trace context, errors, tokens and content as text', async t => {
  const { model } = await host(t);
  for (const view of /** @type {const} */ (['graph', 'timeline'])) {
    const tree = page(model(), { view, sel: 't3' });
    const picked = find(tree, node => node.attrs['data-action'] === 'trajSelect' && node.attrs['data-id'] === 't3' && !/\bbtn\b/.test(node.attrs.class || ''));
    assert.equal(picked[0].attrs['aria-pressed'], 'true', view);
    const details = find(tree, node => node.tag === 'aside')[0];
    const shown = text(details);
    for (const part of ['Tool callrun_in_terminal', '✕ failed', 'OverviewEvent typeTool call (execute_tool run_in_terminal)', 'Step6', 'Toolrun_in_terminal', 'Duration3.9 s',
      `Trace ID${fx.TRACE}`, 'Span IDt3', 'Parent span IDa1', `Run (chat) ID${fx.CHAT}`, 'ErrorKindfailedMessageCommand exited 1Error typeToolError', 'Retried as step 7']) {
      assert.ok(shown.includes(part), `${view}: ${part}`);
    }
    assert.deepEqual(find(details, node => node.attrs['data-action'] === 'trajCopy').map(node => node.attrs['data-value']), [fx.TRACE, 't3', 'a1', fx.CHAT]);
  }
  const model1 = find(page(model(), { sel: 'm1' }), node => node.tag === 'aside')[0];
  assert.match(text(model1), /PerformanceInput tokens12,000Output tokens300Cached tokens6,000Total tokens12,300AI units0\.012/);
  const pre = find(model1, node => node.tag === 'pre')[0];
  assert.deepEqual(pre.children, ['[{"role":"user","content":"Show me the trajectory <img src=x onerror=alert(1)>"}]']);
  assert.match(text(find(page(model(), { sel: 't1' }), node => node.tag === 'aside')[0]), /Tool result · 5,000 characters, first part shown/);
  assert.match(text(find(page(model(), { sel: 't4' }), node => node.tag === 'aside')[0]), /secrets redacted/);
  assert.match(text(find(page(model(), { sel: 'o1' }), node => node.tag === 'aside')[0]), /Its parent span lost-parent was not exported/);
  assert.match(text(find(page(model()), node => node.tag === 'aside')[0]), /Select a step/);
});

test('filters: errors only keeps failed, timed-out and cancelled steps with their ancestors as muted context, and resets in one click', async t => {
  const { model } = await host(t);
  const run = /** @type {import('../../extension/ui/types').Trajectory} */ (model().trajectory);
  const view = views.visible(run, { ...views.uiState(UI), errors: true });
  assert.deepEqual([...view.matched], ['t3', 'm3', 'm5']);
  assert.deepEqual(view.shown.map(e => e.id), ['a1', 't3', 't5', 'a2', 'm3', 'm5']);
  const tree = page(model(), { errors: true });
  const nodes = find(tree, node => node.tag === 'g' && node.attrs['data-action'] === 'trajSelect');
  assert.deepEqual(nodes.filter(node => /\bmuted\b/.test(node.attrs.class)).map(node => node.attrs['data-id']), ['a1', 't5', 'a2']);
  assert.match(text(tree), /3 of 14 steps match: errors only\. Ancestors they need stay as muted context\.Reset filters/);
  assert.equal(find(tree, node => node.attrs['data-action'] === 'trajErrors')[0].attrs['aria-pressed'], 'true');
  assert.equal(find(tree, node => node.attrs['data-action'] === 'trajClear').length, 1);
});

test('filters: search matches names, span and trace IDs; agent, type and status filters combine; nothing left offers a reset', async t => {
  const { model } = await host(t);
  const run = /** @type {import('../../extension/ui/types').Trajectory} */ (model().trajectory);
  const ids = (/** @type {Partial<import('../../extension/ui/types').TrajectoryUi>} */ state) => [...views.visible(run, { ...views.uiState(UI), ...state }).matched];
  assert.deepEqual(ids({ q: 'GREP' }), ['t2']);
  assert.deepEqual(ids({ q: 'm4' }), ['m4']);
  assert.deepEqual(ids({ q: 'toolerror' }), ['t3']);
  assert.equal(ids({ q: fx.TRACE }).length, 14);
  assert.deepEqual(ids({ agent: 'Explore' }), ['a2', 'm3', 'm4']);
  assert.deepEqual(ids({ agent: 'Explore', kind: 'model', status: 'ok' }), ['m4']);
  assert.deepEqual(views.visible(run, { ...views.uiState(UI), agent: 'Explore' }).shown.map(e => e.id), ['a1', 't5', 'a2', 'm3', 'm4']);
  const tree = page(model(), { kind: 'tool' });
  const options = find(find(tree, node => node.tag === 'select' && node.attrs['data-field'] === 'kind')[0], node => node.tag === 'option');
  assert.deepEqual(options.map(node => [node.attrs.value, 'selected' in node.attrs]), [['all', false], ['agent', false], ['model', false], ['tool', true], ['handoff', false]]);
  assert.match(text(tree), /7 of 14 steps match: Tool call/);
  const nothing = page(model(), { q: 'no-such-step' });
  assert.match(text(nothing), /No steps match these filtersThe filters removed every step of this run\.Reset filters/);
  assert.equal(find(nothing, node => node.attrs['data-action'] === 'trajClear' && /primary/.test(node.attrs.class)).length, 1);
});
