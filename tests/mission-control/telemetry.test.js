'use strict';
/** Verify the Telemetry page: the chat's numbers measured or estimated, local signals, and the experimental model review streamed from a Copilot model. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { mission } = require('./vscode-stub');
const { insights, digest, analysisPrompt } = require('../../extension/ui/insights');
const { activity } = require('../../extension/ui/activity');
const { text } = require('../../extension/ui/media/vnode');
const { dashboard } = require('../../extension/ui/media/pages');
const { message } = require('../../extension/ui/validate');
const UI = { page: 'telemetry', filter: 'all', open: {}, seq: 0 };

/** Write a chat that reads two skills, repeats one search three times and fails a command.
 * @param {string} folder
 * @param {string} root
 * @returns {string}
 */
function chat(folder, root) {
  fs.mkdirSync(folder, { recursive: true });
  const skill = path.join(root, 'skills', 'ux-flows', 'SKILL.md');
  fs.mkdirSync(path.dirname(skill), { recursive: true });
  fs.writeFileSync(skill, 'x'.repeat(4000));
  const start = Date.now() - 10 * 60_000;
  const at = seconds => new Date(start + seconds * 1000).toISOString();
  const rows = [['user.message', 0, { content: 'Build the Pawstagram feed with dog profiles' }], ['assistant.turn_start', 1, {}],
    ['tool.execution_start', 2, { toolCallId: 'a', toolName: 'read_file', arguments: { filePath: skill } }], ['tool.execution_complete', 3, { toolCallId: 'a', success: true }],
    ...[10, 20, 30].flatMap((s, i) => [['tool.execution_start', s, { toolCallId: `g${i}`, toolName: 'grep_search', arguments: { query: 'feedCard' } }],
      ['tool.execution_complete', s + 1, { toolCallId: `g${i}`, success: true }]]),
    ['tool.execution_start', 40, { toolCallId: 'r', toolName: 'run_in_terminal', arguments: { command: 'npm test', explanation: 'Run the feed checks' } }],
    ['tool.execution_complete', 300, { toolCallId: 'r', success: false }], ['assistant.message', 301, { content: 'The feed check failed; fixing the card layout.' }],
    ['assistant.turn_end', 301, {}]];
  const file = path.join(folder, 'feed.jsonl');
  fs.writeFileSync(file, rows.map(([type, s, data]) => JSON.stringify({ type, timestamp: at(s), data }) + '\n').join(''));
  return file;
}

test('without telemetry the summary estimates tokens and AI units, counts calls, turns and skills, and finds repeats, failures and pauses', t => {
  const fixture = mission(t);
  const file = chat(fixture.transcripts, fixture.root);
  const run = { ...activity(fixture.root, file, null, Date.now()), chats: [] };
  const data = insights(run);
  assert.equal(data.measured, false);
  assert.equal(data.turns, 1);
  assert.equal(data.toolCalls, 5);
  assert.equal(data.failures, 1);
  assert.deepEqual(data.skills, { count: 1, names: ['ux-flows'], tokens: 1000, measured: false });
  assert.equal(data.thinkingTokens, null);
  assert.ok(data.total > 12000 && data.aiu > 1);
  assert.match(data.method, /^Estimated \(research telemetry is off\)/);
  assert.deepEqual(data.signals.map(signal => signal.title), ['Repeated 3 times: Searched for “feedCard”', '1 failed tool call', 'Longest pause: 4 min']);
  const log = digest(run, data);
  assert.match(log, /^Chat: Build the Pawstagram feed with dog profiles/);
  assert.match(log, /#\d+ \d\d:\d\d:\d\d run \[failed\]: Run the feed checks \| npm test/);
  assert.match(analysisPrompt('Why did it fail?', log), /exactly 3 bullets[\s\S]*The user asks: Why did it fail\?/);
});

test('with research telemetry the totals, AI units and thinking tokens are measured', () => {
  const run = { session: { title: 'Feed', turns: 2, tools: 3, commands: 1, failures: 0, events: [], todos: [],
    stats: { chars: { user: 400, agent: 400, args: 400 }, skills: [], repeats: [], gap: null } }, chats: [], errors: null,
  loadout: { skills: 4, tokens: 9000, overBudget: false, maxSkills: 10, maxTokens: 32000 },
  tokens: { models: [{ model: 'claude-haiku-5.5', calls: 2, failed: 0, input: 50000, output: 2000, cached: 30000, reasoning: 1500 }], aiu: 2.5 } };
  const data = insights(run);
  assert.equal(data.measured, true);
  assert.deepEqual([data.input, data.output, data.total, data.aiu, data.thinkingTokens], [50000, 2000, 52000, 2.5, 1500]);
  assert.deepEqual(data.skills, { count: 4, names: [], tokens: 9000, measured: true });
  assert.equal(data.method, 'Measured by research telemetry for this chat.');
});

test('the Telemetry tab shows the tiles, the token mix, the signals and the experimental review, all as text', async t => {
  const fixture = mission(t);
  chat(fixture.transcripts, fixture.root);
  fixture.controls.models.push({ id: 'claude-haiku-5.5', name: 'Claude Haiku 5.5', family: 'claude-haiku', sendRequest: async () => ({ text: (async function* () {})() }) },
    { id: 'gpt-6-astra', name: 'GPT-6 Astra', family: 'gpt-6' });
  await fixture.controls.provider.execute({ action: 'loadModels' });
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.deepEqual(model.models.map(row => row.name), ['Claude Haiku 5.5', 'GPT-6 Astra']);
  const page = dashboard(model, UI, Date.now());
  const shown = text(page);
  for (const part of ['Telemetry · this chat', 'Estimated: research telemetry is off', 'Turns', 'Tool calls', 'Skills used', 'Skill tokens', 'Prompt and chat tokens',
    'Thinking tokens', 'recorded only with research telemetry on', 'Where the tokens go', 'Repeated 3 times', 'Ask a model about this chat', 'Experimental']) {
    assert.ok(shown.includes(part), part);
  }
  const find = (node, match) => typeof node === 'string' ? [] : [...(match(node) ? [node] : []), ...node.children.flatMap(child => find(child, match))];
  const options = find(page, node => node.tag === 'option');
  assert.deepEqual(options.filter(node => 'selected' in node.attrs).map(node => node.attrs.value), ['claude-haiku-5.5']);
  assert.equal(find(page, node => node.tag === 'textarea').length, 1);
  assert.equal(find(page, node => node.attrs['data-action'] === 'analyze').length, 1);
});

test('Analyze streams the model\'s three bullets into the page and sends only the chat\'s log', async t => {
  const fixture = mission(t);
  chat(fixture.transcripts, fixture.root);
  /** @type {any[]} */
  const sent = [];
  fixture.controls.models.push({ id: 'claude-haiku-5.5', name: 'Claude Haiku 5.5', family: 'claude-haiku', sendRequest: async (messages, options) => {
    sent.push({ messages, options });
    return { text: (async function* () { yield '- Repeated the same search three times (#4-#6).\n'; yield '- Ignored nothing.\n- Decided the layout alone (#9).'; })() };
  } });
  await fixture.controls.commands.get('frontierHve.refreshMissionControl')();
  await fixture.controls.provider.execute({ action: 'analyze', model: 'claude-haiku-5.5', question: 'Where did it loop?' });
  const result = fixture.controls.commands.get('frontierHve.missionControlModel')().analysis;
  assert.equal(result.status, 'done');
  assert.equal(result.model, 'Claude Haiku 5.5');
  assert.match(result.text, /^- Repeated the same search three times/);
  assert.match(sent[0].messages[0].content, /The user asks: Where did it loop\?/);
  assert.match(sent[0].messages[0].content, /Steps, oldest first/);
  assert.match(sent[0].options.justification, /at your request/);
  const page = text(dashboard(fixture.controls.commands.get('frontierHve.missionControlModel')(), UI, Date.now()));
  assert.match(page, /Repeated the same search three times \(#4-#6\)/);
  await assert.rejects(fixture.controls.provider.execute({ action: 'analyze', model: 'missing', question: 'x' }), /model missing is not available/);
  assert.throws(() => message({ action: 'analyze', model: 'x' }), /Unexpected fields/);
});

test('without Copilot models the page says so instead of failing', async t => {
  const fixture = mission(t);
  chat(fixture.transcripts, fixture.root);
  await fixture.controls.provider.execute({ action: 'loadModels' });
  const model = fixture.controls.commands.get('frontierHve.missionControlModel')();
  assert.match(model.modelsError, /No Copilot models are available/);
  assert.match(text(dashboard(model, UI, Date.now())), /No Copilot models are available/);
});
