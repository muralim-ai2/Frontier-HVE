'use strict';
/** Frontier HVE extension: renders the agent plugin, registers it with Copilot Chat, and sets up the workspace. */

const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const { renderPlugin } = require('./render');

const MIN_PYTHON = [3, 11];
const EMPTY_PROFILE = {
  prompt_style: null, wants_evidence: null, verbosity: null, output_format: null, build_preference: null, depth_evidence: 0,
  explanation_depth: null, bloat_triggers: [],
};
const PREFERENCES = [
  { label: 'No code', value: 'no_code', description: 'Describe the outcome; the agent writes the code and explains as it goes' },
  { label: 'Low code', value: 'low_code', description: 'Read and adjust code with guidance' },
  { label: 'Pro code', value: 'pro_code', description: 'Write and review code yourself' },
];

/**
 * Return the Python version on PATH as [major, minor], or null when python cannot be run.
 * @returns {Promise<number[] | null>}
 */
function pythonVersion() {
  return new Promise((resolve) => {
    execFile('python', ['--version'], (error, stdout, stderr) => {
      const match = /Python (\d+)\.(\d+)/.exec(`${stdout}${stderr}`);
      resolve(error || !match ? null : [Number(match[1]), Number(match[2])]);
    });
  });
}

/**
 * Render the plugin into global storage and register it in chat.pluginLocations; return the plugin folder.
 * @param {vscode.ExtensionContext} context
 * @returns {Promise<string>}
 */
async function registerPlugin(context) {
  const pluginDir = path.join(context.globalStorageUri.fsPath, 'plugin');
  renderPlugin(context.extensionPath, pluginDir, context.extension.packageJSON.version);
  const chat = vscode.workspace.getConfiguration('chat');
  const locations = { ...(chat.get('pluginLocations') || {}), [pluginDir]: true };
  await chat.update('pluginLocations', locations, vscode.ConfigurationTarget.Global);
  await chat.update('plugins.enabled', true, vscode.ConfigurationTarget.Global);
  await context.globalState.update('renderedVersion', context.extension.packageJSON.version);
  return pluginDir;
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
 * Optionally point the Copilot OTel file export at this workspace (research metrics; the file grows and needs pruning).
 * @param {string} workspace
 */
async function offerTelemetry(workspace) {
  const choice = await vscode.window.showQuickPick(['No', 'Yes'], {
    title: 'Turn on the Copilot telemetry file export for research metrics? (large file; benchmark use only)',
  });
  if (choice !== 'Yes') {
    return;
  }
  const otel = vscode.workspace.getConfiguration('github.copilot.chat.otel');
  await otel.update('enabled', true, vscode.ConfigurationTarget.Global);
  await otel.update('exporterType', 'file', vscode.ConfigurationTarget.Global);
  await otel.update('outfile', path.join(workspace, '.hve', 'runs', 'copilot-otel.jsonl'), vscode.ConfigurationTarget.Global);
}

/**
 * Run the full setup: Python check, plugin registration, workspace state, optional telemetry.
 * @param {vscode.ExtensionContext} context
 */
async function setUp(context) {
  const version = await pythonVersion();
  if (!version || version[0] < MIN_PYTHON[0] || (version[0] === MIN_PYTHON[0] && version[1] < MIN_PYTHON[1])) {
    const install = await vscode.window.showErrorMessage(
      `Frontier HVE needs Python ${MIN_PYTHON.join('.')} or newer on PATH (found ${version ? version.join('.') : 'none'}).`,
      'Install Python 3.12 with winget');
    if (install) {
      const terminal = vscode.window.createTerminal('Frontier HVE setup');
      terminal.show();
      terminal.sendText('winget install -e --id Python.Python.3.12');
    }
    return;
  }
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    vscode.window.showErrorMessage('Open the project folder first, then run "Frontier HVE: Set up" again.');
    return;
  }
  await registerPlugin(context);
  await setUpWorkspace(folders[0].uri.fsPath);
  await offerTelemetry(folders[0].uri.fsPath);
  const reload = await vscode.window.showInformationMessage(
    'Frontier HVE is ready. Reload the window, then pick an HVE agent in the Chat view (Session Target: Local).', 'Reload Window');
  if (reload) {
    vscode.commands.executeCommand('workbench.action.reloadWindow');
  }
}

/**
 * Register the setup command and re-render the plugin after an extension update.
 * @param {vscode.ExtensionContext} context
 */
async function activate(context) {
  context.subscriptions.push(vscode.commands.registerCommand('frontierHve.setup', () => setUp(context)));
  const rendered = context.globalState.get('renderedVersion');
  if (rendered && rendered !== context.extension.packageJSON.version) {
    await registerPlugin(context);
    vscode.window.showInformationMessage('Frontier HVE was updated. Reload the window to use the new agents.');
  }
}

/** Nothing to clean up: the plugin stays registered until the extension is uninstalled. */
function deactivate() {}

module.exports = { activate, deactivate };
