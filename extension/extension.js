'use strict';
/** Frontier HVE extension: renders the agent plugin, registers it with Copilot Chat, and sets up the workspace. */

const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const { renderPlugin, renderPlugins, pluginHome } = require('./render');

const MIN_PYTHON = [3, 11];
const PYTHON_LAUNCHERS = [['python'], ['python3'], ['py', '-3']];
const PYTHON_DOWNLOAD = 'https://www.python.org/downloads/';
const EMPTY_PROFILE = {
  prompt_style: null, wants_evidence: null, verbosity: null, output_format: null, build_preference: null, depth_evidence: 0,
  explanation_depth: null, bloat_triggers: [],
};
const PREFERENCES = [
  { label: 'Assisted', value: 'low_code', description: 'Read and adjust code with guidance' },
  { label: 'Pro', value: 'pro_code', description: 'Use AI to code and review continuously' },
];

/**
 * Return the Python version a launcher runs as [major, minor], or null when it cannot be run.
 * @param {string[]} launcher Command and leading arguments, for example ['py', '-3'].
 * @returns {Promise<number[] | null>}
 */
function pythonVersion(launcher) {
  return new Promise((resolve) => {
    execFile(launcher[0], [...launcher.slice(1), '--version'], (error, stdout, stderr) => {
      const match = /Python (\d+)\.(\d+)/.exec(`${stdout}${stderr}`);
      resolve(error || !match ? null : [Number(match[1]), Number(match[2])]);
    });
  });
}

/**
 * Return the first launcher on PATH that runs Python 3.11 or newer, as a command string, or null when there is none.
 * @returns {Promise<string | null>}
 */
async function findPython() {
  for (const launcher of PYTHON_LAUNCHERS) {
    const version = await pythonVersion(launcher);
    if (version && (version[0] > MIN_PYTHON[0] || (version[0] === MIN_PYTHON[0] && version[1] >= MIN_PYTHON[1]))) {
      return launcher.join(' ');
    }
  }
  return null;
}

/**
 * Render the plugin into global storage and register it in chat.pluginLocations; return the plugin folder.
 * @param {vscode.ExtensionContext} context
 * @param {string | null} python Python launcher, or null to render without Python hooks.
 * @returns {Promise<string>}
 */
async function registerPlugin(context, python) {
  const pluginDir = path.join(context.globalStorageUri.fsPath, 'plugin');
  renderPlugin(context.extensionPath, pluginDir, context.extension.packageJSON.version, python);
  const chat = vscode.workspace.getConfiguration('chat');
  const locations = { ...(chat.get('pluginLocations') || {}), [pluginDir]: true };
  await chat.update('pluginLocations', locations, vscode.ConfigurationTarget.Global);
  await chat.update('plugins.enabled', true, vscode.ConfigurationTarget.Global);
  await context.globalState.update('renderedVersion', context.extension.packageJSON.version);
  await context.globalState.update('renderedPython', python);
  await refreshPlugins(context, python);
  return pluginDir;
}

/**
 * Render the enabled installed plugins and point chat.pluginLocations at exactly those; return whether the set changed.
 * @param {vscode.ExtensionContext} context
 * @param {string | null} python Python launcher, or null to render without Python hooks.
 * @returns {Promise<boolean>}
 */
async function refreshPlugins(context, python) {
  const folders = renderPlugins(context.extensionPath, python);
  const rendered = path.join(pluginHome(), 'rendered') + path.sep;
  const chat = vscode.workspace.getConfiguration('chat');
  const current = chat.get('pluginLocations') || {};
  const kept = Object.fromEntries(Object.entries(current).filter(([dir]) => !dir.startsWith(rendered)));
  const locations = { ...kept, ...Object.fromEntries(folders.map((dir) => [dir, true])) };
  const changed = JSON.stringify(Object.keys(current).sort()) !== JSON.stringify(Object.keys(locations).sort());
  if (changed) {
    await chat.update('pluginLocations', locations, vscode.ConfigurationTarget.Global);
  }
  return changed;
}

/**
 * Run a runtime Python tool with arguments and return its parsed JSON output.
 * @param {vscode.ExtensionContext} context
 * @param {string} python Python launcher.
 * @param {string} script Runtime-relative script path, for example 'tools/plugins/plugin.py'.
 * @param {string[]} args
 * @returns {Promise<any>}
 */
function runTool(context, python, script, args) {
  const [command, ...launcher] = python.split(' ');
  const file = path.join(context.extensionPath, 'runtime', ...script.split('/'));
  return new Promise((resolve, reject) => {
    execFile(command, [...launcher, file, ...args], { maxBuffer: 10 * 1024 * 1024 }, (error, out, err) => {
      if (error) {
        reject(new Error(`${script} ${args[0]} failed: ${err || error.message}`));
      } else {
        resolve(JSON.parse(out));
      }
    });
  });
}

/**
 * Return the --index arguments for the organization plugin index setting, or none when it is not configured.
 * @returns {string[]}
 */
function indexArgs() {
  const index = vscode.workspace.getConfiguration('frontierHve').get('pluginIndex');
  return index ? ['--index', index] : [];
}

/**
 * Inspect a plugin source, ask the user to confirm its identity, hash and tools when needed, install it and re-render plugins.
 * @param {vscode.ExtensionContext} context
 * @param {string} python Python launcher.
 * @param {string} source Plugin folder, .hveplugin file, https git URL or index:<name>@<version>.
 * @param {string} owner 'user', or the id of the wrapper extension that ships the package.
 * @returns {Promise<object | null>} The install result, or null when the user declined.
 */
async function installPlugin(context, python, source, owner) {
  const info = await runTool(context, python, 'tools/plugins/plugin.py', ['inspect', source, ...indexArgs()]);
  const confirm = [];
  if (info.needsConfirmation) {
    const trust = info.verifiedByIndex ? 'Verified against the organization plugin index.'
      : 'Not from the organization plugin index: install it only if you trust this source.';
    const detail = `${info.id} ${info.version} by ${info.publisher}\nsha256 ${info.sha256}\n${trust}\n`
      + `Tools its agents may use: ${info.tools.join(', ')}` + (info.newTools.length ? `\nNew tools: ${info.newTools.join(', ')}` : '');
    const choice = await vscode.window.showWarningMessage(`Install plugin ${info.name}?`, { modal: true, detail }, 'Install');
    if (choice !== 'Install') {
      return null;
    }
    confirm.push('--confirm', info.sha256);
  }
  const result = await runTool(context, python, 'tools/plugins/plugin.py',
    ['install', source, ...indexArgs(), ...confirm, '--owner', owner]);
  await refreshPlugins(context, python);
  return result;
}

/**
 * Ask where to install a plugin from, install it, and offer a reload so its agents appear.
 * @param {vscode.ExtensionContext} context
 */
async function installPluginCommand(context) {
  const python = await findPython();
  if (!python) {
    await warnNoPython();
    return;
  }
  const kind = await vscode.window.showQuickPick(
    ['Organization index (name@version)', 'Folder', '.hveplugin file', 'Git URL (https, ending in .git)'],
    { title: 'Frontier HVE: install a plugin from' });
  let source;
  if (kind === 'Organization index (name@version)') {
    const value = await vscode.window.showInputBox({ prompt: 'Plugin name@version from the frontierHve.pluginIndex setting' });
    source = value && `index:${value}`;
  } else if (kind === 'Folder' || kind === '.hveplugin file') {
    const picked = await vscode.window.showOpenDialog({ canSelectFolders: kind === 'Folder', canSelectFiles: kind !== 'Folder',
      filters: kind === 'Folder' ? undefined : { 'Frontier HVE plugin': ['hveplugin'] } });
    source = picked && picked[0].fsPath;
  } else if (kind) {
    source = await vscode.window.showInputBox({ prompt: 'https git URL of the plugin repository, ending in .git' });
  }
  if (!source) {
    return;
  }
  const result = await installPlugin(context, python, source, 'user');
  if (result) {
    await offerReload(result.unchanged ? `Plugin ${result.id} ${result.version} is already installed.`
      : `Plugin ${result.id} ${result.version} is installed.`);
  }
}

/**
 * Let the user enable, disable or uninstall an installed plugin, then re-render and offer a reload.
 * @param {vscode.ExtensionContext} context
 */
async function managePluginsCommand(context) {
  const python = await findPython();
  if (!python) {
    await warnNoPython();
    return;
  }
  const plugins = await runTool(context, python, 'tools/plugins/plugin.py', ['list']);
  if (!plugins.length) {
    vscode.window.showInformationMessage('No Frontier HVE plugins are installed. Run "Frontier HVE: Install plugin".');
    return;
  }
  const picked = await vscode.window.showQuickPick(plugins.map((p) => ({
    label: p.name, description: `${p.version} ${p.enabled ? 'enabled' : `disabled (${p.disabledReason})`}`,
    detail: `agents: ${p.agents.join(', ')}; flows: ${p.flows.join(', ') || 'none'}; templates: ${p.templates.join(', ')}`, plugin: p,
  })), { title: 'Frontier HVE: manage plugins' });
  if (!picked) {
    return;
  }
  const action = await vscode.window.showQuickPick([picked.plugin.enabled ? 'Disable' : 'Enable', 'Uninstall'], { title: picked.label });
  if (!action) {
    return;
  }
  await runTool(context, python, 'tools/plugins/plugin.py', [action.toLowerCase(), picked.label]);
  await refreshPlugins(context, python);
  await offerReload(`Plugin ${picked.label}: ${action.toLowerCase()}d.`);
}

/**
 * Clean up the store, disable revoked or changed plugins, uninstall plugins whose wrapper extension is gone, and re-render.
 * @param {vscode.ExtensionContext} context
 * @param {string} python Python launcher.
 * @returns {Promise<boolean>} Whether the rendered plugin set changed.
 */
async function reconcilePlugins(context, python) {
  await runTool(context, python, 'tools/plugins/plugin.py', ['reconcile', ...indexArgs()]);
  const plugins = await runTool(context, python, 'tools/plugins/plugin.py', ['list']);
  for (const plugin of plugins.filter((p) => p.owner !== 'user' && !vscode.extensions.getExtension(p.owner))) {
    await runTool(context, python, 'tools/plugins/plugin.py', ['uninstall', plugin.name]);
  }
  return refreshPlugins(context, python);
}

/**
 * Offer to install the plugins the open workspace's frontier-hve.plugins.json requires, and report version conflicts without
 * changing the global install; return whether anything was installed.
 * @param {vscode.ExtensionContext} context
 * @param {string} python Python launcher.
 * @returns {Promise<boolean>}
 */
async function checkRequirements(context, python) {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    return false;
  }
  const report = await runTool(context, python, 'tools/plugins/plugin.py', ['requirements', folders[0].uri.fsPath]);
  for (const conflict of report.conflicts) {
    vscode.window.showWarningMessage(`This workspace needs plugin ${conflict.name} ${conflict.range}; installed is ${conflict.installed}`
      + `${conflict.enabled ? '' : ' (disabled)'}. Other workspaces share the global install, so Frontier HVE does not change it: `
      + 'use "Frontier HVE: Manage plugins" or "Install plugin" if you want to.');
  }
  let installed = false;
  for (const need of report.missing) {
    const choice = await vscode.window.showInformationMessage(
      `This workspace needs Frontier HVE plugin ${need.name} ${need.range} (from ${need.source}).`, 'Install', 'Not now');
    if (choice === 'Install') {
      installed = Boolean(await installPlugin(context, python, need.source, 'user')) || installed;
    }
  }
  return installed;
}

/** Explain that Python is missing and offer the download page. */
async function warnNoPython() {
  const open = await vscode.window.showWarningMessage(
    `Frontier HVE needs Python ${MIN_PYTHON.join('.')}+ on PATH for its guards and harness tools; agents run without them until then. `
    + 'Install Python, then run "Frontier HVE: Set up".', 'Download Python');
  if (open) {
    vscode.env.openExternal(vscode.Uri.parse(PYTHON_DOWNLOAD));
  }
}

/**
 * Create <workspace>/.hve with runs/ and the user profile, ask how the user prefers to build, and optionally ignore .hve in git.
 * @param {string} workspace
 */
async function setUpWorkspace(workspace) {
  const state = path.join(workspace, '.hve');
  fs.mkdirSync(path.join(state, 'runs'), { recursive: true });
  const profileFile = path.join(state, 'user_profile.json');
  const profile = fs.existsSync(profileFile) ? JSON.parse(fs.readFileSync(profileFile, 'utf8')) : { ...EMPTY_PROFILE };
  const preference = await vscode.window.showQuickPick(PREFERENCES, {
    title: 'Frontier HVE: how do you prefer to build?', placeHolder: 'A starting point; the agents adapt to how you work', ignoreFocusOut: true,
  });
  if (preference) {
    profile.build_preference = preference.value;
  }
  fs.writeFileSync(profileFile, JSON.stringify(profile, null, 2) + '\n');
  const gitignore = path.join(workspace, '.gitignore');
  const ignored = fs.existsSync(gitignore) && fs.readFileSync(gitignore, 'utf8').split(/\r?\n/).includes('.hve/');
  if (!ignored && await vscode.window.showQuickPick(['Yes', 'No'], { title: 'Add .hve/ (Frontier HVE state) to .gitignore?' }) === 'Yes') {
    fs.appendFileSync(gitignore, `${fs.existsSync(gitignore) ? '\n' : ''}.hve/\n`);
  }
}

/**
 * Point the Copilot OTel file export at the open workspace for benchmark metrics (the file holds full chat content and grows large).
 */
async function enableResearchTelemetry() {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    vscode.window.showErrorMessage('Open the research workspace first.');
    return;
  }
  const choice = await vscode.window.showWarningMessage(
    'Turn on the Copilot telemetry file export? It records full chat content into .hve/runs/copilot-otel.jsonl; use it for benchmarks only.',
    { modal: true }, 'Turn on');
  if (choice !== 'Turn on') {
    return;
  }
  const otel = vscode.workspace.getConfiguration('github.copilot.chat.otel');
  await otel.update('enabled', true, vscode.ConfigurationTarget.Global);
  await otel.update('exporterType', 'file', vscode.ConfigurationTarget.Global);
  await otel.update('outfile', path.join(folders[0].uri.fsPath, '.hve', 'runs', 'copilot-otel.jsonl'), vscode.ConfigurationTarget.Global);
}

/**
 * Measure the always-on context load (skills, instructions, MCP) and show its size and any warnings; the report is .hve/context_load.json.
 * @param {vscode.ExtensionContext} context
 * @param {string} workspace
 * @param {string} python Python launcher.
 */
async function reportContextLoad(context, workspace, python) {
  const script = path.join(context.extensionPath, 'runtime', 'tools', 'skills', 'context_load.py');
  const [command, ...args] = python.split(' ');
  const stdout = await new Promise((resolve, reject) => {
    execFile(command, [...args, script], { cwd: workspace, maxBuffer: 10 * 1024 * 1024 }, (error, out, err) => {
      if (error) {
        reject(new Error(`context_load.py failed: ${err || error.message}`));
      } else {
        resolve(out);
      }
    });
  });
  const report = JSON.parse(stdout);
  const shares = Object.entries(report.share_pct).map(([window, pct]) => `${pct}% of ${Number(window) / 1000}K`).join(', ');
  const summary = `Frontier HVE: ${report.total_tokens.toLocaleString()} tokens load into every request before you type `
    + `(${report.skill_count} skills; ${shares}).`;
  const warnings = report.warnings.length ? ` Warnings: ${report.warnings.join('; ')}. Run /check-context-load for fixes.` : '';
  const open = await vscode.window.showInformationMessage(summary + warnings, 'Show report');
  if (open) {
    await vscode.window.showTextDocument(vscode.Uri.file(path.join(workspace, '.hve', 'context_load.json')));
  }
}

/**
 * Re-detect Python, re-render the plugin, then set up the open workspace: build preference, .gitignore and context-load report.
 * @param {vscode.ExtensionContext} context
 */
async function setUp(context) {
  const python = await findPython();
  await registerPlugin(context, python);
  if (!python) {
    await warnNoPython();
    return;
  }
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    vscode.window.showErrorMessage('Open the project folder first, then run "Frontier HVE: Set up" again.');
    return;
  }
  await setUpWorkspace(folders[0].uri.fsPath);
  await reportContextLoad(context, folders[0].uri.fsPath, python);
  await offerReload(`Frontier HVE is ready (Python: ${python}).`);
}

/**
 * Ask to reload the window so Copilot Chat picks up the rendered agents.
 * @param {string} message
 */
async function offerReload(message) {
  const reload = await vscode.window.showInformationMessage(
    `${message} Reload the window, then pick an HVE agent in a new chat with Session Target: Local.`, 'Reload Window');
  if (reload) {
    vscode.commands.executeCommand('workbench.action.reloadWindow');
  }
}

/**
 * Register the commands, render the plugin on first install, update or Python change, reconcile installed plugins, show a status
 * item while Python is missing, and return the API wrapper extensions use to install their bundled plugin package.
 * @param {vscode.ExtensionContext} context
 * @returns {Promise<{installPlugin: Function, uninstallPlugin: Function}>}
 */
async function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand('frontierHve.setup', () => setUp(context)),
    vscode.commands.registerCommand('frontierHve.researchTelemetry', enableResearchTelemetry),
    vscode.commands.registerCommand('frontierHve.installPlugin', () => installPluginCommand(context)),
    vscode.commands.registerCommand('frontierHve.managePlugins', () => managePluginsCommand(context)));
  const python = await findPython();
  const api = {
    /** Install a wrapper extension's bundled .hveplugin through the core pipeline; the wrapper's id becomes the owner. */
    installPlugin: async (packagePath, ownerId) => installPlugin(context, await requirePython(), packagePath, ownerId),
    /** Uninstall a plugin by its short name. */
    uninstallPlugin: async (name) => {
      const launcher = await requirePython();
      const result = await runTool(context, launcher, 'tools/plugins/plugin.py', ['uninstall', name]);
      await refreshPlugins(context, launcher);
      return result;
    },
  };
  if (!python) {
    const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);
    item.text = '$(warning) Frontier HVE: guards off (no Python)';
    item.tooltip = `Install Python ${MIN_PYTHON.join('.')}+, then click to run "Frontier HVE: Set up".`;
    item.command = 'frontierHve.setup';
    item.show();
    context.subscriptions.push(item);
  }
  const rendered = context.globalState.get('renderedVersion') === context.extension.packageJSON.version
    && context.globalState.get('renderedPython') === python;
  if (!rendered) {
    await registerPlugin(context, python);
    // Not awaited: activation must not wait for the user to dismiss a notification.
    void (python ? offerReload('Frontier HVE agents are installed.') : warnNoPython());
  }
  if (python) {
    // Not awaited, so a slow or unreachable plugin index never delays activation; failures are shown, not hidden.
    void reconcilePlugins(context, python)
      .then(async (changed) => (await checkRequirements(context, python)) || changed)
      .then((changed) => changed && rendered && offerReload('Frontier HVE plugins changed.'),
        (error) => vscode.window.showErrorMessage(`Frontier HVE could not check installed plugins: ${error.message}`));
  }
  return api;
}

/**
 * Return the Python launcher, or raise with the install instruction when there is none.
 * @returns {Promise<string>}
 */
async function requirePython() {
  const python = await findPython();
  if (!python) {
    throw new Error(`Frontier HVE plugins need Python ${MIN_PYTHON.join('.')}+ on PATH; install it and run "Frontier HVE: Set up".`);
  }
  return python;
}

/** Nothing to clean up: the plugin stays registered until the extension is uninstalled. */
function deactivate() {}

module.exports = { activate, deactivate };
