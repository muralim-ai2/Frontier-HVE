'use strict';
/** Telemetry for one chat: a summary measured from research telemetry when it is on and estimated from the transcript when it is off, local warning signals, and the digest an analysis model reads. */
const BASE_CONTEXT_TOKENS = 12000;
const AIU_PER_1K_INPUT = 0.125;
const CHARS_PER_TOKEN = 4;
const DIGEST_STEPS = 150;

/** Return a character count as tokens.
 * @param {number} chars
 * @returns {number}
 */
function tokens(chars) { return Math.round(chars / CHARS_PER_TOKEN); }

/** Return a time of day in this machine's time zone.
 * @param {string | undefined} iso
 * @returns {string}
 */
function clock(iso) { return new Date(String(iso)).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }); }

/** Return the summary and signals of the chat Mission Control shows.
 * @param {import('./types').Activity} run
 * @returns {import('./types').Insights | null}
 */
function insights(run) {
  const s = run.session;
  if (!s) return null;
  const { chars, skills, repeats, gap } = s.stats;
  const measured = run.tokens;
  const skillTokens = run.loadout ? { value: run.loadout.tokens, measured: true } : { value: tokens(skills.reduce((sum, skill) => sum + skill.bytes, 0)), measured: false };
  const conversation = tokens(chars.user + chars.agent + chars.args);
  const estimatedInput = s.turns * (BASE_CONTEXT_TOKENS + skillTokens.value) + Math.round(s.turns * conversation / 2);
  const estimatedOutput = tokens(chars.agent + chars.args);
  const input = measured ? measured.models.reduce((sum, use) => sum + use.input, 0) : estimatedInput;
  const output = measured ? measured.models.reduce((sum, use) => sum + use.output, 0) : estimatedOutput;
  const reasoning = measured ? measured.models.reduce((sum, use) => sum + use.reasoning, 0) : 0;
  const stopped = s.events.filter(event => event.state === 'stopped').length;
  const asked = s.events.filter(event => event.kind === 'ask').length;
  const pause = gap ? Math.round((Date.parse(gap.to) - Date.parse(gap.from)) / 1000) : 0;
  /** @type {import('./types').Signal[]} */
  const signals = [
    ...repeats.map(call => ({ tone: /** @type {const} */ ('warn'), title: `Repeated ${call.count} times: ${call.title}`, detail: 'The same call with the same arguments; a possible loop.' })),
    ...(s.failures ? [{ tone: /** @type {const} */ ('error'), title: `${s.failures} failed tool ${s.failures === 1 ? 'call' : 'calls'}`, detail: 'See Problems on the Live page.' }] : []),
    ...(stopped ? [{ tone: /** @type {const} */ ('warn'), title: `${stopped} ${stopped === 1 ? 'call' : 'calls'} never reported a result`, detail: 'Copilot recorded no result; the agent moved on.' }] : []),
    ...(pause >= 120 ? [{ tone: /** @type {const} */ ('info'), title: `Longest pause: ${Math.round(pause / 60)} min`, detail: `Nothing recorded from ${clock(gap?.from)} to ${clock(gap?.to)}: long thinking, a long command, or waiting.` }] : []),
    ...(run.errors?.paused ? [{ tone: /** @type {const} */ ('error'), title: 'Paused by the error guard', detail: `${run.errors.failures.length} failed commands in a row.` }] : []),
    ...(asked ? [{ tone: /** @type {const} */ ('info'), title: `Asked you ${asked} ${asked === 1 ? 'time' : 'times'}`, detail: 'Questions the agent put to you in Chat.' }] : []),
  ];
  return {
    chat: s.title || 'Untitled chat', measured: !!measured, turns: s.turns, toolCalls: s.tools, commands: s.commands, failures: s.failures,
    skills: { count: Math.max(skills.length, run.loadout?.skills || 0), names: skills.map(skill => skill.name), tokens: skillTokens.value, measured: skillTokens.measured },
    chatTokens: tokens(chars.user + chars.agent), argTokens: tokens(chars.args), thinkingTokens: reasoning || null,
    input, output, total: input + output, aiu: measured ? measured.aiu : estimatedInput / 1000 * AIU_PER_1K_INPUT, signals,
    method: measured ? 'Measured by research telemetry for this chat.'
      : `Estimated (research telemetry is off): ${BASE_CONTEXT_TOKENS.toLocaleString('en-US')} tokens of instructions and tool definitions plus the skill load per turn, `
        + `the conversation growing over ${s.turns} turns, 4 characters per token, and ${AIU_PER_1K_INPUT} AI units per 1,000 input tokens `
        + '(measured on a Claude Opus 5.5 session). Tool results are not in the transcript, so the real figure is higher.',
  };
}

/** Return a compact, numbered log of the chat for an analysis model.
 * @param {import('./types').Activity} run
 * @param {import('./types').Insights} summary
 * @returns {string}
 */
function digest(run, summary) {
  const s = /** @type {import('./types').Session} */ (run.session);
  const steps = s.events.slice(0, DIGEST_STEPS).reverse().map((event, index) =>
    `#${index + 1} ${event.at.slice(11, 19)} ${event.kind}${event.state === 'ok' ? '' : ` [${event.state}]`}: ${event.title}${event.detail ? ` | ${event.detail.slice(0, 160)}` : ''}`);
  return [`Chat: ${summary.chat}`, `Turns ${s.turns}, tool calls ${s.tools}, commands ${s.commands}, failed ${s.failures}, skills read: ${summary.skills.names.join(', ') || 'none'}.`,
    s.todos.length ? `To-do list: ${s.todos.map(todo => `${todo.title} (${todo.status})`).join('; ')}` : '',
    run.errors?.failures.length ? `Error guard: ${run.errors.paused ? 'paused after ' : ''}${run.errors.failures.map(failure => failure.command).join(' ; ')}` : '',
    summary.signals.length ? `Signals: ${summary.signals.map(signal => signal.title).join('; ')}` : '',
    `Steps, oldest first (last ${steps.length}):`, ...steps].filter(Boolean).join('\n');
}

/** Return the instruction for the analysis model.
 * @param {string} question
 * @param {string} log
 * @returns {string}
 */
function analysisPrompt(question, log) {
  return ['You review one AI coding-agent chat from its activity log below. Look for thinking errors (wrong assumptions, errors it ignored), '
    + 'circular or repeated tool calls, places it got stuck and looped, and decisions it made without asking the user. Use only what the log shows.',
  'Reply with exactly 3 bullets, each one crisp sentence that cites step numbers (#n). If the log shows nothing for a point, say so plainly.',
  `The user asks: ${question}`, '', log].join('\n');
}

module.exports = { insights, digest, analysisPrompt, BASE_CONTEXT_TOKENS, AIU_PER_1K_INPUT };
