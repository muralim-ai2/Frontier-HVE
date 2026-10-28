'use strict';
/** Verify Mission Control's controller: the live model, refresh on transcript changes, navigation, the telemetry switch, packs and file access. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { workspace, removeWorkspace } = require('./helpers');
const { mission } = require('./vscode-stub');
const { project, ASK } = require('./fixtures');
const STARTED = new Date(Date.now() - 30_000).toISOString();

/** Write a chat transcript the way Copilot Chat does, one JSON event per line.
 * @param {string} folder
 * @param {object[]} rows
 * @returns {void}
 */
function transcript(folder, rows) {
  fs.mkdirSync(folder, { recursive: true });
  fs.writeFileSync(path.join(folder, 'session-1.jsonl'), rows.map(row => JSON.stringify({ timestamp: STARTED, ...row }) + '\n').join(''));
}

/** Return the models posted to views.
 * @param {{calls: unknown[][]}} controls
 * @returns {import('../../extension/ui/types').Model[]}
 */
function posted(controls) {
  return controls.calls.filter(call => call[0] === 'post').map(call => /** @type {{model: import('../../extension/ui/types').Model}} */ (call[1]).model);
}

test('the model carries the latest chat session from this window\'s transcripts', async t => {
  const fixture = mission(t);
  transcript(fixture.transcripts, [{ type: 'user.message', data: { content: 'Build the policy checker' } }, { type: 'assistant.turn_start', data: {} },
    { type: 'tool.execution_start', data: { toolCallId: 'a', toolName: 'create_file', arguments: { filePath: path.join(fixture.root, 'policy.js') } } }]);
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.equal(model.surface, 'editor');
  assert.equal(model.activity.session.status, 'working');
  assert.equal(model.activity.session.current.title, 'Created policy.js');
});

test('a transcript change refreshes a visible view with the new step', async t => {
  const fixture = mission(t);
  const view = fixture.controls.view(true);
  fixture.controls.provider.resolveWebviewView(view);
  transcript(fixture.transcripts, [{ type: 'assistant.turn_start', data: {} },
    { type: 'tool.execution_start', data: { toolCallId: 'a', toolName: 'run_in_terminal', arguments: { command: 'npm test', explanation: 'Run the checks' } } }]);
  fixture.controls.watchers[1].listeners.forEach(listener => listener());
  await new Promise(resolve => setTimeout(resolve, 700));
  assert.equal(posted(fixture.controls).at(-1).activity.session.current.title, 'Run the checks');
});

test('opening the dashboard on a page navigates once and later updates keep the user\'s own choice', async t => {
  const fixture = mission(t);
  await fixture.controls.provider.execute({ action: 'openDashboard', page: 'plan' });
  assert.equal(fixture.controls.panels.length, 1);
  const first = posted(fixture.controls).filter(model => model.surface === 'editor').at(-1);
  assert.deepEqual(first.navigate, { page: 'plan', seq: 1 });
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  assert.deepEqual(posted(fixture.controls).at(-1).navigate, { page: 'plan', seq: 1 });
  await fixture.controls.provider.execute({ action: 'openDashboard', page: 'skills' });
  assert.equal(fixture.controls.panels.length, 1);
  assert.deepEqual(posted(fixture.controls).at(-1).navigate, { page: 'skills', seq: 2 });
  await assert.rejects(fixture.controls.provider.execute({ action: 'openDashboard', page: 'chat' }), /Unknown page/);
});

test('the telemetry switch runs the extension\'s own commands with no extra confirmation', async t => {
  const fixture = mission(t);
  await fixture.controls.provider.execute({ action: 'telemetry', value: 'on' });
  await fixture.controls.provider.execute({ action: 'telemetry', value: 'off' });
  const ran = fixture.controls.calls.map(call => call[0]);
  assert.ok(ran.includes('frontierHve.researchTelemetry') && ran.includes('frontierHve.researchTelemetryOff'));
  assert.ok(!ran.includes('confirmation'));
  await assert.rejects(fixture.controls.provider.execute({ action: 'telemetry', value: 'maybe' }), /on or off/);
});

test('set-up and pack buttons run the original commands directly, and pack changes reload the installed packs', async t => {
  const home = fs.mkdtempSync(path.join(fs.realpathSync.native(os.tmpdir()), 'hve-mission-control-'));
  const previous = process.env.HVE_PLUGIN_HOME;
  process.env.HVE_PLUGIN_HOME = home;
  t.after(() => { process.env.HVE_PLUGIN_HOME = previous; removeWorkspace(home); });
  const fixture = mission(t);
  await fixture.controls.provider.execute({ action: 'command', name: 'installPack' });
  await fixture.controls.provider.execute({ action: 'command', name: 'setup' });
  const ran = fixture.controls.calls.map(call => call[0]);
  assert.ok(ran.includes('frontierHve.installPlugin') && ran.includes('frontierHve.setup'));
  assert.ok(!ran.includes('confirmation'));
  assert.deepEqual(fixture.controls.commands.get('frontierHve.missionControlModel')().packs, []);
  await assert.rejects(fixture.controls.provider.execute({ action: 'command', name: 'telemetryOn' }), /Unknown harness command/);
});

test('files open beside Mission Control only when it lists them', async t => {
  const fixture = mission(t);
  project(fixture.root);
  fs.writeFileSync(path.join(fixture.root, 'policy.js'), 'export {}');
  fs.writeFileSync(path.join(fixture.root, 'secret.txt'), 'private');
  fs.mkdirSync(path.join(fixture.root, '.hve', 'skills', 'ux-flows'), { recursive: true });
  fs.writeFileSync(path.join(fixture.root, '.hve', 'skills', 'ux-flows', 'SKILL.md'), '# UX flows');
  transcript(fixture.transcripts, [{ type: 'tool.execution_start', data: { toolCallId: 'o', toolName: 'run_in_terminal', arguments: { command: `python lifecycle.py open ${ASK}` } } },
    { type: 'tool.execution_start', data: { toolCallId: 'a', toolName: 'create_file', arguments: { filePath: path.join(fixture.root, 'policy.js') } } }]);
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  await fixture.controls.provider.execute({ action: 'openFile', path: 'policy.js' });
  await fixture.controls.provider.execute({ action: 'openFile', path: '.hve/skills/ux-flows/SKILL.md' });
  const opened = fixture.controls.calls.filter(call => call[0] === 'document');
  assert.deepEqual(opened.map(call => path.relative(fs.realpathSync(fixture.root), call[1].fsPath)), ['policy.js', path.join('.hve', 'skills', 'ux-flows', 'SKILL.md')]);
  assert.equal(opened[0][2].viewColumn, -2);
  await assert.rejects(fixture.controls.provider.execute({ action: 'openFile', path: 'secret.txt' }), /not listed/);
});

test('an unreadable transcript shows as an activity error while the task view keeps working', async t => {
  const fixture = mission(t);
  project(fixture.root);
  fs.mkdirSync(fixture.transcripts, { recursive: true });
  fs.writeFileSync(path.join(fixture.transcripts, 'session-1.jsonl'), '{"type":\n');
  const result = await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  assert.ok(result.ask);
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.match(model.activityError, /Invalid chat event on line 1/);
  assert.equal(model.activity, null);
});

test('Continue in Chat is gone: no command, no action and no Chat draft', async t => {
  const fixture = mission(t);
  assert.ok(![...fixture.controls.commands.keys()].some(id => /continue/i.test(id)));
  await assert.rejects(fixture.controls.provider.execute({ action: 'continue' }), /Unknown UI action/);
  assert.ok(!fixture.controls.calls.some(call => call[0] === 'workbench.action.chat.open'));
});
