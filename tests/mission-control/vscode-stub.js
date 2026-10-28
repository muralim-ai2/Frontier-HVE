'use strict';
/** Supply a small VS Code host double while retaining real filesystem and harness operations. */
const path = require('node:path');
const fs = require('node:fs');
const Module = require('node:module');
const { pathToFileURL } = require('node:url');
const { EXTENSION, workspace, removeWorkspace } = require('./helpers');

/** Represent an independently disposable host resource. */
class Disposable {
  /** @param {() => void} [action] */
  constructor(action = () => {}) { this.action = action; this.disposed = false; }
  /** Release the resource once. @returns {void} */
  dispose() { if (!this.disposed) { this.disposed = true; this.action(); } }
}

/** Return a local URI double.
 * @param {string} file
 * @returns {{fsPath: string, scheme: string, toString: () => string}}
 */
function uri(file) { return { fsPath: file, scheme: 'file', toString: () => pathToFileURL(file).href }; }

/** Return a webview double that records rendered messages.
 * @param {unknown[][]} calls
 * @returns {object}
 */
function webview(calls) {
  return { options: {}, html: '', cspSource: 'https://local.test', asWebviewUri: file => file,
    postMessage: async value => { calls.push(['render', value]); return true; }, onDidReceiveMessage: () => new Disposable() };
}

/** Create a host double scoped to explicitly supplied test directories.
 * @param {string[]} roots
 * @param {string} storage
 * @returns {{api: object, context: object, controls: object, load: (relative: string) => any}}
 */
function host(roots, storage) {
  const commands = new Map();
  const settings = new Map();
  const controls = { commands, settings, provider: null, inputs: [], confirmations: [], calls: [], watchers: [], errors: [], statusItems: [],
    /** Return a Primary Side Bar view double. @param {boolean} [visible] @returns {object} */
    view: (visible = false) => ({ visible, webview: webview(controls.calls), onDidDispose: () => new Disposable() }) };
  const folders = roots.map((root, index) => ({ name: path.basename(root), uri: uri(root), index }));
  const api = {
    Disposable,
    Uri: { file: uri, parse: value => ({ toString: () => value }), joinPath: (base, ...parts) => uri(path.join(base.fsPath, ...parts)) },
    RelativePattern: class { constructor(base, pattern) { this.base = base; this.pattern = pattern; } },
    ViewColumn: { Active: -1, Beside: -2 },
    StatusBarAlignment: { Left: 1, Right: 2 },
    ConfigurationTarget: { Global: 1 },
    env: { openExternal: async target => { controls.calls.push(['external', target.toString()]); return true; } },
    workspace: {
      isTrusted: true, workspaceFolders: folders,
      getConfiguration: section => ({
        get: key => settings.get(`${section}.${key}`),
        update: async (key, value) => { settings.set(`${section}.${key}`, value); },
      }),
      createFileSystemWatcher: pattern => {
        /** @type {(() => void)[]} */
        const listeners = [];
        const listen = listener => { listeners.push(listener); return new Disposable(); };
        const watcher = Object.assign(new Disposable(), { pattern, listeners, onDidCreate: listen, onDidChange: listen, onDidDelete: listen });
        controls.watchers.push(watcher);
        return watcher;
      },
      onDidChangeWorkspaceFolders: () => new Disposable(),
      onDidChangeConfiguration: () => new Disposable(),
      openTextDocument: async file => ({ uri: file }),
    },
    window: {
      createOutputChannel: () => Object.assign(new Disposable(), { appendLine: value => controls.calls.push(['log', value]) }),
      createStatusBarItem: () => {
        const item = Object.assign(new Disposable(), { text: '', tooltip: '', command: '', visible: false });
        Object.assign(item, { show: () => { item.visible = true; }, hide: () => { item.visible = false; } });
        controls.statusItems.push(item);
        return item;
      },
      registerWebviewViewProvider: (id, provider) => {
        controls.provider = provider;
        controls.calls.push(['provider', id]);
        return new Disposable(() => { controls.provider = null; });
      },
      showErrorMessage: async message => { controls.errors.push(message); },
      showInformationMessage: async message => { controls.calls.push(['information', message]); },
      showInputBox: async () => controls.inputs.shift(),
      showWarningMessage: async (...args) => { controls.calls.push(['confirmation', ...args]); return controls.confirmations.shift(); },
      showQuickPick: async choices => choices[0],
      showTextDocument: async (document, options) => { controls.calls.push(['document', document, options]); },
      createWebviewPanel: () => {
        let close = () => {};
        return { webview: webview(controls.calls), onDidDispose: callback => { close = callback; return new Disposable(); },
          reveal: () => {}, dispose: () => close() };
      },
    },
    commands: {
      registerCommand: (id, action) => { commands.set(id, action); return new Disposable(() => commands.delete(id)); },
      getCommands: async () => [...commands.keys(), 'workbench.action.chat.open'],
      executeCommand: async (id, ...args) => {
        controls.calls.push([id, ...args]);
        if (commands.has(id)) return commands.get(id)(...args);
        return undefined;
      },
    },
  };
  /** @returns {{get: (key: string) => unknown, update: (key: string, value: unknown) => Promise<void>}} */
  const memento = () => {
    const memory = new Map();
    return { get: key => memory.get(key), update: async (key, value) => { memory.set(key, value); } };
  };
  const context = {
    subscriptions: [], extensionPath: EXTENSION, extensionUri: uri(EXTENSION), globalStorageUri: uri(storage),
    extension: { packageJSON: JSON.parse(fs.readFileSync(path.join(EXTENSION, 'package.json'), 'utf8')) },
    workspaceState: memento(), globalState: memento(),
  };
  return { api, context, controls, load: relative => {
    const original = Module._load;
    Module._load = function (request, parent, isMain) {
      return request === 'vscode' ? api : original.call(this, request, parent, isMain);
    };
    try {
      for (const file of Object.keys(require.cache)) if (file.startsWith(EXTENSION + path.sep)) delete require.cache[file];
      return require(path.join(EXTENSION, relative));
    } finally { Module._load = original; }
  } };
}

/** Register Mission Control alone in a host double with a fixed Python launcher, disposed after the test.
 * @param {import('node:test').TestContext} t
 * @param {number} [count]
 * @returns {ReturnType<typeof host> & {root: string}}
 */
function mission(t, count = 1) {
  const roots = Array.from({ length: count }, () => workspace());
  const storage = workspace();
  const fixture = host(roots, storage);
  fixture.context.subscriptions.push(...fixture.load(path.join('ui', 'mission-control.js')).register(fixture.context, async () => 'python'));
  t.after(() => {
    fixture.context.subscriptions.forEach(resource => resource.dispose());
    [...roots, storage].forEach(removeWorkspace);
  });
  return { ...fixture, root: roots[0], storage };
}

module.exports = { host, mission };
