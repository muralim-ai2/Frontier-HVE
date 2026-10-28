'use strict';
/** Verify Mission Control's connection to the bundled lifecycle runtime without changing a project. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { EXTENSION, bundled, workspace, removeWorkspace } = require('./helpers');
const { runtime, inspect, validateOperation, lifecycle, guardMode, BASE_COMMANDS } = require('../../extension/ui/lifecycle-cli');

test('connects to the bundled runtime without creating workspace state', async t => {
  const folder = workspace();
  t.after(() => removeWorkspace(folder));
  assert.equal(await inspect(bundled(), folder), 'Direct delivery');
  assert.deepEqual(fs.readdirSync(folder), []);
  assert.equal(guardMode(EXTENSION), 'advise');
  assert.equal(bundled().script, path.join(EXTENSION, 'runtime', 'tools', 'loop', 'lifecycle.py'));
});

test('requires a launcher and the bundled lifecycle entry point', () => {
  assert.throws(() => runtime(EXTENSION, []), /launcher is required/);
  assert.throws(() => runtime(path.join(EXTENSION, 'missing'), ['python']), /ENOENT/);
  assert.deepEqual(runtime(EXTENSION, ['py', '-3']).pythonArguments, ['-3']);
});

test('an unusable Python launcher surfaces the failing operation', async t => {
  const folder = workspace();
  t.after(() => removeWorkspace(folder));
  await assert.rejects(lifecycle(runtime(EXTENSION, ['hve-no-such-python']), folder, ['list']), /Harness lifecycle\.py list failed/);
});

test('only allowlisted lifecycle operations can execute', () => {
  for (const args of [['stage', 'deliver', 'done', 'skip'], ['checklist'], ['tick', 'opt:telemetry', 'on', 'yes'],
    ['tick', 'task:x', 'accepted', ''], ['contract', 'direct', '../../escape', 'HVE creator', __filename]]) {
    assert.throws(() => validateOperation(args), /Unsupported/);
  }
  validateOperation(['tick-for', '20261028-1200-policy', 'a'.repeat(64), 'task:policy', 'accepted', 'Reviewed by user']);
  validateOperation(['contract', 'direct', 'policy', 'HVE creator', __filename]);
  assert.equal(BASE_COMMANDS.setup, 'frontierHve.setup');
});

test('a live command failure is not converted into successful state', async t => {
  const folder = workspace();
  t.after(() => removeWorkspace(folder));
  await assert.rejects(lifecycle(bundled(), folder, ['where', path.join(folder, 'missing-request.txt')]), /Harness lifecycle\.py where failed/);
  assert.deepEqual(fs.readdirSync(folder), []);
});
