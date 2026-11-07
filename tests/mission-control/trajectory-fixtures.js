'use strict';
/** Deterministic Copilot OTel span fixtures for the Agent Trajectory tab, in the file exporter's line format. */
const fs = require('node:fs');
const path = require('node:path');
const CHAT = 'chat-main';
const SUB = 'chat-explore';
const TRACE = 'trace-0001';
const T0 = Date.UTC(2026, 10, 7, 21, 0, 0);
const SECRET = 'ghp_' + 'a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8';

/** Return an OTel [seconds, nanoseconds] time for T0 plus milliseconds.
 * @param {number} ms
 * @returns {[number, number]}
 */
function hr(ms) {
  const total = T0 + ms;
  return [Math.floor(total / 1000), (total % 1000) * 1e6];
}

/** Return one span line as the Copilot file exporter writes it; a null end leaves the span running.
 * @param {string} id
 * @param {string | null} parent
 * @param {string} name
 * @param {number} from
 * @param {number | null} to
 * @param {Record<string, unknown>} [attributes]
 * @param {{code: number, message?: string}} [status]
 * @returns {Record<string, unknown>}
 */
function span(id, parent, name, from, to, attributes = {}, status = { code: 0 }) {
  return { traceId: TRACE, spanId: id, traceFlags: 1, parentSpanContext: parent ? { traceId: TRACE, spanId: parent, traceFlags: 1 } : undefined, name, kind: 0,
    startTime: hr(from), endTime: hr(to ?? from), duration: [0, 0], ended: to !== null, status,
    attributes: { 'gen_ai.operation.name': name.split(' ')[0], 'copilot_chat.chat_session_id': CHAT, ...attributes },
    events: [], links: [], resource: { attributes: { 'session.id': 'window-1', 'service.name': 'copilot-chat' } }, instrumentationScope: { name: 'copilot-chat' } };
}

/** Return a model call span.
 * @param {string} id
 * @param {string} parent
 * @param {number} from
 * @param {number | null} to
 * @param {number} input
 * @param {Record<string, unknown>} [extra]
 * @param {{code: number, message?: string}} [status]
 * @returns {Record<string, unknown>}
 */
function chat(id, parent, from, to, input, extra = {}, status = { code: 0 }) {
  return span(id, parent, 'chat claude-opus-5.5', from, to, { 'gen_ai.request.model': 'claude-opus-5.5', 'gen_ai.response.model': 'claude-opus-5.5',
    ...(status.code === 2 ? {} : { 'gen_ai.usage.input_tokens': input, 'gen_ai.usage.output_tokens': Math.round(input / 40), 'gen_ai.usage.cache_read.input_tokens': Math.round(input / 2) }),
    'gen_ai.system_instructions': 'You are an agent. '.repeat(400), ...extra }, status);
}

/** Return a tool call span.
 * @param {string} id
 * @param {string} parent
 * @param {string} tool
 * @param {number} from
 * @param {number | null} to
 * @param {Record<string, unknown>} [extra]
 * @param {{code: number, message?: string}} [status]
 * @returns {Record<string, unknown>}
 */
function tool(id, parent, tool, from, to, extra = {}, status = { code: 0 }) {
  return span(id, parent, `execute_tool ${tool}`, from, to, { 'gen_ai.tool.name': tool, 'gen_ai.tool.call.id': `call_${id}`, ...extra }, status);
}

/** Return the multi-agent run: parallel tools, a failed command and its retry, a handoff to a sub-agent whose model call times out and is retried,
 * a cancelled model call, a tool still running, and an orphan span; one span is exported twice and children come before parents.
 * @returns {Record<string, unknown>[]}
 */
function multiAgentRun() {
  const rows = [
    span('a1', null, 'invoke_agent Frontier HVE Collab', 0, 60000, { 'gen_ai.agent.name': 'Frontier HVE Collab' }),
    chat('m1', 'a1', 100, 2000, 12000, { 'gen_ai.input.messages': JSON.stringify([{ role: 'user', content: 'Show me the trajectory <img src=x onerror=alert(1)>' }]) }),
    tool('t1', 'a1', 'read_file', 2100, null, { 'gen_ai.tool.call.arguments': '{"filePath":"extension/ui/trajectory.js"}' }),
    tool('t1', 'a1', 'read_file', 2100, 2300, { 'gen_ai.tool.call.arguments': '{"filePath":"extension/ui/trajectory.js"}', 'gen_ai.tool.call.result': 'x'.repeat(5000) }),
    tool('t2', 'a1', 'grep_search', 2150, 2600, { 'gen_ai.tool.call.arguments': '{"query":"traceparent"}' }),
    chat('m2', 'a1', 2700, 5000, 14000),
    tool('t3', 'a1', 'run_in_terminal', 5100, 9000, { 'gen_ai.tool.call.arguments': '{"command":"npm test"}', 'error.type': 'ToolError' }, { code: 2, message: 'Command exited 1' }),
    tool('t4', 'a1', 'run_in_terminal', 9100, 12000, { 'gen_ai.tool.call.arguments': `{"command":"npm test","env":"GITHUB_TOKEN=${SECRET}"}` }),
    tool('t5', 'a1', 'runSubagent', 12100, 40000, { 'gen_ai.tool.call.arguments': '{"agentName":"Explore","description":"Find telemetry code"}' }),
    span('a2', 't5', 'invoke_agent Explore', 12200, 39000, { 'gen_ai.agent.name': 'Explore', 'copilot_chat.chat_session_id': SUB, 'copilot_chat.parent_chat_session_id': CHAT }),
    chat('m3', 'a2', 12300, 20000, 0, { 'copilot_chat.chat_session_id': SUB }, { code: 2, message: 'Request timed out' }),
    chat('m4', 'a2', 20100, 30000, 9000, { 'copilot_chat.chat_session_id': SUB, 'gen_ai.output.messages': '[{"role":"assistant","content":"Found activity.js"}]' }),
    chat('m5', 'a1', 40100, 41000, 0, {}, { code: 2, message: 'Canceled' }),
    tool('t6', 'a1', 'view_image', 41100, null),
    tool('o1', 'lost-parent', 'get_errors', 50000, 50100),
    { ...span('x1', null, 'invoke_agent Other', 0, 10), traceId: 'trace-other', attributes: { 'gen_ai.operation.name': 'invoke_agent', 'copilot_chat.chat_session_id': 'another-chat' } },
    { hrTime: hr(5), body: 'a log record shares the export file', attributes: {} },
  ];
  return rows.reverse();
}

/** Return a large run: one agent with model calls and many tool calls.
 * @param {number} tools
 * @returns {Record<string, unknown>[]}
 */
function largeRun(tools) {
  return [span('a1', null, 'invoke_agent Frontier HVE Collab', 0, tools * 20 + 100, { 'gen_ai.agent.name': 'Frontier HVE Collab' }),
    ...Array.from({ length: tools }, (_, index) => index % 10 === 0 ? chat(`m${index}`, 'a1', index * 20, index * 20 + 15, 1000) : tool(`t${index}`, 'a1', 'read_file', index * 20, index * 20 + 15))];
}

/** Write span lines as the research telemetry export inside a workspace and return its absolute path.
 * @param {string} root
 * @param {Record<string, unknown>[]} rows
 * @returns {string}
 */
function writeExport(root, rows) {
  const file = path.join(root, '.hve', 'runs', 'copilot-otel.jsonl');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, rows.map(row => JSON.stringify(row) + '\n').join(''));
  return file;
}

/** Write a transcript for the main chat and return its path.
 * @param {string} folder
 * @returns {string}
 */
function writeTranscript(folder) {
  fs.mkdirSync(folder, { recursive: true });
  const at = /** @param {number} ms */ ms => new Date(T0 + ms).toISOString();
  const rows = [['user.message', 0, { content: 'Show me the trajectory of this run' }], ['assistant.turn_start', 10, {}],
    ['tool.execution_start', 2100, { toolCallId: 'a', toolName: 'read_file', arguments: { filePath: 'extension/ui/trajectory.js' } }],
    ['tool.execution_complete', 2300, { toolCallId: 'a', success: true }],
    ['tool.execution_start', 5100, { toolCallId: 'b', toolName: 'run_in_terminal', arguments: { command: 'npm test', explanation: 'Run the tests' } }],
    ['tool.execution_complete', 9000, { toolCallId: 'b', success: false }],
    ['tool.execution_start', 12100, { toolCallId: 'c', toolName: 'runSubagent', arguments: { agentName: 'Explore', description: 'Find telemetry code' } }],
    ['tool.execution_complete', 40000, { toolCallId: 'c', success: true }],
    ['assistant.message', 42000, { content: 'The trajectory is ready.' }], ['assistant.turn_end', 42000, {}]];
  const file = path.join(folder, `${CHAT}.jsonl`);
  fs.writeFileSync(file, rows.map(([type, ms, data]) => JSON.stringify({ type, timestamp: at(Number(ms)), data }) + '\n').join(''));
  return file;
}

module.exports = { CHAT, SUB, TRACE, T0, SECRET, span, chat, tool, multiAgentRun, largeRun, writeExport, writeTranscript };
