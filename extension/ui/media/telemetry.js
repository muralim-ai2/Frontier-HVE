'use strict';
/** Mission Control's Telemetry page: the chat's numbers at a glance, its warning signals, and an experimental model review. */
(function (root) {
  const modular = typeof module === 'object' && module.exports;
  /** @type {typeof globalThis.hveVnode} */
  const { h } = modular ? require('./vnode') : root.hveVnode;
  /** @type {typeof globalThis.hveMarkdown} */
  const markdown = modular ? require('./markdown') : root.hveMarkdown;
  /** @type {typeof globalThis.hveViews} */
  const { icon, ago, count, plural, button, telemetrySwitch } = modular ? require('./views') : root.hveViews;
  const QUESTION = 'Where did it make thinking errors, repeat or loop, get stuck, or decide something without asking me?';

  /** @typedef {import('../types').Model} Model */
  /** @typedef {import('../types').UiState} UiState */
  /** @typedef {import('../types').VNode} VNode */
  /** @typedef {import('../types').Child} Child */

  /** Return one big-number tile.
   * @param {string} glyph
   * @param {string} label
   * @param {Child} value
   * @param {string} hint
   * @param {string} tone
   * @returns {VNode}
   */
  function tile(glyph, label, value, hint, tone) {
    return h('div', { class: `tele-tile tone-${tone}` }, h('span', { class: 'tele-tile-icon' }, icon(glyph)), h('span', { class: 'tele-value' }, value),
      h('span', { class: 'tele-label' }, label), hint ? h('span', { class: 'tele-hint' }, hint) : null);
  }

  /** Return the stacked bar of where the chat's own tokens went.
   * @param {import('../types').Insights} data
   * @returns {VNode}
   */
  function mix(data) {
    const parts = [['skills', 'Skills per request', data.skills.tokens], ['chat', 'Prompts and replies', data.chatTokens], ['tools', 'Tool arguments', data.argTokens],
      ['thinking', 'Thinking', data.thinkingTokens || 0]].filter(part => Number(part[2]) > 0);
    const total = parts.reduce((sum, part) => sum + Number(part[2]), 0) || 1;
    return h('div', { class: 'tele-mix' }, h('div', { class: 'tele-bar', role: 'img', 'aria-label': 'Token mix' },
      ...parts.map(([key, , value]) => h('span', { class: `seg seg-${key}`, 'style-width': Math.max(2, Math.round(Number(value) / total * 100)) }))),
    h('ul', { class: 'tele-legend' }, ...parts.map(([key, label, value]) => h('li', null, h('span', { class: `swatch seg-${key}` }), `${label} `, h('strong', null, count(Number(value)))))));
  }

  /** Return the experimental review: model, question, Analyze, and the streamed answer.
   * @param {Model} model
   * @param {UiState} ui
   * @param {number} now
   * @returns {VNode}
   */
  function review(model, ui, now) {
    const models = model.models || [];
    const chosen = models.find(row => row.id === ui.model) || models.find(row => /haiku/i.test(row.family + row.name)) || models[0];
    const result = model.analysis;
    return h('section', { class: 'card tele-lab' }, h('header', { class: 'card-head' }, h('h2', null, icon('spark'), ' Ask a model about this chat'),
      h('span', { class: 'tele-badge' }, 'Experimental')),
    h('p', { class: 'muted' }, 'A Copilot model reads this chat\'s activity log (steps, failures, repeats, guard alerts; works with research telemetry off) and answers in three crisp bullets. '
      + 'It uses your Copilot quota. VS Code chooses the model\'s reasoning effort.'),
    model.modelsError ? h('div', { class: 'notice error' }, model.modelsError) : null,
    model.models === null && !model.modelsError ? h('p', { class: 'muted' }, 'Loading Copilot models…') : null,
    models.length ? h('div', { class: 'tele-ask' },
      h('label', { class: 'tele-field' }, h('span', { class: 'section-label' }, 'Model'),
        h('select', { 'data-field': 'model', disabled: result?.status === 'running' }, ...models.map(row => h('option', { value: row.id, selected: row.id === chosen?.id }, row.name)))),
      h('label', { class: 'tele-field grow' }, h('span', { class: 'section-label' }, 'Question'),
        h('textarea', { 'data-field': 'question', rows: 2, maxlength: 1000, placeholder: QUESTION }, ui.question ?? QUESTION)),
      button('Analyze', 'analyze', { kind: 'primary', icon: 'spark', disabled: model.busy || result?.status === 'running' || !model.activity?.session,
        title: 'Send this chat\'s activity log to the chosen model' })) : null,
    result ? h('div', { class: `tele-answer status-${result.status}`, 'aria-live': 'polite' },
      h('div', { class: 'meta' }, `${result.model} on “${result.chat}” · ${result.status === 'running' ? 'thinking…' : ago(result.at, now)}`),
      result.text ? h('div', { class: 'markdown' }, ...markdown.render(result.text)) : h('div', { class: 'tele-shimmer' }, h('span', null), h('span', null), h('span', null))) : null);
  }

  /** Render the Telemetry page.
   * @param {Model} model
   * @param {UiState} ui
   * @param {number} now
   * @returns {Child[]}
   */
  function telemetry(model, ui, now) {
    const data = model.insights;
    if (!data) {
      return [h('div', { class: 'empty-state' }, h('strong', null, 'No chat to measure yet'),
        h('p', { class: 'muted' }, 'Telemetry appears for the chat shown on Live as soon as it starts.'))];
    }
    const kind = data.measured ? 'measured' : 'estimated';
    return [
      h('section', { class: 'tele-hero' }, h('div', { class: 'tele-hero-text' }, h('span', { class: 'section-label' }, 'Telemetry · this chat'),
        h('h2', null, data.chat), h('span', { class: `tele-pill ${kind}` }, data.measured ? 'Measured by research telemetry' : 'Estimated: research telemetry is off')),
      h('div', { class: 'tele-total' }, h('span', { class: 'tele-big' }, count(data.total)), h('span', null, `${kind === 'measured' ? '' : '≈ '}tokens in total`),
        h('span', { class: 'tele-aiu' }, `${kind === 'measured' ? '' : '≈ '}${data.aiu.toFixed(1)} AI units`))),
      h('div', { class: 'tele-tiles' },
        tile('pulse', 'Turns', data.turns, 'model calls the agent made', 'violet'),
        tile('tool', 'Tool calls', data.toolCalls, `${plural(data.commands, 'command')} · ${data.failures} failed`, 'blue'),
        tile('box', 'Skills used', data.skills.count, data.skills.names.slice(0, 4).join(', ') || 'none read in this chat', 'teal'),
        tile('list', 'Skill tokens', count(data.skills.tokens), data.skills.measured ? 'loaded into every request' : 'estimated from the skill files read', 'amber'),
        tile('chat', 'Prompt and chat tokens', count(data.chatTokens), 'your messages and the agent\'s replies (estimated)', 'pink'),
        tile('spark', 'Thinking tokens', data.thinkingTokens === null ? '—' : count(data.thinkingTokens),
          data.thinkingTokens === null ? 'recorded only with research telemetry on' : 'reasoning the model reported', 'indigo')),
      h('section', { class: 'card' }, h('header', { class: 'card-head' }, h('h2', null, 'Where the tokens go'),
        h('span', { class: 'muted' }, `${count(data.input)} in · ${count(data.output)} out`)), mix(data), h('p', { class: 'tele-method' }, data.method),
      data.measured ? null : telemetrySwitch(model)),
      h('section', { class: 'card' }, h('header', { class: 'card-head' }, h('h2', null, 'Signals'), h('span', { class: 'muted' }, 'found locally, no model')),
        data.signals.length ? h('ul', { class: 'tele-signals' }, ...data.signals.map(signal => h('li', { class: `tone-${signal.tone}` },
          icon(signal.tone === 'info' ? 'clock' : 'alert'), h('div', null, h('strong', null, signal.title), h('span', { class: 'muted' }, signal.detail)))))
          : h('p', { class: 'muted' }, 'No loops, failures, dropped results or long pauses in this chat.')),
      review(model, ui, now),
    ];
  }

  const api = { telemetry, QUESTION };
  if (modular) module.exports = api;
  else root.hveTelemetry = api;
})(globalThis);
