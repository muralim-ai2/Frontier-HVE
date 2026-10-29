'use strict';
/** Mission Control: the Frontier HVE sidebar and dashboard, kept live from the harness files and this window's chat transcripts. */
const vscode = require('vscode');
const path = require('node:path');
const { randomBytes } = require('node:crypto');
const { runtime, inspect, guardMode, packs } = require('./lifecycle-cli');
const { snapshot } = require('./workspace-state');
const { activity } = require('./activity');
const { listAsks, askTree } = require('./asks');
const { chatList, shownChat, claimsFrom, pendingFrom } = require('./chats');
const { Workflow } = require('./workflow');
const { HarnessTree } = require('./harness-tree');
const actions = require('./actions');
const askFlow = require('./ask-flow');
const analysis = require('./analysis');
const { insights } = require('./insights');
const { record, text, message, errorText } = require('./validate');
const PAGES = ['live', 'plan', 'progress', 'files', 'others', 'telemetry', 'skills', 'settings'];
const SCRIPTS = ['vnode.js', 'markdown.js', 'views.js', 'telemetry.js', 'pages.js', 'app.js'];
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
    /** @type {string | null} The ask on screen when it is not the active ask. */
    this.selected = null;
    /** @type {string | null} The chat on screen when it is not the ask's latest. */
    this.chat = null;
    this.disposed = false;
    /** @type {NodeJS.Timeout | null} */
    this.treeTimer = null;
    this.tree = new HarnessTree(() => this.workspace?.uri.scheme === 'file' ? this.workspace.uri.fsPath : null);
    const version = text(record(context.extension.packageJSON, 'Extension manifest').version, 'Extension version');
    /** @type {Omit<import('./types').Model, 'now' | 'surface' | 'workspace' | 'telemetry' | 'navigate' | 'transcripts'>} */
    this.state = { busy: false, error: null, workspaceMessage: null, connection: { version, python: null, guard: guardMode(context.extensionPath) },
      asks: null, asksError: null, snapshot: null, snapshotError: null, activity: null, activityError: null, pending: null, handoff: null, handoffError: null, insights: null, models: null, modelsError: null, analysis: null, files: null, filesError: null,
      packs: null, packsError: null };
    this.restoreWorkspace();
  }

  /** Restore an explicit selection or use the only local workspace, and the ask on screen.
   * @returns {void}
   */
  restoreWorkspace() {
    const folders = vscode.workspace.workspaceFolders || [];
    const saved = this.context.workspaceState.get('selectedWorkspace');
    this.workspace = folders.find(folder => folder.uri.toString() === saved) || (folders.length === 1 ? folders[0] : null);
    const ask = this.context.workspaceState.get('selectedAsk');
    this.selected = typeof ask === 'string' ? ask : null;
    this.flow = null;
    this.bindWatchers();
  }

  /** Show an ask (null follows the active ask) and its latest chat; the choice is kept for this window.
   * @param {string | null} ask
   * @returns {Promise<void>}
   */
  async view(ask) {
    this.selected = ask;
    this.chat = null;
    await this.context.workspaceState.update('selectedAsk', ask);
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

  /** Watch the workspace's .hve/ and .harness/ folders and this window's chat transcripts.
   * @returns {void}
   */
  bindWatchers() {
    this.watchers.forEach(watcher => watcher.dispose());
    this.watchers = [];
    this.tree.refresh();
    if (this.workspace?.uri.scheme !== 'file') return;
    const patterns = [new vscode.RelativePattern(this.workspace, '.hve/**/*')];
    const storage = this.context.storageUri;
    if (storage) patterns.push(new vscode.RelativePattern(vscode.Uri.file(path.dirname(storage.fsPath)), 'GitHub.copilot-chat/transcripts/*.jsonl'));
    patterns.push(new vscode.RelativePattern(this.workspace, '.harness/**/*'));
    for (const pattern of patterns) {
      const watcher = vscode.workspace.createFileSystemWatcher(pattern);
      const changed = pattern.pattern.endsWith('.jsonl') ? () => this.scheduleRefresh() : () => { this.scheduleRefresh(); this.scheduleTree(); };
      watcher.onDidCreate(changed);
      watcher.onDidChange(changed);
      watcher.onDidDelete(changed);
      this.watchers.push(watcher);
    }
  }

  /** Coalesce file changes into one refresh of the Harness files pane, which reads only the folders it shows.
   * @returns {void}
   */
  scheduleTree() {
    if (this.disposed) return;
    if (this.treeTimer) clearTimeout(this.treeTimer);
    this.treeTimer = setTimeout(() => { this.treeTimer = null; this.tree.refresh(); }, REFRESH_DELAY_MS);
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

  /** Read one section of the model; a failure is logged and shown in that section while the others stay live.
   * @template T
   * @param {string} label
   * @param {() => Promise<T>} read
   * @returns {Promise<{value: T | null, error: string | null}>}
   */
  async section(label, read) {
    try {
      return { value: await read(), error: null };
    } catch (error) {
      const shown = errorText(error);
      this.output.appendLine(`${label}: ${shown}`);
      return { value: null, error: shown };
    }
  }

  /** Re-read the project's asks, the ask on screen, its chats and its folder.
   * @returns {Promise<import('./types').Snapshot | null>}
   */
  async refresh() {
    if (!vscode.workspace.isTrusted) throw new Error('Trust this workspace to use Mission Control.');
    this.state.workspaceMessage = null;
    if (!this.workspace) {
      Object.assign(this.state, { asks: null, asksError: null, snapshot: null, snapshotError: null, activity: null, activityError: null, files: null, filesError: null });
      this.state.workspaceMessage = (vscode.workspace.workspaceFolders?.length || 0) > 1
        ? 'Choose which workspace folder Mission Control follows.' : 'Open a project folder to use Mission Control.';
      this.paint();
      return null;
    }
    const root = this.target().uri.fsPath;
    const now = Date.now();
    this.python ||= await this.findPython();
    this.state.connection.python = this.python;
    const asks = await this.section('Asks', async () => {
      const rows = listAsks(root);
      if (this.selected !== null && !rows.some(ask => ask.id === this.selected)) await this.view(null);
      return rows;
    });
    const state = await this.section('Harness state', async () => snapshot(root, this.selected));
    const viewed = state.value?.ask?.id ?? this.selected ?? asks.value?.find(ask => ask.active)?.id ?? null;
    const live = await this.section('Live activity', async () => {
      const transcripts = this.transcripts();
      const claims = claimsFrom(this.context.workspaceState.get('chatAsks'));
      const pending = pendingFrom(this.context.workspaceState.get('pendingChat'), now);
      const { chats, claimed } = chatList(transcripts, root, (asks.value || []).map(ask => ask.id), claims, pending, now);
      if (claimed) {
        await this.context.workspaceState.update('chatAsks', { ...claims, [claimed.chat]: { ask: claimed.ask, how: 'started' } });
        await this.context.workspaceState.update('pendingChat', null);
      }
      this.state.pending = claimed ? null : pending;
      const shown = shownChat(chats, viewed, this.chat);
      return { ...activity(root, shown && transcripts ? path.join(transcripts, `${shown.id}.jsonl`) : null, this.telemetry().file, now), chats };
    });
    const files = await this.section('Ask files', async () => viewed ? askTree(root, viewed) : null);
    const carried = await this.section('Ask carried over', async () => askFlow.handoff(this));
    Object.assign(this.state, { asks: asks.value, asksError: asks.error, snapshot: state.value, snapshotError: state.error,
      activity: live.value, activityError: live.error, files: files.value, filesError: files.error,
      handoff: carried.value, handoffError: carried.error, insights: live.value ? insights(live.value) : null });
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
    await this.view(null);
    this.bindWatchers();
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

  /** Dispatch a validated view action and show failures before rejecting them.
   * @param {unknown} raw
   * @returns {Promise<import('./types').Snapshot | null>}
   */
  async execute(raw) {
    if (this.disposed) throw new Error('Mission Control has been disposed.');
    const data = message(raw);
    const mutating = ['newAsk', 'newChat', 'startHandoff', 'dismissHandoff', 'activateAsk', 'review', 'command', 'telemetry', 'selectWorkspace'].includes(data.action);
    if (mutating && this.state.busy) throw new Error('Another Mission Control action is still running.');
    if (mutating) { this.state.busy = true; this.paint(); }
    try {
      switch (data.action) {
        case 'ready': case 'refresh': break;
        case 'openDashboard': this.open(data.page); break;
        case 'selectWorkspace': await this.selectWorkspace(); break;
        case 'newAsk': await askFlow.newAsk(this); break;
        case 'newChat': await askFlow.newChat(this); break;
        case 'startHandoff': await askFlow.startHandoff(this); break;
        case 'dismissHandoff': await askFlow.dismissHandoff(this); break;
        case 'attachReferences': await askFlow.attachReferences(this); break;
        case 'loadModels': await analysis.loadModels(this); break;
        case 'analyze': await analysis.analyze(this, data.model, data.question); break;
        case 'selectAsk': await actions.selectAsk(this, data.ask); break;
        case 'activateAsk': await actions.activateAsk(this, data.ask); break;
        case 'selectChat': actions.selectChat(this, data.chat); break;
        case 'linkChat': await actions.linkChat(this, data.chat); break;
        case 'editPlan': await actions.editPlan(this); break;
        case 'revealAsk': await actions.revealAsk(this); break;
        case 'review': await actions.review(this, data); break;
        case 'command': await actions.command(this, data.name); break;
        case 'telemetry': await actions.telemetrySwitch(data.value); break;
        case 'loadPacks': await this.loadPacks(); break;
        case 'openFile': await actions.openFile(this, data.path); break;
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
    if (this.treeTimer) clearTimeout(this.treeTimer);
    this.watchers.forEach(watcher => watcher.dispose());
    this.tree.dispose();
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
  const files = vscode.window.createTreeView('frontierHve.harnessFiles', { treeDataProvider: ui.tree, showCollapseAll: true });
  ui.tree.view = files;
  askFlow.offerHandoff(ui).catch(error => ui.show(error));
  return [ui, files,
    vscode.window.registerWebviewViewProvider('frontierHve.missionControl', ui),
    vscode.commands.registerCommand('frontierHve.openMissionControl', () => ui.execute({ action: 'openDashboard', page: 'live' })),
    vscode.commands.registerCommand('frontierHve.refreshMissionControl', () => ui.execute({ action: 'refresh' })),
    vscode.commands.registerCommand('frontierHve.selectWorkspace', () => ui.execute({ action: 'selectWorkspace' })),
    vscode.commands.registerCommand('frontierHve.newAsk', () => ui.execute({ action: 'newAsk' })),
    vscode.commands.registerCommand('frontierHve.editPlan', () => ui.execute({ action: 'editPlan' })),
    vscode.commands.registerCommand('frontierHve.missionControlModel', () => ui.model('editor')),
    vscode.workspace.onDidChangeWorkspaceFolders(() => { ui.restoreWorkspace(); ui.scheduleRefresh(); }),
    vscode.workspace.onDidChangeConfiguration(event => {
      if (event.affectsConfiguration('github.copilot.chat.otel')) ui.scheduleRefresh();
    })];
}

module.exports = { MissionControl, register, documentHtml };
