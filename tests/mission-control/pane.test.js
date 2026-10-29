'use strict';
/** Verify the Harness files pane: everything under .hve/ and .harness/ as a native tree, ask folders titled, files opening on click, links never followed, live updates. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { workspace, removeWorkspace, json, EXTENSION } = require('./helpers');
const { mission } = require('./vscode-stub');
const { project, ASK } = require('./fixtures');
const manifest = JSON.parse(fs.readFileSync(path.join(EXTENSION, 'package.json'), 'utf8'));
const DRAFT = '20261028-1300-draft';

/** Return the registered tree view and its data provider.
 * @param {ReturnType<typeof mission>} fixture
 * @returns {{view: any, tree: any}}
 */
function pane(fixture) {
  const view = fixture.controls.trees.find(tree => tree.id === 'frontierHve.harnessFiles');
  assert.ok(view, 'The Harness files pane must be registered.');
  return { view, tree: view.options.treeDataProvider };
}

/** Return a child node by name.
 * @param {any} tree
 * @param {any} node
 * @param {string} name
 * @returns {any}
 */
function child(tree, node, name) {
  const found = tree.getChildren(node).find(entry => entry.name === name);
  assert.ok(found, `${node ? node.path : 'root'} has no ${name}`);
  return found;
}

/** Write a project with an active ask, a folder without a contract, loose files, run records and loop evidence.
 * @param {string} root
 * @returns {void}
 */
function populate(root) {
  project(root);
  fs.mkdirSync(path.join(root, '.hve', 'asks', DRAFT));
  fs.writeFileSync(path.join(root, '.hve', 'asks', DRAFT, 'request.md'), 'A draft the agent never finished');
  fs.writeFileSync(path.join(root, '.hve', 'asks', 'request.md'), 'Build: Pawstagram');
  json(root, '.hve\\runs\\d973bb01.errors.json', { failures: [], paused: false });
  fs.mkdirSync(path.join(root, '.harness', 'evidence', 'prototype'), { recursive: true });
  fs.writeFileSync(path.join(root, '.harness', 'evidence', 'prototype', 'home.png'), Buffer.alloc(2048));
}

test('the pane is contributed under Mission Control, with a welcome message when there is nothing to show', t => {
  assert.deepEqual(manifest.contributes.views.frontierHve.map(view => view.id), ['frontierHve.missionControl', 'frontierHve.harnessFiles']);
  assert.equal(manifest.contributes.views.frontierHve[1].name, 'Harness files');
  const welcome = manifest.contributes.viewsWelcome.find(row => row.view === 'frontierHve.harnessFiles');
  assert.match(welcome.contents, /No \.hve\/ or \.harness\/ folder/);
  assert.match(welcome.contents, /\(command:frontierHve\.newAsk\)/);
  const fixture = mission(t);
  const { view, tree } = pane(fixture);
  assert.equal(view.options.showCollapseAll, true);
  assert.deepEqual(tree.getChildren(), []);
});

test('everything under .hve/ and .harness/ is listed: folders first, ask folders newest first, loose files and records included', t => {
  const fixture = mission(t);
  populate(fixture.root);
  const { tree } = pane(fixture);
  const roots = tree.getChildren();
  assert.deepEqual(roots.map(node => node.name), ['.hve', '.harness']);
  const hve = roots[0];
  assert.equal(tree.getTreeItem(hve).collapsibleState, 2);
  assert.deepEqual(tree.getChildren(hve).map(node => node.name), ['asks', 'project', 'runs']);
  const asks = child(tree, hve, 'asks');
  assert.equal(tree.getTreeItem(asks).collapsibleState, 2);
  assert.deepEqual(tree.getChildren(asks).map(node => [node.name, node.kind]), [[DRAFT, 'folder'], [ASK, 'folder'], ['active.json', 'file'], ['request.md', 'file']]);
  const active = tree.getTreeItem(child(tree, asks, ASK));
  assert.equal(active.description, 'active · Build the onboarding workspace');
  assert.equal(active.collapsibleState, 2);
  assert.match(active.tooltip, /The active ask/);
  const draft = tree.getTreeItem(child(tree, asks, DRAFT));
  assert.equal(draft.description, undefined);
  assert.equal(draft.collapsibleState, 1);
  assert.deepEqual(tree.getChildren(child(tree, asks, DRAFT)).map(node => node.name), ['request.md']);
  assert.deepEqual(tree.getChildren(child(tree, asks, ASK)).map(node => node.name), ['loop', 'contract.json', 'plan.md', 'request.md']);
  const shot = child(tree, child(tree, child(tree, roots[1], 'evidence'), 'prototype'), 'home.png');
  assert.equal(shot.path, '.harness/evidence/prototype/home.png');
  assert.equal(tree.getTreeItem(shot).description, '2.0 KB');
  assert.equal(tree.getTreeItem(child(tree, child(tree, hve, 'runs'), 'd973bb01.errors.json')).collapsibleState, 0);
});

test('a file opens on click from its own path, and folders do not', t => {
  const fixture = mission(t);
  populate(fixture.root);
  const { tree } = pane(fixture);
  const plan = child(tree, child(tree, child(tree, tree.getChildren()[0], 'asks'), ASK), 'plan.md');
  const item = tree.getTreeItem(plan);
  assert.equal(item.command.command, 'vscode.open');
  assert.equal(path.relative(fs.realpathSync(fixture.root), item.command.arguments[0].fsPath), path.join('.hve', 'asks', ASK, 'plan.md'));
  assert.equal(item.resourceUri.fsPath, item.command.arguments[0].fsPath);
  assert.match(item.description, / B$/);
  assert.equal(tree.getTreeItem(tree.getChildren()[0]).command, undefined);
});

test('links are listed but never followed, and very large folders stop at 500 entries with a note', t => {
  const fixture = mission(t);
  populate(fixture.root);
  const outside = workspace();
  t.after(() => removeWorkspace(outside));
  fs.writeFileSync(path.join(outside, 'secret.txt'), 'private');
  fs.symlinkSync(outside, path.join(fixture.root, '.hve', 'runs', 'linked'), 'junction');
  const { tree } = pane(fixture);
  const runs = child(tree, tree.getChildren()[0], 'runs');
  const link = child(tree, runs, 'linked');
  assert.equal(link.kind, 'other');
  const item = tree.getTreeItem(link);
  assert.equal(item.description, 'link or special file, not opened');
  assert.equal(item.command, undefined);
  assert.equal(item.collapsibleState, 0);
  assert.deepEqual(tree.getChildren(link), []);
  const bulk = path.join(fixture.root, '.harness', 'bulk');
  fs.mkdirSync(bulk);
  for (let index = 0; index < 503; index += 1) fs.writeFileSync(path.join(bulk, `log-${String(index).padStart(3, '0')}.txt`), 'x');
  const listed = tree.getChildren(child(tree, tree.getChildren()[1], 'bulk'));
  assert.equal(listed.length, 501);
  assert.equal(listed.at(-1).name, '3 more not shown');
  assert.equal(tree.getTreeItem(listed.at(-1)).command, undefined);
});

test('changes under .hve/ and .harness/ refresh the pane even while the Mission Control view is hidden; chat transcripts do not', async t => {
  const fixture = mission(t);
  const { tree } = pane(fixture);
  let fired = 0;
  tree.onDidChangeTreeData(() => { fired += 1; });
  const patterns = fixture.controls.watchers.map(watcher => watcher.pattern.pattern);
  assert.deepEqual(patterns, ['.hve/**/*', 'GitHub.copilot-chat/transcripts/*.jsonl', '.harness/**/*']);
  const settle = () => new Promise(resolve => setTimeout(resolve, 600));
  fixture.controls.watchers[1].listeners.forEach(listener => listener());
  await settle();
  assert.equal(fired, 0);
  fixture.controls.watchers[2].listeners.forEach(listener => listener());
  fixture.controls.watchers[0].listeners.forEach(listener => listener());
  await settle();
  assert.equal(fired, 1);
  assert.deepEqual(fixture.controls.errors, []);
});

test('an unreadable ask contract is shown at the top of the pane while every file stays browsable', t => {
  const fixture = mission(t);
  populate(fixture.root);
  const contract = path.join(fixture.root, '.hve', 'asks', ASK, 'contract.json');
  const good = fs.readFileSync(contract, 'utf8');
  fs.writeFileSync(contract, '{"ask":');
  const { view, tree } = pane(fixture);
  const asks = child(tree, tree.getChildren()[0], 'asks');
  assert.match(view.message, /Ask titles cannot be read: Invalid JSON in .*contract\.json/);
  assert.equal(tree.getTreeItem(child(tree, asks, ASK)).description, undefined);
  assert.ok(child(tree, child(tree, asks, ASK), 'contract.json'));
  fs.writeFileSync(contract, good);
  tree.getChildren();
  assert.equal(view.message, undefined);
});

test('the pane follows the selected workspace folder and is disposed with Mission Control', async t => {
  const fixture = mission(t, 2);
  const { view, tree } = pane(fixture);
  assert.deepEqual(tree.getChildren(), []);
  populate(fixture.root);
  await fixture.controls.commands.get('frontierHve.selectWorkspace')();
  assert.deepEqual(tree.getChildren().map(node => node.name), ['.hve', '.harness']);
  fixture.context.subscriptions.forEach(resource => resource.dispose());
  assert.equal(view.closed, true);
});
