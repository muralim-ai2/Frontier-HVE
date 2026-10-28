'use strict';
/** Write representative current-layout harness fixtures into disposable projects. */
const fs = require('node:fs');
const path = require('node:path');
const { json } = require('./helpers');
const { planDigest } = require('../../extension/ui/workspace-state');
const ASK = '20261028-1200-onboarding';

/** Write a complete project with a verified feature and unreviewed delivery milestone.
 * @param {string} root
 * @returns {string}
 */
function project(root) {
  const folder = path.join('.hve', 'asks', ASK);
  const plan = '# Workspace policy\n\nReject invalid configuration.\n';
  json(root, '.hve\\project\\project.json', { name: 'Client onboarding', goal: 'Build the onboarding workspace', asks: [ASK] });
  json(root, '.hve\\asks\\active.json', { active: ASK });
  json(root, path.join(folder, 'contract.json'), {
    ask: ASK, request: 'Build the onboarding workspace', agent: 'HVE creator', lifecycle: 'direct', current: 'deliver',
    stages: [{ name: 'deliver', goal: 'Deliver the workspace policy', status: 'done' }],
    tasks: [{ name: 'policy', passes: true }], checklist: {}, checklist_rendered: {},
    plan: { sha256: planDigest(plan), revisions: [] }, decisions: [], skills: { selected: [] },
  });
  fs.writeFileSync(path.join(root, folder, 'plan.md'), plan);
  fs.writeFileSync(path.join(root, folder, 'request.md'), 'Build the onboarding workspace');
  json(root, '.hve\\project\\feature_list.json', [{ name: 'policy', description: 'Reject invalid workspace configuration', verify: 'node policy.test.js', passes: true }]);
  json(root, '.hve\\project\\state.json', { lock: { policy: { ask: ASK, verify: 'node policy.test.js' } } });
  json(root, path.join(folder, 'loop', 'prs', 'policy.json'), {
    feature: 'policy', verify: { command: 'node policy.test.js', exit_code: 0, output_tail: '3 checks passed' },
  });
  const evidence = path.join(root, folder, 'loop', 'evidence', 'policy');
  fs.mkdirSync(evidence, { recursive: true });
  fs.writeFileSync(path.join(evidence, 'check.log'), 'All required checks passed.');
  return folder;
}

module.exports = { ASK, project };
