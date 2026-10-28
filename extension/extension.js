'use strict';
/** Frontier HVE extension: renders the agent plugin, registers it with Copilot Chat, and sets up the workspace. */

const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const { renderPlugin } = require('./render');
const packs = require('./packs');
const missionControl = require('./ui/mission-control');

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
const HARNESSES = [
  { label: 'Copilot', description: 'Copilot CLI and the VS Code Copilot harness (~/.copilot)', client: 'copilot' },
  { label: 'Claude Code', description: '~/.claude', client: 'claude' },
  { label: 'Codex', description: '~/.codex and ~/.agents', client: 'codex' },
  { label: 'Cursor', description: '~/.cursor', client: 'cursor' },
  { label: 'Copilot cloud agent', description: 'this repository\'s .github folder; you commit it', client: 'cloud' },
];
const COPILOT_HOOK_FILE = '~/.copilot/hooks/hve.json';

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

/**
 * Run an action with the Python launcher, or explain that Python is missing.
 * @param {(python: string) => Promise<void>} action
 */
async function withPython(action) {
  const python = await findPython();
  if (!python) {
    await warnNoPython();
    return;
  }
  await action(python);
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
 * @param {vscode.ExtensionContext} context
 */
async function enableResearchTelemetry(context) {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    vscode.window.showErrorMessage('Open the research workspace first.');
    return;
  }
  const choice = await vscode.window.showWarningMessage(
    'Turn on the Copilot telemetry file export? It records full chat content into .hve/runs/copilot-otel.jsonl. Use it for benchmarks or an ask that opted in, then turn it off ("Frontier HVE: Turn off research telemetry").',
    { modal: true }, 'Turn on');
  if (choice !== 'Turn on') {
    return;
  }
  const otel = vscode.workspace.getConfiguration('github.copilot.chat.otel');
  await otel.update('enabled', true, vscode.ConfigurationTarget.Global);
  await otel.update('exporterType', 'file', vscode.ConfigurationTarget.Global);
  await otel.update('outfile', path.join(folders[0].uri.fsPath, '.hve', 'runs', 'copilot-otel.jsonl'), vscode.ConfigurationTarget.Global);
  const python = await findPython();
  if (python) {
    await trimTelemetry(context, folders[0].uri.fsPath, python);
  }
}

/**
 * Trim the workspace's Copilot OTel export (last days, size cap) and make git ignore it, telling the user what changed.
 * @param {vscode.ExtensionContext} context
 * @param {string} workspace
 * @param {string} python Python launcher.
 */
async function trimTelemetry(context, workspace, python) {
  const script = path.join(context.extensionPath, 'runtime', 'tools', 'observe', 'otel_trim.py');
  const report = await runPythonJson(python, script, [], workspace);
  const notes = [];
  if (report.export && report.before_mb > report.after_mb) {
    notes.push(`trimmed the Copilot telemetry export (${report.export}) from ${report.before_mb} MB to ${report.after_mb} MB, keeping the `
      + `last ${report.keep_days} days up to ${report.cap_mb} MB`);
  }
  if (report.gitignore_added) {
    notes.push('added .hve/runs/copilot-otel.jsonl to .gitignore (it holds full chat content)');
  }
  if (notes.length) {
    vscode.window.showInformationMessage(`Frontier HVE ${notes.join(' and ')}.`);
  }
}

/**
 * Turn off the Copilot OTel file export the research telemetry command turned on.
 */
async function disableResearchTelemetry() {
  await vscode.workspace.getConfiguration('github.copilot.chat.otel').update('enabled', false, vscode.ConfigurationTarget.Global);
  vscode.window.showInformationMessage('Research telemetry is off. Chats are no longer recorded to .hve/runs/copilot-otel.jsonl.');
}

/**
 * Show a status bar reminder, which turns telemetry off when clicked, for as long as the Copilot OTel export is on.
 * @param {vscode.StatusBarItem} item
 */
function showTelemetryReminder(item) {
  if (vscode.workspace.getConfiguration('github.copilot.chat.otel').get('enabled') === true) {
    item.show();
  } else {
    item.hide();
  }
}

/**
 * Run a runtime Python script and return its parsed JSON output.
 * @param {string} python Python launcher.
 * @param {string} script Script path.
 * @param {string[]} args Script arguments.
 * @param {string} cwd Working directory.
 * @returns {Promise<any>}
 */
function runPythonJson(python, script, args, cwd) {
  const [command, ...launcherArgs] = python.split(' ');
  return new Promise((resolve, reject) => {
    execFile(command, [...launcherArgs, script, ...args], { cwd, maxBuffer: 10 * 1024 * 1024 }, (error, out, err) => {
      if (error) {
        reject(new Error(`${path.basename(script)} failed: ${err || error.message}`));
      } else {
        resolve(JSON.parse(out));
      }
    });
  });
}

/**
 * Measure the always-on context load (skills, instructions, MCP) and show its size and any warnings; the report is .hve/context_load.json.
 * @param {vscode.ExtensionContext} context
 * @param {string} workspace
 * @param {string} python Python launcher.
 */
async function reportContextLoad(context, workspace, python) {
  const script = path.join(context.extensionPath, 'runtime', 'tools', 'skills', 'context_load.py');
  const report = await runPythonJson(python, script, [], workspace);
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
 * Install the HVE agents, skills and hooks for the harnesses the user picks (user scope; Cloud into this repository), and keep the
 * Local harness from running the Copilot hook file next to its own agent-scoped hooks.
 * @param {vscode.ExtensionContext} context
 */
async function installHarnesses(context) {
  const python = await findPython();
  if (!python) {
    await warnNoPython();
    return;
  }
  const picked = await vscode.window.showQuickPick(HARNESSES, {
    canPickMany: true, ignoreFocusOut: true, title: 'Frontier HVE: install the HVE agents, skills and guard hooks for',
  });
  if (!picked || picked.length === 0) {
    return;
  }
  const folders = vscode.workspace.workspaceFolders;
  const cloud = picked.some((item) => item.client === 'cloud');
  if (cloud && (!folders || folders.length === 0)) {
    vscode.window.showErrorMessage('Open the repository first to install for the Copilot cloud agent.');
    return;
  }
  if (cloud && await vscode.window.showWarningMessage(
    'The Copilot cloud agent reads agents, skills and hooks from the repository: this writes .github/agents, .github/skills, '
    + '.github/hooks/hve.json and .github/hve/runtime for you to review and commit.', { modal: true }, 'Write them') !== 'Write them') {
    return;
  }
  const chat = vscode.workspace.getConfiguration('chat');
  await chat.update('hookFilesLocations', { ...(chat.get('hookFilesLocations') || {}), [COPILOT_HOOK_FILE]: false, '.github/hooks/hve.json': false },
    vscode.ConfigurationTarget.Global);
  const script = path.join(context.extensionPath, 'runtime', 'tools', 'adapters', 'export.py');
  const cwd = folders && folders.length > 0 ? folders[0].uri.fsPath : context.extensionPath;
  const lines = [];
  for (const item of picked) {
    const args = item.client === 'cloud' ? ['cloud', cwd] : [item.client, '--user', '--python', python];
    const report = await runPythonJson(python, script, args, cwd);
    lines.push(`${item.label}: ${report.invoke}.`);
  }
  vscode.window.showInformationMessage(`Frontier HVE installed. ${lines.join(' ')} Known gaps per harness: docs/wiki/Adapters.md.`);
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
    `${message} Reload the window, then pick a Frontier agent (E2E Delivery, BYOW or Prototype Creator) or HVE creator in a new chat with Session Target: Local.`,
    'Reload Window');
  if (reload) {
    vscode.commands.executeCommand('workbench.action.reloadWindow');
  }
}

/**
 * Register the commands, render the plugin on first install, update or Python change, and show a status item while Python is missing.
 * @param {vscode.ExtensionContext} context
 */
async function activate(context) {
  const host = { run: runPythonJson, offerReload };
  context.subscriptions.push(
    vscode.commands.registerCommand('frontierHve.setup', () => setUp(context)),
    vscode.commands.registerCommand('frontierHve.installHarnesses', () => installHarnesses(context)),
    vscode.commands.registerCommand('frontierHve.researchTelemetry', () => enableResearchTelemetry(context)),
    vscode.commands.registerCommand('frontierHve.researchTelemetryOff', disableResearchTelemetry),
    vscode.commands.registerCommand('frontierHve.installPlugin', () => withPython((python) => packs.installPackCommand(context, python, host))),
    vscode.commands.registerCommand('frontierHve.managePlugins', () => withPython((python) => packs.managePacksCommand(context, python, host))));
  context.subscriptions.push(...missionControl.register(context, findPython));
  const telemetry = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);
  telemetry.text = '$(record) Research telemetry on';
  telemetry.tooltip = 'Copilot chats are recorded with full content to .hve/runs/copilot-otel.jsonl. Click to turn research telemetry off.';
  telemetry.command = 'frontierHve.researchTelemetryOff';
  showTelemetryReminder(telemetry);
  context.subscriptions.push(telemetry, vscode.workspace.onDidChangeConfiguration((event) => {
    if (event.affectsConfiguration('github.copilot.chat.otel')) {
      showTelemetryReminder(telemetry);
    }
  }));
  const python = await findPython();
  const folders = vscode.workspace.workspaceFolders;
  if (python && folders && folders.length > 0 && fs.existsSync(path.join(folders[0].uri.fsPath, '.hve', 'runs', 'copilot-otel.jsonl'))) {
    // Not awaited: activation must not wait on a large file; a failure is shown, not swallowed.
    trimTelemetry(context, folders[0].uri.fsPath, python).catch((error) => vscode.window.showErrorMessage(`Frontier HVE: ${error.message}`));
  }
  if (python) {
    // Not awaited: activation must not wait on the store or on the user's answers; a failure is shown, not swallowed.
    packs.startPacks(context, python, host).catch((error) => vscode.window.showErrorMessage(`Frontier HVE expertise packs: ${error.message}`));
  }
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
