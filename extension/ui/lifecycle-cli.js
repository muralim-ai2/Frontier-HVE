'use strict';
/** Run the bundled harness lifecycle CLI for Mission Control. */
const fs = require('node:fs');
const path = require('node:path');
const { promisify } = require('node:util');
const { execFile } = require('node:child_process');
const { record, text, list, integer, errorText } = require('./validate');
const execute = promisify(execFile);
const BASE_COMMANDS = Object.freeze({
  setup: 'frontierHve.setup',
  installPack: 'frontierHve.installPlugin',
  managePacks: 'frontierHve.managePlugins',
  installHarnesses: 'frontierHve.installHarnesses',
});

/** @typedef {{extensionPath: string, python: string, pythonArguments: string[], script: string}} Runtime */

/** Describe the bundled lifecycle runtime for a verified Python launcher.
 * @param {string} extensionPath
 * @param {string[]} launcher Command and leading arguments, for example ['py', '-3'].
 * @returns {Runtime}
 */
function runtime(extensionPath, launcher) {
  if (!launcher.length) throw new Error('A Python launcher is required.');
  launcher.forEach(part => text(part, 'Python launcher'));
  const script = path.join(extensionPath, 'runtime', 'tools', 'loop', 'lifecycle.py');
  if (!fs.statSync(script).isFile()) throw new Error(`Harness lifecycle entry point is not a file: ${script}`);
  return { extensionPath, python: launcher[0], pythonArguments: launcher.slice(1), script };
}

/** Validate the small set of lifecycle operations exposed by Mission Control.
 * @param {string[]} args
 * @returns {void}
 */
function validateOperation(args) {
  if (args.some(argument => typeof argument !== 'string' || argument.includes('\0'))) throw new Error('Invalid lifecycle argument.');
  if (args.length === 1 && ['list', 'where', 'plan-status'].includes(args[0])) return;
  if (args.length === 2 && args[0] === 'where' && path.isAbsolute(args[1])) return;
  const ask = /^\d{8}-\d{4}-[a-z0-9][a-z0-9-]{0,40}$/;
  if (args.length === 2 && ['review-status', 'open', 'forget'].includes(args[0]) && ask.test(args[1])) return;
  if (args.length === 6 && args[0] === 'tick-for' && ask.test(args[1]) && /^[a-f0-9]{64}$/.test(args[2])
      && /^(stage|task):[a-z0-9][a-z0-9_.-]*$/.test(args[3]) && ['accepted', 'changes'].includes(args[4]) && args[5].trim()) return;
  if (args.length === 5 && args[0] === 'contract' && args[1] === 'direct' && /^[a-z0-9][a-z0-9-]{0,40}$/.test(args[2])
      && args[3] === 'Frontier Lite' && path.isAbsolute(args[4])) return;
  throw new Error(`Unsupported lifecycle operation: ${args[0]}. Mission Control cannot run arbitrary commands or change workflow stages.`);
}

/** Run a bundled Python tool in the workspace and return its JSON output.
 * @param {Runtime} connection
 * @param {string} workspace
 * @param {string} script
 * @param {string[]} args
 * @returns {Promise<unknown>}
 */
async function runTool(connection, workspace, script, args) {
  if (!path.isAbsolute(workspace) || !fs.statSync(workspace).isDirectory()) throw new Error('An existing absolute workspace directory is required.');
  try {
    const result = await execute(connection.python, [...connection.pythonArguments, '-B', script, ...args], {
      cwd: workspace, timeout: 60000, maxBuffer: 8 * 1024 * 1024, windowsHide: true,
      env: { ...process.env, PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1' },
    });
    if (result.stderr.trim()) throw new Error(`Harness wrote diagnostics: ${result.stderr.trim()}`);
    return /** @type {unknown} */ (JSON.parse(result.stdout));
  } catch (error) {
    throw new Error(`Harness ${path.basename(script)} ${args[0]} failed in ${workspace}: ${errorText(error)}`, { cause: error });
  }
}

/** Execute an allowlisted lifecycle command in the explicit target workspace.
 * @param {Runtime} connection
 * @param {string} workspace
 * @param {string[]} args
 * @returns {Promise<unknown>}
 */
async function lifecycle(connection, workspace, args) {
  validateOperation(args);
  return runTool(connection, workspace, connection.script, args);
}

/** Return the installed expertise packs from the pack store (read-only).
 * @param {Runtime} connection
 * @param {string} workspace
 * @returns {Promise<import('./types').Pack[]>}
 */
async function packs(connection, workspace) {
  const script = path.join(connection.extensionPath, 'runtime', 'tools', 'plugins', 'plugin.py');
  /** @type {(value: unknown, context: string) => string[]} */
  const names = (value, context) => list(value, context).map(item => text(item, context));
  return list(await runTool(connection, workspace, script, ['list']), 'Installed packs').map(value => {
    const pack = record(value, 'Installed pack');
    return { id: text(pack.id, 'Pack id'), name: text(pack.name, 'Pack name'), version: text(pack.version, 'Pack version'),
      enabled: pack.enabled === true, disabledReason: pack.disabledReason ? text(pack.disabledReason, 'Disabled reason') : null,
      source: text(pack.source, 'Pack source'), agents: names(pack.agents, 'Pack agents'), lifecycles: names(pack.lifecycles, 'Pack lifecycles'),
      knowledge: names(pack.knowledge, 'Pack knowledge'), templates: names(pack.templates, 'Pack templates') };
  });
}

/** Build or refresh the workspace's solution map (.hve/map/) and return its size class and counts.
 * @param {Runtime} connection
 * @param {string} workspace
 * @returns {Promise<{sizeClass: string, files: number, concepts: number, page: string}>}
 */
async function buildMap(connection, workspace) {
  const script = path.join(connection.extensionPath, 'runtime', 'tools', 'map', 'solution_map.py');
  const result = record(await runTool(connection, workspace, script, ['build']), 'Solution map build');
  const size = record(result.size, 'Map size');
  return { sizeClass: text(size.class, 'Map size class'), files: integer(size.files, 'Map files'), concepts: integer(result.concepts, 'Map concepts'),
    page: path.join(workspace, '.hve', 'map', 'explorer.html') };
}

/** Return the title of the bundled direct lifecycle after checking the catalogue runs.
 * @param {Runtime} connection
 * @param {string} workspace
 * @returns {Promise<string>}
 */
async function inspect(connection, workspace) {
  const choices = list(await lifecycle(connection, workspace, ['list']), 'Lifecycle catalogue').map(value => record(value, 'Lifecycle'));
  const direct = choices.find(choice => choice.name === 'direct');
  if (!direct) throw new Error('The bundled harness does not expose its direct lifecycle.');
  return text(direct.title, 'Direct lifecycle title');
}

/** Read the bundled loop guard mode without claiming that every guard blocks.
 * @param {string} extensionPath
 * @returns {'advise' | 'enforce'}
 */
function guardMode(extensionPath) {
  const file = path.join(extensionPath, 'runtime', 'hooks', 'guard_mode.json');
  const value = record(JSON.parse(fs.readFileSync(file, 'utf8')), file);
  const mode = text(value.loop_guard, `${file}: loop_guard`);
  if (mode !== 'advise' && mode !== 'enforce') throw new Error(`Unrecognized loop guard mode: ${mode}`);
  return mode;
}

module.exports = { BASE_COMMANDS, runtime, validateOperation, lifecycle, packs, buildMap, inspect, guardMode };
