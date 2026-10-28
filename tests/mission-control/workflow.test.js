'use strict';
/** Verify Mission Control's confirmed task, review and Chat actions end to end through its commands and the bundled runtime. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { mission } = require('./vscode-stub');
const { snapshot } = require('../../extension/ui/workspace-state');

/** Create a real ask through the New task command after the user confirms it.
 * @param {ReturnType<typeof mission>} fixture
 * @param {string} slug
 * @returns {Promise<import('../../extension/ui/types').Snapshot>}
 */
async function create(fixture, slug) {
  fixture.controls.inputs.push('Build an onboarding policy checker', slug);
  fixture.controls.confirmations.push('Create task');
  await fixture.controls.commands.get('frontierHve.newTask')();
  return snapshot(fixture.root);
}

test('new task creates a real ask only after a confirmation that names the workspace', async t => {
  const fixture = mission(t);
  const state = await create(fixture, 'onboarding');
  assert.match(state.ask.id, /-onboarding$/);
  assert.equal(state.ask.agent, 'HVE creator');
  assert.ok(fixture.controls.calls.some(call => call[0] === 'confirmation' && call[1].includes(fixture.root)));
  assert.ok(!fixture.controls.calls.some(call => call[0] === 'workbench.action.chat.open'));
  assert.deepEqual(fs.readdirSync(fixture.storage), []);
});

test('cancelled creation does not modify the target project', async t => {
  const fixture = mission(t);
  fixture.controls.inputs.push('Build an onboarding policy checker', 'cancelled');
  await fixture.controls.commands.get('frontierHve.newTask')();
  await fixture.controls.commands.get('frontierHve.newTask')();
  assert.deepEqual(fs.readdirSync(fixture.root), []);
});

test('requested changes persist through the guarded API and Chat receives a draft, not a sent request', async t => {
  const fixture = mission(t);
  const state = await create(fixture, 'review');
  fixture.controls.inputs.push('Clarify the policy acceptance criteria.');
  fixture.controls.confirmations.push('Request changes');
  await fixture.controls.provider.execute({ action: 'review', item: 'stage:deliver', value: 'changes', revision: state.revision });
  const saved = snapshot(fixture.root);
  assert.equal(saved.reviews[0].decision, 'changes');
  assert.equal(saved.reviews[0].note, 'Clarify the policy acceptance criteria.');
  await fixture.controls.commands.get('frontierHve.continueInChat')();
  const chat = fixture.controls.calls.find(call => call[0] === 'workbench.action.chat.open');
  assert.equal(chat[1].isPartialQuery, true);
  assert.ok(chat[1].query.includes(state.ask.id));
});

test('accepting unfinished work is refused before any confirmation or write', async t => {
  const fixture = mission(t);
  const state = await create(fixture, 'unfinished');
  const seen = fixture.controls.calls.length;
  await assert.rejects(fixture.controls.provider.execute({ action: 'review', item: 'stage:deliver', value: 'accepted', revision: state.revision }),
    /Acceptance requires/);
  assert.equal(snapshot(fixture.root).revision, state.revision);
  assert.ok(!fixture.controls.calls.slice(seen).some(call => call[0] === 'confirmation'));
});

test('a stale view cannot record a review after the project changes', async t => {
  const fixture = mission(t);
  const state = await create(fixture, 'stale');
  fs.appendFileSync(path.join(fixture.root, '.hve', 'asks', state.ask.id, 'plan.md'), '\nAnother requirement.');
  await assert.rejects(fixture.controls.provider.execute({ action: 'review', item: 'stage:deliver', value: 'changes', revision: state.revision }),
    /state changed/);
  assert.equal(snapshot(fixture.root).reviews[0].decision, 'open');
});
