'use strict';
/** Verify Mission Control ships inside the existing extension, activates without a Copilot dependency, and owns only its resources. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { EXTENSION, workspace, removeWorkspace } = require('./helpers');
const { host } = require('./vscode-stub');
const { project } = require('./fixtures');
const { snapshot } = require('../../extension/ui/workspace-state');
const { message } = require('../../extension/ui/validate');
const manifest = JSON.parse(fs.readFileSync(path.join(EXTENSION, 'package.json'), 'utf8'));
const ORIGINAL = ['frontierHve.setup', 'frontierHve.installHarnesses', 'frontierHve.researchTelemetry', 'frontierHve.researchTelemetryOff',
  'frontierHve.installPlugin', 'frontierHve.managePlugins'];
const MISSION = ['frontierHve.openMissionControl', 'frontierHve.refreshMissionControl', 'frontierHve.selectWorkspace', 'frontierHve.newTask',
  'frontierHve.continueInChat'];

/** Register Mission Control alone in a host double with a fixed Python launcher.
 * @param {import('node:test').TestContext} t
 * @param {number} [count]
 * @returns {ReturnType<typeof host> & {root: string}}
 */
function mission(t, count = 1) {
  const roots = Array.from({ length: count }, () => workspace());
  const storage = workspace();
  const fixture = host(roots, storage);
  fixture.context.subscriptions.push(...fixture.load(path.join('ui', 'mission-control.js')).register(fixture.context, async () => 'python'));
  t.after(() => {
    fixture.context.subscriptions.forEach(resource => resource.dispose());
    [...roots, storage].forEach(removeWorkspace);
  });
  return { ...fixture, root: roots[0] };
}

test('the existing extension contributes Mission Control, keeps its commands and has no Copilot extension dependency', () => {
  assert.equal(manifest.name, 'frontier-hve');
  assert.equal(manifest.extensionDependencies, undefined);
  assert.equal(manifest.dependencies, undefined);
  assert.deepEqual(manifest.activationEvents, ['onStartupFinished']);
  assert.deepEqual(manifest.contributes.commands.map(command => command.command), [...ORIGINAL, ...MISSION]);
  assert.deepEqual(manifest.contributes.viewsContainers.activitybar, [{ id: 'frontierHve', title: 'Frontier HVE', icon: 'ui/media/hve.svg' }]);
  assert.deepEqual(manifest.contributes.views.frontierHve, [{ type: 'webview', id: 'frontierHve.missionControl', name: 'Mission Control' }]);
  assert.ok(manifest.contributes.configuration.properties['frontierHve.pluginIndex']);
  for (const file of ['ui/media/hve.svg', 'ui/media/app.css', 'ui/media/app.js']) assert.ok(fs.statSync(path.join(EXTENSION, file)).isFile(), file);
});

test('full activation registers Mission Control before setup work and keeps every original behaviour', async t => {
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
  await assert.rejects(fixture.controls.commands.get('frontierHve.refreshMissionControl')(), /needs Python 3\.11\+/);
  assert.deepEqual(fs.readdirSync(root), []);
});

test('registration is passive and renders the bundled runtime state without creating project files', async t => {
  const fixture = mission(t);
  assert.ok(!fixture.controls.calls.some(call => call[0] !== 'provider'));
  const view = fixture.controls.view();
  fixture.controls.provider.resolveWebviewView(view);
  assert.ok(view.webview.options.localResourceRoots[0].fsPath.endsWith(path.join('extension', 'ui', 'media')));
  assert.match(view.webview.html, /app\.css/);
  const result = await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  assert.equal(result.ask, null);
  assert.deepEqual(fs.readdirSync(fixture.root), []);
  assert.equal(fixture.controls.watchers[0].pattern.pattern, '.hve/{project,asks}/**/*');
  const rendered = fixture.controls.calls.filter(call => call[0] === 'render').at(-1);
  assert.match(rendered[1].html, new RegExp(`HVE ${manifest.version.replace(/\./g, '\\.')}`));
});

test('multi-root requires selection and untrusted workspaces are rejected', async t => {
  const fixture = mission(t, 2);
  assert.equal(await fixture.controls.commands.get('frontierHve.refreshMissionControl')(), null);
  fixture.api.workspace.isTrusted = false;
  await assert.rejects(fixture.controls.commands.get('frontierHve.newTask')(), /Trust this workspace/);
  assert.ok(fixture.controls.errors.length);
  assert.deepEqual(fs.readdirSync(fixture.root), []);
});

test('webview messages reject arbitrary commands and unexpected fields', () => {
  assert.throws(() => message({ action: 'execute', command: 'arbitrary' }), /Unknown UI/);
  assert.throws(() => message({ action: 'configurePython' }), /Unknown UI/);
  assert.throws(() => message({ action: 'refresh', shell: 'arbitrary' }), /Unexpected fields/);
  assert.throws(() => message({ action: 'review', item: 'stage:deliver' }), /Unexpected fields/);
  assert.equal(message({ action: 'navigate', page: 'evidence' }).page, 'evidence');
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
