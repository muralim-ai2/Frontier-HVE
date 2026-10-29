'use strict';
/** The Harness files pane: everything under the workspace's .hve/ and .harness/ folders as a native, lazily expanded tree; links are listed but never followed. */
const vscode = require('vscode');
const fs = require('node:fs');
const path = require('node:path');
const { containedPath } = require('./file-access');
const { listAsks } = require('./asks');
const { errorText } = require('./validate');
const ROOTS = ['.hve', '.harness'];
const OPEN = ['.hve', '.harness', '.hve/asks'];
const FOLDER_LIMIT = 500;

/** @typedef {{path: string, name: string, kind: 'folder' | 'file' | 'other' | 'more', size: number, modified: string | null}} Node */

/** Return a file size in words.
 * @param {number} bytes
 * @returns {string}
 */
function size(bytes) {
  return bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Return a folder's entries: folders first, ask folders newest first, at most 500 with a note for the rest.
 * @param {string} root
 * @param {string} relative
 * @returns {Node[]}
 */
function entries(root, relative) {
  const asks = relative === '.hve/asks';
  const nodes = fs.readdirSync(containedPath(root, relative), { withFileTypes: true }).map(entry => {
    const child = `${relative}/${entry.name}`;
    const stat = fs.lstatSync(path.join(root, child));
    const kind = stat.isSymbolicLink() ? 'other' : stat.isDirectory() ? 'folder' : stat.isFile() ? 'file' : 'other';
    return /** @type {Node} */ ({ path: child, name: entry.name, kind, size: stat.size, modified: stat.mtime.toISOString() });
  }).sort((a, b) => Number(b.kind === 'folder') - Number(a.kind === 'folder') || (asks && a.kind === 'folder' ? b.name.localeCompare(a.name) : a.name.localeCompare(b.name)));
  if (nodes.length <= FOLDER_LIMIT) return nodes;
  return [...nodes.slice(0, FOLDER_LIMIT), { path: `${relative}/…`, name: `${nodes.length - FOLDER_LIMIT} more not shown`, kind: 'more', size: 0, modified: null }];
}

/** Provide the Harness files tree for the workspace Mission Control follows. */
class HarnessTree {
  /** @param {() => string | null} workspace Returns the followed local workspace folder, or null. */
  constructor(workspace) {
    this.workspace = workspace;
    /** @type {vscode.EventEmitter<Node | undefined>} */
    this.changed = new vscode.EventEmitter();
    this.onDidChangeTreeData = this.changed.event;
    /** @type {vscode.TreeView<Node> | null} */
    this.view = null;
    /** @type {Map<string, import('./types').AskSummary>} */
    this.asks = new Map();
  }

  /** Re-read the tree from disk.
   * @returns {void}
   */
  refresh() { this.changed.fire(undefined); }

  /** Return the top folders, or a folder's entries.
   * @param {Node} [node]
   * @returns {Node[]}
   */
  getChildren(node) {
    const workspace = this.workspace();
    if (!workspace) return [];
    const root = fs.realpathSync(workspace);
    if (node) return node.kind === 'folder' ? entries(root, node.path) : [];
    this.readAsks(root);
    return ROOTS.filter(name => fs.existsSync(path.join(root, name)))
      .map(name => ({ path: name, name, kind: fs.lstatSync(path.join(root, name)).isSymbolicLink() ? 'other' : 'folder', size: 0, modified: null }));
  }

  /** Read the ask titles shown beside ask folders; a failure is shown at the top of the pane and the files stay browsable.
   * @param {string} root
   * @returns {void}
   */
  readAsks(root) {
    try {
      this.asks = new Map(listAsks(root).map(ask => [ask.id, ask]));
      if (this.view) this.view.message = undefined;
    } catch (error) {
      this.asks = new Map();
      if (this.view) this.view.message = `Ask titles cannot be read: ${errorText(error)}`;
    }
  }

  /** Return how a node shows: folders expand, files open on click, links and notes do nothing.
   * @param {Node} node
   * @returns {vscode.TreeItem}
   */
  getTreeItem(node) {
    const workspace = /** @type {string} */ (this.workspace());
    const uri = vscode.Uri.file(path.join(fs.realpathSync(workspace), ...node.path.split('/')));
    const item = new vscode.TreeItem(node.name, vscode.TreeItemCollapsibleState.None);
    item.id = node.path;
    item.contextValue = node.kind;
    if (node.kind === 'more') {
      item.iconPath = new vscode.ThemeIcon('ellipsis');
      item.tooltip = 'This folder has more than 500 entries. Open it in the Explorer to see all of them.';
      return item;
    }
    item.resourceUri = uri;
    item.tooltip = `${node.path}${node.modified ? `\nChanged ${new Date(node.modified).toLocaleString()}` : ''}`;
    if (node.kind === 'other') {
      item.iconPath = new vscode.ThemeIcon('link');
      item.description = 'link or special file, not opened';
      return item;
    }
    if (node.kind === 'file') {
      item.description = size(node.size);
      item.command = { command: 'vscode.open', title: 'Open', arguments: [uri] };
      return item;
    }
    const ask = node.path.startsWith('.hve/asks/') && node.path.split('/').length === 3 ? this.asks.get(node.name) : undefined;
    item.iconPath = vscode.ThemeIcon.Folder;
    item.collapsibleState = OPEN.includes(node.path) || ask?.active ? vscode.TreeItemCollapsibleState.Expanded : vscode.TreeItemCollapsibleState.Collapsed;
    if (ask) {
      item.description = `${ask.active ? 'active · ' : ''}${ask.title}`;
      item.tooltip = `${node.path}\n${ask.title}\n${ask.agent}${ask.stage ? ` · ${ask.stage}` : ''}${ask.active ? '\nThe active ask: agents work on it.' : ''}`;
    }
    return item;
  }

  /** Release the change event.
   * @returns {void}
   */
  dispose() { this.changed.dispose(); }
}

module.exports = { HarnessTree, entries };
