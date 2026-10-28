'use strict';
/** Write a browser preview of Mission Control built read-only from a workspace and its chat transcripts, for visual checks. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { EXTENSION } = require('./helpers');
const { snapshot } = require('../../extension/ui/workspace-state');
const { activity } = require('../../extension/ui/activity');

const [workspace, transcripts, telemetry, at] = process.argv.slice(2);
if (!workspace || !transcripts) throw new Error('usage: node preview.js <workspace> <transcripts folder> [telemetry export or -] [ISO time to show]');
const now = at ? Date.parse(at) : Date.now();
const file = telemetry && telemetry !== '-' ? telemetry : null;
const manifest = JSON.parse(fs.readFileSync(path.join(EXTENSION, 'package.json'), 'utf8'));
/** @type {import('../../extension/ui/types').Model} */
const model = { now: new Date(now).toISOString(), surface: 'sidebar', busy: false, error: null, workspace: { name: path.basename(workspace), path: workspace },
  workspaceMessage: null, connection: { version: manifest.version, python: 'python', guard: 'advise' }, telemetry: { enabled: !!file, file }, transcripts,
  snapshot: snapshot(workspace), snapshotError: null, activity: activity(workspace, transcripts, file, now), activityError: null, packs: [], packsError: null,
  navigate: { page: 'live', seq: 0 } };
const out = fs.mkdtempSync(path.join(os.tmpdir(), 'hve-preview-'));
const media = name => pathToFileURL(path.join(EXTENSION, 'ui', 'media', name)).href;
fs.writeFileSync(path.join(out, 'model.js'), `window.previewModel = ${JSON.stringify(model)};\nwindow.previewNow = ${now};\n`);
fs.writeFileSync(path.join(out, 'bridge.js'), `const params = new URLSearchParams(location.search);
const theme = 'vscode-' + (params.get('theme') || 'dark');
document.documentElement.className = theme;
document.body.className = theme;
const started = performance.now();
Date.now = () => window.previewNow + (performance.now() - started);
window.previewActions = [];
window.acquireVsCodeApi = () => ({
  postMessage(message) {
    window.previewActions.push(message);
    if (message.action !== 'ready') return;
    const surface = params.get('surface') || 'sidebar';
    setTimeout(() => window.postMessage({ type: 'model', model: { ...window.previewModel, surface, navigate: { page: params.get('page') || 'live', seq: 1 } } }, '*'));
  },
  getState() { return undefined; },
  setState() {},
});
`);
fs.writeFileSync(path.join(out, 'index.html'), `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Mission Control preview</title>
<link rel="stylesheet" href="${media('app.css')}"><link rel="stylesheet" href="${pathToFileURL(path.join(__dirname, 'preview-theme.css')).href}"></head>
<body><div id="root"></div><div id="announce" class="sr-only" role="status" aria-live="polite"></div>
<script src="model.js"></script><script src="bridge.js"></script>
${['vnode.js', 'markdown.js', 'views.js', 'pages.js', 'app.js'].map(name => `<script src="${media(name)}"></script>`).join('\n')}</body></html>`);
console.log(pathToFileURL(path.join(out, 'index.html')).href);
