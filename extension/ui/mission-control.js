'use strict';
/** Mission Control: the Frontier HVE sidebar and editor views with explicit user confirmations. */
const vscode = require('vscode');
const path = require('node:path');
const { randomBytes } = require('node:crypto');
const { BASE_COMMANDS, runtime, inspect, guardMode } = require('./lifecycle-cli');
const { snapshot } = require('./workspace-state');
const { containedPath } = require('./file-access');
const { Workflow } = require('./workflow');
const { render, documentHtml, PAGES } = require('./render');
const { record, text, message, errorText } = require('./validate');

/** Coordinate Mission Control's views, workspace selection and confirmed harness actions. */
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
    /** @type {vscode.WebviewPanel | null} */
    this.panel = null;
    /** @type {vscode.WorkspaceFolder | null} */
    this.workspace = null;
    /** @type {vscode.FileSystemWatcher | null} */
    this.watcher = null;
    /** @type {NodeJS.Timeout | null} */
    this.timer = null;
    /** @type {Workflow | null} */
    this.flow = null;
    this.page = 'overview';
    /** @type {string | null} */
    this.check = null;
    this.disposed = false;
    /** @type {import('./types').ViewState} */
    this.state = { snapshot: null, connection: 'Not connected', python: 'Not checked', guard: 'Unavailable',
      telemetry: false, busy: false, error: null, workspaceMessage: null };
    this.restoreWorkspace();
  }

  /** Restore an explicit selection or use the only local workspace.
   * @returns {void}
   */
  restoreWorkspace() {
    const folders = vscode.workspace.workspaceFolders || [];
    const saved = this.context.workspaceState.get('selectedWorkspace');
    this.workspace = folders.find(folder => folder.uri.toString() === saved) || (folders.length === 1 ? folders[0] : null);
    this.bindWatcher();
  }

  /** Watch only project and ask state in the selected workspace.
   * @returns {void}
   */
  bindWatcher() {
    this.watcher?.dispose();
    this.watcher = null;
    if (this.workspace?.uri.scheme !== 'file') return;
    this.watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(this.workspace, '.hve/{project,asks}/**/*'));
    this.watcher.onDidCreate(() => this.scheduleRefresh());
    this.watcher.onDidChange(() => this.scheduleRefresh());
    this.watcher.onDidDelete(() => this.scheduleRefresh());
  }

  /** Coalesce filesystem notifications without polling telemetry.
   * @returns {void}
   */
  scheduleRefresh() {
    if (this.disposed) return;
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      if (!this.state.busy) void vscode.commands.executeCommand('frontierHve.refreshMissionControl');
    }, 250);
  }

  /** Require a trusted local workspace before reading state or executing code.
   * @returns {vscode.WorkspaceFolder}
   */
  target() {
    if (!vscode.workspace.isTrusted) throw new Error('Trust this workspace before using the live harness.');
    if (!this.workspace) throw new Error('Select a workspace folder first.');
    if (this.workspace.uri.scheme !== 'file') throw new Error('This release requires a local filesystem workspace.');
    return this.workspace;
  }

  /** Connect to this extension's bundled runtime with the detected Python launcher.
   * @returns {Promise<Workflow>}
   */
  async connect() {
    this.target();
    if (this.flow) return this.flow;
    const python = await this.findPython();
    if (!python) throw new Error('Mission Control needs Python 3.11+ on PATH (python, python3 or py -3). Install it, then run "Frontier HVE: Set up".');
    const connection = runtime(this.context.extensionPath, python.split(' '));
    await inspect(connection, this.target().uri.fsPath);
    this.flow = new Workflow(connection, this.context.globalStorageUri.fsPath);
    this.state.connection = `HVE ${text(record(this.context.extension.packageJSON, 'Extension manifest').version, 'Extension version')}`;
    this.state.python = python;
    this.state.guard = guardMode(connection) === 'advise' ? 'Advisory (not an enforced block)' : 'Enforced';
    return this.flow;
  }

  /** Re-read passive state without reconciling plan checkboxes.
   * @returns {Promise<import('./types').Snapshot | null>}
   */
  async refresh() {
    if (!vscode.workspace.isTrusted) throw new Error('Workspace trust is required.');
    this.state.workspaceMessage = null;
    if (!this.workspace) {
      this.state.snapshot = null;
      this.state.workspaceMessage = (vscode.workspace.workspaceFolders?.length || 0) > 1
        ? 'Select one workspace explicitly; the UI will not assume the first folder.'
        : 'Open a local project folder to connect to the harness.';
    } else {
      await this.connect();
      this.state.snapshot = snapshot(this.target().uri.fsPath);
    }
    this.state.telemetry = vscode.workspace.getConfiguration('github.copilot.chat.otel').get('enabled') === true;
    this.state.error = null;
    this.paint();
    return this.state.snapshot;
  }

  /** Publish escaped content to each currently open surface.
   * @returns {void}
   */
  paint() {
    if (this.disposed) return;
    for (const [view, surface] of this.views) {
      void view.postMessage({ type: 'render', html: render(this.state, surface, this.page, this.check), busy: this.state.busy });
    }
  }

  /** Attach a restricted webview and its message handler.
   * @param {vscode.Webview} webview
   * @param {'sidebar' | 'editor'} surface
   * @returns {vscode.Disposable}
   */
  attach(webview, surface) {
    const media = vscode.Uri.joinPath(this.context.extensionUri, 'ui', 'media');
    webview.options = { enableScripts: true, localResourceRoots: [media] };
    webview.html = documentHtml(webview.asWebviewUri(vscode.Uri.joinPath(media, 'app.css')).toString(),
      webview.asWebviewUri(vscode.Uri.joinPath(media, 'app.js')).toString(), webview.cspSource, randomBytes(18).toString('hex'));
    this.views.set(webview, surface);
    const listener = webview.onDidReceiveMessage(async value => { await this.execute(value); });
    return new vscode.Disposable(() => { listener.dispose(); this.views.delete(webview); });
  }

  /** Resolve the contributed Primary Side Bar view.
   * @param {vscode.WebviewView} view
   * @returns {void}
   */
  resolveWebviewView(view) {
    const attached = this.attach(view.webview, 'sidebar');
    view.onDidDispose(() => attached.dispose());
  }

  /** Open or reveal the shared editor detail view.
   * @param {string} [page]
   * @returns {void}
   */
  open(page = 'overview') {
    if (!PAGES.includes(page)) throw new Error(`Unknown page: ${page}`);
    this.page = page;
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel('frontierHve.missionControlDetail', 'HVE Mission Control', vscode.ViewColumn.Active, {});
      const attached = this.attach(this.panel.webview, 'editor');
      this.panel.onDidDispose(() => { attached.dispose(); this.panel = null; });
    } else this.panel.reveal(vscode.ViewColumn.Active, true);
    this.paint();
  }

  /** Ask the user to select a workspace without changing VS Code's folder order.
   * @returns {Promise<void>}
   */
  async selectWorkspace() {
    const folders = vscode.workspace.workspaceFolders || [];
    if (!folders.length) throw new Error('Open a local folder in VS Code first.');
    const selected = await vscode.window.showQuickPick(folders.map(folder => ({ label: folder.name, description: folder.uri.fsPath, folder })),
      { title: 'Frontier HVE Mission Control: target workspace', ignoreFocusOut: true });
    if (!selected) return;
    if (selected.folder.uri.scheme !== 'file') throw new Error('Choose a local filesystem workspace.');
    this.workspace = selected.folder;
    this.flow = null;
    await this.context.workspaceState.update('selectedWorkspace', selected.folder.uri.toString());
    this.bindWatcher();
    await this.refresh();
  }

  /** Collect and confirm an actual task creation request.
   * @returns {Promise<void>}
   */
  async newTask() {
    const target = this.target();
    const flow = await this.connect();
    const request = await vscode.window.showInputBox({ title: 'New HVE task', prompt: 'What outcome should HVE creator deliver? This creates a real direct-delivery ask.',
      ignoreFocusOut: true, validateInput: value => !value.trim() || value.length > 20000 ? 'Enter a request of 1-20,000 characters.' : null });
    if (request === undefined) return;
    const slug = await vscode.window.showInputBox({ title: 'Task identifier', prompt: 'Use a short identifier for the ask folder.',
      ignoreFocusOut: true, validateInput: value => /^[a-z0-9][a-z0-9-]{0,40}$/.test(value) ? null : 'Use 1-41 lowercase letters, digits or hyphens.' });
    if (slug === undefined) return;
    const description = await flow.describeTask(target.uri.fsPath, request);
    const confirm = await vscode.window.showWarningMessage(`Create "${slug}" in ${target.uri.fsPath}?`,
      { modal: true, detail: `${description.why}\n${description.activeAsk ? `Current ask ${description.activeAsk} will no longer be active.\n` : ''}The existing harness will create an ask, record the project and install selected skills locally. It will not start an agent, enable telemetry, commit or push.` }, 'Create task');
    if (confirm !== 'Create task') return;
    this.target();
    this.state.snapshot = await flow.createTask(target.uri.fsPath, description.revision, slug, request);
    this.check = null;
    this.open('overview');
    void vscode.window.showInformationMessage(`Created ${this.state.snapshot.ask?.id}. Use Continue in Chat to plan and execute the work.`);
  }

  /** Open a real Chat draft with the exact current ask context.
   * @returns {Promise<void>}
   */
  async continueInChat() {
    const target = this.target();
    const state = snapshot(target.uri.fsPath);
    if (!state.ask) throw new Error('Create or open a task before continuing in Chat.');
    const available = await vscode.commands.getCommands(true);
    if (!available.includes('workbench.action.chat.open')) throw new Error('This VS Code host does not expose the supported Chat opening command.');
    const query = `Continue the existing Frontier HVE ask ${state.ask.id} in workspace ${target.uri.fsPath} using ${state.ask.agent}. `
      + `Read its contract and plan first. Request: ${state.ask.request}. Do not create a replacement ask. `
      + 'Check the active ask identity, plan status, evidence and pending human decisions before continuing.';
    await vscode.commands.executeCommand('workbench.action.chat.open', { query, isPartialQuery: true });
    void vscode.window.showInformationMessage(`The draft is in Chat. Select ${state.ask.agent}, review it, and press Send. No agent was started automatically.`);
  }

  /** Confirm and persist a human decision through the guarded core API.
   * @param {Record<string, string>} data
   * @returns {Promise<void>}
   */
  async review(data) {
    if (data.value !== 'accepted' && data.value !== 'changes') throw new Error('Unknown review decision.');
    const target = this.target();
    const flow = await this.connect();
    const ticket = await flow.prepareReview(target.uri.fsPath, data.revision, data.item, data.value);
    const note = await vscode.window.showInputBox({ title: data.value === 'accepted' ? 'What evidence did you review?' : 'What needs to change?',
      ignoreFocusOut: true, validateInput: value => !value.trim() ? 'A human review note is required.' : value.length > 4000 ? 'Use at most 4,000 characters.' : null });
    if (note === undefined) return;
    const label = data.value === 'accepted' ? 'Record acceptance' : 'Request changes';
    const confirm = await vscode.window.showWarningMessage(`${label} for ${data.item}?`, { modal: true,
      detail: `Workspace: ${target.uri.fsPath}\nAsk: ${ticket.ask}\n${note}\n\nThis records a real human decision. It does not push code or advance workflow stages.` }, label);
    if (confirm !== label) return;
    this.target();
    this.state.snapshot = await flow.recordReview(target.uri.fsPath, ticket, note);
    void vscode.window.showInformationMessage(`${label} saved for ${ticket.ask}.`);
  }

  /** Invoke only existing harness commands in their actual workspace context.
   * @param {string} name
   * @returns {Promise<void>}
   */
  async baseCommand(name) {
    if (!Object.hasOwn(BASE_COMMANDS, name)) throw new Error('Unknown harness command.');
    const target = this.target();
    await this.connect();
    const first = vscode.workspace.workspaceFolders?.[0];
    if (first?.uri.toString() !== target.uri.toString()) {
      throw new Error('The original harness setup/pack commands target the first workspace folder. Open the selected folder in its own window before using these controls.');
    }
    const command = BASE_COMMANDS[/** @type {keyof typeof BASE_COMMANDS} */ (name)];
    if (!(await vscode.commands.getCommands(true)).includes(command)) throw new Error(`The installed harness did not register ${command}.`);
    const confirm = await vscode.window.showWarningMessage(`Run the existing harness command "${name}"?`, {
      modal: true, detail: `Target workspace: ${target.uri.fsPath}\nThe original harness owns this command and its configuration changes.`,
    }, 'Run command');
    if (confirm !== 'Run command') return;
    this.target();
    await vscode.commands.executeCommand(command);
  }

  /** Open only a file listed in the latest validated workspace snapshot.
   * @param {string} relative
   * @returns {Promise<void>}
   */
  async openFile(relative) {
    const state = snapshot(this.target().uri.fsPath);
    if (!state.files.includes(relative)) throw new Error('The requested file is not in the current evidence snapshot.');
    const file = containedPath(state.workspace, relative);
    const uri = vscode.Uri.file(file);
    if (['.png', '.jpg', '.jpeg', '.webp'].includes(path.extname(file).toLowerCase())) await vscode.commands.executeCommand('vscode.open', uri);
    else await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(uri), { preview: true });
  }

  /** Dispatch a validated UI action and expose failures before rejecting them.
   * @param {unknown} raw
   * @returns {Promise<import('./types').Snapshot | null>}
   */
  async execute(raw) {
    if (this.disposed) throw new Error('Mission Control has been disposed.');
    const data = message(raw);
    const mutating = ['newTask', 'review', 'baseCommand', 'selectWorkspace'].includes(data.action);
    if (mutating && this.state.busy) throw new Error('Another UI operation is still in progress.');
    if (mutating) { this.state.busy = true; this.paint(); }
    try {
      switch (data.action) {
        case 'ready': case 'refresh': await this.refresh(); break;
        case 'navigate': this.open(data.page); break;
        case 'inspectCheck':
          if (!this.state.snapshot?.features.some(feature => feature.name === data.name)) throw new Error('This feature is not in the current workspace.');
          this.check = data.name; this.open('evidence'); break;
        case 'selectWorkspace': await this.selectWorkspace(); break;
        case 'newTask': await this.newTask(); await this.refresh(); break;
        case 'continue': await this.continueInChat(); break;
        case 'review': await this.review(data); await this.refresh(); break;
        case 'baseCommand': await this.baseCommand(data.command); this.flow = null; await this.refresh(); break;
        case 'openFile': await this.openFile(data.path); break;
        default: throw new Error('Unsupported UI action.');
      }
      return this.state.snapshot;
    } catch (error) {
      const contextual = new Error(`Frontier HVE Mission Control: ${errorText(error)}`, { cause: error });
      this.state.error = contextual.message;
      this.output.appendLine(contextual.message);
      this.paint();
      void vscode.window.showErrorMessage(contextual.message);
      throw contextual;
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
    this.watcher?.dispose();
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
    vscode.commands.registerCommand('frontierHve.openMissionControl', async () => { ui.open(); return ui.execute({ action: 'refresh' }); }),
    vscode.commands.registerCommand('frontierHve.refreshMissionControl', () => ui.execute({ action: 'refresh' })),
    vscode.commands.registerCommand('frontierHve.selectWorkspace', () => ui.execute({ action: 'selectWorkspace' })),
    vscode.commands.registerCommand('frontierHve.newTask', () => ui.execute({ action: 'newTask' })),
    vscode.commands.registerCommand('frontierHve.continueInChat', () => ui.execute({ action: 'continue' })),
    vscode.workspace.onDidChangeWorkspaceFolders(() => { ui.restoreWorkspace(); ui.flow = null; ui.scheduleRefresh(); }),
    vscode.workspace.onDidChangeConfiguration(event => {
      if (event.affectsConfiguration('github.copilot.chat.otel')) ui.scheduleRefresh();
    })];
}

module.exports = { MissionControl, register };
