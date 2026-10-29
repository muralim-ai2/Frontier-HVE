'use strict';
/** List the project's asks, map an ask's folder and propose a name for a new ask, read-only and bounded. */
const fs = require('node:fs');
const path = require('node:path');
const { Reader, containedPath } = require('./file-access');
const { record, text, list } = require('./validate');
const { headline } = require('./activity');
const ASK = /^\d{8}-\d{4}-[a-z0-9][a-z0-9-]{0,40}$/;
const ASK_LIMIT = 200;
const TREE_LIMIT = 400;
const TREE_DEPTH = 6;
const HANDOFF_MS = 24 * 60 * 60 * 1000;
const FILLER = new Set(['a', 'an', 'the', 'and', 'or', 'for', 'to', 'of', 'in', 'on', 'with', 'that', 'this', 'it', 'is', 'are', 'be', 'we', 'i', 'me', 'my',
  'our', 'please', 'can', 'you', 'could', 'would', 'should', 'new', 'some', 'into', 'from', 'by', 'as', 'at', 'so', 'just', 'also']);
const VERBS = new Set(['build', 'create', 'make', 'add', 'implement', 'write', 'design', 'develop', 'set', 'setup', 'update', 'fix', 'improve', 'change',
  'help', 'need', 'want', 'let', 'lets']);

/** Return the UTC time encoded in an ask identifier, in milliseconds.
 * @param {string} id
 * @returns {number}
 */
function askTime(id) {
  if (!ASK.test(id)) throw new Error(`Invalid ask identifier: ${id}`);
  return Date.UTC(Number(id.slice(0, 4)), Number(id.slice(4, 6)) - 1, Number(id.slice(6, 8)), Number(id.slice(9, 11)), Number(id.slice(11, 13)));
}

/** Return the project's asks, newest first, each with its title, agent, current stage and whether it is the active ask.
 * @param {string} workspace
 * @returns {import('./types').AskSummary[]}
 */
function listAsks(workspace) {
  const reader = new Reader(workspace);
  const folder = path.join('.hve', 'asks');
  const absolute = containedPath(reader.root, folder);
  if (!fs.existsSync(absolute)) return [];
  const pointer = reader.json(path.join(folder, 'active.json'), true);
  const active = pointer === undefined ? null : text(record(pointer, 'Active ask pointer').active, 'Active ask');
  return fs.readdirSync(absolute, { withFileTypes: true }).filter(entry => entry.isDirectory() && ASK.test(entry.name)).map(entry => entry.name)
    .sort().reverse().slice(0, ASK_LIMIT).filter(name => fs.existsSync(path.join(absolute, name, 'contract.json'))).map(name => {
      const contract = record(reader.json(path.join(folder, name, 'contract.json')), `${name} contract`);
      if (contract.ask !== name) throw new Error(`${name}: the contract names a different ask.`);
      const stages = list(contract.stages, `${name} stages`).map(value => record(value, `${name} stage`));
      const current = stages.find(stage => stage.name === contract.current) || stages[0];
      return { id: name, title: headline(text(contract.request, `${name} request`)), created: text(contract.created, `${name} creation time`),
        agent: text(contract.agent, `${name} agent`), stage: current ? `${text(current.name, 'Stage name')}: ${text(current.status, 'Stage status')}` : null,
        active: name === active };
    }).sort((a, b) => Date.parse(b.created) - Date.parse(a.created) || b.id.localeCompare(a.id));
}

/** Return an ask's folder as a tree, folders first, bounded in depth and entries; links and special files are listed but never followed.
 * @param {string} workspace
 * @param {string} ask
 * @returns {import('./types').AskFiles}
 */
function askTree(workspace, ask) {
  if (!ASK.test(ask)) throw new Error(`Invalid ask identifier: ${ask}`);
  const root = fs.realpathSync(workspace);
  const folder = path.join('.hve', 'asks', ask);
  const absolute = containedPath(root, folder);
  if (!fs.existsSync(absolute) || !fs.statSync(absolute).isDirectory()) throw new Error(`No ask folder: ${folder}`);
  let count = 0;
  let truncated = false;
  /** @param {string} relative @param {number} depth @returns {import('./types').FileNode[]} */
  const walk = (relative, depth) => fs.readdirSync(containedPath(root, relative), { withFileTypes: true })
    .sort((a, b) => Number(b.isDirectory()) - Number(a.isDirectory()) || a.name.localeCompare(b.name)).flatMap(entry => {
      if (count >= TREE_LIMIT) { truncated = true; return []; }
      count += 1;
      const child = path.join(relative, entry.name);
      const stat = fs.lstatSync(path.join(root, child));
      const kind = stat.isSymbolicLink() ? 'other' : stat.isDirectory() ? 'folder' : stat.isFile() ? 'file' : 'other';
      if (kind === 'folder' && depth >= TREE_DEPTH) truncated = true;
      const children = kind === 'folder' && depth < TREE_DEPTH ? walk(child, depth + 1) : [];
      return [{ name: entry.name, path: child.split(path.sep).join('/'), kind, size: kind === 'folder' ? children.length : stat.size,
        modified: stat.mtime.toISOString(), children }];
    });
  const entries = walk(folder, 1);
  return { ask, path: folder.split(path.sep).join('/'), entries, count, truncated };
}

/** Return a short lowercase name for a new ask from its request: its first few meaningful words, at most 41 characters.
 * @param {string} request
 * @returns {string}
 */
function slugFor(request) {
  const words = request.toLowerCase().normalize('NFKD').replace(/[^a-z0-9\s-]/g, ' ').split(/[\s-]+/).filter(Boolean);
  let start = 0;
  while (start < words.length && (VERBS.has(words[start]) || FILLER.has(words[start]))) start += 1;
  let slug = '';
  for (const word of words.slice(start).filter(value => !FILLER.has(value)).slice(0, 4)) {
    const next = slug ? `${slug}-${word}` : word.slice(0, 41);
    if (next.length > 41) break;
    slug = next;
  }
  return slug || 'ask';
}

/** Return the request saved in the ask: the title as a heading, then the description.
 * @param {{title: string, description: string}} brief
 * @returns {string}
 */
function askRequest(brief) {
  return brief.description ? `# ${brief.title}\n\n${brief.description}` : `# ${brief.title}`;
}

/** Return the text the harness's scope check reads: the description first, where a creation verb and the subject usually are, then the title.
 * @param {{title: string, description: string}} brief
 * @returns {string}
 */
function scopeText(brief) {
  return brief.description ? `${brief.description}\n\n${brief.title}` : brief.title;
}

/** Return the short message filled into a chat for an ask; the user edits or sends it, Mission Control never sends it.
 * @param {'new' | 'follow-up' | 'resume'} kind A new ask, new work on an existing ask, or picking an ask up again.
 * @param {{id: string, title: string}} ask
 * @param {{title: string, description: string} | null} brief
 * @returns {string}
 */
function starterPrompt(kind, ask, brief) {
  const use = `If you are an agent that uses .hve or .harness folders, work in the ask .hve/asks/${ask.id}/ (request and plan attached) and keep its records in that same folder; `
    + 'do not create another. Otherwise ignore this if it does not apply.';
  if (kind === 'resume') return [`Continue: ${ask.title}`, use, 'Say where it stands, then ask me what next.'].join('\n');
  if (!brief) throw new Error('A new ask or a follow-up needs a title.');
  return [kind === 'new' ? brief.title : `${ask.title}, follow-up: ${brief.title}`, brief.description, use,
    'Ask me for references or constraints first, then confirm the scope.'].filter(Boolean).join('\n');
}

/** Return the report files of the latest evaluation runs under .hve/evaluations/, newest run first, bounded; links are skipped.
 * @param {string} workspace
 * @returns {string[]}
 */
function evaluationFiles(workspace) {
  const root = fs.realpathSync(workspace);
  const folder = containedPath(root, path.join('.hve', 'evaluations'));
  if (!fs.existsSync(folder)) return [];
  return fs.readdirSync(folder, { withFileTypes: true }).filter(entry => entry.isDirectory() && entry.name !== 'input')
    .map(entry => ({ name: entry.name, mtime: fs.statSync(path.join(folder, entry.name)).mtimeMs })).sort((a, b) => b.mtime - a.mtime).slice(0, 8)
    .flatMap(run => fs.readdirSync(path.join(folder, run.name), { withFileTypes: true }).filter(entry => entry.isFile() && /\.(md|json)$/i.test(entry.name))
      .slice(0, 6).map(entry => `.hve/evaluations/${run.name}/${entry.name}`));
}

/** Return the asks the project still lists whose contract.json is gone, because their files were deleted.
 * @param {string} workspace
 * @returns {string[]}
 */
function deletedAsks(workspace) {
  const reader = new Reader(workspace);
  const value = reader.json(path.join('.hve', 'project', 'project.json'), true);
  if (value === undefined) return [];
  return list(record(value, 'Project record').asks, 'Project asks').map(id => text(id, 'Project ask'))
    .filter(id => ASK.test(id) && !fs.existsSync(path.join(reader.root, '.hve', 'asks', id, 'contract.json')));
}

/** Return the brief carried over from another workspace when it was saved for this folder in the last day, or null.
 * @param {unknown} value
 * @param {string} folder This window's workspace folder.
 * @param {number} now
 * @returns {import('./types').Handoff | null}
 */
function handoffFrom(value, folder, now) {
  if (value === undefined || value === null) return null;
  const row = record(value, 'Carried-over ask');
  const title = text(row.title, 'Carried-over title').trim();
  const description = text(row.description, 'Carried-over description', true);
  const at = text(row.at, 'Carried-over time');
  if (title.length < 3 || title.length > 80 || description.length > 4000 || Number.isNaN(Date.parse(at))) throw new Error('Invalid carried-over ask.');
  /** @param {string} file @returns {string} */
  const same = file => process.platform === 'win32' ? path.resolve(file).toLowerCase() : path.resolve(file);
  if (same(text(row.folder, 'Carried-over folder')) !== same(folder) || now - Date.parse(at) > HANDOFF_MS) return null;
  return { title, description, from: text(row.from, 'Carried-over source'), at };
}

module.exports = { ASK, askTime, listAsks, askTree, slugFor, askRequest, scopeText, starterPrompt, evaluationFiles, deletedAsks, handoffFrom };
