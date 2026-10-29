'use strict';
/** Mission Control extras: prune the research telemetry export, build and open the solution map, and start an infographic in a chat. */
const vscode = require('vscode');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
const { pipeline } = require('node:stream/promises');
const { buildMap } = require('./lifecycle-cli');
const { containedPath } = require('./file-access');
const { AGENT } = require('./ask-flow');
const MAP_PAGE = path.join('.hve', 'map', 'explorer.html');

/** @typedef {import('./mission-control').MissionControl} MissionControl */

/** Archive and empty, or just empty, the research telemetry export after the user confirms.
 * @param {MissionControl} mc
 * @returns {Promise<void>}
 */
async function pruneTelemetry(mc) {
  const file = mc.telemetry().file;
  if (!file) throw new Error('No telemetry export is configured. Turn research telemetry on once to create it.');
  if (!file.endsWith('.jsonl')) throw new Error(`Mission Control only prunes a .jsonl telemetry export, not ${file}.`);
  if (!fs.existsSync(file)) throw new Error(`There is no telemetry export to prune at ${file}.`);
  const megabytes = (fs.statSync(file).size / 1024 / 1024).toFixed(1);
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const archive = path.join(path.dirname(file), `otel-archive-${stamp}.jsonl.gz`);
  const choice = await vscode.window.showWarningMessage(`Prune research telemetry (${megabytes} MB)?`, { modal: true, detail: `${file}\n\n`
    + `Archive, then empty: a compressed copy goes to ${path.basename(archive)} next to it, then the export is emptied.\nDelete all records: the export is emptied with no copy.\n\n`
    + `Research telemetry stays ${mc.telemetry().enabled ? 'on: new chats keep recording' : 'off'}. Token figures for chats recorded before now are lost from the Telemetry tab. `
    + 'Best done while no chat is running.' }, 'Archive, then empty', 'Delete all records');
  if (!choice) return;
  if (choice === 'Archive, then empty') {
    await pipeline(fs.createReadStream(file), zlib.createGzip(), fs.createWriteStream(archive));
    if (!fs.statSync(archive).size) throw new Error(`The archive ${archive} is empty; the export was not emptied.`);
  }
  fs.truncateSync(file, 0);
  void vscode.window.showInformationMessage(choice === 'Archive, then empty' ? `Telemetry archived to ${archive} and the export emptied.` : 'Telemetry export emptied.');
}

/** Return when the solution map page was last built, or null.
 * @param {string} root
 * @returns {{built: string, bytes: number} | null}
 */
function mapInfo(root) {
  const page = containedPath(root, MAP_PAGE);
  if (!fs.existsSync(page)) return null;
  const stat = fs.statSync(page);
  return { built: stat.mtime.toISOString(), bytes: stat.size };
}

/** Build or refresh the workspace's solution map with the bundled tool, then open it in a tab.
 * @param {MissionControl} mc
 * @returns {Promise<void>}
 */
async function refreshMap(mc) {
  const root = mc.target().uri.fsPath;
  const flow = await mc.connect();
  const map = await buildMap(flow.connection, root);
  void vscode.window.showInformationMessage(`Solution map built: ${map.sizeClass} repository, ${map.files} files, ${map.concepts} concepts.`);
  openMap(mc);
}

/** Show the solution map explorer in its own editor tab; it is the self-contained page the map tool writes.
 * @param {MissionControl} mc
 * @returns {void}
 */
function openMap(mc) {
  const page = containedPath(mc.target().uri.fsPath, MAP_PAGE);
  if (!fs.existsSync(page)) throw new Error('There is no solution map yet. Build it first.');
  const html = fs.readFileSync(page, 'utf8');
  if (mc.mapPanel) mc.mapPanel.reveal(vscode.ViewColumn.Active);
  else {
    const panel = vscode.window.createWebviewPanel('frontierHve.solutionMap', 'Solution map', vscode.ViewColumn.Active, { enableScripts: true, localResourceRoots: [] });
    panel.onDidDispose(() => { mc.mapPanel = null; });
    mc.mapPanel = panel;
  }
  /** @type {vscode.WebviewPanel} */ (mc.mapPanel).webview.html = html;
}

/** Open a new Local chat with the clickable-infographic skill and a subject filled in, not sent.
 * @param {MissionControl} mc
 * @returns {Promise<void>}
 */
async function infographic(mc) {
  mc.target();
  const subject = await vscode.window.showInputBox({ title: 'Clickable infographic: what should it show?', value: 'How this repository works, from request to delivery',
    prompt: 'A subject and the question it answers. A chat opens with the infographic skill and this filled in; you send it.', ignoreFocusOut: true,
    validateInput: value => value.trim().length < 3 || value.length > 300 ? 'Use 3-300 characters.' : null });
  if (subject === undefined) return;
  await vscode.commands.executeCommand('workbench.action.chat.open');
  await vscode.commands.executeCommand('workbench.action.chat.newLocalChat');
  await vscode.commands.executeCommand('workbench.action.chat.open', { query: `/clickable-infographic ${subject.trim()}`, isPartialQuery: true, mode: AGENT });
}

module.exports = { pruneTelemetry, mapInfo, refreshMap, openMap, infographic };
