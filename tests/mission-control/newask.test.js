'use strict';
/** Verify New ask asks for a title, then an optional description, names the ask from the title and shows it, and lets the harness's scope check read the description. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { mission } = require('./vscode-stub');
const { listAsks, askRequest, scopeText } = require('../../extension/ui/asks');
const { snapshot } = require('../../extension/ui/workspace-state');

/** Return the input boxes shown so far.
 * @param {{calls: unknown[][]}} controls
 * @returns {any[]}
 */
function inputs(controls) { return controls.calls.filter(call => call[0] === 'input').map(call => call[1]); }

/** Return the confirmations shown so far.
 * @param {{calls: unknown[][]}} controls
 * @returns {any[][]}
 */
function confirmations(controls) { return controls.calls.filter(call => call[0] === 'confirmation'); }

/** Create an ask through New ask with a title and description.
 * @param {ReturnType<typeof mission>} fixture
 * @param {string} title
 * @param {string} description
 * @param {string[]} [answers] Buttons chosen in order.
 * @returns {Promise<void>}
 */
async function create(fixture, title, description, answers = ['Create ask']) {
  fixture.controls.inputs.push(title, description);
  fixture.controls.confirmations.push(...answers);
  await fixture.controls.commands.get('frontierHve.newAsk')();
}

test('the first box asks for a short title and the second for an optional description, each saying what it wants', async t => {
  const fixture = mission(t);
  await fixture.controls.commands.get('frontierHve.newAsk')();
  const [first] = inputs(fixture.controls);
  assert.equal(first.title, 'New ask (1 of 2): title');
  assert.equal(first.placeHolder, 'Title');
  assert.match(first.prompt, /short name/);
  assert.match(first.prompt, /describe it in the next step/);
  assert.equal(first.validateInput('ab'), 'Use 3-80 characters.');
  assert.equal(first.validateInput('x'.repeat(81)), 'Use 3-80 characters.');
  assert.equal(first.validateInput('!!!'), 'Use at least one letter or digit.');
  assert.equal(first.validateInput('Dog profile badges'), null);
  fixture.controls.inputs.push('Dog profile badges');
  await fixture.controls.commands.get('frontierHve.newAsk')();
  const second = inputs(fixture.controls).at(-1);
  assert.equal(second.title, 'New ask (2 of 2): what should “Dog profile badges” deliver?');
  assert.match(second.prompt, /^Optional\./);
  assert.match(second.prompt, /files and screenshots in the chat/);
  assert.equal(second.validateInput(''), null);
  assert.equal(second.validateInput('x'.repeat(4001)), 'Use at most 4,000 characters.');
  assert.deepEqual(fs.readdirSync(fixture.root), []);
});

test('the ask is named from the title, saves the title as its heading, and shows the title', async t => {
  const fixture = mission(t);
  await create(fixture, '  Dog profile badges ', 'Come up with 3 creative badge ideas for dog profiles and build them');
  const [ask] = listAsks(fixture.root);
  assert.match(ask.id, /^\d{8}-\d{4}-dog-profile-badges$/);
  assert.equal(ask.title, 'Dog profile badges');
  const saved = fs.readFileSync(path.join(fixture.root, '.hve', 'asks', ask.id, 'request.md'), 'utf8').replace(/\r\n/g, '\n').trim();
  assert.equal(saved, '# Dog profile badges\n\nCome up with 3 creative badge ideas for dog profiles and build them');
  assert.equal(snapshot(fixture.root).ask.title, 'Dog profile badges');
  const [confirm] = confirmations(fixture.controls);
  assert.equal(confirm[1], `Create ask “Dog profile badges” in ${path.basename(fixture.root)}?`);
  assert.match(confirm[2].detail, /\.hve\/asks\/<UTC date-time>-dog-profile-badges\//);
  assert.deepEqual(confirm.slice(3), ['Create ask', 'Change folder name…']);
  assert.equal(fixture.controls.commands.get('frontierHve.missionControlModel')().snapshot.ask.title, 'Dog profile badges');
});

test('a title alone is enough, and the folder name can still be changed', async t => {
  const fixture = mission(t);
  fixture.controls.inputs.push('Investor pitch deck', '', 'pitch');
  fixture.controls.confirmations.push('Change folder name…', 'Create ask');
  await fixture.controls.commands.get('frontierHve.newAsk')();
  const [ask] = listAsks(fixture.root);
  assert.match(ask.id, /-pitch$/);
  assert.equal(ask.title, 'Investor pitch deck');
  assert.equal(fs.readFileSync(path.join(fixture.root, '.hve', 'asks', ask.id, 'request.md'), 'utf8').trim(), '# Investor pitch deck');
  assert.equal(inputs(fixture.controls).at(-1).title, 'Ask folder name');
});

test('the harness reads the description to spot a follow-up, and the question names both asks by title', async t => {
  const fixture = mission(t);
  await create(fixture, 'Pawstagram', 'Build Pawstagram, a social photo app for dogs with a home feed, dog profiles and a pack hive');
  const [first] = listAsks(fixture.root);
  await create(fixture, 'Dog profile badges', 'Add breed badges and walk streaks to the dog profile', ['Create a separate ask', 'Create ask']);
  const follow = confirmations(fixture.controls).find(call => /follow-up/.test(call[1]));
  assert.equal(follow[1], '“Dog profile badges” looks like a follow-up to the open ask “Pawstagram”.');
  assert.deepEqual(follow.slice(3), ['Continue the open ask', 'Create a separate ask']);
  const asks = listAsks(fixture.root);
  assert.deepEqual(asks.map(ask => ask.title).sort(), ['Dog profile badges', 'Pawstagram']);
  assert.equal(asks.find(ask => ask.active).title, 'Dog profile badges');
  assert.ok(fs.existsSync(path.join(fixture.root, '.hve', 'asks', first.id, 'contract.json')));
});

test('cancelling at either box creates nothing', async t => {
  const fixture = mission(t);
  fixture.controls.inputs.push('Dog profile badges');
  await fixture.controls.commands.get('frontierHve.newAsk')();
  await fixture.controls.commands.get('frontierHve.newAsk')();
  assert.deepEqual(fs.readdirSync(fixture.root), []);
  assert.ok(!confirmations(fixture.controls).length);
});

test('the saved request and the scope text are built from the title and description', () => {
  assert.equal(askRequest({ title: 'Feed speed', description: '' }), '# Feed speed');
  assert.equal(askRequest({ title: 'Feed speed', description: 'Load photos in under a second' }), '# Feed speed\n\nLoad photos in under a second');
  assert.equal(scopeText({ title: 'Feed speed', description: '' }), 'Feed speed');
  assert.equal(scopeText({ title: 'Feed speed', description: 'Create a faster feed' }), 'Create a faster feed\n\nFeed speed');
});
