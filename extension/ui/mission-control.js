'use strict';
/** Mission Control: the Frontier HVE sidebar and dashboard, kept live from the harness files and this window's chat transcripts. */
const vscode = require('vscode');
const path = require('node:path');
const { randomBytes } = require('node:crypto');
const { BASE_COMMANDS, runtime, inspect, guardMode, packs } = require('./lifecycle-cli');
const { snapshot } = require('./workspace-state');
const { activity } = require('./activity');
const { containedPath } = require('./file-access');
const { Workflow } = require('./workflow');
const { record, text, message, errorText } = require('./validate');
const PAGES = ['live', 'plan', 'progress', 'skills', 'settings'];
const SCRIPTS = ['vnode.js', 'markdown.js', 'views.js', 'pages.js', 'app.js'];
const REFRESH_DELAY_MS = 400;

/** Return the restricted webview document that loads Mission Control's styles and scripts.
 * @param {{cspSource: string, asWebviewUri: (uri: vscode.Uri) => vscode.Uri}} webview
 * @param {vscode.Uri} media
 * @returns {string}
 */
function documentHtml(webview, media) {
  const nonce = randomBytes(18).toString('hex');
  /** @param {string} name @returns {string} */
  const uri = name => webview.asWebviewUri(vscode.Uri.joinPath(media, name)).toString();
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${webview.cspSource}; style-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
<title>Frontier HVE Mission Control</title><link rel="stylesheet" href="${uri('app.css')}"></head>
<body><div id="root" aria-busy="true"><p class="loading">Connecting to the harness…</p></div><div id="announce" class="sr-only" role="status" aria-live="polite"></div>
${SCRIPTS.map(name => `<script nonce="${nonce}" src="${uri(name)}"></script>`).join('\n')}</body></html>`;
}

/** Coordinate Mission Control's views, live refresh, workspace selection and confirmed harness actions. */
class MissionControl {
  /**
   * @param {vscode.ExtensionContext} context
   * @param {() => Promise<string | null>} findPython Returns a verified Python 3.11+ launcher, or null.
   */
  constructor(context, findPython) {
    this.context = context;
    this.findPython = findPython;
    this.output = vscode.window.createOutputChannel('Frontier HVE Mission Control');
    /** @type {Map<vscode.Webview, 'sidebar' | 'editor'>} */
    this.views = new Map();
    /** @type {vscode.WebviewView | null} */
    this.sidebar = null;
    /** @type {vscode.WebviewPanel | null} */
    this.panel = null;
    /** @type {vscode.WorkspaceFolder | null} */
    this.workspace = null;
    /** @type {vscode.FileSystemWatcher[]} */
    this.watchers = [];
    /** @type {NodeJS.Timeout | null} */
    this.timer = null;
    /** @type {Workflow | null} */
    this.flow = null;
    /** @type {string | null} */
    this.python = null;
    /** @type {{page: import('./types').Page, seq: number}} */
    this.navigate = { page: 'live', seq: 0 };
    this.disposed = false;
    const version = text(record(context.extension.packageJSON, 'Extension manifest').version, 'Extension version');
    /** @type {Omit<import('./types').Model, 'now' | 'surface' | 'workspace' | 'telemetry' | 'navigate' | 'transcripts'>} */
    this.state = { busy: false, error: null, workspaceMessage: null, connection: { version, python: null, guard: guardMode(context.extensionPath) },
      snapshot: null, snapshotError: null, activity: null, activityError: null, packs: null, packsError: null };
    this.restoreWorkspace();
  }

  /** Restore an explicit selection or use the only local workspace.
   * @returns {void}
   */
  restoreWorkspace() {
    const folders = vscode.workspace.workspaceFolders || [];
    const saved = this.context.workspaceState.get('selectedWorkspace');
    this.workspace = folders.find(folder => folder.uri.toString() === saved) || (folders.length === 1 ? folders[0] : null);
    this.flow = null;
    this.bindWatchers();
  }

  /** Return this window's Copilot Chat transcript folder, a sibling of the extension's workspace storage.
   * @returns {string | null}
   */
  transcripts() {
    const storage = this.context.storageUri;
    return storage ? path.join(path.dirname(storage.fsPath), 'GitHub.copilot-chat', 'transcripts') : null;
  }

  /** Return the research telemetry switch and its export file.
   * @returns {import('./types').Model['telemetry']}
   */
  telemetry() {
    const otel = vscode.workspace.getConfiguration('github.copilot.chat.otel');
    const file = otel.get('outfile');
    return { enabled: otel.get('enabled') === true, file: typeof file === 'string' && file ? file : null };
  }

  /** Watch the workspace's harness state and this window's chat transcripts.
   * @returns {void}
   */
  bindWatchers() {
    this.watchers.forEach(watcher => watcher.dispose());
    this.watchers = [];
    if (this.workspace?.uri.scheme !== 'file') return;
    const patterns = [new vscode.RelativePattern(this.workspace, '.hve/**/*')];
    const storage = this.context.storageUri;
    if (storage) patterns.push(new vscode.RelativePattern(vscode.Uri.file(path.dirname(storage.fsPath)), 'GitHub.copilot-chat/transcripts/*.jsonl'));
    for (const pattern of patterns) {
      const watcher = vscode.workspace.createFileSystemWatcher(pattern);
      watcher.onDidCreate(() => this.scheduleRefresh());
      watcher.onDidChange(() => this.scheduleRefresh());
      watcher.onDidDelete(() => this.scheduleRefresh());
      this.watchers.push(watcher);
    }
  }

  /** Coalesce change notifications into one refresh of a visible view; a hidden view refreshes itself when shown again.
   * @returns {void}
   */
  scheduleRefresh() {
    if (this.disposed || !(this.sidebar?.visible || this.panel?.visible)) return;
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      if (!this.state.busy) this.refresh().catch(error => this.show(error));
    }, REFRESH_DELAY_MS);
  }

  /** Require a trusted local workspace before reading state or running harness tools.
   * @returns {vscode.WorkspaceFolder}
   */
  target() {
    if (!vscode.workspace.isTrusted) throw new Error('Trust this workspace to use Mission Control.');
    if (!this.workspace) throw new Error('Select a workspace folder first.');
    if (this.workspace.uri.scheme !== 'file') throw new Error('Mission Control needs a local folder.');
    return this.workspace;
  }

  /** Connect the task and review workflow to this extension's runtime with the detected Python launcher.
   * @returns {Promise<Workflow>}
   */
  async connect() {
    const root = this.target().uri.fsPath;
    if (this.flow) return this.flow;
    const python = await this.findPython();
    if (!python) throw new Error('Mission Control needs Python 3.11+ on PATH (python, python3 or py -3). Install it, then run "Frontier HVE: Set up".');
    const connection = runtime(this.context.extensionPath, python.split(' '));
    await inspect(connection, root);
    this.python = python;
    this.state.connection.python = python;
    this.flow = new Workflow(connection, this.context.globalStorageUri.fsPath);
    return this.flow;
  }

  /** Re-read the harness state and live activity; a section that cannot be read shows its own error.
   * @returns {Promise<import('./types').Snapshot | null>}
   */
  async refresh() {
    if (!vscode.workspace.isTrusted) throw new Error('Trust this workspace to use Mission Control.');
    this.state.workspaceMessage = null;
    if (!this.workspace) {
      Object.assign(this.state, { snapshot: null, activity: null, snapshotError: null, activityError: null });
      this.state.workspaceMessage = (vscode.workspace.workspaceFolders?.length || 0) > 1
        ? 'Choose which workspace folder Mission Control follows.' : 'Open a project folder to use Mission Control.';
      this.paint();
      return null;
    }
    const root = this.target().uri.fsPath;
    this.python ||= await this.findPython();
    this.state.connection.python = this.python;
    try {
      this.state.snapshot = snapshot(root);
      this.state.snapshotError = null;
    } catch (error) {
      this.state.snapshot = null;
      this.state.snapshotError = errorText(error);
      this.output.appendLine(`Harness state: ${this.state.snapshotError}`);
    }
    try {
      this.state.activity = activity(root, this.transcripts(), this.telemetry().file, Date.now());
      this.state.activityError = null;
    } catch (error) {
      this.state.activity = null;
      this.state.activityError = errorText(error);
      this.output.appendLine(`Live activity: ${this.state.activityError}`);
    }
    this.paint();
    return this.state.snapshot;
  }

  /** Return the model a surface renders.
   * @param {'sidebar' | 'editor'} surface
   * @returns {import('./types').Model}
   */
  model(surface) {
    return { ...this.state, now: new Date().toISOString(), surface, navigate: this.navigate, telemetry: this.telemetry(), transcripts: this.transcripts(),
      workspace: this.workspace ? { name: this.workspace.name, path: this.workspace.uri.fsPath } : null };
  }

  /** Send the current model to each open surface.
   * @returns {void}
   */
  paint() {
    if (this.disposed) return;
    for (const [view, surface] of this.views) void view.postMessage({ type: 'model', model: this.model(surface) });
  }

  /** Show a failure in the views and the output channel.
   * @param {unknown} error
   * @returns {Error}
   */
  show(error) {
    const contextual = new Error(`Frontier HVE Mission Control: ${errorText(error)}`, { cause: error });
    this.state.error = contextual.message;
    this.output.appendLine(contextual.message);
    this.paint();
    return contextual;
  }

  /** Attach a restricted webview and its message handler.
   * @param {vscode.Webview} webview
   * @param {'sidebar' | 'editor'} surface
   * @returns {vscode.Disposable}
   */
  attach(webview, surface) {
    const media = vscode.Uri.joinPath(this.context.extensionUri, 'ui', 'media');
    webview.options = { enableScripts: true, localResourceRoots: [media] };
    webview.html = documentHtml(webview, media);
    this.views.set(webview, surface);
    const listener = webview.onDidReceiveMessage(async value => { await this.execute(value); });
    return new vscode.Disposable(() => { listener.dispose(); this.views.delete(webview); });
  }

  /** Resolve the contributed Primary Side Bar view.
   * @param {vscode.WebviewView} view
   * @returns {void}
   */
  resolveWebviewView(view) {
    this.sidebar = view;
    const attached = this.attach(view.webview, 'sidebar');
    view.onDidDispose(() => { attached.dispose(); this.sidebar = null; });
  }

  /** Open or reveal the dashboard on a page.
   * @param {string} page
   * @returns {void}
   */
  open(page) {
    if (!PAGES.includes(page)) throw new Error(`Unknown page: ${page}`);
    this.navigate = { page: /** @type {import('./types').Page} */ (page), seq: this.navigate.seq + 1 };
    if (!this.panel) {
      const panel = vscode.window.createWebviewPanel('frontierHve.missionControlDetail', 'HVE Mission Control', vscode.ViewColumn.Active, {});
      this.panel = panel;
      const attached = this.attach(panel.webview, 'editor');
      panel.onDidDispose(() => { attached.dispose(); this.panel = null; });
    } else this.panel.reveal(vscode.ViewColumn.Active, false);
    this.paint();
  }

  /** Ask which workspace folder to follow without changing VS Code's folder order.
   * @returns {Promise<void>}
   */
  async selectWorkspace() {
    const folders = vscode.workspace.workspaceFolders || [];
    if (!folders.length) throw new Error('Open a local folder in VS Code first.');
    const selected = await vscode.window.showQuickPick(folders.map(folder => ({ label: folder.name, description: folder.uri.fsPath, folder })),
      { title: 'Frontier HVE: which folder should Mission Control follow?', ignoreFocusOut: true });
    if (!selected) return;
    if (selected.folder.uri.scheme !== 'file') throw new Error('Choose a local folder.');
    this.workspace = selected.folder;
    this.flow = null;
    await this.context.workspaceState.update('selectedWorkspace', selected.folder.uri.toString());
    this.bindWatchers();
  }

  /** Collect and confirm a new task, then create it with the harness.
   * @returns {Promise<void>}
   */
  async newTask() {
    const target = this.target();
    const flow = await this.connect();
    const request = await vscode.window.showInputBox({ title: 'New task (1 of 2): what should be delivered?', prompt: 'Describe the outcome. HVE creator plans and builds it in a new ask.',
      ignoreFocusOut: true, validateInput: value => !value.trim() || value.length > 20000 ? 'Enter 1-20,000 characters.' : null });
    if (request === undefined) return;
    const slug = await vscode.window.showInputBox({ title: 'New task (2 of 2): short name', prompt: 'Used for the task folder, for example pawstagram-feed.',
      ignoreFocusOut: true, validateInput: value => /^[a-z0-9][a-z0-9-]{0,40}$/.test(value) ? null : 'Use 1-41 lowercase letters, digits or hyphens.' });
    if (slug === undefined) return;
    const description = await flow.describeTask(target.uri.fsPath, request);
    const confirm = await vscode.window.showWarningMessage(`Create task "${slug}" in ${target.uri.fsPath}?`,
      { modal: true, detail: `${description.why}.\n${description.activeAsk ? `The current task ${description.activeAsk} stays on disk but is no longer active.\n` : ''}This writes the task's contract and plan under .hve/ and copies its skills. No agent starts.` }, 'Create task');
    if (confirm !== 'Create task') return;
    this.target();
    await flow.createTask(target.uri.fsPath, description.revision, slug, request);
    this.open('plan');
    void vscode.window.showInformationMessage(`Task "${slug}" is ready. In Copilot Chat, pick HVE creator and describe the work; it continues this task.`);
  }

  /** Open the active ask's plan.md in a text editor beside Mission Control.
   * @returns {Promise<void>}
   */
  async editPlan() {
    const state = snapshot(this.target().uri.fsPath);
    if (!state.plan) throw new Error('There is no plan.md to edit: start a task first.');
    await vscode.window.showTextDocument(vscode.Uri.file(containedPath(state.workspace, state.plan.path)), { viewColumn: vscode.ViewColumn.Beside, preview: false });
  }

  /** Confirm and record a human sign-off through the guarded review commands.
   * @param {Record<string, string>} data
   * @returns {Promise<void>}
   */
  async review(data) {
    if (data.value !== 'accepted' && data.value !== 'changes') throw new Error('Unknown review decision.');
    const target = this.target();
    const flow = await this.connect();
    const ticket = await flow.prepareReview(target.uri.fsPath, data.revision, data.item, data.value);
    const note = await vscode.window.showInputBox({ title: data.value === 'accepted' ? `Accept ${data.item}: what did you check?` : `Changes for ${data.item}: what needs to change?`,
      ignoreFocusOut: true, validateInput: value => !value.trim() ? 'A note is required.' : value.length > 4000 ? 'Use at most 4,000 characters.' : null });
    if (note === undefined) return;
    const label = data.value === 'accepted' ? 'Accept' : 'Request changes';
    const confirm = await vscode.window.showWarningMessage(`${label}: ${data.item}?`, { modal: true,
      detail: `Task ${ticket.ask} in ${target.uri.fsPath}\n\n“${note}”\n\nThis records your decision in the task. It does not push code or start the next stage.` }, label);
    if (confirm !== label) return;
    this.target();
    await flow.recordReview(target.uri.fsPath, ticket, note);
    void vscode.window.showInformationMessage(`${label === 'Accept' ? 'Accepted' : 'Changes requested for'} ${data.item}.`);
  }

  /** Run one of the extension's own commands; it asks its own questions.
   * @param {string} name
   * @returns {Promise<void>}
   */
  async command(name) {
    if (!Object.hasOwn(BASE_COMMANDS, name)) throw new Error('Unknown harness command.');
    const target = this.target();
    if (vscode.workspace.workspaceFolders?.[0]?.uri.toString() !== target.uri.toString()) {
      throw new Error('Set-up and pack commands act on the first folder of this window. Open the selected folder in its own window to use them.');
    }
    await vscode.commands.executeCommand(BASE_COMMANDS[/** @type {keyof typeof BASE_COMMANDS} */ (name)]);
    if (name === 'installPack' || name === 'managePacks') await this.loadPacks();
  }

  /** Turn research telemetry on (the extension's own warning explains what it records) or off.
   * @param {string} value
   * @returns {Promise<void>}
   */
  async telemetrySwitch(value) {
    if (value !== 'on' && value !== 'off') throw new Error('Telemetry must be on or off.');
    await vscode.commands.executeCommand(value === 'on' ? 'frontierHve.researchTelemetry' : 'frontierHve.researchTelemetryOff');
  }

  /** Read the installed expertise packs; a failure shows on the Skills and packs page.
   * @returns {Promise<void>}
   */
  async loadPacks() {
    try {
      const flow = await this.connect();
      this.state.packs = await packs(flow.connection, this.target().uri.fsPath);
      this.state.packsError = null;
    } catch (error) {
      this.state.packs = null;
      this.state.packsError = errorText(error);
      this.output.appendLine(`Expertise packs: ${this.state.packsError}`);
    }
    this.paint();
  }

  /** Open a file Mission Control lists: evidence, the plan, files the agent changed, or a loaded skill.
   * @param {string} relative
   * @returns {Promise<void>}
   */
  async openFile(relative) {
    const root = this.target().uri.fsPath;
    const state = snapshot(root);
    const listed = [...state.files, ...(this.state.activity?.session?.files.map(file => file.path) || []),
      ...state.skills.map(skill => path.join('.hve', 'skills', skill.name, 'SKILL.md'))].map(file => path.normalize(file));
    if (!listed.includes(path.normalize(relative))) throw new Error('That file is not listed in Mission Control.');
    const uri = vscode.Uri.file(containedPath(state.workspace, relative));
    if (['.png', '.jpg', '.jpeg', '.webp', '.gif'].includes(path.extname(relative).toLowerCase())) await vscode.commands.executeCommand('vscode.open', uri);
    else await vscode.window.showTextDocument(uri, { viewColumn: vscode.ViewColumn.Beside, preview: true });
  }

  /** Dispatch a validated view action and show failures before rejecting them.
   * @param {unknown} raw
   * @returns {Promise<import('./types').Snapshot | null>}
   */
  async execute(raw) {
    if (this.disposed) throw new Error('Mission Control has been disposed.');
    const data = message(raw);
    const mutating = ['newTask', 'review', 'command', 'telemetry', 'selectWorkspace'].includes(data.action);
    if (mutating && this.state.busy) throw new Error('Another Mission Control action is still running.');
    if (mutating) { this.state.busy = true; this.paint(); }
    try {
      switch (data.action) {
        case 'ready': case 'refresh': break;
        case 'openDashboard': this.open(data.page); break;
        case 'selectWorkspace': await this.selectWorkspace(); break;
        case 'newTask': await this.newTask(); break;
        case 'editPlan': await this.editPlan(); break;
        case 'review': await this.review(data); break;
        case 'command': await this.command(data.name); break;
        case 'telemetry': await this.telemetrySwitch(data.value); break;
        case 'loadPacks': await this.loadPacks(); break;
        case 'openFile': await this.openFile(data.path); break;
        default: throw new Error('Unsupported Mission Control action.');
      }
      this.state.error = null;
      return await this.refresh();
    } catch (error) {
      const shown = this.show(error);
      void vscode.window.showErrorMessage(shown.message);
      throw shown;
    } finally {
      if (mutating) { this.state.busy = false; this.paint(); }
    }
  }

  /** Dispose only resources owned by Mission Control.
   * @returns {void}
   */
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    if (this.timer) clearTimeout(this.timer);
    this.watchers.forEach(watcher => watcher.dispose());
    this.panel?.dispose();
    this.views.clear();
    this.output.dispose();
  }
}

/** Register Mission Control's view and commands; return the resources to dispose with the extension.
 * @param {vscode.ExtensionContext} context
 * @param {() => Promise<string | null>} findPython Returns a verified Python 3.11+ launcher, or null.
 * @returns {vscode.Disposable[]}
 */
function register(context, findPython) {
  const ui = new MissionControl(context, findPython);
  return [ui,
    vscode.window.registerWebviewViewProvider('frontierHve.missionControl', ui),
    vscode.commands.registerCommand('frontierHve.openMissionControl', () => ui.execute({ action: 'openDashboard', page: 'live' })),
    vscode.commands.registerCommand('frontierHve.refreshMissionControl', () => ui.execute({ action: 'refresh' })),
    vscode.commands.registerCommand('frontierHve.selectWorkspace', () => ui.execute({ action: 'selectWorkspace' })),
    vscode.commands.registerCommand('frontierHve.newTask', () => ui.execute({ action: 'newTask' })),
    vscode.commands.registerCommand('frontierHve.editPlan', () => ui.execute({ action: 'editPlan' })),
    vscode.commands.registerCommand('frontierHve.missionControlModel', () => ui.model('editor')),
    vscode.workspace.onDidChangeWorkspaceFolders(() => { ui.restoreWorkspace(); ui.scheduleRefresh(); }),
    vscode.workspace.onDidChangeConfiguration(event => {
      if (event.affectsConfiguration('github.copilot.chat.otel')) ui.scheduleRefresh();
    })];
}

module.exports = { MissionControl, register, documentHtml };
