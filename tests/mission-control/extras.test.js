'use strict';
/** Verify the extras: pruning research telemetry, building and opening the solution map, the infographic chat, evaluation and provenance links, the progress summary and chat details. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
const { mission } = require('./vscode-stub');
const { project, ASK } = require('./fixtures');
const { chatMeta } = require('../../extension/ui/chats');
const { evaluationFiles } = require('../../extension/ui/asks');
const { text } = require('../../extension/ui/media/vnode');
const { dashboard } = require('../../extension/ui/media/pages');
const { sidebar } = require('../../extension/ui/media/views');
const UI = { page: 'progress', filter: 'all', open: {}, seq: 0 };

/** Write a telemetry export and point the research telemetry setting at it.
 * @param {ReturnType<typeof mission>} fixture
 * @returns {string}
 */
function telemetryFile(fixture) {
  const file = path.join(fixture.root, '.hve', 'runs', 'copilot-otel.jsonl');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, '{"name":"chat a"}\n{"name":"chat b"}\n');
  fixture.controls.settings.set('github.copilot.chat.otel.outfile', '.hve/runs/copilot-otel.jsonl');
  fixture.controls.settings.set('github.copilot.chat.otel.enabled', true);
  return file;
}

test('Prune data archives the telemetry export, then empties it, after confirmation; Delete all empties it with no copy', async t => {
  const fixture = mission(t);
  const file = telemetryFile(fixture);
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.equal(model.telemetry.file, file);
  assert.equal(model.telemetry.bytes, 36);
  assert.match(text(sidebar({ ...model, surface: 'sidebar' }, UI, Date.now())), /Prune data \(0\.0 MB\)…/);
  await fixture.controls.provider.execute({ action: 'pruneTelemetry' });
  assert.equal(fs.statSync(file).size, 36);
  fixture.controls.confirmations.push('Archive, then empty');
  await fixture.controls.provider.execute({ action: 'pruneTelemetry' });
  const archive = fs.readdirSync(path.dirname(file)).find(name => name.startsWith('otel-archive-'));
  assert.equal(zlib.gunzipSync(fs.readFileSync(path.join(path.dirname(file), archive))).toString(), '{"name":"chat a"}\n{"name":"chat b"}\n');
  assert.equal(fs.statSync(file).size, 0);
  const asked = fixture.controls.calls.filter(call => call[0] === 'confirmation').at(-1);
  assert.deepEqual(asked.slice(3), ['Archive, then empty', 'Delete all records']);
  fs.writeFileSync(file, '{"name":"chat c"}\n');
  fixture.controls.confirmations.push('Delete all records');
  await fixture.controls.provider.execute({ action: 'pruneTelemetry' });
  assert.equal(fs.statSync(file).size, 0);
  assert.equal(fs.readdirSync(path.dirname(file)).filter(name => name.startsWith('otel-archive-')).length, 1);
  fixture.controls.settings.set('github.copilot.chat.otel.outfile', 'notes.txt');
  await assert.rejects(fixture.controls.provider.execute({ action: 'pruneTelemetry' }), /only prunes a \.jsonl telemetry export/);
});

test('Build the map runs the bundled map tool, and the map opens in its own tab', async t => {
  const fixture = mission(t);
  fs.writeFileSync(path.join(fixture.root, 'app.js'), 'export function feed() { return 1; }\n');
  await assert.rejects(fixture.controls.provider.execute({ action: 'openMap' }), /no solution map yet/);
  await fixture.controls.provider.execute({ action: 'refreshMap' });
  assert.ok(fs.statSync(path.join(fixture.root, '.hve', 'map', 'explorer.html')).size > 1000);
  assert.match(fixture.controls.calls.find(call => call[0] === 'information')[1], /^Solution map built: small repository, \d+ files, \d+ concepts\.$/);
  const panel = fixture.controls.panels.at(-1);
  assert.match(panel.webview.html, /<script/);
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.ok(model.map.built);
  const page = text(dashboard(model, { ...UI, page: 'visuals' }, Date.now()));
  assert.match(page, /Solution mapbuilt just now/);
  assert.match(page, /Refresh the mapOpen the map/);
  assert.match(page, /Clickable infographic/);
});

test('Make an infographic opens a new Local chat with the skill and the subject filled in, not sent', async t => {
  const fixture = mission(t);
  fixture.controls.inputs.push('How Pawstagram turns a photo into a post');
  await fixture.controls.provider.execute({ action: 'infographic' });
  const chat = fixture.controls.calls.filter(call => String(call[0]).startsWith('workbench.action.chat.'));
  assert.deepEqual(chat.map(call => call[0]), ['workbench.action.chat.open', 'workbench.action.chat.newLocalChat', 'workbench.action.chat.open']);
  assert.deepEqual(chat[2][1], { query: '/clickable-infographic How Pawstagram turns a photo into a post', isPartialQuery: true, mode: 'Frontier HVE Collab' });
});

test('Progress lists evaluation reports and the ask\'s contract and provenance, and they open beside Mission Control', async t => {
  const fixture = mission(t);
  project(fixture.root);
  const run = path.join(fixture.root, '.hve', 'evaluations', 'run-1');
  fs.mkdirSync(run, { recursive: true });
  fs.writeFileSync(path.join(run, 'report.json'), '{"decision":"pass","score":0.82}');
  fs.mkdirSync(path.join(fixture.root, '.hve', 'evaluations', 'input'));
  fs.writeFileSync(path.join(fixture.root, '.hve', 'asks', ASK, 'provenance.md'), '# Provenance\n\nAll five pillars recorded.');
  assert.deepEqual(evaluationFiles(fixture.root), ['.hve/evaluations/run-1/report.json']);
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  const page = text(dashboard(model, UI, Date.now()));
  assert.match(page, /Evaluations\.hve\/evaluations\/run-1\/report\.json/);
  assert.match(page, new RegExp(`Contract and provenance.*\\.hve/asks/${ASK}/contract\\.json\\.hve/asks/${ASK}/provenance\\.md`));
  assert.match(page, /Summarize this ask/);
  await fixture.controls.provider.execute({ action: 'openFile', path: '.hve/evaluations/run-1/report.json' });
  await fixture.controls.provider.execute({ action: 'openFile', path: `.hve/asks/${ASK}/provenance.md` });
  assert.equal(fixture.controls.calls.filter(call => call[0] === 'document').length, 2);
});

test('Summarize streams a three-bullet summary of the ask from its state, provenance and latest evaluation', async t => {
  const fixture = mission(t);
  project(fixture.root);
  fs.writeFileSync(path.join(fixture.root, '.hve', 'asks', ASK, 'provenance.md'), '# Provenance\n\nPolicy delivered.');
  /** @type {string[]} */
  const prompts = [];
  fixture.controls.models.push({ id: 'claude-haiku-5.5', name: 'Claude Haiku 5.5', family: 'claude-haiku', sendRequest: async messages => {
    prompts.push(messages[0].content);
    return { text: (async function* () { yield '- Delivered the policy.\n- No evaluation ran.\n- Accept the deliver stage next.'; })() };
  } });
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  await fixture.controls.provider.execute({ action: 'summarize', model: 'claude-haiku-5.5' });
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.equal(model.analysis.topic, 'progress');
  assert.match(prompts[0], /exactly 3 bullets/);
  assert.match(prompts[0], /provenance\.md:\n# Provenance/);
  assert.match(prompts[0], /No evaluation report yet\./);
  assert.match(text(dashboard(model, UI, Date.now())), /Accept the deliver stage next/);
  assert.doesNotMatch(text(dashboard(model, { ...UI, page: 'telemetry' }, Date.now())), /Accept the deliver stage next/);
});

test('a chat\'s agent, model and Local execution come from VS Code\'s own session record', t => {
  const fixture = mission(t);
  const sessions = path.join(path.dirname(path.dirname(fixture.transcripts)), 'chatSessions');
  fs.mkdirSync(sessions, { recursive: true });
  fs.writeFileSync(path.join(sessions, 'chat-1.jsonl'), '{"kind":0,"v":{"requests":[]}}\n'
    + '{"kind":2,"v":[{"modelId":"copilot/claude-opus-5.5","modeInfo":{"telemetryModeName":"Frontier Prototype Creator"}}]}\n'
    + '{"kind":2,"v":[{"modelId":"copilot/claude-haiku-5.5","modeInfo":{"telemetryModeName":"Frontier HVE Collab"}}]}\n');
  assert.deepEqual(chatMeta(fixture.transcripts, 'chat-1'), { agent: 'Frontier HVE Collab', model: 'claude-haiku-5.5', mode: 'Local' });
  assert.deepEqual(chatMeta(fixture.transcripts, 'chat-2'), { agent: null, model: null, mode: null });
  assert.throws(() => chatMeta(fixture.transcripts, '../x'), /Invalid chat session id/);
});

test('every surface is marked as an early release', async t => {
  const fixture = mission(t);
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.match(text(sidebar({ ...model, surface: 'sidebar' }, UI, Date.now())), /^Frontier HVEEarly/);
  assert.match(text(dashboard(model, UI, Date.now())), /Early release/);
});
