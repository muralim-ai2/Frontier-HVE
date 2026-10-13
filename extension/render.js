'use strict';
/** Render the Frontier HVE agent plugin from the packaged templates; no VS Code API, so it can be tested with plain Node. */

const fs = require('fs');
const os = require('os');
const path = require('path');

const PLACEHOLDER = /\{\{RUNTIME\}\}/g;
const PYTHON_CALL = /\bpython "\{\{RUNTIME\}\}/g;
const FRONTMATTER = /^---\r?\n[\s\S]*?\r?\n---\r?\n/;
const HOOKS_BLOCK = /^hooks:\r?\n(?:[ \t]+.*\n)*/m;
const LOCAL_CHECK = '\nHarness check: the session hooks add a line starting `Frontier HVE deliverable templates: session` to your context. '
  + 'If it is missing, the guards are not running: tell the user to start a new chat with Session Target **Local** before you continue.\n';
const NO_PYTHON = '\n> **Python not found.** Frontier HVE found no Python 3.11+ when it set up this agent, so its guard hooks are off and its '
  + 'harness commands will fail. Before anything else, tell the user to install Python 3.11+, run **Frontier HVE: Set up** and reload the window.\n';
const AGENTS_LINE = /^agents: \[(.*)\]$/m;

/**
 * Return the global plugin home shared with the Python tools: HVE_PLUGIN_HOME when set, else ~/.frontier-hve.
 * @returns {string}
 */
function pluginHome() {
  return process.env.HVE_PLUGIN_HOME || path.join(os.homedir(), '.frontier-hve');
}

/**
 * Return the enabled plugins' registry entries; none when no plugin was ever installed.
 * @param {string} home Plugin home folder.
 * @returns {object[]}
 */
function enabledPlugins(home) {
  const file = path.join(home, 'plugins.json');
  if (!fs.existsSync(file)) {
    return [];
  }
  const registry = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (registry.version !== 1) {
    throw new Error(`${file} is not a version 1 plugin registry`);
  }
  return Object.values(registry.plugins).filter((entry) => entry.enabled);
}

/**
 * Return the core hook block for a plugin agent: template guard, the skill loader limited to its plugin, and the stage guard when
 * the agent runs exactly one stage of one of its plugin's flows.
 * @param {object} entry Plugin registry entry.
 * @param {string} agent Agent name within the plugin.
 * @returns {string}
 */
function pluginHooks(entry, agent) {
  const command = (script) => `    - type: command\n      command: 'python "{{RUNTIME}}/hooks/${script}"'\n`;
  const loader = `${command('skill_loader.py')}      env:\n        HARNESS_SKILLS_MIN_STATUS: provisional\n        HARNESS_PLUGIN: ${entry.name}\n`;
  const stages = Object.entries(entry.manifest.flows).flatMap(([flowId, flow]) => Object.entries(flow.stages)
    .filter(([, stage]) => stage.agent === `${entry.name}:${agent}`).map(([stage]) => [flowId, stage]));
  const stageGuard = stages.length === 1
    ? `${command('flow_guard.py')}      env:\n        HARNESS_PROJECT: .\n        FLOW_STAGE: ${stages[0][1]}\n`
      + `        FLOW_REF: ${entry.name}:${stages[0][0]}\n`
    : '';
  return `hooks:\n  SessionStart:\n${command('template_guard.py')}`
    + `  UserPromptSubmit:\n${command('template_guard.py')}${loader}`
    + `  PreToolUse:\n${loader}  PostToolUse:\n${loader}`
    + `  Stop:\n${command('template_guard.py')}${stageGuard}`;
}

/**
 * Return the names under which plugin flow stage agents are rendered, so creator-flow may delegate to them.
 * @param {object[]} plugins Enabled plugin registry entries.
 * @returns {string[]}
 */
function flowStageAgents(plugins) {
  const names = plugins.flatMap((entry) => Object.values(entry.manifest.flows)
    .flatMap((flow) => Object.values(flow.stages).map((stage) => stage.agent)).filter((agent) => agent.startsWith(`${entry.name}:`)));
  return [...new Set(names)].sort();
}

/**
 * Return one agent rendered for this machine: runtime path and Python launcher filled in, or, without Python, no hooks and a warning.
 * @param {string} text Agent template.
 * @param {string} runtime Runtime folder with forward slashes.
 * @param {string | null} python Python launcher command (for example `python3` or `py -3`), or null when none was found.
 * @returns {string}
 */
function renderAgent(text, runtime, python) {
  if (!text.includes('python "{{RUNTIME}}')) {
    return text.replace(PLACEHOLDER, runtime);
  }
  const front = FRONTMATTER.exec(text)[0];
  const body = text.slice(front.length);
  if (python === null) {
    return (front.replace(HOOKS_BLOCK, '').replace(/^description: /m, 'description: (Needs Python) ') + NO_PYTHON + body)
      .replace(PLACEHOLDER, runtime);
  }
  const launcher = python === 'python' ? '' : `\nPython on this machine is \`${python}\`: use it wherever a skill or tool says \`python\`.\n`;
  return (front + (front.includes('SessionStart:') ? LOCAL_CHECK : '') + launcher + body)
    .replace(PYTHON_CALL, `${python} "{{RUNTIME}}`).replace(PLACEHOLDER, runtime);
}

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
 * @param {string | null} python Python launcher command, or null when none was found.
 * @returns {string[]} Names of the rendered agent files.
 */
function renderPlugin(extensionDir, pluginDir, version, python) {
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
  const stageAgents = flowStageAgents(enabledPlugins(pluginHome()));
  for (const name of agents) {
    let text = fs.readFileSync(path.join(extensionDir, 'agents', name), 'utf8');
    if (name === 'hve-creator-flow.agent.md' && stageAgents.length) {
      text = text.replace(AGENTS_LINE, (line, list) => `agents: [${list}, ${stageAgents.join(', ')}]`);
    }
    fs.writeFileSync(path.join(agentsOut, name), renderAgent(text, runtime, python));
  }
  removeStale(agentsOut, agents);
  return agents;
}

/**
 * Render every enabled plugin into <home>/rendered/<id>/ as an Agent Plugins folder (agents named '<plugin>:<agent>' with core hooks)
 * and delete rendered folders of plugins that are no longer enabled; return the rendered folders.
 * @param {string} extensionDir Folder of the installed extension (holds runtime/).
 * @param {string | null} python Python launcher command, or null when none was found.
 * @returns {string[]}
 */
function renderPlugins(extensionDir, python) {
  const home = pluginHome();
  const runtime = path.join(extensionDir, 'runtime').split(path.sep).join('/');
  const renderedRoot = path.join(home, 'rendered');
  fs.mkdirSync(renderedRoot, { recursive: true });
  const plugins = enabledPlugins(home);
  const folders = [];
  for (const entry of plugins) {
    const out = path.join(renderedRoot, entry.id);
    const agentsOut = path.join(out, 'com.github.copilot', 'agents');
    fs.mkdirSync(agentsOut, { recursive: true });
    fs.writeFileSync(path.join(out, 'plugin.json'), JSON.stringify({
      $schema: 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json',
      name: entry.name,
      version: entry.version,
      description: `${entry.manifest.displayName} (Frontier HVE plugin by ${entry.manifest.publisher}), rendered by Frontier HVE.`,
    }, null, 2) + '\n');
    const files = [];
    for (const agent of entry.manifest.agents) {
      const source = fs.readFileSync(path.join(home, 'plugins', entry.id, entry.version, agent.file), 'utf8').replace(/\r\n/g, '\n');
      const front = FRONTMATTER.exec(source)[0];
      const named = front.replace(/^name: .*$/m, `name: ${entry.name}:${agent.name}`).replace(/\n---\n$/, `\n${pluginHooks(entry, agent.name)}---\n`);
      const file = `${agent.name}.agent.md`;
      fs.writeFileSync(path.join(agentsOut, file), renderAgent(named + source.slice(front.length), runtime, python));
      files.push(file);
    }
    removeStale(agentsOut, files);
    folders.push(out);
  }
  removeStale(renderedRoot, plugins.map((entry) => entry.id));
  return folders;
}

module.exports = { renderPlugin, renderPlugins, pluginHome };
