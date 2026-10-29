'use strict';
/** Mission Control's sidebar and the view parts it shares with the dashboard, built as view trees from the host's model. */
(function (root) {
  /** @type {typeof globalThis.hveVnode} */
  const { h } = typeof module === 'object' && module.exports ? require('./vnode') : root.hveVnode;

  /** @typedef {import('../types').Model} Model */
  /** @typedef {import('../types').UiState} UiState */
  /** @typedef {import('../types').VNode} VNode */
  /** @typedef {import('../types').Child} Child */
  /** @typedef {import('../types').ActivityEvent} ActivityEvent */
  /** @typedef {{tone: 'error' | 'warn' | 'info', icon: string, title: string, detail: string, page?: string}} Need */

  /** @type {Record<string, (string | {cx: number, cy: number, r: number})[]>} */
  const ICONS = {
    logo: ['M12 2 21 7v10l-9 5-9-5V7Z', 'M8.5 8v8m7-8v8m-7-4h7'],
    refresh: ['M20 5v5h-5M4 19v-5h5', 'M19 9A7 7 0 0 0 6.3 6.3M4.9 15a7 7 0 0 0 12.8 2.7'],
    plus: ['M12 5v14M5 12h14'],
    pencil: ['M4 20h4L19 9l-4-4L4 16v4Z', 'm13.5 6.5 4 4'],
    file: ['M6 2.5h8l4 4V21.5H6Z', 'M14 2.5V7h4'],
    check: ['m5 12.5 4.5 4.5L19 7'],
    alert: ['M12 3.5 2.5 20h19Z', 'M12 10v4.5', 'M12 17.2v.1'],
    clock: [{ cx: 12, cy: 12, r: 9 }, 'M12 7v5l3 2'],
    user: [{ cx: 12, cy: 8, r: 4 }, 'M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5'],
    chat: ['M4 4.5h16v11.5H9.5L4 20.5Z'],
    eye: ['M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z', { cx: 12, cy: 12, r: 3 }],
    terminal: ['m5 7.5 4.5 4.5L5 16.5', 'M12 17h7'],
    search: [{ cx: 11, cy: 11, r: 6.5 }, 'm20 20-4.3-4.3'],
    question: [{ cx: 12, cy: 12, r: 9 }, 'M9.6 9.3a2.5 2.5 0 1 1 3.4 2.4c-.7.3-1 .9-1 1.6', 'M12 16.8v.1'],
    users: [{ cx: 9, cy: 8, r: 3.5 }, 'M2.5 20c0-3.4 2.9-5.5 6.5-5.5s6.5 2.1 6.5 5.5', 'M16 4.6a3.5 3.5 0 0 1 0 6.8', 'M21.5 20c0-2.6-1.6-4.4-4-5.1'],
    list: ['M9 6.5h11M9 12h11M9 17.5h11', 'M4.5 6.5h.1M4.5 12h.1M4.5 17.5h.1'],
    shield: ['m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z'],
    tool: ['M14.7 6.3a4 4 0 0 0 5 5L11 20a2.1 2.1 0 0 1-3-3l8.7-8.7Z'],
    pulse: ['M3 12h4l3-7 4 14 3-7h4'],
    map: ['M9 4.5 3.5 6.5v13l5.5-2 6 2 5.5-2v-13l-5.5 2Z', 'M9 4.5v13m6-11v13'],
    flag: ['M5.5 21V4', 'M5.5 4.5h11l-2 4 2 4h-11'],
    box: ['m12 3 8.5 4.7v8.6L12 21l-8.5-4.7V7.7Z', 'm3.5 7.7 8.5 4.7 8.5-4.7M12 12.4V21'],
    gear: [{ cx: 12, cy: 12, r: 3.2 }, 'M12 2.5v3m0 13v3M2.5 12h3m13 0h3M5.3 5.3l2.1 2.1m9.2 9.2 2.1 2.1M5.3 18.7l2.1-2.1m9.2-9.2 2.1-2.1'],
    chevron: ['m9.5 6 6 6-6 6'],
    folder: ['M3 6.5h6l2 2h10v11H3Z'],
    spark: ['M12 3v4m0 10v4M3 12h4m10 0h4', 'm6.3 6.3 2.4 2.4m6.6 6.6 2.4 2.4m0-11.4-2.4 2.4m-6.6 6.6-2.4 2.4'],
  };
  const KIND_ICON = { prompt: 'user', message: 'chat', read: 'eye', edit: 'pencil', run: 'terminal', search: 'search', ask: 'question',
    delegate: 'users', todo: 'list', guard: 'shield', tool: 'tool' };
  /** @type {[import('../types').Page, string, string][]} */
  const PAGES = [['live', 'Live', 'pulse'], ['plan', 'Plan', 'map'], ['progress', 'Progress', 'flag'], ['files', 'Files', 'folder'], ['skills', 'Skills & packs', 'box'],
    ['settings', 'Settings', 'gear']];

  /** Return a decorative line icon.
   * @param {string} name
   * @param {string} [extra]
   * @returns {VNode}
   */
  function icon(name, extra = '') {
    return h('svg', { class: `icon ${extra}`.trim(), viewBox: '0 0 24 24', 'aria-hidden': 'true' },
      ...ICONS[name].map(part => typeof part === 'string' ? h('path', { d: part }) : h('circle', part)));
  }

  /** Return how long ago a time was, in words.
   * @param {string} iso
   * @param {number} now
   * @returns {string}
   */
  function ago(iso, now) {
    const seconds = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
    if (seconds < 10) return 'just now';
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.round(minutes / 60);
    return hours < 24 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`;
  }

  /** Return a compact count such as 553k or 1.2M.
   * @param {number} value
   * @returns {string}
   */
  function count(value) {
    return value >= 1e6 ? `${(value / 1e6).toFixed(1)}M` : value >= 1e4 ? `${Math.round(value / 1e3)}k` : value.toLocaleString('en-US');
  }

  /** Return a plural noun with its count.
   * @param {number} value
   * @param {string} noun
   * @returns {string}
   */
  function plural(value, noun) { return `${value} ${noun}${value === 1 ? '' : 's'}`; }

  /** Return a readable name for a project or task slug.
   * @param {string} slug
   * @returns {string}
   */
  function pretty(slug) {
    const words = slug.replace(/[-_]+/g, ' ').trim();
    return words.charAt(0).toUpperCase() + words.slice(1);
  }

  /** Return an action button; data values travel as text.
   * @param {string} label
   * @param {string} action
   * @param {{kind?: string, icon?: string, data?: Record<string, string>, disabled?: boolean, title?: string}} [options]
   * @returns {VNode}
   */
  function button(label, action, options = {}) {
    const data = Object.fromEntries(Object.entries(options.data || {}).map(([key, value]) => [`data-${key}`, value]));
    return h('button', { class: `btn ${options.kind || ''}`.trim(), type: 'button', 'data-action': action, disabled: !!options.disabled,
      title: options.title, 'aria-label': label ? null : options.title, ...data }, options.icon ? icon(options.icon) : null, label ? h('span', null, label) : null);
  }

  /** Return the session status shown in the header chip.
   * @param {Model} model
   * @returns {{key: string, label: string}}
   */
  function sessionState(model) {
    const session = model.activity?.session;
    if (!session) return { key: 'none', label: 'No chat yet' };
    return { working: { key: 'working', label: 'Working' }, waiting: { key: 'waiting', label: 'Waiting for you' }, idle: { key: 'idle', label: 'Idle' } }[session.status];
  }

  /** Return the live status chip.
   * @param {Model} model
   * @returns {VNode}
   */
  function chip(model) {
    const state = sessionState(model);
    return h('span', { class: `chip status-${state.key}` }, h('span', { class: 'dot', 'aria-hidden': 'true' }), state.label);
  }

  /** Return the things that need the user now, most urgent first.
   * @param {Model} model
   * @returns {Need[]}
   */
  function needs(model) {
    /** @type {Need[]} */
    const items = [];
    const run = model.activity;
    const session = run?.session;
    const snap = model.snapshot;
    if (model.error) items.push({ tone: 'error', icon: 'alert', title: 'The last action failed', detail: model.error });
    if (model.asksError) items.push({ tone: 'error', icon: 'alert', title: 'Mission Control cannot list the asks', detail: model.asksError });
    if (model.handoffError) items.push({ tone: 'error', icon: 'alert', title: 'Mission Control cannot read the ask carried over from another workspace', detail: model.handoffError });
    if (model.snapshotError) items.push({ tone: 'error', icon: 'alert', title: 'Mission Control cannot read the ask files', detail: model.snapshotError });
    if (model.activityError) items.push({ tone: 'error', icon: 'alert', title: 'Mission Control cannot read the live activity', detail: model.activityError });
    if (session?.status === 'waiting') items.push({ tone: 'warn', icon: 'question', title: 'The agent is waiting for your answer in Chat', detail: session.current?.detail || '' });
    if (run?.errors?.paused) {
      items.push({ tone: 'error', icon: 'alert', title: `Paused after ${plural(run.errors.failures.length, 'failed command')} in a row`,
        detail: 'Answer the agent in Chat: fix the environment, change the approach or skip the step.', page: 'live' });
    } else if (run?.errors?.failures.length) {
      items.push({ tone: 'warn', icon: 'alert', title: run.errors.failures.length === 1 ? 'The last command failed' : `The last ${run.errors.failures.length} commands failed`,
        detail: run.errors.failures[run.errors.failures.length - 1].command, page: 'live' });
    }
    if (snap?.plan?.status === 'draft') items.push({ tone: 'info', icon: 'map', title: 'The plan is a draft', detail: 'Read it, and edit it if needed, before the agent builds.', page: 'plan' });
    if (snap?.plan?.status === 'edited') items.push({ tone: 'warn', icon: 'map', title: 'The plan changed since it was agreed', detail: 'The agent reviews the change before it continues.', page: 'plan' });
    if (snap?.pendingPlanTicks) items.push({ tone: 'info', icon: 'check', title: 'Ticks in plan.md are not recorded yet', detail: 'The agent records them at its next step.', page: 'plan' });
    const ready = snap ? snap.reviews.filter(review => review.ready && review.decision === 'open') : [];
    if (ready.length) items.push({ tone: 'warn', icon: 'check', title: `${plural(ready.length, 'item')} ready for your sign-off`, detail: ready.map(review => review.item).join(', '), page: 'plan' });
    const load = run?.loadout;
    if (load?.overBudget) {
      items.push({ tone: 'info', icon: 'box', title: 'Skill load is over the guideline',
        detail: `${load.skills} skills, ${count(load.tokens)} tokens on every request (guideline ${load.maxSkills} skills, ${count(load.maxTokens)} tokens)`, page: 'skills' });
    }
    return items;
  }

  /** Return the attention list, or nothing when all is well.
   * @param {Need[]} items
   * @param {boolean} compact
   * @returns {VNode | null}
   */
  function attention(items, compact) {
    if (!items.length) return null;
    return h('section', { class: 'needs', 'aria-label': 'Needs you' }, h('div', { class: 'section-label' }, 'Needs you', h('span', { class: 'count' }, items.length)),
      ...items.map(item => h('div', { class: `need tone-${item.tone}` }, icon(item.icon),
        h('div', { class: 'need-text' }, h('strong', null, item.title), item.detail ? h('span', { class: compact ? 'clamp' : '' }, item.detail) : null),
        item.page ? button('', 'go', { kind: 'icon', icon: 'chevron', data: { page: item.page }, title: `Open ${item.page}` }) : null)));
  }

  /** Return one timeline row.
   * @param {ActivityEvent} event
   * @param {number} now
   * @param {boolean} compact
   * @returns {VNode}
   */
  function eventRow(event, now, compact) {
    return h('li', { class: `event kind-${event.kind} state-${event.state}` },
      h('span', { class: 'event-icon' }, icon(event.state === 'running' ? 'spark' : KIND_ICON[event.kind] || 'tool', event.state === 'running' ? 'spin' : '')),
      h('div', { class: 'event-body' }, h('div', { class: 'event-title' }, event.title,
        event.state === 'failed' ? h('span', { class: 'pill error' }, 'failed') : event.state === 'stopped' ? h('span', { class: 'pill' }, 'stopped') : null),
      event.detail && !compact ? h('div', { class: 'event-detail' }, event.detail) : null),
      h('time', { title: new Date(event.at).toLocaleString() }, ago(event.at, now)));
  }

  /** Return the agent's to-do list.
   * @param {import('../types').Todo[]} todos
   * @param {number} limit
   * @returns {VNode}
   */
  function todoList(todos, limit) {
    const shown = todos.slice(0, limit);
    return h('ul', { class: 'todos' }, ...shown.map(todo => h('li', { class: `todo todo-${todo.status}` },
      icon(todo.status === 'completed' ? 'check' : todo.status === 'in-progress' ? 'spark' : 'clock', todo.status === 'in-progress' ? 'spin' : ''), h('span', null, todo.title))),
    todos.length > limit ? h('li', { class: 'todo more' }, `+${todos.length - limit} more`) : null);
  }

  /** Return a progress bar.
   * @param {number} done
   * @param {number} total
   * @param {string} label
   * @returns {VNode}
   */
  function bar(done, total, label) {
    return h('div', { class: 'bar', role: 'progressbar', 'aria-label': label, 'aria-valuenow': done, 'aria-valuemax': total },
      h('span', { 'style-width': total ? Math.round(done / total * 100) : 0 }));
  }

  /** Return the research telemetry switch with what it means.
   * @param {Model} model
   * @returns {VNode}
   */
  function telemetrySwitch(model) {
    const on = model.telemetry.enabled;
    return h('div', { class: 'switch-row' }, h('div', null, h('strong', null, 'Research telemetry'),
      h('span', { class: 'muted' }, on ? 'On: new chats record tokens, cost and full content' : 'Off: no tokens or chat content recorded')),
    h('button', { class: `switch ${on ? 'on' : ''}`.trim(), type: 'button', role: 'switch', 'aria-checked': on ? 'true' : 'false', 'aria-label': 'Research telemetry',
      'data-action': 'telemetry', 'data-value': on ? 'off' : 'on', disabled: model.busy }, h('span', { class: 'knob' })));
  }

  /** Return the chats that work on the ask on screen; with no ask, every chat of this window.
   * @param {Model} model
   * @returns {import('../types').Chat[]}
   */
  function askChats(model) {
    const ask = model.snapshot?.ask;
    const chats = model.activity?.chats || [];
    return ask ? chats.filter(chat => chat.asks.some(link => link.ask === ask.id)) : chats;
  }

  /** Return why no chat activity is shown.
   * @param {Model} model
   * @returns {string}
   */
  function noChat(model) {
    if (model.pending && model.pending.ask === model.snapshot?.ask?.id) return 'A new chat is open for this ask. Its activity appears here once you send your first message.';
    if (model.activityError) return 'Mission Control cannot read this window\'s chats: see Needs you.';
    if (!model.transcripts) return 'This window has no workspace storage, so Mission Control cannot follow its chats.';
    if (!model.activity?.chats.length) return 'No Copilot Chat session has run in this workspace yet.';
    return 'No chat is linked to this ask yet. A chat is linked when it creates or reopens the ask, edits its files, or is opened for it here.';
  }

  /** Return the notice for an ask carried over from another workspace, with Start the ask and Not now.
   * @param {Model} model
   * @returns {VNode | null}
   */
  function handoffNotice(model) {
    const carried = model.handoff;
    if (!carried) return null;
    return h('div', { class: 'notice handoff' }, icon('spark'),
      h('span', null, `Ready to start here: “${carried.title}”, carried over from ${carried.from}, where Mission Control recommended a workspace of its own.`),
      button('Start the ask', 'startHandoff', { kind: 'primary', disabled: model.busy, title: 'New ask with this title and description filled in' }),
      button('Not now', 'dismissHandoff', { disabled: model.busy }));
  }

  /** Return the dropdown of the project's asks; choosing one only changes what Mission Control shows.
   * @param {Model} model
   * @returns {VNode | null}
   */
  function askPicker(model) {
    const asks = model.asks || [];
    if (!asks.length) return null;
    const shown = model.snapshot?.ask?.id || '';
    return h('label', { class: 'ask-picker' }, h('span', { class: 'section-label' }, `Ask · ${plural(asks.length, 'ask')} in this project`),
      h('select', { 'data-action': 'selectAsk', disabled: model.busy, title: 'Show another ask. Make active switches the ask agents work on.' },
        shown ? null : h('option', { value: '', selected: true }, 'No ask is active'),
        ...asks.map(ask => h('option', { value: ask.id, selected: ask.id === shown },
          `${ask.title} · ${new Date(ask.created).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}${ask.active ? ' · active' : ''}`))));
  }

  /** Return the notice shown while an ask other than the active one is on screen.
   * @param {Model} model
   * @returns {VNode | null}
   */
  function viewing(model) {
    const ask = model.snapshot?.ask;
    if (!ask || ask.active) return null;
    const active = model.asks?.find(row => row.active);
    return h('div', { class: 'notice viewing' }, icon('eye'),
      h('span', null, active ? `You are viewing an earlier ask. Agents work on “${active.title}”.` : 'You are viewing an ask that is not active. No ask is active.'),
      button('Make active', 'activateAsk', { data: { ask: ask.id }, disabled: model.busy, title: 'Agents, hooks and guards then work on this ask. Asks you leave stay on disk.' }));
  }

  /** Return the ask card: what is being built, by whom, and how far along.
   * @param {Model} model
   * @param {number} now
   * @returns {VNode}
   */
  function askCard(model, now) {
    const snap = model.snapshot;
    const session = model.activity?.session;
    if (!snap?.ask) {
      return h('section', { class: 'card task empty' }, h('strong', null, model.asks?.length ? 'No ask is active' : 'No ask in this project yet'),
        h('p', { class: 'muted' }, model.asks?.length ? 'Choose an earlier ask above, or start one with New ask.'
          : 'An ask is one piece of work in this project. Start one with New ask, or pick an HVE agent in Copilot Chat. Chat activity shows below either way.'));
    }
    const done = session ? session.todos.filter(todo => todo.status === 'completed').length : 0;
    const stage = snap.stages.find(row => row.name === snap.ask?.current) || snap.stages[0];
    return h('button', { class: 'card task', type: 'button', 'data-action': 'go', 'data-page': 'live', title: snap.ask.request },
      h('span', { class: 'section-label' }, snap.project ? pretty(snap.project.name) : 'Ask'),
      h('strong', { class: 'task-title' }, snap.ask.title),
      h('span', { class: 'meta' }, [snap.ask.agent, stage ? `${stage.name}: ${stage.status}` : null, `started ${ago(snap.ask.created, now)}`,
        plural(askChats(model).length, 'chat')].filter(Boolean).join(' · ')),
      session && session.todos.length ? h('span', { class: 'task-progress' }, bar(done, session.todos.length, 'To-do progress'), `${done} of ${session.todos.length} to-dos done`) : null);
  }

  /** Return what the agent is doing right now, with its to-do list.
   * @param {Model} model
   * @param {number} now
   * @returns {VNode}
   */
  function nowSection(model, now) {
    const session = model.activity?.session;
    if (!session) return h('section', { class: 'now' }, h('div', { class: 'section-label' }, 'Now'), h('p', { class: 'muted' }, noChat(model)));
    const current = session.current;
    return h('section', { class: 'now' }, h('div', { class: 'section-label' }, 'Now'),
      current ? h('div', { class: `current kind-${current.kind}` }, icon(current.kind === 'ask' ? 'question' : 'spark', current.kind === 'ask' ? '' : 'spin'),
        h('div', null, h('strong', null, current.title), current.detail ? h('span', { class: 'clamp muted' }, current.detail) : null, h('time', null, `started ${ago(current.at, now)}`)))
        : h('div', { class: 'current idle' }, icon('clock'), h('div', null, h('strong', null, session.status === 'idle' ? 'Idle' : 'Thinking'),
          h('span', { class: 'muted' }, `Last activity ${ago(session.lastAt, now)}`))),
      session.todos.length ? todoList(session.todos, 6) : null);
  }

  /** Return the latest events with a link to the full activity.
   * @param {Model} model
   * @param {number} now
   * @returns {VNode | null}
   */
  function recent(model, now) {
    const events = (model.activity?.session?.events || []).filter(event => event.kind !== 'todo').slice(0, 6);
    if (!events.length) return null;
    return h('section', { class: 'recent' }, h('div', { class: 'section-label' }, 'Recent'), h('ul', { class: 'timeline compact' }, ...events.map(event => eventRow(event, now, true))),
      button('All activity', 'go', { kind: 'link', data: { page: 'live' } }));
  }

  /** Return the page links with a short status each.
   * @param {Model} model
   * @returns {VNode}
   */
  function pageLinks(model) {
    const snap = model.snapshot;
    const passing = snap ? snap.features.filter(feature => feature.passes).length : 0;
    /** @type {Record<string, string>} */
    const badges = { plan: snap?.plan ? { empty: 'not written', draft: 'draft', agreed: 'agreed', edited: 'changed' }[snap.plan.status] : '',
      progress: snap?.features.length ? `${passing}/${snap.features.length}` : '', files: model.files ? String(model.files.count) : '',
      skills: snap?.skills.length ? String(snap.skills.length) : '' };
    return h('nav', { class: 'links', 'aria-label': 'Mission Control pages' }, ...PAGES.map(([page, label, glyph]) =>
      h('button', { class: 'link-row', type: 'button', 'data-action': 'go', 'data-page': page }, icon(glyph), h('span', null, label),
        badges[page] ? h('span', { class: 'badge' }, badges[page]) : null, icon('chevron', 'trail'))));
  }

  /** Render the Primary Side Bar.
   * @param {Model} model
   * @param {UiState} ui
   * @param {number} now
   * @returns {VNode}
   */
  function sidebar(model, ui, now) {
    return h('div', { class: `sidebar ${model.busy ? 'busy' : ''}`.trim(), 'data-page': ui.page },
      h('header', { class: 'top' }, icon('logo', 'brand'), h('strong', null, 'Frontier HVE'), chip(model),
        button('', 'refresh', { kind: 'icon', icon: 'refresh', title: 'Refresh', disabled: model.busy })),
      model.workspaceMessage ? h('div', { class: 'notice' }, model.workspaceMessage, button('Choose folder', 'selectWorkspace')) : null,
      button('New ask', 'newAsk', { kind: 'primary new-ask', icon: 'plus', disabled: model.busy || !model.workspace,
        title: 'Start a new piece of work in this project; the harness first checks whether it continues the open ask' }),
      handoffNotice(model), askPicker(model), viewing(model), askCard(model, now), attention(needs(model), true), nowSection(model, now), recent(model, now), pageLinks(model),
      h('footer', null, telemetrySwitch(model)));
  }

  const api = { ICONS, PAGES, icon, ago, count, plural, pretty, button, chip, needs, attention, eventRow, todoList, bar, telemetrySwitch, sessionState,
    askChats, noChat, askPicker, viewing, handoffNotice, sidebar };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.hveViews = api;
})(globalThis);
