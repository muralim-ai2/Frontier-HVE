'use strict';
/** Render the Frontier HVE agent plugin from the packaged templates; no VS Code API, so it can be tested with plain Node. */

const fs = require('fs');
const path = require('path');

const PLACEHOLDER = /\{\{RUNTIME\}\}/g;

/**
 * Write the plugin folder: plugin.json, skills, guardrail scripts, and agents with the runtime path filled in.
 * @param {string} extensionDir Folder of the installed extension (holds agents/, skills/ and runtime/).
 * @param {string} pluginDir Folder to (re)create for the rendered plugin.
 * @param {string} version Extension version recorded in plugin.json.
 * @returns {string[]} Names of the rendered agent files.
 */
function renderPlugin(extensionDir, pluginDir, version) {
  const runtime = path.join(extensionDir, 'runtime').split(path.sep).join('/');
  fs.rmSync(pluginDir, { recursive: true, force: true });
  const agentsOut = path.join(pluginDir, 'com.github.copilot', 'agents');
  fs.mkdirSync(agentsOut, { recursive: true });
  fs.writeFileSync(path.join(pluginDir, 'plugin.json'), JSON.stringify({
    $schema: 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json',
    name: 'frontier-hve',
    version,
    description: 'Frontier HVE agents and skills, rendered by the Frontier HVE extension.',
  }, null, 2) + '\n');
  fs.cpSync(path.join(extensionDir, 'skills'), path.join(pluginDir, 'skills'), { recursive: true });
  fs.cpSync(path.join(extensionDir, 'runtime', 'scripts'), path.join(pluginDir, 'scripts'), { recursive: true });
  const agents = fs.readdirSync(path.join(extensionDir, 'agents')).filter((name) => name.endsWith('.agent.md'));
  for (const name of agents) {
    const text = fs.readFileSync(path.join(extensionDir, 'agents', name), 'utf8');
    fs.writeFileSync(path.join(agentsOut, name), text.replace(PLACEHOLDER, runtime));
  }
  return agents;
}

module.exports = { renderPlugin };
