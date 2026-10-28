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
    });
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

module.exports = { ASK, askTime, listAsks, askTree, slugFor };
