'use strict';
/** Render the Frontier HVE agent plugin from the packaged templates; no VS Code API, so it can be tested with plain Node. */

const fs = require('fs');
const path = require('path');

const PLACEHOLDER = /\{\{RUNTIME\}\}/g;

/**
 * Delete the entries of dir that are not in keep.
 * @param {string} dir
 * @param {string[]} keep
 */
function removeStale(dir, keep) {
  for (const name of fs.readdirSync(dir).filter((entry) => !keep.includes(entry))) {
    fs.rmSync(path.join(dir, name), { recursive: true });
  }
}

/**
 * Write the plugin folder in place (VS Code holds it open): plugin.json, skills, guardrail scripts, and agents with the runtime path.
 * @param {string} extensionDir Folder of the installed extension (holds agents/, skills/ and runtime/).
 * @param {string} pluginDir Folder to create or update for the rendered plugin.
 * @param {string} version Extension version recorded in plugin.json.
 * @returns {string[]} Names of the rendered agent files.
 */
function renderPlugin(extensionDir, pluginDir, version) {
  const runtime = path.join(extensionDir, 'runtime').split(path.sep).join('/');
  const agentsOut = path.join(pluginDir, 'com.github.copilot', 'agents');
  fs.mkdirSync(agentsOut, { recursive: true });
  fs.writeFileSync(path.join(pluginDir, 'plugin.json'), JSON.stringify({
    $schema: 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json',
    name: 'frontier-hve',
    version,
    description: 'Frontier HVE agents and skills, rendered by the Frontier HVE extension.',
  }, null, 2) + '\n');
  for (const part of ['skills', 'scripts']) {
    const source = part === 'skills' ? path.join(extensionDir, 'skills') : path.join(extensionDir, 'runtime', 'scripts');
    fs.cpSync(source, path.join(pluginDir, part), { recursive: true });
    removeStale(path.join(pluginDir, part), fs.readdirSync(source));
  }
  const agents = fs.readdirSync(path.join(extensionDir, 'agents')).filter((name) => name.endsWith('.agent.md'));
  for (const name of agents) {
    const text = fs.readFileSync(path.join(extensionDir, 'agents', name), 'utf8');
    fs.writeFileSync(path.join(agentsOut, name), text.replace(PLACEHOLDER, runtime));
  }
  removeStale(agentsOut, agents);
  return agents;
}

module.exports = { renderPlugin };
