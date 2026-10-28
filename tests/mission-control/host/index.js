'use strict';
/** Check the installed Frontier HVE package in a real VS Code host with Copilot Chat disabled. */
const vscode = require('vscode');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

/** Return a required environment value set by the release check.
 * @param {string} name
 * @returns {string}
 */
function setting(name) {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required; run this through tests/mission-control/release.js.`);
  return value;
}

/** Wait for VS Code to finish activating the extension on its own startup event.
 * @param {vscode.Extension<unknown>} extension
 * @returns {Promise<void>}
 */
async function activated(extension) {
  for (let waited = 0; !extension.isActive; waited += 250) {
    if (waited >= 60000) throw new Error('Frontier HVE did not activate on startup within 60 seconds.');
    await new Promise(resolve => setTimeout(resolve, 250));
  }
}

/** Run the checks without calling activate() or starting an agent.
 * @returns {Promise<void>}
 */
async function run() {
  const folder = vscode.workspace.workspaceFolders?.[0];
  assert.ok(folder, 'Expected the isolated Pawstagram workspace.');
  const extension = vscode.extensions.getExtension('muralim-ai2.frontier-hve');
  assert.ok(extension, 'Frontier HVE must be installed in the isolated host.');
  assert.ok(extension.extensionPath.startsWith(setting('HVE_HOST_EXTENSIONS')), 'Frontier HVE must load from its installed VSIX, not a development path.');
  assert.equal(vscode.extensions.getExtension('GitHub.copilot-chat'), undefined, 'Copilot Chat must be disabled for this check.');
  const { snapshot } = require(path.join(extension.extensionPath, 'ui', 'workspace-state.js'));
  const before = snapshot(folder.uri.fsPath).revision;
  await activated(extension);
  const available = await vscode.commands.getCommands(true);
  for (const id of JSON.parse(setting('HVE_HOST_COMMANDS'))) assert.ok(available.includes(id), `Missing registered command ${id}`);
  const locations = Object.keys(vscode.workspace.getConfiguration('chat').get('pluginLocations') || {});
  const plugin = locations.find(dir => dir.endsWith(path.join('muralim-ai2.frontier-hve', 'plugin')));
  assert.ok(plugin, 'Activation must still render and register the HVE agent plugin.');
  assert.equal(fs.readdirSync(path.join(plugin, 'com.github.copilot', 'agents')).filter(name => name.endsWith('.agent.md')).length, 41);
  await vscode.commands.executeCommand('workbench.view.extension.frontierHve');
  const state = await vscode.commands.executeCommand('frontierHve.openMissionControl');
  assert.match(state.ask.id, /-pawstagram$/);
  assert.equal(state.ask.agent, 'HVE creator');
  assert.ok(vscode.window.tabGroups.all.some(group => group.tabs.some(tab => tab.label === 'HVE Mission Control')), 'Mission Control editor must open.');
  assert.equal(snapshot(folder.uri.fsPath).revision, before, 'Opening Mission Control must not change project state.');
  fs.writeFileSync(setting('HVE_HOST_REPORT'), JSON.stringify({
    status: 'passed', vscode: vscode.version, extension: extension.packageJSON.version, ask: state.ask.id,
    checks: ['installed from VSIX', 'Copilot Chat disabled', 'activated on startup without a manual activate call', 'all contributed commands registered',
      'HVE agent plugin rendered and registered (41 agents)', 'Activity Bar container opened', 'Mission Control editor opened with live ask',
      'no passive project mutation'],
  }, null, 2));
}

module.exports = { run };
