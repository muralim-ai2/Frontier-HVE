'use strict';
/** Check rendered UI semantics, escaping, live labels, and its restricted webview shell. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { EXTENSION, workspace, removeWorkspace } = require('./helpers');
const { project } = require('./fixtures');
const { snapshot } = require('../../extension/ui/workspace-state');
const { PAGES, render, documentHtml } = require('../../extension/ui/render');

/** Return a view model from a disposable fixture.
 * @param {import('node:test').TestContext} t
 * @returns {import('../../extension/ui/types').ViewState}
 */
function state(t) {
  const root = workspace();
  t.after(() => removeWorkspace(root));
  project(root);
  return { snapshot: snapshot(root), connection: 'HVE 0.19.0', python: 'python', guard: 'Advisory', telemetry: false,
    busy: false, error: null, workspaceMessage: null };
}

test('all five pages and sidebar render live state', t => {
  const model = state(t);
  for (const page of PAGES) {
    const html = render(model, 'editor', page);
    assert.match(html, /Client onboarding/);
    assert.match(html, /Live workspace data/);
  }
  const sidebar = render(model, 'sidebar', 'overview');
  assert.match(sidebar, /CURRENT TASK/);
  assert.match(sidebar, /Telemetry off/);
  assert.match(sidebar, /1 of 1 features marked passing/);
  assert.match(sidebar, /aria-current="page"/);
  assert.throws(() => render(model, 'editor', 'unknown'), /Unknown/);
});

test('evidence uses the recorded command and output, not invented totals', t => {
  const html = render(state(t), 'editor', 'evidence', 'policy');
  assert.match(html, /Recorded exit 0/);
  assert.match(html, /3 checks passed/);
  assert.match(html, /node policy.test.js/);
  assert.match(html, /No usage|not a fresh test run/);
  assert.match(html, /data-action="openFile"/);
});

test('approval buttons carry the exact snapshot revision and require ready work', t => {
  const model = state(t);
  const html = render(model, 'editor', 'approvals');
  assert.ok(html.includes(`data-revision="${model.snapshot.revision}"`));
  assert.match(html, /data-value="accepted"/);
  assert.match(html, /data-value="changes"/);
  assert.doesNotMatch(html, /requires Frontier HVE 0\.18\.1/);
  model.snapshot.planState = 'unsynced';
  const stale = render(model, 'editor', 'approvals');
  assert.match(stale, /The plan changed/);
  assert.match(stale, /data-value="accepted"[\s\S]*?disabled/);
});

test('workspace text and evidence output cannot inject HTML or attributes', t => {
  const model = state(t);
  model.snapshot.ask.request = '<script>alert(1)</script>';
  model.snapshot.features[0].check.output = '</code><img src=x onerror=alert(1)>';
  assert.ok(!render(model, 'editor', 'overview').includes('<script>'));
  const html = render(model, 'editor', 'evidence');
  assert.ok(!html.includes('<img src=x'));
  assert.match(html, /&lt;img/);
});

test('errors and unavailable workspace states are visible', t => {
  const model = state(t);
  model.error = 'Invalid state file';
  assert.match(render(model, 'sidebar', 'overview'), /role="alert"/);
  model.error = null;
  model.snapshot = null;
  model.workspaceMessage = 'Select one of the workspace folders.';
  assert.match(render(model, 'editor', 'overview'), /Select one of/);
});

test('webview CSP forbids remote scripts and the bundled script and styles are accessible', () => {
  const html = documentHtml('local:style', 'local:script', 'https://local.example', 'fixed-test-nonce');
  assert.match(html, /default-src 'none'/);
  assert.match(html, /script-src 'nonce-fixed-test-nonce'/);
  assert.ok(!html.includes('unsafe-inline'));
  assert.match(html, /role="status"/);
  const media = path.join(EXTENSION, 'ui', 'media');
  new vm.Script(fs.readFileSync(path.join(media, 'app.js'), 'utf8'));
  const css = fs.readFileSync(path.join(media, 'app.css'), 'utf8');
  assert.match(css, /--vscode-focusBorder/);
  assert.match(css, /vscode-high-contrast/);
  assert.match(css, /focus-visible/);
});
