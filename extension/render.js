'use strict';
/** Render the Frontier HVE agent plugin from the packaged templates; no VS Code API, so it can be tested with plain Node. */

const fs = require('fs');
const path = require('path');

const PLACEHOLDER = /\{\{RUNTIME\}\}/g;
const PYTHON_CALL = /\bpython "\{\{RUNTIME\}\}/g;
const FRONTMATTER = /^---\r?\n[\s\S]*?\r?\n---\r?\n/;
const HOOKS_BLOCK = /^hooks:\r?\n(?:[ \t]+.*\n)*/m;
const LOCAL_CHECK = '\nHarness check: the session hooks add a line starting `Frontier HVE deliverable templates: session` to your context. '
  + 'If it is missing, the guards are not running: tell the user to start a new chat with Session Target **Local** before you continue.\n';
const NO_PYTHON = '\n> **Python not found.** Frontier HVE found no Python 3.11+ when it set up this agent, so its guard hooks are off and its '
  + 'harness commands will fail. Before anything else, tell the user to install Python 3.11+, run **Frontier HVE: Set up** and reload the window.\n';

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
  for (const name of agents) {
    const text = fs.readFileSync(path.join(extensionDir, 'agents', name), 'utf8');
    fs.writeFileSync(path.join(agentsOut, name), renderAgent(text, runtime, python));
  }
  removeStale(agentsOut, agents);
  return agents;
}

/**
 * Return the core hook block for a pack agent: template guard and the skill loader.
 * @returns {string}
 */
function packHooks() {
  const command = (script) => `    - type: command\n      command: 'python "{{RUNTIME}}/hooks/${script}"'\n`;
  const loader = `${command('skill_loader.py')}      env:\n        HARNESS_SKILLS_MIN_STATUS: provisional\n`;
  return `hooks:\n  SessionStart:\n${command('template_guard.py')}`
    + `  UserPromptSubmit:\n${command('template_guard.py')}${loader}`
    + `  PreToolUse:\n${loader}  PostToolUse:\n${loader}`
    + `  Stop:\n${command('template_guard.py')}`;
}

/**
 * Render each available expertise pack into <renderedRoot>/<id>/ as an Agent Plugins folder (agents named '<pack>:<agent>' with core
 * hooks) and delete rendered folders of packs no longer available; return the rendered folders.
 * @param {string} extensionDir Folder of the installed extension (holds runtime/).
 * @param {string | null} python Python launcher command, or null when none was found.
 * @param {string} renderedRoot Folder that holds one rendered folder per pack.
 * @param {{id: string, name: string, version: string, folder: string, manifest: object}[]} packs Packs from `plugin.py packs`.
 * @returns {string[]}
 */
function renderPacks(extensionDir, python, renderedRoot, packs) {
  const runtime = path.join(extensionDir, 'runtime').split(path.sep).join('/');
  fs.mkdirSync(renderedRoot, { recursive: true });
  const folders = [];
  for (const pack of packs) {
    const out = path.join(renderedRoot, pack.id);
    const agentsOut = path.join(out, 'com.github.copilot', 'agents');
    fs.mkdirSync(agentsOut, { recursive: true });
    fs.writeFileSync(path.join(out, 'plugin.json'), JSON.stringify({
      $schema: 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json',
      name: pack.name,
      version: pack.version,
      description: `${pack.manifest.displayName} (Frontier HVE expertise pack by ${pack.manifest.publisher}), rendered by Frontier HVE.`,
    }, null, 2) + '\n');
    const files = [];
    for (const agent of pack.manifest.agents) {
      const source = fs.readFileSync(path.join(pack.folder, agent.file), 'utf8').replace(/\r\n/g, '\n');
      const front = FRONTMATTER.exec(source)[0];
      const named = front.replace(/^name: .*$/m, `name: ${pack.name}:${agent.name}`).replace(/\n---\n$/, `\n${packHooks()}---\n`);
      const file = `${agent.name}.agent.md`;
      fs.writeFileSync(path.join(agentsOut, file), renderAgent(named + source.slice(front.length), runtime, python));
      files.push(file);
    }
    removeStale(agentsOut, files);
    folders.push(out);
  }
  removeStale(renderedRoot, packs.map((pack) => pack.id));
  return folders;
}

module.exports = { renderPlugin, renderPacks };
