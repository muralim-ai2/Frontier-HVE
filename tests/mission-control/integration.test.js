'use strict';
/** Exercise real task creation and guarded review persistence against the bundled lifecycle runtime. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { bundled, workspace, removeWorkspace } = require('./helpers');
const { lifecycle } = require('../../extension/ui/lifecycle-cli');
const { Workflow } = require('../../extension/ui/workflow');
const { snapshot } = require('../../extension/ui/workspace-state');

/** Prepare a scratch project using real lifecycle commands.
 * @param {import('node:test').TestContext} t
 * @returns {Promise<{root: string, storage: string, flow: Workflow, state: import('../../extension/ui/types').Snapshot}>}
 */
async function setup(t) {
  const root = workspace();
  const storage = workspace();
  t.after(() => { removeWorkspace(root); removeWorkspace(storage); });
  const flow = new Workflow(bundled(), storage);
  const description = await flow.describeTask(root, 'Build an onboarding policy checker');
  assert.equal(description.verdict, 'new-project');
  assert.deepEqual(fs.readdirSync(root), []);
  const state = await flow.createTask(root, description.revision, 'policy', 'Build an onboarding policy checker');
  return { root, storage, flow, state };
}

/** Synchronize a real plan and finish its direct delivery stage.
 * @param {string} root
 * @param {string} ask
 * @returns {void}
 */
function completeStage(root, ask) {
  const connection = bundled();
  const plan = path.join(root, '.hve', 'asks', ask, 'plan.md');
  fs.writeFileSync(plan, '# Policy delivery\n\nCheck required configuration and report the result.\n' + fs.readFileSync(plan, 'utf8'));
  for (const args of [['plan-sync', 'Recorded test plan'], ['stage', 'deliver', 'done', 'Verified scratch delivery']]) {
    execFileSync(connection.python, ['-B', connection.script, ...args], { cwd: root, env: { ...process.env, PYTHONUTF8: '1' } });
  }
}

test('real task creation is visible to the harness and cleans request inputs', async t => {
  const { root, storage, state } = await setup(t);
  assert.match(state.ask.id, /-policy$/);
  assert.equal(state.ask.agent, 'HVE creator');
  const where = await lifecycle(bundled(), root, ['where']);
  assert.equal(where.open_ask.ask, state.ask.id);
  assert.equal(where.project.asks[0], state.ask.id);
  assert.deepEqual(fs.readdirSync(storage), []);
  assert.ok(fs.existsSync(path.join(root, '.hve', 'asks', state.ask.id, 'request.md')));
});

test('acceptance and requested changes persist through the guarded API', async t => {
  const { root, flow, state } = await setup(t);
  completeStage(root, state.ask.id);
  const ready = snapshot(root);
  const ticket = await flow.prepareReview(root, ready.revision, 'stage:deliver', 'accepted');
  const accepted = await flow.recordReview(root, ticket, 'Human inspected the scratch evidence');
  assert.equal(accepted.reviews[0].decision, 'accepted');
  assert.equal(accepted.decisions.at(-1).choice, 'accepted');
  const next = await flow.prepareReview(root, accepted.revision, 'stage:deliver', 'changes');
  const revised = await flow.recordReview(root, next, 'Add a missing input check');
  assert.equal(revised.reviews[0].decision, 'changes');
  assert.equal(revised.reviews[0].note, 'Add a missing input check');
});

test('preparing a review ticket does not write project state', async t => {
  const { root, flow, state } = await setup(t);
  completeStage(root, state.ask.id);
  const ready = snapshot(root);
  const contract = fs.readFileSync(path.join(root, '.hve', 'asks', state.ask.id, 'contract.json'));
  await flow.prepareReview(root, ready.revision, 'stage:deliver', 'accepted');
  assert.equal(snapshot(root).revision, ready.revision);
  assert.deepEqual(fs.readFileSync(path.join(root, '.hve', 'asks', state.ask.id, 'contract.json')), contract);
});

test('stale UI and active-ask switches cannot approve another task', async t => {
  const { root, flow, state } = await setup(t);
  completeStage(root, state.ask.id);
  const ready = snapshot(root);
  const ticket = await flow.prepareReview(root, ready.revision, 'stage:deliver', 'accepted');
  const second = await flow.createTask(root, ready.revision, 'second', 'Build a second onboarding checker');
  await assert.rejects(flow.recordReview(root, ticket, 'Old approval'), /state changed/);
  await assert.rejects(lifecycle(bundled(), root, ['tick-for', ticket.ask, ticket.revision, ticket.item, ticket.value, 'Stale subprocess']), /changed/);
  assert.ok(second.reviews.every(review => review.decision === 'open'));
  assert.ok(snapshot(root).reviews.every(review => review.decision === 'open'));
});

test('changed plans, incomplete work, and invalid identifiers reject before mutation', async t => {
  const { root, flow, state } = await setup(t);
  await assert.rejects(flow.prepareReview(root, state.revision, 'stage:deliver', 'accepted'), /Acceptance requires/);
  await assert.rejects(flow.createTask(root, state.revision, '..\\escape', 'Build a checker'), /identifier/);
  completeStage(root, state.ask.id);
  const ready = snapshot(root);
  const ticket = await flow.prepareReview(root, ready.revision, 'stage:deliver', 'accepted');
  fs.appendFileSync(path.join(root, '.hve', 'asks', state.ask.id, 'plan.md'), '\nAnother requirement.');
  await assert.rejects(flow.recordReview(root, ticket, 'Old approval'), /state changed/);
  assert.equal(snapshot(root).reviews[0].decision, 'open');
  assert.equal(flow.busy, false);
});
