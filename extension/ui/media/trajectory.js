'use strict';
/** Mission Control's Agent Trajectory page: one chat's run as a synced graph, timeline and details panel, with search and filters. */
(function (root) {
  const modular = typeof module === 'object' && module.exports;
  /** @type {typeof globalThis.hveVnode} */
  const { h } = modular ? require('./vnode') : root.hveVnode;
  /** @type {typeof globalThis.hveViews} */
  const { icon, ago, count, plural, button, telemetrySwitch } = modular ? require('./views') : root.hveViews;
  /** @type {typeof globalThis.hveTelemetry} */
  const { chatPicker } = modular ? require('./telemetry') : root.hveTelemetry;
  const NODE = { w: 200, h: 54, dx: 240, dy: 68 };
  const MAX_GRAPH = 400;
  const PAGE_ROWS = 300;
  /** @type {Record<import('../types').TrajectoryKind, [string, string, number]>} */
  const KIND = { agent: ['Agent', 'users', 16], handoff: ['Handoff', 'users', 16], model: ['Model call', 'spark', 3], tool: ['Tool call', 'tool', 8],
    user: ['User input', 'user', 27], response: ['Response', 'chat', 27], guard: ['Guard', 'shield', 0], other: ['Span', 'pulse', 8] };
  /** @type {Record<import('../types').TrajectoryStatus, [string, string, string]>} */
  const STATUS = { ok: ['completed', '✓', 'good'], failed: ['failed', '✕', 'error'], timeout: ['timed out', '⏱', 'error'], cancelled: ['cancelled', '⊘', 'warn'],
    running: ['running', '●', ''], stopped: ['no result recorded', '?', 'warn'] };
  const PROBLEMS = ['failed', 'timeout', 'cancelled'];
  /** @type {import('../types').TrajectoryUi} */
  const DEFAULT = { view: 'graph', sel: null, q: '', status: 'all', kind: 'all', agent: 'all', errors: false, time: 'elapsed', collapsed: {},
    zoom: { k: 1, x: 16, y: 16 }, paused: false, limit: PAGE_ROWS };

  /** @typedef {import('../types').Model} Model */
  /** @typedef {import('../types').UiState} UiState */
  /** @typedef {import('../types').VNode} VNode */
  /** @typedef {import('../types').Child} Child */
  /** @typedef {import('../types').Trajectory} Trajectory */
  /** @typedef {import('../types').TrajectoryEvent} TrajectoryEvent */
  /** @typedef {import('../types').TrajectoryUi} TrajectoryUi */

  /** Return the page's view state with defaults filled in.
   * @param {UiState} ui
   * @returns {TrajectoryUi}
   */
  function uiState(ui) {
    return { ...DEFAULT, ...ui.traj, zoom: { ...DEFAULT.zoom, ...ui.traj?.zoom }, collapsed: { ...ui.traj?.collapsed } };
  }

  /** Return a duration in words.
   * @param {number} ms
   * @returns {string}
   */
  function duration(ms) {
    if (ms < 1000) return `${Math.round(ms)} ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`;
    return `${Math.floor(ms / 60000)} min ${Math.round(ms % 60000 / 1000)} s`;
  }

  /** Return a time as a clock time or as elapsed time from the run's start.
   * @param {number} at
   * @param {TrajectoryUi} s
   * @param {Trajectory} run
   * @returns {string}
   */
  function when(at, s, run) {
    return s.time === 'clock' ? new Date(at).toLocaleTimeString('en-GB', { hour12: false }) : `+${duration(Math.max(0, at - (run.start ?? at)))}`;
  }

  /** Return text cut to a length with an ellipsis.
   * @param {string} value
   * @param {number} limit
   * @returns {string}
   */
  function clip(value, limit) { return value.length > limit ? `${value.slice(0, limit - 1)}…` : value; }

  /** Return what a screen reader says for an event.
   * @param {TrajectoryEvent} e
   * @returns {string}
   */
  function label(e) {
    return [`Step ${e.seq}: ${KIND[e.kind][0]} ${e.name}`, STATUS[e.status][0], e.durationMs === null ? null : duration(e.durationMs), e.retry ? `retry ${e.retry}` : null,
      e.agent && e.kind !== 'agent' && e.kind !== 'handoff' ? null : e.agent, e.children.length ? plural(e.children.length, 'child step') : null].filter(Boolean).join(', ');
  }

  /** Return the agent an event runs under: its own, or its nearest ancestor's.
   * @param {TrajectoryEvent} e
   * @param {Map<string, TrajectoryEvent>} byId
   * @returns {string | null}
   */
  function owner(e, byId) {
    for (let at = /** @type {TrajectoryEvent | undefined} */ (e); at; at = at.orphan || !at.parentId ? undefined : byId.get(at.parentId)) if (at.agent) return at.agent;
    return null;
  }

  /** Return the events to show in depth-first order: matches plus the ancestors they need for lineage, minus the steps under collapsed branches.
   * @param {Trajectory} run
   * @param {TrajectoryUi} s
   * @returns {{shown: TrajectoryEvent[], matched: Set<string>, active: boolean, hidden: number}}
   */
  function visible(run, s) {
    const byId = new Map(run.events.map(e => [e.id, e]));
    /** @param {TrajectoryEvent} e @returns {TrajectoryEvent | undefined} */
    const up = e => e.orphan || !e.parentId ? undefined : byId.get(e.parentId);
    const q = s.q.trim().toLowerCase();
    const active = !!q || s.status !== 'all' || s.kind !== 'all' || s.agent !== 'all' || s.errors;
    /** @param {TrajectoryEvent} e @returns {boolean} */
    const test = e => (!q || [e.name, e.agent, e.tool, e.model, e.rawType, e.spanId, e.traceId, e.statusMessage, KIND[e.kind][0],
      e.attributes.find(([key]) => key === 'error.type')?.[1]].some(v => !!v && v.toLowerCase().includes(q)))
      && (s.status === 'all' || e.status === s.status) && (s.kind === 'all' || e.kind === s.kind) && (s.agent === 'all' || owner(e, byId) === s.agent)
      && (!s.errors || PROBLEMS.includes(e.status));
    const matched = new Set(run.events.filter(e => !active || test(e)).map(e => e.id));
    const keep = new Set(matched);
    for (const id of matched) for (let at = up(/** @type {TrajectoryEvent} */ (byId.get(id))); at && !keep.has(at.id); at = up(at)) keep.add(at.id);
    const folded = new Set();
    const shown = run.events.filter(e => {
      if (!keep.has(e.id)) return false;
      const parent = up(e);
      if (parent && (s.collapsed[parent.id] || folded.has(parent.id))) { folded.add(e.id); return false; }
      return true;
    });
    return { shown, matched, active, hidden: run.events.length - shown.length };
  }

  /** Return left-to-right tree positions: depth sets the column, leaves take rows in step order and parents sit centred on their children.
   * @param {TrajectoryEvent[]} events
   * @returns {{at: Map<string, {x: number, y: number}>, width: number, height: number}}
   */
  function layout(events) {
    const ids = new Set(events.map(e => e.id));
    /** @type {Map<string, TrajectoryEvent[]>} */
    const kids = new Map();
    const roots = [];
    for (const e of events) {
      if (e.parentId && !e.orphan && ids.has(e.parentId)) kids.set(e.parentId, [...(kids.get(e.parentId) || []), e]);
      else roots.push(e);
    }
    /** @type {Map<string, {x: number, y: number}>} */
    const at = new Map();
    let rows = 0;
    let depth = 0;
    /** @param {TrajectoryEvent} e @param {number} level */
    const place = (e, level) => {
      const children = kids.get(e.id) || [];
      children.forEach(child => place(child, level + 1));
      const y = children.length ? ((at.get(children[0].id)?.y || 0) + (at.get(children[children.length - 1].id)?.y || 0)) / 2 : rows++ * NODE.dy;
      at.set(e.id, { x: level * NODE.dx, y });
      depth = Math.max(depth, level);
    };
    roots.forEach(e => place(e, 0));
    return { at, width: depth * NODE.dx + NODE.w, height: Math.max(0, rows - 1) * NODE.dy + NODE.h };
  }

  /** Return the shown child and parent of an event for arrow-key navigation.
   * @param {TrajectoryEvent} e
   * @param {Set<string>} shown
   * @returns {Record<string, string | null>}
   */
  function links(e, shown) {
    return { 'data-parent': e.parentId && !e.orphan && shown.has(e.parentId) ? e.parentId : null, 'data-child': e.children.find(id => shown.has(id)) || null };
  }

  /** Return the graph: one node per shown event, edges from parent to child, handoffs and retries labelled.
   * @param {TrajectoryEvent[]} shown
   * @param {Set<string>} matched
   * @param {TrajectoryUi} s
   * @returns {VNode}
   */
  function graph(shown, matched, s) {
    const nodes = shown.slice(0, MAX_GRAPH);
    const { at, width, height } = layout(nodes);
    const ids = new Set(nodes.map(e => e.id));
    const focus = s.sel && ids.has(s.sel) ? s.sel : nodes[0]?.id;
    const edges = nodes.filter(e => e.parentId && !e.orphan && at.has(e.parentId)).map(e => {
      const from = /** @type {{x: number, y: number}} */ (at.get(/** @type {string} */ (e.parentId)));
      const to = /** @type {{x: number, y: number}} */ (at.get(e.id));
      const [x1, y1, x2, y2] = [from.x + NODE.w, from.y + NODE.h / 2, to.x, to.y + NODE.h / 2];
      const mid = (x1 + x2) / 2;
      const tag = e.kind === 'handoff' ? 'handoff' : e.retry ? `retry ${e.retry}` : null;
      return [h('path', { class: `tedge${e.kind === 'handoff' ? ' handoff' : ''}${e.retry ? ' retry' : ''}${matched.has(e.id) ? '' : ' muted'}`, d: `M${x1} ${y1}C${mid} ${y1} ${mid} ${y2} ${x2} ${y2}` }),
        tag ? h('text', { class: 'tedge-label', x: mid - 22, y: y2 - 6 }, tag) : null];
    });
    const cards = nodes.map(e => {
      const p = /** @type {{x: number, y: number}} */ (at.get(e.id));
      const [status, glyph] = STATUS[e.status];
      const folded = s.collapsed[e.id] && e.children.length;
      return h('g', { class: `tnode kind-${e.kind} status-${e.status}${s.sel === e.id ? ' sel' : ''}${matched.has(e.id) ? '' : ' muted'}`, transform: `translate(${p.x} ${p.y})`,
        tabindex: e.id === focus ? 0 : -1, role: 'button', 'aria-pressed': s.sel === e.id ? 'true' : 'false', 'aria-label': label(e), 'data-action': 'trajSelect', 'data-id': e.id,
        'data-x': p.x, 'data-y': p.y, ...links(e, ids) },
      h('title', null, label(e)),
      h('rect', { class: 'tshape', width: NODE.w, height: NODE.h, rx: KIND[e.kind][2] }), h('rect', { class: 'tstripe', width: 4, height: NODE.h }),
      h('text', { class: 'tl1', x: 12, y: 16 }, `#${e.seq} · ${KIND[e.kind][0]}${e.retry ? ` · retry ${e.retry}` : ''}${e.orphan ? ' · orphan' : ''}`),
      h('text', { class: 'tl2', x: 12, y: 33 }, clip(e.name, 27)),
      h('text', { class: 'tl3', x: 12, y: 48 }, `${glyph} ${status}${e.durationMs === null ? '' : ` · ${duration(e.durationMs)}`}`),
      folded ? h('text', { class: 'tmore', x: NODE.w - 30, y: 16 }, `+${e.children.length}`) : null);
    });
    return h('div', { class: 'tgraph', 'data-width': width, 'data-height': height },
      h('svg', { class: 'tgraph-svg', role: 'group', 'aria-label': `Trajectory graph, ${plural(nodes.length, 'step')}. Arrow keys move between steps; Left goes to the parent, Right to the first child. The timeline lists the same steps.` },
        h('g', { class: 'tviewport', transform: `translate(${s.zoom.x} ${s.zoom.y}) scale(${s.zoom.k})` }, ...edges, ...cards)),
      shown.length > MAX_GRAPH ? h('p', { class: 'tgraph-note' }, `Showing the first ${MAX_GRAPH} of ${shown.length} steps. Collapse branches, filter, or use the timeline for the rest.`) : null);
  }

  /** Return the timeline: nested rows in step order with their time, duration bar against the run, status and tokens.
   * @param {Trajectory} run
   * @param {TrajectoryEvent[]} shown
   * @param {Set<string>} matched
   * @param {TrajectoryUi} s
   * @returns {VNode}
   */
  function timeline(run, shown, matched, s) {
    const start = run.start ?? 0;
    const span = Math.max(1, (run.lastUpdate ?? start) - start);
    const ids = new Set(shown.map(e => e.id));
    const rows = shown.slice(0, s.limit).map(e => {
      const end = e.end ?? run.lastUpdate ?? e.start;
      const [status, glyph, tone] = STATUS[e.status];
      const folded = !!s.collapsed[e.id];
      return h('li', { class: `trow kind-${e.kind} status-${e.status} depth-${Math.min(e.depth, 8)}${s.sel === e.id ? ' sel' : ''}${matched.has(e.id) ? '' : ' muted'}` },
        e.children.length ? h('button', { class: 'ttoggle', type: 'button', 'data-action': 'trajToggle', 'data-id': e.id, 'aria-expanded': folded ? 'false' : 'true',
          'aria-label': `${folded ? 'Expand' : 'Collapse'} step ${e.seq}` }, icon('chevron', folded ? '' : 'open')) : h('span', { class: 'ttoggle' }),
        h('button', { class: 'tsel', type: 'button', 'data-action': 'trajSelect', 'data-id': e.id, 'aria-pressed': s.sel === e.id ? 'true' : 'false', 'aria-label': label(e), ...links(e, ids) },
          h('span', { class: 'num muted' }, `#${e.seq}`), h('time', { class: 'num' }, when(e.start, s, run)),
          h('span', { class: `tkind kind-${e.kind}` }, icon(KIND[e.kind][1]), KIND[e.kind][0]),
          h('span', { class: 'tname' }, h('span', null, e.name), e.retry ? h('span', { class: 'pill warn' }, `retry ${e.retry}`) : null, e.orphan ? h('span', { class: 'pill' }, 'orphan') : null),
          h('span', { class: 'muted twho' }, e.kind === 'model' ? e.model || '' : e.kind === 'tool' ? '' : e.agent || ''),
          h('span', { class: 'ttrack', 'aria-hidden': 'true' }, h('span', { 'style-width': (e.start - start) / span * 100 }),
            h('span', { class: 'tbar', 'style-width': Math.max(0.6, (end - e.start) / span * 100) })),
          h('span', { class: 'num' }, e.durationMs === null ? (e.status === 'running' ? 'running' : '—') : duration(e.durationMs)),
          h('span', { class: `pill ${tone}`.trim() }, `${glyph} ${status}`),
          h('span', { class: 'num muted' }, e.tokens ? `${count(e.tokens.input)} in · ${count(e.tokens.output)} out` : '')));
    });
    return h('div', { class: 'ttimeline' }, h('ol', { class: 'tlist', 'aria-label': `Trajectory timeline, ${plural(shown.length, 'step')} in execution order` }, ...rows),
      shown.length > s.limit ? button(`Show ${Math.min(PAGE_ROWS, shown.length - s.limit)} more of ${shown.length - s.limit} remaining steps`, 'trajMore', { kind: 'link' }) : null);
  }

  /** Return a label and value row, with a copy button for identifiers; nothing when the value is missing.
   * @param {string} name
   * @param {string | number | null | undefined} value
   * @param {boolean} [copy]
   * @returns {VNode | null}
   */
  function kv(name, value, copy = false) {
    if (value === null || value === undefined || value === '') return null;
    return h('div', { class: 'kv' }, h('span', { class: 'muted' }, name), h('span', { class: 'v' }, String(value)),
      copy ? button('', 'trajCopy', { kind: 'icon', icon: 'copy', data: { value: String(value) }, title: `Copy ${name}` }) : null);
  }

  /** Return a details section, or nothing when it has no rows.
   * @param {string} title
   * @param {Child[]} rows
   * @returns {VNode | null}
   */
  function part(title, rows) {
    const kept = rows.filter(Boolean);
    return kept.length ? h('section', { class: 'tpart' }, h('h3', null, title), ...kept) : null;
  }

  /** Return the details panel of the selected event; telemetry text is shown as text, never as markup.
   * @param {Trajectory} run
   * @param {TrajectoryUi} s
   * @param {Map<string, TrajectoryEvent>} byId
   * @returns {VNode}
   */
  function details(run, s, byId) {
    const e = s.sel ? byId.get(s.sel) : undefined;
    if (!e) {
      return h('aside', { class: 'tdetails empty', 'aria-label': 'Event details' }, h('strong', null, 'Select a step'),
        h('p', { class: 'muted' }, 'Click a node or a row, or move with the arrow keys, to see its trace context, tokens, input, output and errors.'));
    }
    const parent = e.parentId && !e.orphan ? byId.get(e.parentId) : undefined;
    const retried = PROBLEMS.includes(e.status) && parent ? parent.children.map(id => byId.get(id)).find(other => other && other.retry === e.retry + 1 && other.name === e.name) : undefined;
    /** @param {import('../types').TrajectoryContent} c @returns {VNode} */
    const content = c => h('details', { class: 'tcontent', 'data-key': `content:${e.id}:${c.label}` }, h('summary', null, c.label, h('span', { class: 'muted' },
      ` · ${c.chars.toLocaleString('en-US')} characters${c.truncated ? ', first part shown' : ''}${c.redacted ? ', secrets redacted' : ''}`)), h('pre', null, c.text));
    const t = e.tokens;
    return h('aside', { class: 'tdetails', 'aria-label': `Details of step ${e.seq}` },
      h('header', { class: 'tdetails-head' }, h('span', { class: `tkind kind-${e.kind}` }, icon(KIND[e.kind][1]), KIND[e.kind][0]), h('strong', null, e.name),
        h('span', { class: `pill ${STATUS[e.status][2]}`.trim() }, `${STATUS[e.status][1]} ${STATUS[e.status][0]}`)),
      h('div', { class: 'actions-row' }, parent ? button('Parent', 'trajSelect', { icon: 'chevron', data: { id: parent.id }, title: `Go to step ${parent.seq}` }) : null,
        e.children.length ? button(s.collapsed[e.id] ? 'Expand branch' : 'Collapse branch', 'trajToggle', { data: { id: e.id } }) : null,
        s.view === 'graph' ? button('Center', 'trajCenter', { title: 'Center this step in the graph' }) : null),
      part('Overview', [kv('Event type', `${KIND[e.kind][0]} (${e.rawType})`), kv('Step', e.seq), kv('Status', STATUS[e.status][0]), kv('Agent', e.agent), kv('Model', e.model), kv('Tool', e.tool),
        kv('Start', new Date(e.start).toLocaleString('en-GB')), kv('End', e.end === null ? null : new Date(e.end).toLocaleString('en-GB')),
        kv('Duration', e.durationMs === null ? null : duration(e.durationMs)), kv('Retry attempt', e.retry || null),
        e.orphan ? h('p', { class: 'muted' }, `Its parent span ${e.parentId} was not exported, so it is shown as a root.`) : null]),
      part('Trace context', [kv('Trace ID', e.traceId, true), kv('Span ID', e.spanId, true), kv('Parent span ID', e.parentId, true), kv('Run (chat) ID', run.chat, true),
        kv('Conversation ID', e.session && e.session !== run.chat ? e.session : null, true)]),
      part('Error', PROBLEMS.includes(e.status) ? [kv('Kind', STATUS[e.status][0]), kv('Message', e.statusMessage),
        kv('Error type', e.attributes.find(([key]) => key === 'error.type')?.[1]), retried ? button(`Retried as step ${retried.seq}`, 'trajSelect', { kind: 'link', data: { id: retried.id } })
          : h('p', { class: 'muted' }, 'No retry of this step was recorded.')] : []),
      part('Input', e.content.filter(c => c.side === 'input').map(content)),
      part('Output', e.content.filter(c => c.side === 'output').map(content)),
      part('Performance', t ? [kv('Input tokens', t.input.toLocaleString('en-US')), kv('Output tokens', t.output.toLocaleString('en-US')),
        kv('Cached tokens', t.cached.toLocaleString('en-US')), kv('Thinking tokens', t.reasoning ? t.reasoning.toLocaleString('en-US') : null),
        kv('Total tokens', (t.input + t.output).toLocaleString('en-US')), kv('AI units', t.aiu ? t.aiu.toFixed(3) : null)] : []),
      part('Children', e.children.length ? [h('div', { class: 'tchildren' }, ...e.children.slice(0, 12).map(id => byId.get(id)).filter(/** @returns {c is TrajectoryEvent} */ c => !!c)
        .map(child => button(`#${child.seq} ${clip(child.name, 22)}`, 'trajSelect', { kind: 'link', data: { id: child.id } }))),
      e.children.length > 12 ? h('p', { class: 'muted' }, `+${e.children.length - 12} more in the timeline`) : null] : []),
      part('Attributes', e.attributes.length || e.resource.length || e.spanEvents.length || e.links.length ? [h('details', { class: 'tcontent', 'data-key': `attrs:${e.id}` },
        h('summary', null, `${plural(e.attributes.length, 'attribute')}, ${plural(e.resource.length, 'resource attribute')}, ${plural(e.spanEvents.length, 'event')}, ${plural(e.links.length, 'link')}`),
        ...e.attributes.map(([key, value]) => kv(key, value)), ...e.resource.map(([key, value]) => kv(`resource ${key}`, value)),
        ...e.spanEvents.map(item => kv(`event ${item.name}`, new Date(item.at).toLocaleTimeString('en-GB'))), ...e.links.map(link => kv('link', link, true)))] : []));
  }

  /** Return the summary bar: the run's identity, state, counts, tokens and actions.
   * @param {Model} model
   * @param {Trajectory} run
   * @param {TrajectoryUi} s
   * @param {number} now
   * @returns {VNode}
   */
  function summary(model, run, s, now) {
    const live = run.running > 0 || ['working', 'waiting'].includes(model.activity?.session?.status || '');
    const byId = new Map(run.events.map(e => [e.id, e]));
    const pool = run.events.some(e => e.status === 'running') ? run.events.filter(e => e.status === 'running') : run.events;
    const latest = pool.reduce((best, e) => !best || e.start >= best.start ? e : best, /** @type {TrajectoryEvent | null} */ (null));
    const current = latest ? owner(latest, byId) : null;
    const state = s.paused ? 'Paused' : live ? 'Live' : 'Completed';
    const status = run.errors ? `${plural(run.errors, 'error')}` : run.running ? 'running' : 'no errors';
    const otel = model.telemetry.file && model.workspace && model.telemetry.file.startsWith(model.workspace.path) ? model.telemetry.file.slice(model.workspace.path.length + 1).split('\\').join('/') : null;
    /** @param {string} name @param {Child} value @returns {VNode} */
    const stat = (name, value) => h('div', { class: 'tstat' }, h('span', { class: 'muted' }, name), h('strong', null, value));
    return h('section', { class: 'tsummary card' },
      h('div', { class: 'tsummary-head' }, h('div', null, h('span', { class: 'section-label' }, 'Agent trajectory · one chat'), h('h2', null, run.title || 'Untitled chat')),
        h('div', { class: 'tele-chips' }, h('span', { class: `chip status-${state === 'Live' ? 'working' : state === 'Paused' ? 'waiting' : 'idle'}` }, h('span', { class: 'dot', 'aria-hidden': 'true' }), state),
          h('span', { class: `pill ${run.errors ? 'error' : 'good'}` }, status),
          h('span', { class: 'pill' }, run.source === 'telemetry' ? 'from research telemetry spans' : 'from the chat transcript (reduced)'))),
      h('div', { class: 'tstats' }, stat('Started', run.start === null ? '—' : `${new Date(run.start).toLocaleTimeString('en-GB', { hour12: false })} (${ago(new Date(run.start).toISOString(), now)})`),
        stat('Duration', run.durationMs === null ? '—' : `${duration(run.durationMs)}${run.end === null ? ' so far' : ''}`),
        stat('Agents', run.agents.length ? `${run.agents.length} · ${clip(run.agents.join(', '), 40)}` : '—'), stat('Active agent', current || '—'),
        stat('Model calls', run.modelCalls), stat('Tool calls', run.toolCalls), stat('Handoffs', run.handoffs), stat('Errors', run.errors),
        stat('Input tokens', run.source === 'telemetry' ? count(run.input) : '—'), stat('Output tokens', run.source === 'telemetry' ? count(run.output) : '—'),
        stat('Cached tokens', run.source === 'telemetry' ? count(run.cached) : '—'), stat('AI units', run.aiu === null ? 'not recorded' : run.aiu.toFixed(2)),
        stat('Last update', run.lastUpdate === null ? '—' : ago(new Date(run.lastUpdate).toISOString(), now))),
      h('div', { class: 'tids' }, kv('Trace ID', run.traceIds.length ? `${run.traceIds[0]}${run.traceIds.length > 1 ? ` (+${run.traceIds.length - 1} more)` : ''}` : null, !!run.traceIds.length),
        kv('Run (chat) ID', run.chat, true)),
      h('div', { class: 'actions-row' }, button('Refresh', 'refresh', { icon: 'refresh', disabled: model.busy, title: 'Read the telemetry and transcript again' }),
        button(s.paused ? 'Resume live updates' : 'Pause live updates', 'trajPause', { icon: s.paused ? 'pulse' : 'clock',
          title: s.paused ? 'Show the latest telemetry' : 'Keep this picture still; new telemetry keeps arriving and shows when you resume' }),
        otel && run.source === 'telemetry' ? button('Open raw export', 'openFile', { kind: 'link', data: { path: otel }, title: `Open ${otel} beside Mission Control` }) : null));
  }

  /** Return the search and filter controls with the active filters and a one-click reset.
   * @param {Trajectory} run
   * @param {TrajectoryUi} s
   * @param {{matched: Set<string>, active: boolean}} view
   * @returns {VNode}
   */
  function filters(run, s, view) {
    /** @param {'status' | 'kind' | 'agent'} field @param {string} name @param {[string, string][]} options @returns {VNode} */
    const pick = (field, name, options) => h('label', { class: 'tele-field' }, h('span', { class: 'section-label' }, name),
      h('select', { 'data-action': 'trajFilter', 'data-field': field }, ...[['all', `All ${name.toLowerCase()}`], ...options].map(([value, text]) =>
        h('option', { value, selected: s[field] === value }, text))));
    const kinds = [...new Set(run.events.map(e => e.kind))].map(kind => /** @type {[string, string]} */ ([kind, KIND[kind][0]]));
    const statuses = [...new Set(run.events.map(e => e.status))].map(status => /** @type {[string, string]} */ ([status, STATUS[status][0]]));
    const chips = [s.q ? `“${s.q}”` : null, s.status !== 'all' ? STATUS[/** @type {import('../types').TrajectoryStatus} */ (s.status)]?.[0] || s.status : null,
      s.kind !== 'all' ? KIND[/** @type {import('../types').TrajectoryKind} */ (s.kind)]?.[0] || s.kind : null, s.agent !== 'all' ? `agent ${s.agent}` : null, s.errors ? 'errors only' : null].filter(Boolean);
    return h('section', { class: 'tfilters', 'aria-label': 'Search and filter the trajectory' },
      h('label', { class: 'tele-field grow' }, h('span', { class: 'section-label' }, 'Search'),
        h('input', { type: 'search', 'data-action': 'trajQuery', value: s.q, placeholder: 'Operation, agent, tool, model, trace or span ID, error', 'aria-label': 'Search events' })),
      pick('status', 'Statuses', statuses), pick('kind', 'Types', kinds), pick('agent', 'Agents', run.agents.map(name => /** @type {[string, string]} */ ([name, name]))),
      h('button', { class: `filter ${s.errors ? 'on' : ''}`.trim(), type: 'button', 'data-action': 'trajErrors', 'aria-pressed': s.errors ? 'true' : 'false' }, 'Errors only'),
      h('p', { class: 'tfilter-note muted', role: 'status' }, view.active ? `${view.matched.size} of ${plural(run.events.length, 'step')} match: ${chips.join(' · ')}. Ancestors they need stay as muted context.`
        : `${plural(run.events.length, 'step')}`, view.active ? button('Reset filters', 'trajClear', { kind: 'link' }) : null));
  }

  /** Return the view switch and the graph controls.
   * @param {TrajectoryUi} s
   * @returns {VNode}
   */
  function toolbar(s) {
    /** @param {string} value @param {string} text @returns {VNode} */
    const mode = (value, text) => h('button', { class: `filter ${s.view === value ? 'on' : ''}`.trim(), type: 'button', 'data-action': 'trajView', 'data-value': value,
      'aria-pressed': s.view === value ? 'true' : 'false' }, text);
    const graphOnly = s.view === 'graph' ? [button('', 'trajZoomOut', { kind: 'icon', icon: 'minus', title: 'Zoom out' }), button('', 'trajZoomIn', { kind: 'icon', icon: 'plus', title: 'Zoom in' }),
      button('Fit', 'trajFit', { title: 'Fit the whole graph in view' }), button('Reset view', 'trajHome', { title: 'Back to 100% at the top left' })] : [];
    return h('div', { class: 'ttoolbar' }, h('div', { class: 'filters', role: 'group', 'aria-label': 'View' }, mode('graph', 'Graph'), mode('timeline', 'Timeline')),
      h('div', { class: 'actions-row' }, ...graphOnly, button(s.time === 'clock' ? 'Show elapsed time' : 'Show clock time', 'trajTime', { kind: 'link' }),
        button('Collapse all', 'trajCollapseAll', { kind: 'link' }), button('Expand all', 'trajExpandAll', { kind: 'link' })));
  }

  /** Return an empty state with a next step.
   * @param {string} title
   * @param {string} detail
   * @param {Child} [action]
   * @returns {VNode}
   */
  function empty(title, detail, action = null) {
    return h('div', { class: 'empty-state' }, h('strong', null, title), h('p', { class: 'muted' }, detail), action);
  }

  /** Render the Agent Trajectory page.
   * @param {Model} model
   * @param {UiState} ui
   * @param {number} now
   * @returns {Child[]}
   */
  function trajectory(model, ui, now) {
    const s = uiState(ui);
    const run = model.trajectory;
    if (model.trajectoryError || (!run && model.error)) {
      return [h('div', { class: 'notice error', role: 'alert' }, `Mission Control cannot read this chat's trajectory: ${model.trajectoryError || model.error}`,
        button('Retry', 'refresh', { kind: 'primary', icon: 'refresh', disabled: model.busy })), chatPicker(model)];
    }
    if (!run) return [empty('No chat selected', 'Pick a chat of this window to see its agents, model calls, tool calls and handoffs in order. The Live and Telemetry pages follow the same chat.'), chatPicker(model)];
    const view = visible(run, s);
    const byId = new Map(run.events.map(e => [e.id, e]));
    const pending = model.trajectoryPending;
    return [
      summary(model, run, s, now),
      chatPicker(model),
      s.paused ? h('div', { class: 'notice' }, icon('clock'), `Live updates paused${pending ? `: ${plural(pending, 'new step')} waiting` : ''}. Telemetry keeps arriving.`,
        button('Resume', 'trajPause', { kind: 'primary' })) : null,
      run.source === 'transcript' ? h('div', { class: 'notice' }, icon('alert'), 'Reduced view from the chat transcript: research telemetry is off or recorded no spans for this chat, '
        + 'so there are no trace IDs, nesting, durations or tokens.', telemetrySwitch(model)) : null,
      run.running || run.orphans || run.truncated ? h('div', { class: 'notice' }, icon('alert'), ['Partial telemetry:', run.running ? `${plural(run.running, 'step')} still running or not yet exported.` : null,
        run.orphans ? `${plural(run.orphans, 'span')} whose parent was not exported ${run.orphans === 1 ? 'is' : 'are'} shown as roots.` : null,
        run.truncated ? `The oldest ${plural(run.truncated, 'span')} ${run.truncated === 1 ? 'is' : 'are'} left out; the latest 1,000 are shown.` : null].filter(Boolean).join(' ')) : null,
      run.events.length ? filters(run, s, view) : null,
      !run.events.length ? empty('No trajectory events recorded', 'This chat has no recorded steps yet. They appear here as the agent works.')
        : view.shown.length ? [toolbar(s), h('div', { class: `tmain view-${s.view}` }, s.view === 'graph' ? graph(view.shown, view.matched, s) : timeline(run, view.shown, view.matched, s),
          details(run, s, byId))]
          : empty('No steps match these filters', 'The filters removed every step of this run.', button('Reset filters', 'trajClear', { kind: 'primary' })),
    ];
  }

  const api = { trajectory, uiState, visible, layout, NODE, PAGE_ROWS };
  if (modular) module.exports = api;
  else root.hveTrajectory = api;
})(globalThis);
