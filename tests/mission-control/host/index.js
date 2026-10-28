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
  assert.equal(fs.readFileSync(path.join(plugin, 'skills', 'wow-uplift', 'SKILL.md'), 'utf8'), fs.readFileSync(setting('HVE_HOST_UPLIFT'), 'utf8'),
    'The rendered wow-uplift skill must be the current source.');
  assert.ok(!available.includes('frontierHve.continueInChat'), 'Continue in Chat must be gone.');
  await vscode.commands.executeCommand('workbench.view.extension.frontierHve');
  const state = await vscode.commands.executeCommand('frontierHve.openMissionControl');
  assert.match(state.ask.id, /-pawstagram$/);
  assert.equal(state.ask.agent, 'HVE creator');
  assert.ok(vscode.window.tabGroups.all.some(group => group.tabs.some(tab => tab.label === 'HVE Mission Control')), 'Mission Control editor must open.');
  assert.equal(snapshot(folder.uri.fsPath).revision, before, 'Opening Mission Control must not change project state.');
  const opened = await vscode.commands.executeCommand('frontierHve.missionControlModel');
  assert.ok(opened.asks.some(ask => ask.id === state.ask.id && ask.active), 'The ask dropdown must list the active ask.');
  assert.equal(opened.files.ask, state.ask.id, 'The Files page must show the active ask\'s folder.');
  assert.ok(opened.files.entries.some(node => node.name === 'contract.json'), 'The ask folder must list its contract.');
  for (const id of ['workbench.action.chat.open', 'workbench.action.chat.newChat', 'revealInExplorer']) assert.ok(available.includes(id), `VS Code must provide ${id}`);
  const transcripts = opened.transcripts;
  assert.ok(transcripts, 'Mission Control must know this window\'s chat transcript folder.');
  fs.mkdirSync(transcripts, { recursive: true });
  const file = path.join(transcripts, 'host-check.jsonl');
  const event = (type, data) => JSON.stringify({ type, data, timestamp: new Date().toISOString() }) + '\n';
  fs.writeFileSync(file, event('user.message', { content: 'Build the Pawstagram feed' }) + event('assistant.turn_start', {})
    + event('tool.execution_start', { toolCallId: 'o', toolName: 'run_in_terminal', arguments: { command: `python lifecycle.py open ${state.ask.id}` } })
    + event('tool.execution_complete', { toolCallId: 'o', success: true })
    + event('tool.execution_start', { toolCallId: 'a', toolName: 'run_in_terminal', arguments: { command: 'npm test', explanation: 'Check the feed' } }));
  await until(model => model.activity?.session?.current?.title === 'Check the feed', 'Mission Control must show a new chat step without a manual refresh.');
  const linked = (await vscode.commands.executeCommand('frontierHve.missionControlModel')).activity.chats.find(chat => chat.id === 'host-check');
  assert.deepEqual(linked.asks, [{ ask: state.ask.id, how: 'opened' }], 'A chat that reopens the ask must be linked to it.');
  fs.appendFileSync(file, event('tool.execution_complete', { toolCallId: 'a', success: true }) + event('assistant.message', { content: 'The feed is done.' }));
  await until(model => model.activity?.session?.events[0]?.title === 'The feed is done.', 'Mission Control must follow each further step.');
  fs.writeFileSync(setting('HVE_HOST_REPORT'), JSON.stringify({
    status: 'passed', vscode: vscode.version, extension: extension.packageJSON.version, ask: state.ask.id,
    checks: ['installed from VSIX', 'Copilot Chat disabled', 'activated on startup without a manual activate call', 'all contributed commands registered',
      'HVE agent plugin rendered and registered (41 agents)', 'current wow-uplift skill rendered', 'no Continue in Chat command',
      'Activity Bar container opened', 'Mission Control editor opened with live ask', 'no passive project mutation',
      'ask dropdown lists the active ask and the Files page shows its folder', 'chat and Explorer commands used by New ask and Show in Explorer exist',
      'new chat steps appear live through the real file watcher', 'a chat that reopens the ask is linked to it'],
  }, null, 2));
}

/** Wait until Mission Control's own model satisfies a condition, reading it without refreshing.
 * @param {(model: any) => boolean} condition
 * @param {string} failure
 * @returns {Promise<void>}
 */
async function until(condition, failure) {
  for (let waited = 0; ; waited += 250) {
    if (condition(await vscode.commands.executeCommand('frontierHve.missionControlModel'))) return;
    if (waited >= 20000) throw new Error(failure);
    await new Promise(resolve => setTimeout(resolve, 250));
  }
}

module.exports = { run };
