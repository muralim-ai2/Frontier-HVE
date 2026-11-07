'use strict';
/** Build one chat's agent trajectory: its research telemetry OTel spans as a tree, or its transcript steps when telemetry is off. */
const fs = require('node:fs');
const path = require('node:path');
const { containedPath } = require('./file-access');
const { jsonLines, tail, inside, TELEMETRY_TAIL_BYTES } = require('./activity');
const { record } = require('./validate');
const MAX_EVENTS = 1000;
const CONTENT_CHARS = 1500;
const ATTRIBUTE_CHARS = 240;
const STATUS_ERROR = 2;
/** @type {Record<string, [string, 'input' | 'output']>} */
const CONTENT = { 'gen_ai.tool.call.arguments': ['Tool arguments', 'input'], 'gen_ai.input.messages': ['Input messages', 'input'],
  'gen_ai.tool.call.result': ['Tool result', 'output'], 'gen_ai.output.messages': ['Output messages', 'output'] };
const OMITTED = new Set(['gen_ai.system_instructions', 'gen_ai.tool.definitions']);
const SECRETS = [/\b(ghp_[A-Za-z0-9]{36}|github_pat_\w{40,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,})/g,
  /(Bearer\s+)[\w.~+/-]{16,}=*/gi, /((?:api[_-]?key|secret|password|passwd|token|authorization)["']?\s*[:=]\s*["']?)(?=[^"'\s,}]*[A-Za-z])[^"'\s,}]{8,}/gi];
/** @type {Record<import('./types').ActivityEvent['kind'], import('./types').TrajectoryKind>} */
const TRANSCRIPT_KIND = { prompt: 'user', message: 'response', delegate: 'handoff', guard: 'guard', ask: 'user', read: 'tool', edit: 'tool', run: 'tool',
  search: 'tool', todo: 'tool', tool: 'tool' };
/** @type {Map<string, {size: number, mtime: number, value: import('./types').Trajectory | null}>} */
const cache = new Map();

/** @typedef {import('./types').TrajectoryEvent} TrajectoryEvent */

/** Return epoch milliseconds for an OTel [seconds, nanoseconds] time.
 * @param {unknown} value
 * @returns {number}
 */
function millis(value) {
  if (!Array.isArray(value) || typeof value[0] !== 'number' || typeof value[1] !== 'number') throw new Error('Telemetry span time: expected [seconds, nanoseconds].');
  return value[0] * 1000 + value[1] / 1e6;
}

/** Return text with token-like secrets replaced, and whether anything was replaced.
 * @param {string} value
 * @returns {{text: string, redacted: boolean}}
 */
function redact(value) {
  let text = value;
  for (const pattern of SECRETS) text = text.replace(pattern, (_match, keep) => (pattern === SECRETS[0] ? '' : keep) + '[redacted]');
  return { text, redacted: text !== value };
}

/** Return an attribute value as text.
 * @param {unknown} value
 * @returns {string}
 */
function shown(value) {
  return typeof value === 'string' ? value : JSON.stringify(value) ?? String(value);
}

/** Return a number attribute or zero.
 * @param {Record<string, unknown>} attrs
 * @param {string[]} keys
 * @returns {number}
 */
function number(attrs, keys) {
  const value = keys.map(key => attrs[key]).find(item => typeof item === 'number');
  return typeof value === 'number' ? value : 0;
}

/** Return a string attribute or null.
 * @param {Record<string, unknown>} attrs
 * @param {string[]} keys
 * @returns {string | null}
 */
function word(attrs, keys) {
  const value = keys.map(key => attrs[key]).find(item => typeof item === 'string' && item);
  return typeof value === 'string' ? value : null;
}

/** Return the status of a span from its end and OTel status.
 * @param {Record<string, unknown>} span
 * @returns {{status: import('./types').TrajectoryStatus, message: string | null}}
 */
function spanStatus(span) {
  const status = record(span.status, 'Telemetry span status');
  const message = typeof status.message === 'string' && status.message ? status.message : null;
  if (span.ended !== true) return { status: 'running', message };
  if (status.code !== STATUS_ERROR) return { status: 'ok', message };
  return { status: /cancel/i.test(message || '') ? 'cancelled' : /time(d)?[\s_-]?out/i.test(message || '') ? 'timeout' : 'failed', message };
}

/** Return one normalized event from an OTel span record.
 * @param {Record<string, unknown>} span
 * @param {string} chat
 * @returns {TrajectoryEvent}
 */
function fromSpan(span, chat) {
  const attrs = record(span.attributes, 'Telemetry span attributes');
  const name = typeof span.name === 'string' ? span.name : 'span';
  const operation = word(attrs, ['gen_ai.operation.name']) || name.split(' ')[0];
  const session = word(attrs, ['copilot_chat.chat_session_id', 'gen_ai.conversation.id']);
  const kind = operation === 'chat' ? 'model' : operation === 'execute_tool' ? 'tool' : /hook/i.test(operation) ? 'guard'
    : operation === 'invoke_agent' ? (session && session !== chat ? 'handoff' : 'agent') : 'other';
  const start = millis(span.startTime);
  const ended = span.ended === true;
  const end = ended ? millis(span.endTime) : null;
  const { status, message } = spanStatus(span);
  const parent = span.parentSpanContext ? record(span.parentSpanContext, 'Telemetry parent span') : null;
  /** @type {import('./types').TrajectoryContent[]} */
  const content = [];
  /** @type {[string, string][]} */
  const attributes = [];
  for (const [key, value] of Object.entries(attrs)) {
    const full = shown(value);
    if (OMITTED.has(key)) attributes.push([key, `omitted from the viewer (${full.length.toLocaleString('en-US')} characters)`]);
    else if (CONTENT[key]) {
      const safe = redact(full);
      content.push({ label: CONTENT[key][0], side: CONTENT[key][1], text: safe.text.slice(0, CONTENT_CHARS), chars: full.length,
        truncated: safe.text.length > CONTENT_CHARS, redacted: safe.redacted });
    } else {
      const safe = redact(full);
      attributes.push([key, safe.text.length > ATTRIBUTE_CHARS ? `${safe.text.slice(0, ATTRIBUTE_CHARS)}…` : safe.text]);
    }
  }
  const resource = span.resource ? record(record(span.resource, 'Telemetry resource').attributes, 'Telemetry resource attributes') : {};
  const tokens = kind === 'model' ? { input: number(attrs, ['gen_ai.usage.input_tokens']), output: number(attrs, ['gen_ai.usage.output_tokens']),
    cached: number(attrs, ['gen_ai.usage.cache_read.input_tokens']), reasoning: number(attrs, ['gen_ai.usage.reasoning_tokens', 'gen_ai.usage.reasoning.output_tokens']) } : null;
  return {
    id: String(span.spanId), seq: 0, traceId: typeof span.traceId === 'string' ? span.traceId : null, spanId: String(span.spanId),
    parentId: parent && typeof parent.spanId === 'string' ? parent.spanId : null, orphan: false, kind, rawType: name, depth: 0, children: [], retry: 0,
    name: kind === 'tool' ? word(attrs, ['gen_ai.tool.name']) || name : kind === 'model' ? 'Model call' : name.replace(/^invoke_agent\s*/, '') || name,
    agent: kind === 'agent' || kind === 'handoff' ? word(attrs, ['gen_ai.agent.name']) || name.replace(/^invoke_agent\s*/, '') || null : null,
    model: word(attrs, ['gen_ai.response.model', 'gen_ai.request.model']), tool: word(attrs, ['gen_ai.tool.name']),
    status, statusMessage: message ? redact(message).text : null, start, end, durationMs: end === null ? null : Math.max(0, end - start), session,
    tokens, content, attributes: attributes.sort((a, b) => a[0].localeCompare(b[0])),
    resource: Object.entries(resource).map(([key, value]) => /** @type {[string, string]} */ ([key, redact(shown(value)).text])),
    spanEvents: Array.isArray(span.events) ? span.events.map(item => record(item, 'Telemetry span event'))
      .map(item => ({ name: String(item.name), at: Array.isArray(item.time) ? millis(item.time) : start })) : [],
    links: Array.isArray(span.links) ? span.links.map(item => record(record(item, 'Telemetry span link').context, 'Telemetry link context'))
      .map(context => `${context.traceId}/${context.spanId}`) : [],
  };
}

/** Return the span records of a chat and of every span sharing its traces; the latest record of a span id wins, an ended one over a running one.
 * @param {Record<string, unknown>[]} rows
 * @param {string} chat
 * @returns {Record<string, unknown>[]}
 */
function chatSpans(rows, chat) {
  const spans = rows.filter(row => typeof row.spanId === 'string' && 'ended' in row && row.attributes);
  const owners = ['copilot_chat.chat_session_id', 'copilot_chat.parent_chat_session_id', 'gen_ai.conversation.id'];
  const traces = new Set(spans.filter(row => owners.some(key => record(row.attributes, 'Telemetry span attributes')[key] === chat)).map(row => row.traceId));
  /** @type {Map<string, Record<string, unknown>>} */
  const unique = new Map();
  for (const row of spans.filter(item => traces.has(item.traceId))) {
    const seen = unique.get(String(row.spanId));
    if (!seen || row.ended === true || seen.ended !== true) unique.set(String(row.spanId), row);
  }
  return [...unique.values()];
}

/** Link events into a tree ordered by start time, number them depth-first, and mark orphans and retries.
 * @param {TrajectoryEvent[]} events
 * @returns {{events: TrajectoryEvent[], roots: string[]}}
 */
function tree(events) {
  const byId = new Map(events.map(event => [event.id, event]));
  for (const event of events) {
    if (event.parentId && !byId.has(event.parentId)) event.orphan = true;
    let up = event.parentId ? byId.get(event.parentId) : undefined;
    for (let hops = 0; up && hops <= events.length; hops += 1) up = up.parentId ? byId.get(up.parentId) : undefined;
    if (up) event.orphan = true;
  }
  const byStart = /** @param {TrajectoryEvent} a @param {TrajectoryEvent} b */ (a, b) => a.start - b.start || a.id.localeCompare(b.id);
  const roots = events.filter(event => !event.parentId || event.orphan).sort(byStart);
  for (const event of events) if (!roots.includes(event)) /** @type {TrajectoryEvent} */ (byId.get(/** @type {string} */ (event.parentId))).children.push(event.id);
  /** @type {TrajectoryEvent[]} */
  const ordered = [];
  /** @param {TrajectoryEvent} event @param {number} depth */
  const visit = (event, depth) => {
    event.depth = depth;
    event.seq = ordered.push(event);
    const kids = event.children.map(id => /** @type {TrajectoryEvent} */ (byId.get(id))).sort(byStart);
    event.children = kids.map(kid => kid.id);
    kids.forEach((kid, index) => {
      const before = kids.slice(0, index).reverse().find(other => other.kind === kid.kind && other.name === kid.name);
      if (before && ['failed', 'timeout'].includes(before.status)) kid.retry = before.retry + 1;
      visit(kid, depth + 1);
    });
  };
  roots.forEach(root => visit(root, 0));
  return { events: ordered, roots: roots.map(root => root.id) };
}

/** Return the run summary of normalized events.
 * @param {TrajectoryEvent[]} all
 * @param {Pick<import('./types').Trajectory, 'source' | 'chat' | 'title' | 'truncated'>} base
 * @returns {import('./types').Trajectory}
 */
function summarize(all, base) {
  const { events, roots } = tree(all);
  const starts = events.map(event => event.start);
  const ends = events.map(event => event.end ?? event.start);
  const models = events.filter(event => event.kind === 'model');
  const sum = /** @param {'input' | 'output' | 'cached'} key */ key => models.reduce((total, event) => total + (event.tokens?.[key] || 0), 0);
  const start = starts.length ? Math.min(...starts) : null;
  const last = ends.length ? Math.max(...ends) : null;
  const running = events.filter(event => event.status === 'running').length;
  return { ...base, traceIds: [...new Set(events.map(event => event.traceId).filter(/** @returns {id is string} */ id => !!id))],
    start, end: running ? null : last, lastUpdate: last, durationMs: start === null || last === null ? null : last - start,
    agents: [...new Set(events.map(event => event.agent).filter(/** @returns {name is string} */ name => !!name))],
    modelCalls: models.length, toolCalls: events.filter(event => event.kind === 'tool').length, handoffs: events.filter(event => event.kind === 'handoff').length,
    errors: events.filter(event => ['failed', 'timeout'].includes(event.status)).length, input: sum('input'), output: sum('output'), cached: sum('cached'),
    running, orphans: events.filter(event => event.orphan).length, roots, events };
}

/** Return the reduced trajectory of a chat from its transcript steps, without trace context or durations.
 * @param {import('./types').Session} session
 * @returns {import('./types').Trajectory}
 */
function fromTranscript(session) {
  /** @type {Map<string, number>} */
  const seen = new Map();
  const events = session.events.slice().reverse().map(step => {
    const key = `${step.at}|${step.kind}|${step.title}`;
    seen.set(key, (seen.get(key) || 0) + 1);
    const kind = TRANSCRIPT_KIND[step.kind];
    const detail = redact(step.detail);
    /** @type {TrajectoryEvent} */
    const event = { id: `${key}|${seen.get(key)}`, seq: 0, traceId: null, spanId: null, parentId: null, orphan: false, kind, rawType: step.kind, name: step.title,
      agent: null, model: null, tool: kind === 'tool' ? step.kind : null, depth: 0, children: [], retry: 0,
      status: step.state, statusMessage: null, start: Date.parse(step.at), end: null, durationMs: null, session: session.id, tokens: null,
      content: step.detail ? [{ label: 'Detail', side: 'input', text: detail.text, redacted: detail.redacted, chars: step.detail.length, truncated: false }] : [],
      attributes: step.files.length ? [['files', step.files.join(', ')]] : [], resource: [], spanEvents: [], links: [] };
    return event;
  });
  return summarize(events, { source: 'transcript', chat: session.id, title: session.title, truncated: 0 });
}

/** Return the trajectory of the chat on screen: from research telemetry when its export has spans for it, else from the transcript.
 * @param {string} workspace
 * @param {string | null} telemetryFile
 * @param {import('./types').Session | null} session
 * @returns {import('./types').Trajectory | null}
 */
function trajectory(workspace, telemetryFile, session) {
  if (!session) return null;
  const relative = telemetryFile ? inside(telemetryFile, workspace) : null;
  if (!relative || !fs.existsSync(containedPath(workspace, relative))) return fromTranscript(session);
  const file = path.resolve(workspace, relative);
  const stat = fs.statSync(file);
  const key = `${file}|${session.id}`;
  const hit = cache.get(key);
  if (hit && hit.size === stat.size && hit.mtime === stat.mtimeMs) return hit.value || fromTranscript(session);
  const spans = chatSpans(jsonLines(tail(file, TELEMETRY_TAIL_BYTES), relative), session.id);
  const kept = spans.map(span => fromSpan(span, session.id)).sort((a, b) => b.start - a.start).slice(0, MAX_EVENTS);
  const value = kept.length ? summarize(kept, { source: 'telemetry', chat: session.id, title: session.title, truncated: spans.length - kept.length }) : null;
  cache.set(key, { size: stat.size, mtime: stat.mtimeMs, value });
  return value || fromTranscript(session);
}

module.exports = { trajectory, fromSpan, chatSpans, tree, summarize, fromTranscript, redact };
