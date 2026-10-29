'use strict';
/** Verify a different project is steered to a new workspace, and the window that opens it offers to start the ask there with the same title and description. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { workspace, removeWorkspace } = require('./helpers');
const { mission } = require('./vscode-stub');
const { listAsks, handoffFrom } = require('../../extension/ui/asks');
const { text } = require('../../extension/ui/media/vnode');
const { sidebar } = require('../../extension/ui/media/views');
const PAWS = ['Pawstagram', 'Build Pawstagram, a social photo app for dogs with a home feed, dog profiles and a pack hive'];
const TRADING = ['Paws trading platform', 'Create a stock trading platform where pet shops trade shares and owners invest in dog brands'];
const UI = { page: 'live', filter: 'all', open: {}, seq: 0 };

/** Return storage shared by two test windows, like VS Code's global state.
 * @returns {{get: (key: string) => unknown, update: (key: string, value: unknown) => Promise<void>}}
 */
function shared() {
  const memory = new Map();
  return { get: key => memory.get(key), update: async (key, value) => { memory.set(key, value); } };
}

/** Return a folder as the open dialog returns it.
 * @param {string} folder
 * @returns {{fsPath: string, scheme: string, toString: () => string}}
 */
function picked(folder) { return { fsPath: folder, scheme: 'file', toString: () => pathToFileURL(folder).href }; }

/** Run New ask with a title and description and the given answers.
 * @param {ReturnType<typeof mission>} fixture
 * @param {string[]} brief
 * @param {string[]} answers
 * @returns {Promise<void>}
 */
async function newAsk(fixture, brief, answers) {
  fixture.controls.inputs.push(...brief);
  fixture.controls.confirmations.push(...answers);
  await fixture.controls.commands.get('frontierHve.newAsk')();
}

/** Wait until a condition holds, failing after 20 seconds.
 * @param {() => boolean} condition
 * @returns {Promise<void>}
 */
async function until(condition) {
  for (let waited = 0; !condition(); waited += 50) {
    if (waited > 20000) throw new Error('Timed out waiting for the new window to start the ask.');
    await new Promise(resolve => setTimeout(resolve, 50));
  }
}

test('a carried-over ask belongs to one folder for a day, and a malformed one fails loudly', () => {
  const at = '2026-10-29T04:00:00.000Z';
  const saved = { folder: path.join(path.sep, 'work', 'paws-trading'), title: TRADING[0], description: TRADING[1], from: 'pawstagram', at };
  const now = Date.parse(at) + 60_000;
  assert.deepEqual(handoffFrom(saved, path.join(path.sep, 'work', 'paws-trading'), now), { title: TRADING[0], description: TRADING[1], from: 'pawstagram', at });
  if (process.platform === 'win32') assert.ok(handoffFrom(saved, path.join(path.sep, 'WORK', 'Paws-Trading'), now));
  assert.equal(handoffFrom(saved, path.join(path.sep, 'work', 'pawstagram'), now), null);
  assert.equal(handoffFrom(saved, saved.folder, Date.parse(at) + 25 * 3_600_000), null);
  assert.equal(handoffFrom(undefined, saved.folder, now), null);
  assert.throws(() => handoffFrom({ ...saved, title: 'x' }, saved.folder, now), /Invalid carried-over ask/);
});

test('a different project gets the harness\'s reason and a recommendation to start a new workspace before anything is created', async t => {
  const fixture = mission(t);
  await newAsk(fixture, PAWS, ['Create ask']);
  fixture.controls.dialogs.push(undefined);
  await newAsk(fixture, TRADING, ['Start in a new workspace…']);
  const warning = fixture.controls.calls.filter(call => call[0] === 'confirmation').at(-1);
  assert.equal(warning[1], '“Paws trading platform” looks like a different project.');
  assert.match(warning[2].detail, /^The harness says this starts a different project from the one in this workspace/);
  assert.match(warning[2].detail, /This workspace holds one project \(.+\)\. A different product belongs in its own workspace/);
  assert.match(warning[2].detail, /Recommended: start it in a new workspace/);
  assert.deepEqual(warning.slice(3), ['Start in a new workspace…', 'Keep it in this project']);
  const dialog = fixture.controls.calls.find(call => call[0] === 'dialog')[1];
  assert.equal(dialog.canSelectFolders, true);
  assert.equal(dialog.canSelectFiles, false);
  assert.equal(dialog.openLabel, 'Start the project here');
  assert.equal(dialog.defaultUri.fsPath, path.dirname(fixture.root));
  assert.match(dialog.title, /^Folder for “Paws trading platform”/);
  assert.equal(listAsks(fixture.root).length, 1);
  assert.ok(!fixture.controls.calls.some(call => call[0] === 'vscode.openFolder'));
  assert.equal(fixture.context.globalState.get('askHandoff'), undefined);
});

test('choosing a folder keeps the title and description for it and opens it in a new window, creating nothing here', async t => {
  const storage = shared();
  const fixture = mission(t, 1, storage);
  const target = workspace();
  t.after(() => removeWorkspace(target));
  await newAsk(fixture, PAWS, ['Create ask']);
  fixture.controls.dialogs.push([picked(target)]);
  await newAsk(fixture, TRADING, ['Start in a new workspace…']);
  const open = fixture.controls.calls.find(call => call[0] === 'vscode.openFolder');
  assert.equal(open[1].fsPath, target);
  assert.deepEqual(open[2], { forceNewWindow: true });
  const saved = storage.get('askHandoff');
  assert.deepEqual({ ...saved, at: undefined }, { folder: target, title: TRADING[0], description: TRADING[1], from: path.basename(fixture.root), at: undefined });
  assert.equal(listAsks(fixture.root).length, 1);
  assert.ok(!fixture.controls.calls.some(call => call[0] === 'workbench.action.chat.newLocalChat' && fixture.controls.calls.indexOf(call) > fixture.controls.calls.indexOf(open)));
});

test('a folder inside this workspace, or the workspace itself, is refused', async t => {
  const fixture = mission(t);
  await newAsk(fixture, PAWS, ['Create ask']);
  for (const folder of [path.join(fixture.root, 'trading'), fixture.root]) {
    fixture.controls.dialogs.push([picked(folder)]);
    fixture.controls.inputs.push(...TRADING);
    fixture.controls.confirmations.push('Start in a new workspace…');
    await assert.rejects(fixture.controls.provider.execute({ action: 'newAsk' }), /Choose a folder outside .*: a different project needs a folder of its own/);
  }
  assert.equal(fixture.context.globalState.get('askHandoff'), undefined);
});

test('keeping it in this project creates the ask here after the usual confirmation', async t => {
  const fixture = mission(t);
  await newAsk(fixture, PAWS, ['Create ask']);
  await newAsk(fixture, TRADING, ['Keep it in this project', 'Create ask']);
  const create = fixture.controls.calls.filter(call => call[0] === 'confirmation').at(-1);
  assert.match(create[2].detail, /^You chose to keep it in this project\./);
  assert.equal(listAsks(fixture.root).find(ask => ask.active).title, 'Paws trading platform');
});

test('the window that opens the folder offers to start the ask, with the title and description filled in, and creates it there', async t => {
  const storage = shared();
  const fixture = mission(t, 1, storage);
  await storage.update('askHandoff', { folder: fixture.root, title: TRADING[0], description: TRADING[1], from: 'pawstagram', at: new Date().toISOString() });
  fixture.controls.notices.push('Start the ask');
  fixture.controls.inputs.push(...TRADING);
  fixture.controls.confirmations.push('Create ask');
  fixture.context.subscriptions.forEach(resource => resource.dispose());
  const again = fixture.load(path.join('ui', 'mission-control.js')).register(fixture.context, async () => 'python');
  t.after(() => again.forEach(resource => resource.dispose()));
  await until(() => listAsks(fixture.root).length === 1 && fixture.controls.calls.some(call => call[0] === 'workbench.action.chat.newLocalChat'));
  const offer = fixture.controls.calls.find(call => call[0] === 'information');
  assert.equal(offer[1], 'Start the ask “Paws trading platform” here? You began it in pawstagram, where Mission Control recommended a workspace of its own.');
  assert.deepEqual(offer.slice(2), ['Start the ask', 'Not now']);
  const boxes = fixture.controls.calls.filter(call => call[0] === 'input').map(call => call[1]);
  assert.deepEqual(boxes.map(box => box.value), TRADING);
  assert.equal(listAsks(fixture.root)[0].title, 'Paws trading platform');
  assert.equal(storage.get('askHandoff'), undefined);
});

test('the sidebar shows a carried-over ask until it is started or dismissed; Not now forgets it', async t => {
  const storage = shared();
  const fixture = mission(t, 1, storage);
  await storage.update('askHandoff', { folder: fixture.root, title: TRADING[0], description: TRADING[1], from: 'pawstagram', at: new Date().toISOString() });
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  let model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.equal(model.handoff.title, 'Paws trading platform');
  const tree = sidebar({ ...model, surface: 'sidebar' }, UI, Date.now());
  assert.match(text(tree), /Ready to start here: “Paws trading platform”, carried over from pawstagram/);
  await fixture.controls.provider.execute({ action: 'dismissHandoff' });
  model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.equal(model.handoff, null);
  assert.equal(storage.get('askHandoff'), undefined);
  assert.doesNotMatch(text(sidebar({ ...model, surface: 'sidebar' }, UI, Date.now())), /Ready to start here/);
  await assert.rejects(fixture.controls.provider.execute({ action: 'startHandoff' }), /no ask waiting to start in this folder/);
  assert.deepEqual(listAsks(fixture.root), []);
});

test('an ask carried over to another folder is not offered here', async t => {
  const storage = shared();
  const fixture = mission(t, 1, storage);
  await storage.update('askHandoff', { folder: path.join(fixture.root, '..', 'elsewhere'), title: TRADING[0], description: TRADING[1], from: 'pawstagram',
    at: new Date().toISOString() });
  fixture.context.subscriptions.forEach(resource => resource.dispose());
  const again = fixture.load(path.join('ui', 'mission-control.js')).register(fixture.context, async () => 'python');
  t.after(() => again.forEach(resource => resource.dispose()));
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.ok(!fixture.controls.calls.some(call => call[0] === 'information'));
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  assert.equal(fixture.controls.commands.get('frontierHve.missionControlModel')().handoff, null);
  assert.ok(storage.get('askHandoff'));
});
