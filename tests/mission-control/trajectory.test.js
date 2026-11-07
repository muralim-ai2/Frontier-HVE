'use strict';
/** Verify the Agent Trajectory tab: the OTel span adapter, the tab and its states, the synced graph, timeline and details, and the filters. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { workspace, removeWorkspace } = require('./helpers');
const fx = require('./trajectory-fixtures');
const { activity } = require('../../extension/ui/activity');
const { trajectory, redact } = require('../../extension/ui/trajectory');

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
  assert.deepEqual(run.traceIds, [fx.TRACE]);
  assert.deepEqual([run.start, run.durationMs], [fx.T0, 60000]);
  const m1 = event(run, 'm1');
  assert.deepEqual(m1.tokens, { input: 12000, output: 300, cached: 6000, reasoning: 0 });
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
