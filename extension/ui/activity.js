'use strict';
/** Read one chat's live agent activity: its Copilot Chat transcript, its harness run files, and research telemetry. */
const fs = require('node:fs');
const path = require('node:path');
const { Reader, containedPath } = require('./file-access');
const { record, text, list, flag, integer } = require('./validate');
const TAIL_BYTES = 8 * 1024 * 1024;
const TELEMETRY_TAIL_BYTES = 4 * 1024 * 1024;
const IDLE_AFTER_MS = 10 * 60 * 1000;
const EVENT_LIMIT = 80;
const SESSION = /^[\w-]+$/;
const ASK_TOOLS = new Set(['vscode_askQuestions', 'ask_user']);
const TODO_STATES = ['not-started', 'in-progress', 'completed'];
/** @type {Map<string, {size: number, mtime: number, parsed: Parsed}>} */
const cache = new Map();

/** @typedef {import('./types').ActivityEvent} ActivityEvent */
/** @typedef {{id: string, title: string | null, started: string, lastAt: string, turnOpen: boolean, open: {event: ActivityEvent, tool: string} | null,
 *   turns: number, tools: number, failures: number, commands: number, todos: import('./types').Todo[], events: ActivityEvent[],
 *   files: Map<string, {count: number, last: string}>}} Parsed */

/** Return the end of a file, starting at a line boundary when it was cut.
 * @param {string} file
 * @param {number} limit
 * @returns {string}
 */
function tail(file, limit) {
  const size = fs.statSync(file).size;
  const start = Math.max(0, size - limit);
  const handle = fs.openSync(file, 'r');
  try {
    const buffer = Buffer.alloc(size - start);
    fs.readSync(handle, buffer, 0, buffer.length, start);
    const content = buffer.toString('utf8');
    return start === 0 ? content : content.slice(content.indexOf('\n') + 1);
  } finally {
    fs.closeSync(handle);
  }
}

/** Parse newline-terminated JSON lines; an unterminated last line is still being written and is read complete next time.
 * @param {string} content
 * @param {string} source
 * @returns {Record<string, unknown>[]}
 */
function jsonLines(content, source) {
  const lines = content.split('\n');
  lines.pop();
  return lines.map((line, index) => ({ line: line.trim(), index })).filter(row => row.line).map(({ line, index }) => {
    try {
      return record(JSON.parse(line), `${source} line ${index + 1}`);
    } catch (error) {
      throw new Error(`Invalid JSON on line ${index + 1} of ${source}`, { cause: error });
    }
  });
}

/** Return text on one line, cut at a word boundary.
 * @param {string} value
 * @param {number} limit
 * @returns {string}
 */
function clip(value, limit) {
  const line = value.replace(/\s+/g, ' ').trim();
  if (line.length <= limit) return line;
  const cut = line.slice(0, limit - 1);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(' '), limit * 0.6))}…`;
}

/** Return the first meaningful line of a message as a short headline, cut at a natural break when long.
 * @param {string} value
 * @returns {string}
 */
function headline(value) {
  const line = value.split(/\r?\n/).map(row => row.replace(/^#+\s*/, '').replace(/[*_`]/g, '').trim()).find(Boolean) || '';
  if (line.length <= 80) return line;
  const cut = /^(.{30,80}?)(?:\s\(|:\s|;\s|\s[-—–]\s|\.\s)/.exec(line);
  return cut ? cut[1] : clip(line, 80);
}

/** Return a path relative to the workspace with forward slashes, or null when it lies outside.
 * @param {string} file
 * @param {string} workspace
 * @returns {string | null}
 */
function inside(file, workspace) {
  const relative = path.relative(workspace, path.resolve(workspace, file));
  return !relative || relative.startsWith('..') || path.isAbsolute(relative) ? null : relative.split(path.sep).join('/');
}

/** Return a short display name for a file: workspace-relative, or its folder and name.
 * @param {string} file
 * @param {string} workspace
 * @returns {string}
 */
function shown(file, workspace) {
  return inside(file, workspace) || path.join(path.basename(path.dirname(file)), path.basename(file)).split(path.sep).join('/');
}

/** Return a command on one line with harness script paths shortened to the script name.
 * @param {string} value
 * @returns {string}
 */
function shortCommand(value) {
  return value.replace(/(["']?)[^"'\s]*[\\/](?:runtime[\\/])?(?:tools|hooks)[\\/](?:[\w-]+[\\/])*([\w-]+\.py)\1/g, '$2').replace(/\s+/g, ' ').trim();
}

/** Return a string argument or null.
 * @param {Record<string, unknown>} args
 * @param {string} key
 * @returns {string | null}
 */
function arg(args, key) {
  return typeof args[key] === 'string' && args[key] ? /** @type {string} */ (args[key]) : null;
}

/** Return the files an editing tool call names.
 * @param {string} tool
 * @param {Record<string, unknown>} args
 * @returns {string[]}
 */
function editedFiles(tool, args) {
  if (tool === 'multi_replace_string_in_file') {
    return [...new Set(list(args.replacements, 'Replacements').map(row => text(record(row, 'Replacement').filePath, 'Replacement file')))];
  }
  if (tool === 'apply_patch') return [...text(args.input, 'Patch').matchAll(/^\*\*\* (?:Add|Update|Delete) File: (.+)$/gm)].map(match => match[1].trim());
  const file = arg(args, 'filePath');
  return file ? [file] : [];
}

/** Describe one tool call in plain words.
 * @param {string} tool
 * @param {Record<string, unknown>} args
 * @param {string} workspace
 * @param {string} at
 * @returns {ActivityEvent}
 */
function describe(tool, args, workspace, at) {
  /** @type {(kind: ActivityEvent['kind'], title: string, detail?: string, files?: string[]) => ActivityEvent} */
  const event = (kind, title, detail = '', files = []) => ({ at, kind, title, detail, files, state: 'running' });
  const file = arg(args, 'filePath');
  switch (tool) {
    case 'read_file': case 'view_image': return event('read', file ? `Read ${shown(file, workspace)}` : 'Read a file');
    case 'create_file': return event('edit', file ? `Created ${shown(file, workspace)}` : 'Created a file', '', file ? [file] : []);
    case 'replace_string_in_file': case 'insert_edit_into_file': case 'edit_notebook_file': case 'multi_replace_string_in_file': case 'apply_patch': {
      const files = editedFiles(tool, args);
      return event('edit', files.length === 1 ? `Edited ${shown(files[0], workspace)}` : `Edited ${files.length} files`,
        files.length > 1 ? files.map(name => shown(name, workspace)).join(', ') : arg(args, 'explanation') || '', files);
    }
    case 'create_directory': return event('edit', `Created folder ${shown(arg(args, 'dirPath') || '.', workspace)}`);
    case 'run_in_terminal': {
      const command = shortCommand(arg(args, 'command') || '');
      const explanation = arg(args, 'explanation');
      return event('run', explanation ? clip(explanation.replace(/\.$/, ''), 90) : command ? `Ran ${clip(command, 90)}` : 'Ran a command', clip(command, 200));
    }
    case 'get_terminal_output': return event('run', 'Checked terminal output');
    case 'list_dir': return event('read', `Listed ${shown(arg(args, 'path') || '.', workspace)}`);
    case 'grep_search': case 'file_search': case 'semantic_search': return event('search', `Searched for “${clip(arg(args, 'query') || '', 60)}”`);
    case 'manage_todo_list': return event('todo', 'Updated its to-do list');
    case 'vscode_askQuestions': case 'ask_user': {
      const questions = Array.isArray(args.questions) ? args.questions.map(row => record(row, 'Question')) : [];
      return event('ask', `Asked you ${questions.length || 'a'} question${questions.length === 1 ? '' : 's'}`,
        questions.map(row => arg(row, 'header') || arg(row, 'question') || '').filter(Boolean).join(' · '));
    }
    case 'runSubagent': return event('delegate', `Handed off to ${arg(args, 'agentName') || 'a sub-agent'}`, arg(args, 'description') || '');
    case 'execution_subagent': case 'search_subagent': case 'explore_subagent': return event('delegate', 'Started a helper agent', arg(args, 'description') || '');
    case 'fetch_webpage': return event('search', 'Fetched a web page', Array.isArray(args.urls) ? args.urls.join(', ') : '');
    case 'get_errors': return event('read', 'Checked problems');
    case 'task_complete': return event('message', 'Marked the task complete');
    default: return event('tool', `Used ${tool.replace(/^mcp_/, '').replace(/[_-]+/g, ' ')}`);
  }
}

/** Return the agent's to-do list from a manage_todo_list call.
 * @param {Record<string, unknown>} args
 * @returns {import('./types').Todo[]}
 */
function todoList(args) {
  return list(args.todoList, 'To-do list').map(value => {
    const row = record(value, 'To-do item');
    const status = text(row.status, 'To-do status');
    if (!TODO_STATES.includes(status)) throw new Error(`Unknown to-do status: ${status}`);
    return { title: text(row.title, 'To-do title'), status: /** @type {import('./types').Todo['status']} */ (status) };
  });
}

/** Mark tool calls that never reported a result as stopped once the conversation moved on: the agent answered or you wrote again.
 * @param {Map<string, {event: ActivityEvent, tool: string}>} running
 * @returns {void}
 */
function settle(running) {
  for (const call of running.values()) call.event.state = 'stopped';
  running.clear();
}

/** Parse one transcript into its session facts.
 * @param {string} file
 * @param {string} workspace
 * @returns {Parsed}
 */
function parse(file, workspace) {
  const id = path.basename(file, '.jsonl');
  if (!SESSION.test(id)) throw new Error(`Unexpected chat session file name: ${path.basename(file)}`);
  /** @type {Parsed} */
  const s = { id, title: null, started: '', lastAt: '', turnOpen: false, open: null, turns: 0, tools: 0, failures: 0, commands: 0, todos: [],
    events: [], files: new Map() };
  /** @type {Map<string, {event: ActivityEvent, tool: string}>} */
  const running = new Map();
  for (const row of jsonLines(tail(file, TAIL_BYTES), path.basename(file))) {
    const type = text(row.type, 'Transcript event type');
    const at = text(row.timestamp, `${type} timestamp`);
    const data = record(row.data, `${type} data`);
    s.started ||= at;
    s.lastAt = at;
    if (type === 'session.start') s.started = text(data.startTime, 'Session start time');
    else if (type === 'user.message') {
      settle(running);
      const content = text(data.content, 'Your message', true);
      if (content.trim()) {
        s.title ||= headline(content);
        s.events.push({ at, kind: 'prompt', title: headline(content), detail: '', files: [], state: 'ok' });
      }
    } else if (type === 'assistant.turn_start') { s.turnOpen = true; s.turns += 1; }
    else if (type === 'assistant.turn_end') s.turnOpen = false;
    else if (type === 'assistant.message') {
      settle(running);
      const content = text(data.content, 'Agent message', true);
      if (content.trim()) s.events.push({ at, kind: 'message', title: clip(content, 160), detail: '', files: [], state: 'ok' });
    } else if (type === 'tool.execution_start') {
      const tool = text(data.toolName, 'Tool name');
      const args = data.arguments === undefined ? {} : record(data.arguments, `${tool} arguments`);
      const event = describe(tool, args, workspace, at);
      s.tools += 1;
      if (tool === 'run_in_terminal') s.commands += 1;
      if (tool === 'manage_todo_list') s.todos = todoList(args);
      for (const name of event.files) {
        const relative = inside(name, workspace);
        if (relative) s.files.set(relative, { count: (s.files.get(relative)?.count || 0) + 1, last: at });
      }
      s.events.push(event);
      running.set(text(data.toolCallId, 'Tool call id'), { event, tool });
    } else if (type === 'tool.execution_complete') {
      const call = running.get(text(data.toolCallId, 'Tool call id'));
      if (call) {
        running.delete(text(data.toolCallId, 'Tool call id'));
        call.event.state = data.success === false ? 'failed' : 'ok';
        if (call.event.state === 'failed') s.failures += 1;
      }
    }
  }
  s.open = [...running.values()].at(-1) || null;
  return s;
}

/** Return a transcript's parsed facts, reparsing only when the file changed.
 * @param {string} file
 * @param {string} workspace
 * @returns {Parsed}
 */
function parsed(file, workspace) {
  const stat = fs.statSync(file);
  const hit = cache.get(file);
  if (hit && hit.size === stat.size && hit.mtime === stat.mtimeMs) return hit.parsed;
  const result = parse(file, workspace);
  cache.set(file, { size: stat.size, mtime: stat.mtimeMs, parsed: result });
  return result;
}

/** Return a chat's state: waiting for your answer, working, or idle after ten quiet minutes.
 * @param {string | null} openTool The tool still running, if any.
 * @param {boolean} turnOpen
 * @param {string} lastAt
 * @param {number} now
 * @returns {import('./types').Session['status']}
 */
function status(openTool, turnOpen, lastAt, now) {
  const quiet = now - Date.parse(lastAt) > IDLE_AFTER_MS;
  return openTool && ASK_TOOLS.has(openTool) ? 'waiting' : !quiet && (openTool || turnOpen) ? 'working' : 'idle';
}

/** Return the session as shown: working, waiting for you, or idle after ten quiet minutes.
 * @param {Parsed} s
 * @param {number} now
 * @returns {import('./types').Session}
 */
function session(s, now) {
  const state = status(s.open?.tool || null, s.turnOpen, s.lastAt, now);
  const events = s.events.slice(-EVENT_LIMIT).reverse().map(event => ({ ...event, state: event.state === 'running' && state === 'idle' ? 'stopped' : event.state }));
  return { id: s.id, title: s.title, started: s.started, lastAt: s.lastAt, status: state, current: state === 'idle' ? null : s.open?.event || null,
    turns: s.turns, tools: s.tools, failures: s.failures, commands: s.commands, todos: s.todos, events,
    files: [...s.files].map(([file, row]) => ({ path: file, ...row })).sort((a, b) => b.last.localeCompare(a.last)) };
}

/** Read the session's harness run files: the error guard, the skill load and guard alerts.
 * @param {string} workspace
 * @param {string} id
 * @returns {Pick<import('./types').Activity, 'errors' | 'loadout'> & {guards: ActivityEvent[]}}
 */
function runFiles(workspace, id) {
  const reader = new Reader(workspace);
  const runs = path.join('.hve', 'runs');
  const errorsValue = reader.json(path.join(runs, `${id}.errors.json`), true);
  const errors = errorsValue === undefined ? null : (() => {
    const value = record(errorsValue, 'Error guard state');
    return { paused: flag(value.paused, 'Error guard paused'), failures: list(value.failures, 'Error guard failures').map(row => {
      const failure = record(row, 'Failed command');
      return { command: shortCommand(text(failure.command, 'Failed command')), output: text(failure.output, 'Failed command output', true) };
    }) };
  })();
  const loadValue = reader.json(path.join(runs, `${id}.skills.json`), true);
  const loadout = loadValue === undefined ? null : (() => {
    const value = record(loadValue, 'Skill load');
    const budget = record(value.budget, 'Skill budget');
    return { skills: list(value.skills, 'Loaded skills').length, tokens: integer(value.tokens, 'Skill tokens'), overBudget: flag(value.over_budget, 'Over budget'),
      maxSkills: integer(budget.max_skills, 'Skill limit'), maxTokens: integer(budget.max_tokens, 'Token guideline') };
  })();
  const alerts = reader.text(path.join(runs, `${id}.interventions.jsonl`), true);
  const guards = alerts === undefined ? [] : jsonLines(alerts, `${id}.interventions.jsonl`).map(row => /** @type {ActivityEvent} */ ({
    at: new Date(/** @type {number} */ (row.ts_ms)).toISOString(), kind: 'guard', title: `Guard: ${text(row.hook, 'Guard hook').replace(/\.py$/, '').replace(/_/g, ' ')} ${text(row.kind, 'Guard action')}`,
    detail: clip(text(row.detail, 'Guard detail', true), 240), files: [], state: 'ok' }));
  return { errors, loadout, guards };
}

/** Sum research telemetry model calls of one chat session.
 * @param {string} workspace
 * @param {string} file
 * @param {string} id
 * @returns {import('./types').Activity['tokens']}
 */
function usage(workspace, file, id) {
  const relative = inside(file, workspace);
  if (!relative || !fs.existsSync(containedPath(workspace, relative))) return null;
  /** @type {Map<string, import('./types').TokenUse>} */
  const models = new Map();
  let nano = 0;
  for (const row of jsonLines(tail(path.resolve(workspace, file), TELEMETRY_TAIL_BYTES), relative)) {
    if (typeof row.name !== 'string' || !row.name.startsWith('chat ')) continue;
    const attrs = record(row.attributes, 'Telemetry span attributes');
    const owners = [attrs['gen_ai.conversation.id'], attrs['copilot_chat.chat_session_id'], attrs['copilot_chat.parent_chat_session_id']];
    if (!owners.includes(id)) continue;
    const model = text(attrs['gen_ai.response.model'] ?? attrs['gen_ai.request.model'], 'Telemetry model');
    const use = models.get(model) || { model, calls: 0, failed: 0, input: 0, output: 0, cached: 0 };
    use.calls += 1;
    models.set(model, use);
    if (attrs['gen_ai.usage.input_tokens'] === undefined && record(row.status, 'Telemetry span status').code === 2) {
      use.failed += 1;
      continue;
    }
    use.input += integer(attrs['gen_ai.usage.input_tokens'], 'Input tokens');
    use.output += integer(attrs['gen_ai.usage.output_tokens'], 'Output tokens');
    use.cached += attrs['gen_ai.usage.cache_read.input_tokens'] === undefined ? 0 : integer(attrs['gen_ai.usage.cache_read.input_tokens'], 'Cached tokens');
    nano += attrs['copilot_chat.copilot_usage_nano_aiu'] === undefined ? 0 : integer(attrs['copilot_chat.copilot_usage_nano_aiu'], 'AI units');
  }
  return models.size ? { models: [...models.values()].sort((a, b) => b.input - a.input), aiu: nano / 1e9 } : null;
}

/** Return the live activity of one chat session, or nothing when no chat is shown.
 * @param {string} workspace
 * @param {string | null} file The chat's transcript, or null when no chat is shown.
 * @param {string | null} telemetryFile The research telemetry export, or null when it was never configured.
 * @param {number} now
 * @returns {Omit<import('./types').Activity, 'chats'>}
 */
function activity(workspace, file, telemetryFile, now) {
  if (!file) return { session: null, errors: null, loadout: null, tokens: null };
  const current = session(parsed(file, workspace), now);
  const run = runFiles(workspace, current.id);
  current.events = [...current.events, ...run.guards].sort((a, b) => b.at.localeCompare(a.at)).slice(0, EVENT_LIMIT);
  return { session: current, errors: run.errors, loadout: run.loadout, tokens: telemetryFile ? usage(workspace, telemetryFile, current.id) : null };
}

module.exports = { activity, describe, status, headline, clip, jsonLines };
