'use strict';
/** Index this window's Copilot Chat sessions incrementally and link each one to the asks it created, reopened, edited or was opened for. */
const fs = require('node:fs');
const path = require('node:path');
const { record, text } = require('./validate');
const { describe, headline, status } = require('./activity');
const { ASK, askTime } = require('./asks');
const CHAT_LIMIT = 30;
const CHUNK_BYTES = 4 * 1024 * 1024;
const CREATED_WITHIN_MS = 15 * 60 * 1000;
const PENDING_MS = 60 * 60 * 1000;
const SESSION = /^[\w-]+$/;
const CONTRACT = /\bcontract\s+["']?[\w.-]+["']?\s+["']?([a-z0-9][a-z0-9-]{0,40})(?=["'\s;|]|$)/g;
const OPEN = /\bopen\s+["']?(\d{8}-\d{4}-[a-z0-9][a-z0-9-]{0,40})(?=["'\s;|]|$)/g;
const ASK_PATH = /(?:^|[\\/])\.hve[\\/]asks[\\/](\d{8}-\d{4}-[a-z0-9][a-z0-9-]{0,40})[\\/]/;
const HOW = ['started', 'linked'];

/** @typedef {{offset: number, size: number, mtime: number, lines: number, id: string, title: string | null, started: string, lastAt: string,
 *   turnOpen: boolean, running: Map<string, string>, contracts: {slug: string, at: number}[], opened: Set<string>, edited: Set<string>}} Scan */
/** @type {Map<string, Scan>} */
const scans = new Map();

/** Apply one transcript event to a chat's scan.
 * @param {Scan} s
 * @param {Record<string, unknown>} row
 * @param {string} workspace
 * @returns {void}
 */
function apply(s, row, workspace) {
  const type = text(row.type, 'Transcript event type');
  const at = text(row.timestamp, `${type} timestamp`);
  const data = record(row.data, `${type} data`);
  s.started ||= at;
  s.lastAt = at;
  if (type === 'session.start') s.started = text(data.startTime, 'Session start time');
  else if (type === 'user.message') {
    s.running.clear();
    const content = text(data.content, 'Your message', true);
    if (content.trim()) s.title ||= headline(content);
  } else if (type === 'assistant.turn_start') s.turnOpen = true;
  else if (type === 'assistant.turn_end') s.turnOpen = false;
  else if (type === 'assistant.message') s.running.clear();
  else if (type === 'tool.execution_start') {
    const tool = text(data.toolName, 'Tool name');
    const args = data.arguments === undefined ? {} : record(data.arguments, `${tool} arguments`);
    s.running.set(text(data.toolCallId, 'Tool call id'), tool);
    const command = tool === 'run_in_terminal' && typeof args.command === 'string' ? args.command : '';
    if (/lifecycle\.py/.test(command)) {
      for (const match of command.matchAll(CONTRACT)) s.contracts.push({ slug: match[1], at: Date.parse(at) });
      for (const match of command.matchAll(OPEN)) s.opened.add(match[1]);
    }
    const event = describe(tool, args, workspace, at);
    if (event.kind === 'edit') for (const file of event.files) {
      const match = ASK_PATH.exec(file);
      if (match) s.edited.add(match[1]);
    }
  } else if (type === 'tool.execution_complete') s.running.delete(text(data.toolCallId, 'Tool call id'));
}

/** Return a transcript's scan, reading only the complete lines added since the last call.
 * @param {string} file
 * @param {string} workspace
 * @returns {Scan}
 */
function scan(file, workspace) {
  const id = path.basename(file, '.jsonl');
  if (!SESSION.test(id)) throw new Error(`Unexpected chat session file name: ${path.basename(file)}`);
  const stat = fs.statSync(file);
  let s = scans.get(file);
  if (!s || stat.size < s.offset) {
    s = { offset: 0, size: -1, mtime: 0, lines: 0, id, title: null, started: '', lastAt: '', turnOpen: false, running: new Map(), contracts: [],
      opened: new Set(), edited: new Set() };
    scans.set(file, s);
  }
  if (s.size === stat.size && s.mtime === stat.mtimeMs) return s;
  const handle = fs.openSync(file, 'r');
  try {
    while (s.offset < stat.size) {
      const buffer = Buffer.alloc(Math.min(CHUNK_BYTES, stat.size - s.offset));
      const read = fs.readSync(handle, buffer, 0, buffer.length, s.offset);
      const end = buffer.subarray(0, read).lastIndexOf(0x0a);
      if (end < 0) {
        if (read === CHUNK_BYTES) throw new Error(`Line ${s.lines + 1} of ${path.basename(file)} is longer than 4 MB.`);
        break;
      }
      for (const line of buffer.toString('utf8', 0, end).split('\n')) {
        s.lines += 1;
        if (!line.trim()) continue;
        try {
          apply(s, record(JSON.parse(line), `${path.basename(file)} line ${s.lines}`), workspace);
        } catch (error) {
          scans.delete(file);
          throw new Error(`Invalid chat event on line ${s.lines} of ${path.basename(file)}`, { cause: error });
        }
      }
      s.offset += end + 1;
    }
  } finally {
    fs.closeSync(handle);
  }
  s.size = stat.size;
  s.mtime = stat.mtimeMs;
  return s;
}

/** Return the asks a chat works on: the one it was opened for, then those it created, reopened or edited files in.
 * @param {Scan} s
 * @param {string[]} asks
 * @param {import('./types').Claim | null} claim
 * @returns {import('./types').ChatLink[]}
 */
function links(s, asks, claim) {
  /** @type {Map<string, import('./types').ChatLink['how']>} */
  const found = new Map();
  if (claim && asks.includes(claim.ask)) found.set(claim.ask, claim.how);
  for (const { slug, at } of s.contracts) {
    const minute = Math.floor(at / 60000) * 60000;
    const made = asks.filter(id => id.slice(14) === slug && askTime(id) >= minute - 60000 && askTime(id) <= at + CREATED_WITHIN_MS)
      .sort((a, b) => askTime(a) - askTime(b))[0];
    if (made && !found.has(made)) found.set(made, 'created');
  }
  for (const id of s.opened) if (asks.includes(id) && !found.has(id)) found.set(id, 'opened');
  for (const id of s.edited) if (asks.includes(id) && !found.has(id)) found.set(id, 'edited');
  return [...found].map(([ask, how]) => ({ ask, how }));
}

/** Return the recent chats of this window, newest first, with the asks each works on; a chat started after a pending new chat is claimed for its ask.
 * @param {string | null} transcripts
 * @param {string} workspace
 * @param {string[]} asks
 * @param {Record<string, import('./types').Claim>} claims
 * @param {import('./types').Pending | null} pending
 * @param {number} now
 * @returns {{chats: import('./types').Chat[], claimed: {chat: string, ask: string} | null}}
 */
function chatList(transcripts, workspace, asks, claims, pending, now) {
  if (!transcripts || !fs.existsSync(transcripts)) return { chats: [], claimed: null };
  const scanned = fs.readdirSync(transcripts).filter(name => name.endsWith('.jsonl')).map(name => path.join(transcripts, name))
    .map(file => ({ file, mtime: fs.statSync(file).mtimeMs })).sort((a, b) => b.mtime - a.mtime).slice(0, CHAT_LIMIT)
    .map(({ file }) => scan(file, workspace)).filter(s => s.lastAt);
  const fresh = pending ? scanned.filter(s => !Object.hasOwn(claims, s.id) && Date.parse(s.started) >= Date.parse(pending.at) - 5000)
    .sort((a, b) => a.started.localeCompare(b.started))[0] : undefined;
  const claimed = pending && fresh ? { chat: fresh.id, ask: pending.ask } : null;
  const chats = scanned.map(s => ({ id: s.id, title: s.title, started: s.started, lastAt: s.lastAt,
    status: status([...s.running.values()].at(-1) || null, s.turnOpen, s.lastAt, now),
    asks: links(s, asks, claimed?.chat === s.id ? { ask: claimed.ask, how: 'started' } : claims[s.id] || null) }));
  return { chats: chats.sort((a, b) => b.lastAt.localeCompare(a.lastAt)), claimed };
}

/** Return the chat to show for an ask: the one chosen if it works on the ask, else its latest; with no ask, the latest chat.
 * @param {import('./types').Chat[]} chats
 * @param {string | null} ask
 * @param {string | null} chosen
 * @returns {import('./types').Chat | null}
 */
function shownChat(chats, ask, chosen) {
  const mine = ask === null ? chats : chats.filter(chat => chat.asks.some(link => link.ask === ask));
  return mine.find(chat => chat.id === chosen) || mine[0] || null;
}

/** Validate the saved chat-to-ask links.
 * @param {unknown} value
 * @returns {Record<string, import('./types').Claim>}
 */
function claimsFrom(value) {
  if (value === undefined) return {};
  return Object.fromEntries(Object.entries(record(value, 'Saved chat links')).map(([chat, row]) => {
    const claim = record(row, 'Saved chat link');
    const ask = text(claim.ask, 'Linked ask');
    const how = text(claim.how, 'Link kind');
    if (!SESSION.test(chat) || !ASK.test(ask) || !HOW.includes(how)) throw new Error(`Invalid saved chat link: ${chat}`);
    return [chat, { ask, how: /** @type {import('./types').Claim['how']} */ (how) }];
  }));
}

/** Validate the saved new-chat request; it lapses an hour after it was made.
 * @param {unknown} value
 * @param {number} now
 * @returns {import('./types').Pending | null}
 */
function pendingFrom(value, now) {
  if (value === undefined || value === null) return null;
  const row = record(value, 'Saved new chat');
  const ask = text(row.ask, 'New chat ask');
  const at = text(row.at, 'New chat time');
  if (!ASK.test(ask) || Number.isNaN(Date.parse(at))) throw new Error('Invalid saved new chat.');
  return now - Date.parse(at) < PENDING_MS ? { ask, at } : null;
}

module.exports = { SESSION, chatList, shownChat, claimsFrom, pendingFrom };
