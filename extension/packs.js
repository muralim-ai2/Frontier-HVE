'use strict';
/** Frontier HVE expertise packs in the editor: install, manage, reconcile on start, and render pack agents into chat.pluginLocations. */

const vscode = require('vscode');
const os = require('os');
const path = require('path');
const { renderPacks } = require('./render');

/**
 * @typedef {{ run: (python: string, script: string, args: string[], cwd: string) => Promise<any>, offerReload: (message: string) => Promise<void> }} Host
 */

/**
 * Return the global pack home shared with the Python tools: HVE_PLUGIN_HOME when set, else ~/.frontier-hve.
 * @returns {string}
 */
function packHome() {
  return process.env.HVE_PLUGIN_HOME || path.join(os.homedir(), '.frontier-hve');
}

/**
 * Return the open workspace folder, or the extension folder when none is open.
 * @param {vscode.ExtensionContext} context
 * @returns {string}
 */
function workspaceOf(context) {
  const folders = vscode.workspace.workspaceFolders;
  return folders && folders.length > 0 ? folders[0].uri.fsPath : context.extensionPath;
}

/**
 * Run the runtime pack tool (tools/plugins/plugin.py) and return its JSON output.
 * @param {vscode.ExtensionContext} context
 * @param {string} python Python launcher.
 * @param {Host} host
 * @param {string[]} args
 * @returns {Promise<any>}
 */
function packTool(context, python, host, args) {
  return host.run(python, path.join(context.extensionPath, 'runtime', 'tools', 'plugins', 'plugin.py'), args, workspaceOf(context));
}

/**
 * Return the --index arguments for the organization pack index setting, or none when it is not configured.
 * @returns {string[]}
 */
function indexArgs() {
  const index = vscode.workspace.getConfiguration('frontierHve').get('pluginIndex');
  return index ? ['--index', index] : [];
}

/**
 * Render the agents of every pack available to the open workspace (installed and committed in plugins/) and register their folders
 * in chat.pluginLocations; return whether the registered set changed.
 * @param {vscode.ExtensionContext} context
 * @param {string} python Python launcher.
 * @param {Host} host
 * @returns {Promise<boolean>}
 */
async function refreshPacks(context, python, host) {
  const renderedRoot = path.join(packHome(), 'rendered');
  const rendered = renderPacks(context.extensionPath, python, renderedRoot, await packTool(context, python, host, ['packs', workspaceOf(context)]));
  const chat = vscode.workspace.getConfiguration('chat');
  const current = chat.get('pluginLocations') || {};
  const kept = Object.fromEntries(Object.entries(current).filter(([dir]) => !dir.startsWith(renderedRoot + path.sep)));
  const locations = { ...kept, ...Object.fromEntries(rendered.map((dir) => [dir, true])) };
  const changed = JSON.stringify(Object.keys(current).sort()) !== JSON.stringify(Object.keys(locations).sort());
  if (changed) {
    await chat.update('pluginLocations', locations, vscode.ConfigurationTarget.Global);
  }
  return changed;
}

/**
 * Inspect a pack source, ask the user to confirm its identity, hash and tools when needed, install it and re-render the packs.
 * @param {vscode.ExtensionContext} context
 * @param {string} python Python launcher.
 * @param {Host} host
 * @param {string} source Pack folder, .hveplugin file, https git URL or index:<name>@<version>.
 * @returns {Promise<object | null>} The install result, or null when the user declined.
 */
async function installPack(context, python, host, source) {
  const info = await packTool(context, python, host, ['inspect', source, ...indexArgs()]);
  const confirm = [];
  if (info.needsConfirmation) {
    const trust = info.verifiedByIndex ? 'Verified against the organization pack index.'
      : 'Not from the organization pack index: install it only if you trust this source.';
    const detail = `${info.id} ${info.version} by ${info.publisher}\nsha256 ${info.sha256}\n${trust}\n`
      + `Tools its agents may use: ${info.tools.join(', ')}` + (info.newTools.length ? `\nNew tools: ${info.newTools.join(', ')}` : '');
    if (await vscode.window.showWarningMessage(`Install expertise pack ${info.name}?`, { modal: true, detail }, 'Install') !== 'Install') {
      return null;
    }
    confirm.push('--confirm', info.sha256);
  }
  const result = await packTool(context, python, host, ['install', source, ...indexArgs(), ...confirm, '--owner', 'user']);
  await refreshPacks(context, python, host);
  return result;
}

/**
 * Ask where to install a pack from, install it, and offer a reload so its agents appear.
 * @param {vscode.ExtensionContext} context
 * @param {string} python Python launcher.
 * @param {Host} host
 */
async function installPackCommand(context, python, host) {
  const kind = await vscode.window.showQuickPick(
    ['Organization index (name@version)', 'Folder', '.hveplugin file', 'Git URL (https, ending in .git)'],
    { title: 'Frontier HVE: install an expertise pack from' });
  let source;
  if (kind === 'Organization index (name@version)') {
    const value = await vscode.window.showInputBox({ prompt: 'Pack name@version from the frontierHve.pluginIndex setting' });
    source = value && `index:${value}`;
  } else if (kind === 'Folder' || kind === '.hveplugin file') {
    const picked = await vscode.window.showOpenDialog({ canSelectFolders: kind === 'Folder', canSelectFiles: kind !== 'Folder',
      filters: kind === 'Folder' ? undefined : { 'Frontier HVE pack': ['hveplugin'] } });
    source = picked && picked[0].fsPath;
  } else if (kind) {
    source = await vscode.window.showInputBox({ prompt: 'https git URL of the pack repository, ending in .git' });
  }
  if (!source) {
    return;
  }
  const result = await installPack(context, python, host, source);
  if (result) {
    await host.offerReload(`Expertise pack ${result.id} ${result.version} is ${result.unchanged ? 'already ' : ''}installed.`);
  }
}

/**
 * Let the user enable, disable or uninstall an installed pack, then re-render and offer a reload.
 * @param {vscode.ExtensionContext} context
 * @param {string} python Python launcher.
 * @param {Host} host
 */
async function managePacksCommand(context, python, host) {
  const packs = await packTool(context, python, host, ['list']);
  if (!packs.length) {
    vscode.window.showInformationMessage('No expertise packs are installed. Run "Frontier HVE: Install plugin", or commit a pack as plugins/<pack>/.');
    return;
  }
  const picked = await vscode.window.showQuickPick(packs.map((p) => ({
    label: p.name, description: `${p.version} ${p.enabled ? 'enabled' : `disabled (${p.disabledReason})`}`,
    detail: `agents: ${p.agents.join(', ')}; lifecycles: ${p.lifecycles.join(', ') || 'none'}; knowledge: ${p.knowledge.join(', ') || 'none'}`,
    pack: p,
  })), { title: 'Frontier HVE: manage expertise packs' });
  if (!picked) {
    return;
  }
  const action = await vscode.window.showQuickPick([picked.pack.enabled ? 'Disable' : 'Enable', 'Uninstall'], { title: picked.label });
  if (!action) {
    return;
  }
  await packTool(context, python, host, [action.toLowerCase(), picked.label]);
  await refreshPacks(context, python, host);
  await host.offerReload(`Expertise pack ${picked.label}: ${action.toLowerCase()}d.`);
}

/**
 * On start: clean up the store, disable revoked or changed packs, offer the packs the workspace's frontier-hve.plugins.json needs
 * (reporting version conflicts without changing the global install), re-render, and offer a reload when the agents changed.
 * @param {vscode.ExtensionContext} context
 * @param {string} python Python launcher.
 * @param {Host} host
 */
async function startPacks(context, python, host) {
  await packTool(context, python, host, ['reconcile', ...indexArgs()]);
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length > 0) {
    const report = await packTool(context, python, host, ['requirements', folders[0].uri.fsPath]);
    for (const conflict of report.conflicts) {
      vscode.window.showWarningMessage(`This workspace needs expertise pack ${conflict.name} ${conflict.range}; installed is `
        + `${conflict.installed}${conflict.enabled ? '' : ' (disabled)'}. Other workspaces share the global install, so Frontier HVE `
        + 'does not change it: use "Frontier HVE: Manage plugins" or "Install plugin".');
    }
    for (const need of report.missing) {
      const choice = await vscode.window.showInformationMessage(
        `This workspace needs Frontier HVE expertise pack ${need.name} ${need.range} (from ${need.source}).`, 'Install', 'Not now');
      if (choice === 'Install') {
        await installPack(context, python, host, need.source);
      }
    }
  }
  if (await refreshPacks(context, python, host)) {
    await host.offerReload('Frontier HVE expertise pack agents changed.');
  }
}

module.exports = { installPackCommand, managePacksCommand, startPacks };
