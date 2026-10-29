'use strict';
/** Verify Mission Control ships inside the existing extension, activates without a Copilot dependency, and owns only its resources. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { EXTENSION, workspace, removeWorkspace } = require('./helpers');
const { host, mission } = require('./vscode-stub');
const { project } = require('./fixtures');
const { snapshot } = require('../../extension/ui/workspace-state');
const { message } = require('../../extension/ui/validate');
const manifest = JSON.parse(fs.readFileSync(path.join(EXTENSION, 'package.json'), 'utf8'));
const ORIGINAL = ['frontierHve.setup', 'frontierHve.installHarnesses', 'frontierHve.researchTelemetry', 'frontierHve.researchTelemetryOff',
  'frontierHve.installPlugin', 'frontierHve.managePlugins'];
const MISSION = ['frontierHve.openMissionControl', 'frontierHve.refreshMissionControl', 'frontierHve.selectWorkspace', 'frontierHve.newAsk',
  'frontierHve.editPlan'];

/** Return the models posted to views so far.
 * @param {{calls: unknown[][]}} controls
 * @returns {import('../../extension/ui/types').Model[]}
 */
function posted(controls) {
  return controls.calls.filter(call => call[0] === 'post').map(call => /** @type {{model: import('../../extension/ui/types').Model}} */ (call[1]).model);
}

test('the existing extension contributes Mission Control, keeps its commands and has no Copilot extension dependency', () => {
  assert.equal(manifest.name, 'frontier-hve');
  assert.equal(manifest.extensionDependencies, undefined);
  assert.equal(manifest.dependencies, undefined);
  assert.deepEqual(manifest.activationEvents, ['onStartupFinished']);
  assert.deepEqual(manifest.contributes.commands.map(command => command.command), [...ORIGINAL, ...MISSION]);
  assert.deepEqual(manifest.contributes.viewsContainers.activitybar, [{ id: 'frontierHve', title: 'Frontier HVE', icon: 'ui/media/hve.svg' }]);
  assert.deepEqual(manifest.contributes.views.frontierHve, [{ type: 'webview', id: 'frontierHve.missionControl', name: 'Mission Control' },
    { id: 'frontierHve.harnessFiles', name: 'Harness files' }]);
  assert.ok(manifest.contributes.configuration.properties['frontierHve.pluginIndex']);
  for (const file of ['hve.svg', 'app.css', 'app.js', 'vnode.js', 'markdown.js', 'views.js', 'pages.js']) {
    assert.ok(fs.statSync(path.join(EXTENSION, 'ui', 'media', file)).isFile(), file);
  }
});

test('full activation registers Mission Control before setup work, keeps every original behaviour and shows state without Python', async t => {
  const root = workspace();
  const storage = workspace();
  const fixture = host([root], storage);
  const searchPath = process.env.PATH;
  process.env.PATH = '';
  t.after(() => {
    process.env.PATH = searchPath;
    fixture.context.subscriptions.forEach(resource => resource.dispose());
    [root, storage].forEach(removeWorkspace);
  });
  const activation = fixture.load('extension.js').activate(fixture.context);
  for (const id of [...ORIGINAL, ...MISSION]) assert.ok(fixture.controls.commands.has(id), id);
  assert.ok(fixture.controls.calls.some(call => call[0] === 'provider' && call[1] === 'frontierHve.missionControl'));
  await activation;
  assert.ok(fs.statSync(path.join(storage, 'plugin', 'plugin.json')).isFile());
  assert.deepEqual(fixture.controls.settings.get('chat.pluginLocations'), { [path.join(storage, 'plugin')]: true });
  assert.ok(fixture.controls.statusItems.some(item => item.visible && item.text.includes('guards off')));
  assert.equal((await fixture.controls.commands.get('frontierHve.refreshMissionControl')()).ask, null);
  assert.equal(fixture.controls.commands.get('frontierHve.missionControlModel')().connection.python, null);
  await assert.rejects(fixture.controls.commands.get('frontierHve.newAsk')(), /needs Python 3\.11\+/);
  assert.deepEqual(fs.readdirSync(root), []);
});

test('registration is passive, watches harness state and chat transcripts, and posts the model without creating project files', async t => {
  const fixture = mission(t);
  assert.ok(!fixture.controls.calls.some(call => call[0] !== 'provider'));
  assert.deepEqual(fixture.controls.watchers.map(watcher => watcher.pattern.pattern), ['.hve/**/*', 'GitHub.copilot-chat/transcripts/*.jsonl', '.harness/**/*']);
  assert.equal(fixture.controls.watchers[1].pattern.base.fsPath, path.join(fixture.storage, 'window'));
  const view = fixture.controls.view();
  fixture.controls.provider.resolveWebviewView(view);
  assert.ok(view.webview.options.localResourceRoots[0].fsPath.endsWith(path.join('extension', 'ui', 'media')));
  for (const script of ['vnode.js', 'markdown.js', 'views.js', 'pages.js', 'app.js']) assert.match(view.webview.html, new RegExp(script.replace('.', '\\.')));
  const result = await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  assert.equal(result.ask, null);
  assert.deepEqual(fs.readdirSync(fixture.root), []);
  const model = posted(fixture.controls).at(-1);
  assert.equal(model.surface, 'sidebar');
  assert.equal(model.connection.version, manifest.version);
  assert.deepEqual(model.activity.chats, []);
  assert.deepEqual(model.asks, []);
});

test('multi-root requires selection and untrusted workspaces are rejected', async t => {
  const fixture = mission(t, 2);
  assert.equal(await fixture.controls.commands.get('frontierHve.refreshMissionControl')(), null);
  fixture.api.workspace.isTrusted = false;
  await assert.rejects(fixture.controls.commands.get('frontierHve.newAsk')(), /Trust this workspace/);
  assert.ok(fixture.controls.errors.length);
  assert.deepEqual(fs.readdirSync(fixture.root), []);
});

test('view messages are an allowlist: no arbitrary commands, no Chat drafts, no unexpected fields', () => {
  assert.throws(() => message({ action: 'execute', command: 'arbitrary' }), /Unknown UI/);
  assert.throws(() => message({ action: 'continue' }), /Unknown UI/);
  assert.throws(() => message({ action: 'refresh', shell: 'arbitrary' }), /Unexpected fields/);
  assert.throws(() => message({ action: 'review', item: 'stage:deliver' }), /Unexpected fields/);
  assert.equal(message({ action: 'openDashboard', page: 'plan' }).page, 'plan');
  assert.equal(message({ action: 'telemetry', value: 'on' }).value, 'on');
});

test('background changes refresh only a visible Mission Control, so hidden views never run the harness or raise errors', async t => {
  const fixture = mission(t);
  const changed = () => fixture.controls.watchers.forEach(watcher => watcher.listeners.forEach(listener => listener()));
  const settle = () => new Promise(resolve => setTimeout(resolve, 600));
  changed();
  await settle();
  assert.equal(posted(fixture.controls).length, 0);
  const view = fixture.controls.view(true);
  fixture.controls.provider.resolveWebviewView(view);
  changed();
  await settle();
  assert.equal(posted(fixture.controls).length, 1);
  view.visible = false;
  changed();
  await settle();
  assert.equal(posted(fixture.controls).length, 1);
  assert.deepEqual(fixture.controls.errors, []);
});

test('disposal removes only Mission Control resources and leaves harness state intact', async t => {
  const fixture = mission(t);
  project(fixture.root);
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  const before = snapshot(fixture.root).revision;
  fixture.context.subscriptions.forEach(resource => resource.dispose());
  for (const id of MISSION) assert.ok(!fixture.controls.commands.has(id), id);
  assert.equal(fixture.controls.provider, null);
  assert.ok(fixture.controls.watchers.every(watcher => watcher.disposed));
  assert.equal(snapshot(fixture.root).revision, before);
});
