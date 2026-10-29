'use strict';
/** Verify passive state reading, evidence provenance, and explicit error states. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { workspace, removeWorkspace, json } = require('./helpers');
const { ASK, project } = require('./fixtures');
const { snapshot, planDigest } = require('../../extension/ui/workspace-state');
const { containedPath, Reader } = require('../../extension/ui/file-access');

test('empty projects are identified without writes', t => {
  const root = workspace();
  t.after(() => removeWorkspace(root));
  const state = snapshot(root);
  assert.equal(state.project, null);
  assert.equal(state.ask, null);
  assert.deepEqual(fs.readdirSync(root), []);
});

test('real-shaped project state keeps evidence and human decisions separate', t => {
  const root = workspace();
  t.after(() => removeWorkspace(root));
  const folder = project(root);
  const before = fs.readFileSync(path.join(root, folder, 'contract.json'));
  const state = snapshot(root);
  assert.equal(state.ask.id, ASK);
  assert.equal(state.features[0].check.exitCode, 0);
  assert.equal(state.features[0].check.output, '3 checks passed');
  assert.equal(state.reviews[1].decision, 'open');
  assert.equal(state.reviews[1].ready, true);
  assert.equal(state.files.length, 4);
  assert.equal(state.planState, 'synced');
  assert.deepEqual(fs.readFileSync(path.join(root, folder, 'contract.json')), before);
  assert.equal(snapshot(root).revision, state.revision);
});

test('invalid JSON, invalid shapes, and invalid pointers fail explicitly', t => {
  const root = workspace();
  t.after(() => removeWorkspace(root));
  project(root);
  fs.writeFileSync(path.join(root, '.hve', 'asks', 'active.json'), '{');
  assert.throws(() => snapshot(root), /Invalid JSON/);
  json(root, '.hve\\asks\\active.json', { active: '../../escape' });
  assert.throws(() => snapshot(root), /Invalid ask/);
  json(root, '.hve\\asks\\active.json', { active: ASK });
  json(root, '.hve\\project\\feature_list.json', [{ name: 'policy', description: 'policy', verify: 'check', passes: 'true' }]);
  assert.throws(() => snapshot(root), /expected a boolean/);
});

test('missing evidence is never manufactured from a passing flag', t => {
  const root = workspace();
  t.after(() => removeWorkspace(root));
  const folder = project(root);
  fs.unlinkSync(path.join(root, folder, 'loop', 'prs', 'policy.json'));
  const state = snapshot(root);
  assert.equal(state.features[0].passes, true);
  assert.equal(state.features[0].check, null);
  assert.equal(state.reviews[1].ready, false);
});

test('changed plans and file contents change the snapshot revision', t => {
  const root = workspace();
  t.after(() => removeWorkspace(root));
  const folder = project(root);
  const first = snapshot(root);
  fs.appendFileSync(path.join(root, folder, 'plan.md'), '\nChanged requirement.');
  const second = snapshot(root);
  assert.equal(second.planState, 'unsynced');
  assert.notEqual(first.revision, second.revision);
  assert.equal(planDigest('# Plan\r\n<!-- hve:skills -->ignored<!-- /hve:skills -->\r\n'), planDigest('# Plan'));
});

test('pending plan checkboxes are visible without reconciling them', t => {
  const root = workspace();
  t.after(() => removeWorkspace(root));
  const folder = project(root);
  fs.appendFileSync(path.join(root, folder, 'plan.md'), '\n<!-- hve:checklist -->\n- [x] stage:deliver\n<!-- /hve:checklist -->\n');
  const state = snapshot(root);
  assert.equal(state.pendingPlanTicks, true);
  assert.equal(state.reviews[0].decision, 'open');
});

test('path traversal, linked state directories and oversized files are refused', t => {
  const root = workspace();
  const outside = workspace();
  t.after(() => { removeWorkspace(root); removeWorkspace(outside); });
  assert.throws(() => containedPath(root, '..\\escape'), /leaves/);
  assert.throws(() => containedPath(root, outside), /relative/);
  fs.symlinkSync(outside, path.join(root, '.hve'), 'junction');
  assert.throws(() => snapshot(root), /Linked harness paths/);
  fs.unlinkSync(path.join(root, '.hve'));
  fs.writeFileSync(path.join(root, 'huge'), Buffer.alloc(8 * 1024 * 1024 + 1));
  assert.throws(() => new Reader(root).text('huge'), /8 MB/);
});

test('recorded evidence must match the locked feature command', t => {
  const root = workspace();
  t.after(() => removeWorkspace(root));
  const folder = project(root);
  json(root, path.join(folder, 'loop', 'prs', 'policy.json'), {
    feature: 'policy', verify: { command: 'different test', exit_code: 0, output_tail: 'pass' },
  });
  assert.throws(() => snapshot(root), /differs from the feature check/);
});
