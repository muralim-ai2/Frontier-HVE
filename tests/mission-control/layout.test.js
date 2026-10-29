'use strict';
/** Verify New ask sits at the top of the sidebar, once, with or without an ask, including a working chat in a project that has no ask. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { mission } = require('./vscode-stub');
const { project } = require('./fixtures');
const { text } = require('../../extension/ui/media/vnode');
const { sidebar } = require('../../extension/ui/media/views');
const UI = { page: 'live', filter: 'all', open: {}, seq: 0 };

/** Return the sidebar's top-level parts in order, each named by its class or action.
 * @param {import('../../extension/ui/types').VNode} tree
 * @returns {string[]}
 */
function parts(tree) {
  return tree.children.map(node => typeof node === 'string' ? 'text' : node.attrs['data-action'] || node.attrs.class || node.tag);
}

/** Return every view node matching a test.
 * @param {import('../../extension/ui/types').VNode | string} node
 * @param {(node: import('../../extension/ui/types').VNode) => boolean} match
 * @returns {import('../../extension/ui/types').VNode[]}
 */
function find(node, match) {
  return typeof node === 'string' ? [] : [...(match(node) ? [node] : []), ...node.children.flatMap(child => find(child, match))];
}

/** Return the sidebar drawn from Mission Control's own model.
 * @param {ReturnType<typeof mission>} fixture
 * @returns {Promise<import('../../extension/ui/types').VNode>}
 */
async function draw(fixture) {
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  return sidebar({ ...fixture.controls.commands.get('frontierHve.missionControlModel')(), surface: 'sidebar' }, UI, Date.now());
}

test('New ask is the first control under the header and appears nowhere else in the sidebar', async t => {
  const fixture = mission(t);
  project(fixture.root);
  const tree = await draw(fixture);
  const order = parts(tree);
  assert.equal(order[0], 'top');
  assert.equal(order[1], 'newAsk');
  const buttons = find(tree, node => node.attrs['data-action'] === 'newAsk');
  assert.equal(buttons.length, 1);
  assert.match(buttons[0].attrs.class, /\bprimary\b/);
  assert.match(buttons[0].attrs.class, /\bnew-ask\b/);
  const footer = find(tree, node => node.tag === 'footer')[0];
  assert.deepEqual(find(footer, node => node.attrs['data-action'] === 'newAsk'), []);
  assert.equal(find(footer, node => node.attrs.role === 'switch').length, 1);
});

test('with no ask yet, New ask stays at the top, the empty card explains asks without a second button, and the working chat still shows', async t => {
  const fixture = mission(t);
  fs.mkdirSync(fixture.transcripts, { recursive: true });
  const now = new Date().toISOString();
  fs.writeFileSync(path.join(fixture.transcripts, 'live.jsonl'), [{ type: 'user.message', data: { content: 'Build: Pawstagram, a social photo app for dogs' } },
    { type: 'assistant.turn_start', data: {} },
    { type: 'tool.execution_start', data: { toolCallId: 'a', toolName: 'create_file', arguments: { filePath: path.join(fixture.root, 'index.html') } } }]
    .map(row => JSON.stringify({ timestamp: now, ...row }) + '\n').join(''));
  const tree = await draw(fixture);
  assert.equal(parts(tree)[1], 'newAsk');
  assert.equal(find(tree, node => node.attrs['data-action'] === 'newAsk').length, 1);
  const shown = text(tree);
  assert.match(shown, /No ask in this project yet/);
  assert.match(shown, /Start one with New ask/);
  assert.match(shown, /Created index\.html/);
  assert.match(shown, /Working/);
});

test('New ask is disabled while another action runs or no folder is followed', async t => {
  const fixture = mission(t, 2);
  const tree = await draw(fixture);
  const button = find(tree, node => node.attrs['data-action'] === 'newAsk')[0];
  assert.ok('disabled' in button.attrs);
  assert.equal(parts(tree)[1], 'notice');
  assert.equal(parts(tree)[2], 'newAsk');
});
