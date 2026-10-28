'use strict';
/** Verify the ask dropdown: every ask of the project is listed, choosing one only changes the view, and Make active switches asks through the harness. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { workspace, removeWorkspace } = require('./helpers');
const { mission } = require('./vscode-stub');
const { realAsks } = require('./fixtures');
const { listAsks, askTime } = require('../../extension/ui/asks');
const { snapshot } = require('../../extension/ui/workspace-state');
const { message } = require('../../extension/ui/validate');
const { validateOperation } = require('../../extension/ui/lifecycle-cli');
const { text } = require('../../extension/ui/media/vnode');
const { sidebar } = require('../../extension/ui/media/views');
const { dashboard } = require('../../extension/ui/media/pages');
const UI = { page: 'plan', filter: 'all', open: {}, seq: 0 };
const ASKS = [['onboarding', 'Build an onboarding policy checker'], ['reporting', 'Write the quarterly revenue report']];

/** Return the posted models.
 * @param {{calls: unknown[][]}} controls
 * @returns {import('../../extension/ui/types').Model[]}
 */
function posted(controls) {
  return controls.calls.filter(call => call[0] === 'post').map(call => /** @type {{model: import('../../extension/ui/types').Model}} */ (call[1]).model);
}

/** Return every view node matching a test.
 * @param {import('../../extension/ui/types').VNode | string} node
 * @param {(node: import('../../extension/ui/types').VNode) => boolean} match
 * @returns {import('../../extension/ui/types').VNode[]}
 */
function find(node, match) {
  return typeof node === 'string' ? [] : [...(match(node) ? [node] : []), ...node.children.flatMap(child => find(child, match))];
}

/** Return the active ask pointer on disk.
 * @param {string} root
 * @returns {string}
 */
function active(root) {
  return JSON.parse(fs.readFileSync(path.join(root, '.hve', 'asks', 'active.json'), 'utf8')).active;
}

test('every ask of the project is listed newest first with its title, agent, stage and which one is active', async t => {
  const root = workspace();
  const storage = workspace();
  t.after(() => { removeWorkspace(root); removeWorkspace(storage); });
  assert.deepEqual(listAsks(root), []);
  const [first, second] = await realAsks(root, storage, ASKS);
  const asks = listAsks(root);
  assert.deepEqual(asks.map(ask => ask.id), [second, first].sort().reverse());
  const row = asks.find(ask => ask.id === first);
  assert.equal(row.title, 'Build an onboarding policy checker');
  assert.equal(row.agent, 'HVE creator');
  assert.match(row.stage, /: planned$/);
  assert.deepEqual(asks.filter(ask => ask.active).map(ask => ask.id), [second]);
  assert.equal(askTime('20261028-1752-integrated-ui'), Date.parse('2026-10-28T17:52:00Z'));
  assert.throws(() => askTime('../escape'), /Invalid ask identifier/);
});

test('a chosen ask is read in full without touching the active pointer, and unknown asks fail', async t => {
  const root = workspace();
  const storage = workspace();
  t.after(() => { removeWorkspace(root); removeWorkspace(storage); });
  const [first, second] = await realAsks(root, storage, ASKS);
  const shown = snapshot(root, first);
  assert.equal(shown.ask.id, first);
  assert.equal(shown.ask.active, false);
  assert.ok(shown.plan);
  assert.equal(snapshot(root).ask.id, second);
  assert.equal(snapshot(root).ask.active, true);
  assert.equal(snapshot(root, second).revision, snapshot(root).revision);
  assert.equal(active(root), second);
  assert.throws(() => snapshot(root, '20261028-1200-missing'), /missing from the project/);
  assert.throws(() => snapshot(root, '..\\escape'), /Invalid ask identifier/);
});

test('the dropdown switches what Mission Control shows, remembers it, and choosing the active ask follows it again', async t => {
  const fixture = mission(t);
  const [first, second] = await realAsks(fixture.root, fixture.storage, ASKS);
  fixture.controls.provider.resolveWebviewView(fixture.controls.view(true));
  await fixture.controls.provider.execute({ action: 'selectAsk', ask: first });
  let model = posted(fixture.controls).at(-1);
  assert.equal(model.snapshot.ask.id, first);
  assert.equal(model.snapshot.ask.active, false);
  assert.equal(fixture.context.workspaceState.get('selectedAsk'), first);
  assert.equal(active(fixture.root), second);
  await fixture.controls.provider.execute({ action: 'selectAsk', ask: second });
  model = posted(fixture.controls).at(-1);
  assert.equal(model.snapshot.ask.id, second);
  assert.equal(fixture.context.workspaceState.get('selectedAsk'), null);
  await assert.rejects(fixture.controls.provider.execute({ action: 'selectAsk', ask: '20261028-1200-missing' }), /No ask 20261028-1200-missing/);
  assert.throws(() => message({ action: 'selectAsk' }), /Unexpected fields/);
  assert.throws(() => message({ action: 'activateAsk', ask: first, force: 'yes' }), /Unexpected fields/);
});

test('the sidebar and dashboard show the dropdown, mark the active ask, and hold sign-off while an earlier ask is on screen', async t => {
  const fixture = mission(t);
  const [first, second] = await realAsks(fixture.root, fixture.storage, ASKS);
  await fixture.controls.provider.execute({ action: 'selectAsk', ask: first });
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  for (const tree of [sidebar({ ...model, surface: 'sidebar' }, UI, Date.now()), dashboard(model, UI, Date.now())]) {
    const select = find(tree, node => node.tag === 'select');
    assert.equal(select.length, 1);
    assert.equal(select[0].attrs['data-action'], 'selectAsk');
    const options = find(select[0], node => node.tag === 'option');
    assert.deepEqual(options.map(node => node.attrs.value), [second, first].sort().reverse());
    assert.deepEqual(options.filter(node => 'selected' in node.attrs).map(node => node.attrs.value), [first]);
    assert.match(text(options.find(node => node.attrs.value === second)), /Write the quarterly revenue report · .* · active$/);
    assert.match(text(tree), /You are viewing an earlier ask\. Agents work on “Write the quarterly revenue report”/);
    assert.deepEqual(find(tree, node => node.attrs['data-action'] === 'activateAsk').map(node => node.attrs['data-ask']), [first]);
  }
  const plan = dashboard(model, UI, Date.now());
  const reviews = find(plan, node => node.attrs['data-action'] === 'review');
  assert.ok(reviews.length && reviews.every(node => 'disabled' in node.attrs && node.attrs.title === 'Make this ask active to sign off'));
});

test('Make active reopens the earlier ask through the harness only after confirmation, and the view follows it', async t => {
  const fixture = mission(t);
  const [first, second] = await realAsks(fixture.root, fixture.storage, ASKS);
  await fixture.controls.provider.execute({ action: 'selectAsk', ask: first });
  await fixture.controls.provider.execute({ action: 'activateAsk', ask: first });
  assert.equal(active(fixture.root), second);
  const asked = fixture.controls.calls.filter(call => call[0] === 'confirmation');
  assert.equal(asked.length, 1);
  assert.match(asked[0][1], /Make "Build an onboarding policy checker" the active ask\?/);
  assert.match(asked[0][2].detail, /lifecycle\.py open/);
  assert.match(asked[0][2].detail, /stays on disk, unfinished items included/);
  fixture.controls.confirmations.push('Make active');
  await fixture.controls.provider.execute({ action: 'activateAsk', ask: first });
  assert.equal(active(fixture.root), first);
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.equal(model.snapshot.ask.id, first);
  assert.equal(model.snapshot.ask.active, true);
  assert.equal(fixture.context.workspaceState.get('selectedAsk'), null);
  assert.ok(fs.existsSync(path.join(fixture.root, '.hve', 'asks', second, 'contract.json')));
  assert.doesNotThrow(() => validateOperation(['open', second]));
  assert.throws(() => validateOperation(['open', '../escape']), /Unsupported lifecycle operation/);
  assert.throws(() => validateOperation(['close']), /Unsupported lifecycle operation/);
});

test('a remembered ask that no longer exists is dropped and the view follows the active ask', async t => {
  const fixture = mission(t);
  const [, second] = await realAsks(fixture.root, fixture.storage, ASKS);
  await fixture.context.workspaceState.update('selectedAsk', '20261028-1200-removed');
  fixture.context.subscriptions.forEach(resource => resource.dispose());
  const reloaded = fixture.load(path.join('ui', 'mission-control.js')).register(fixture.context, async () => 'python');
  t.after(() => reloaded.forEach(resource => resource.dispose()));
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.equal(model.snapshot.ask.id, second);
  assert.equal(model.asksError, null);
  assert.equal(fixture.context.workspaceState.get('selectedAsk'), null);
});
