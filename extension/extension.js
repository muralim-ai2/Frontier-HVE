'use strict';
/** Frontier HVE extension: renders the agent plugin, registers it with Copilot Chat, and sets up the workspace. */

const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const { renderPlugin } = require('./render');

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
  return pluginDir;
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
 * Register the commands, render the plugin on first install, update or Python change, and show a status item while Python is missing.
 * @param {vscode.ExtensionContext} context
 */
async function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand('frontierHve.setup', () => setUp(context)),
    vscode.commands.registerCommand('frontierHve.researchTelemetry', enableResearchTelemetry));
  const python = await findPython();
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
  if (rendered) {
    return;
  }
  await registerPlugin(context, python);
  // Not awaited: activation must not wait for the user to dismiss a notification.
  void (python ? offerReload('Frontier HVE agents are installed.') : warnNoPython());
}

/** Nothing to clean up: the plugin stays registered until the extension is uninstalled. */
function deactivate() {}

module.exports = { activate, deactivate };
