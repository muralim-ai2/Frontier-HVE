'use strict';
/** Mission Control's dashboard pages: Live, Plan, Progress, Files, Skills and packs, and Settings. */
(function (root) {
  const modular = typeof module === 'object' && module.exports;
  /** @type {typeof globalThis.hveVnode} */
  const { h } = modular ? require('./vnode') : root.hveVnode;
  /** @type {typeof globalThis.hveMarkdown} */
  const markdown = modular ? require('./markdown') : root.hveMarkdown;
  /** @type {typeof globalThis.hveViews} */
  const views = modular ? require('./views') : root.hveViews;
  const { icon, ago, count, plural, pretty, button, chip, needs, attention, eventRow, todoList, bar, telemetrySwitch, askChats, noChat, askPicker, viewing, handoffNotice,
    PAGES } = views;

  /** @typedef {import('../types').Model} Model */
  /** @typedef {import('../types').UiState} UiState */
  /** @typedef {import('../types').VNode} VNode */
  /** @typedef {import('../types').Child} Child */

  const FILTERS = /** @type {const} */ ([['all', 'All'], ['edits', 'Edits'], ['commands', 'Commands'], ['conversation', 'Conversation'], ['problems', 'Problems']]);
  /** @type {Record<string, (event: import('../types').ActivityEvent) => boolean>} */
  const MATCH = { all: () => true, edits: event => event.kind === 'edit', commands: event => event.kind === 'run',
    conversation: event => ['prompt', 'message', 'ask'].includes(event.kind), problems: event => event.state === 'failed' || event.kind === 'guard' };
  const PLAN_STATUS = {
    empty: ['Not written yet', 'The agent writes the plan once you agree the scope in Chat. You can also start it yourself.'],
    draft: ['Draft, not agreed yet', 'Read it and edit it if you want changes. The agent records it as agreed when you approve it in Chat.'],
    agreed: ['Agreed', 'This is the plan the agent works to. If you edit it, the agent reviews your change before it continues.'],
    edited: ['Changed since it was agreed', 'The agent reviews your change and records it (plan-sync) before building further.'],
  };
  const LINKED = { started: 'opened for it here', linked: 'linked by you', continued: 'continued here', created: 'created it', opened: 'reopened it', edited: 'edited its files' };
  /** @type {Record<string, string>} */
  const ABOUT = { 'request.md': 'your request as saved', 'contract.json': 'stages, checklist, sign-offs and decisions', 'plan.md': 'the plan the agent works to',
    loop: 'feature checks, evidence and PR notes', evidence: 'what each check recorded', prs: 'PR notes per feature' };

  /** Return a titled card.
   * @param {string} title
   * @param {Child} body
   * @param {Child} [aside]
   * @returns {VNode}
   */
  function card(title, body, aside = null) {
    return h('section', { class: 'card' }, h('header', { class: 'card-head' }, h('h2', null, title), aside), body);
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

  /** Return a label and value pair.
   * @param {string} label
   * @param {Child} value
   * @returns {VNode}
   */
  function stat(label, value) { return h('div', { class: 'stat' }, h('span', { class: 'muted' }, label), h('strong', null, value)); }

  /** Return a file size in words.
   * @param {number} bytes
   * @returns {string}
   */
  function size(bytes) {
    return bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  /** Return the chats of the ask on screen, a new-chat button for the active ask, and the chats no ask claims.
   * @param {Model} model
   * @param {UiState} ui
   * @param {number} now
   * @returns {VNode}
   */
  function chats(model, ui, now) {
    const ask = model.snapshot?.ask;
    const shown = model.activity?.session?.id;
    const mine = askChats(model);
    const others = ask ? (model.activity?.chats || []).filter(chat => !chat.asks.length) : [];
    /** @param {import('../types').Chat} chat @param {boolean} linked @returns {VNode} */
    const row = (chat, linked) => {
      const how = ask && chat.asks.find(link => link.ask === ask.id);
      const body = [h('span', { class: `dot status-${chat.status}`, 'aria-hidden': 'true' }), h('strong', null, chat.title || 'Untitled chat'),
        h('span', { class: 'muted' }, [how ? LINKED[how.how] : null, { working: 'working', waiting: 'waiting for you', idle: null }[chat.status],
          `last activity ${ago(chat.lastAt, now)}`].filter(Boolean).join(' · '))];
      return h('li', { class: `chat ${chat.id === shown ? 'on' : ''}`.trim() }, linked
        ? h('button', { class: 'chat-pick', type: 'button', 'data-action': 'selectChat', 'data-chat': chat.id, 'aria-current': chat.id === shown ? 'true' : null }, ...body)
        : h('div', { class: 'chat-pick' }, ...body),
      linked ? null : button('Link to this ask', 'linkChat', { kind: 'link', data: { chat: chat.id }, disabled: model.busy }));
    };
    return card(ask ? `Chats for this ask (${mine.length})` : `Chats in this window (${mine.length})`, [
      mine.length ? h('ul', { class: 'chats' }, ...mine.map(chat => row(chat, true))) : h('p', { class: 'muted' }, noChat(model)),
      mine.length && ask && model.pending?.ask === ask.id ? h('p', { class: 'muted' }, noChat(model)) : null,
      others.length ? h('details', { class: 'others', open: !!ui.open['other-chats'], 'data-key': 'other-chats' },
        h('summary', null, `Chats not linked to any ask (${others.length})`), h('ul', { class: 'chats' }, ...others.map(chat => row(chat, false)))) : null],
    ask?.active ? button('New chat for this ask', 'newChat', { icon: 'chat', disabled: model.busy,
      title: 'Open a new, empty Copilot Chat. It is linked to this ask when you send your first message.' }) : null);
  }

  /** Render the Live page: what the agent is doing, the session's numbers, its files and its full activity.
   * @param {Model} model
   * @param {UiState} ui
   * @param {number} now
   * @returns {Child[]}
   */
  function live(model, ui, now) {
    const run = model.activity;
    const session = run?.session;
    if (!session) return [attention(needs(model), false), chats(model, ui, now)];
    const current = session.current;
    const tokens = run?.tokens;
    const events = session.events.filter(MATCH[ui.filter]);
    return [
      attention(needs(model), false),
      chats(model, ui, now),
      h('div', { class: 'grid two' },
        card('Now', [current ? h('div', { class: `current kind-${current.kind}` }, icon(current.kind === 'ask' ? 'question' : 'spark', current.kind === 'ask' ? '' : 'spin'),
          h('div', null, h('strong', null, current.title), current.detail ? h('span', { class: 'muted' }, current.detail) : null, h('time', null, `started ${ago(current.at, now)}`)))
          : h('div', { class: 'current idle' }, icon('clock'), h('div', null, h('strong', null, session.status === 'idle' ? 'Idle' : 'Thinking'),
            h('span', { class: 'muted' }, `Last activity ${ago(session.lastAt, now)}`))),
        session.todos.length ? todoList(session.todos, 50) : h('p', { class: 'muted' }, 'The agent has not shared a to-do list in this chat.')], chip(model)),
        card('This chat', [h('div', { class: 'stats' }, stat('Started', ago(session.started, now)), stat('Turns', session.turns), stat('Tool calls', session.tools),
          stat('Commands', session.commands), stat('Files changed', session.files.length), stat('Failed tool calls', session.failures)),
        tokens ? h('div', { class: 'tokens' }, h('div', { class: 'section-label' }, 'Model use (research telemetry)'),
          h('div', { class: 'md-table' }, h('table', null, h('thead', null, h('tr', null, h('th', null, 'Model'), h('th', null, 'Calls'), h('th', null, 'Input'), h('th', null, 'Cached'), h('th', null, 'Output'))),
            h('tbody', null, ...tokens.models.map(use => h('tr', null, h('td', null, use.model), h('td', null, use.failed ? `${use.calls} (${use.failed} stopped)` : use.calls),
              h('td', null, count(use.input)), h('td', null, count(use.cached)), h('td', null, count(use.output))))))),
          h('p', { class: 'muted' }, `${tokens.aiu.toFixed(1)} AI units used by this chat.`))
          : h('div', { class: 'tokens off' }, h('p', { class: 'muted' }, 'Token use and cost appear here for chats started while research telemetry is on.'), telemetrySwitch(model))])),
      run?.errors?.failures.length ? card(run.errors.paused ? 'Paused by the error guard' : 'Failed commands in a row (error guard)', h('ol', { class: 'failures' },
        ...run.errors.failures.map(failure => h('li', null, h('code', null, failure.command), h('pre', null, failure.output))))) : null,
      session.files.length ? card(`Files changed (${session.files.length})`, h('div', { class: 'files' }, ...session.files.map(file =>
        h('button', { class: 'file', type: 'button', 'data-action': 'openFile', 'data-path': file.path }, icon('file'), h('span', null, file.path),
          h('span', { class: 'muted' }, `${plural(file.count, 'edit')} · ${ago(file.last, now)}`))))) : null,
      card('Activity', h('ol', { class: 'timeline' }, ...(events.length ? events.map(event => eventRow(event, now, false)) : [h('li', { class: 'muted' }, 'Nothing matches this filter yet.')])),
        h('div', { class: 'filters', role: 'group', 'aria-label': 'Filter activity' }, ...FILTERS.map(([value, label]) =>
          h('button', { class: `filter ${ui.filter === value ? 'on' : ''}`.trim(), type: 'button', 'aria-pressed': ui.filter === value ? 'true' : 'false',
            'data-action': 'filter', 'data-value': value }, label)))),
    ];
  }

  /** Render the sign-off list with confirmed Accept and Request changes actions.
   * @param {Model} model
   * @returns {VNode}
   */
  function signoff(model) {
    const snap = /** @type {import('../types').Snapshot} */ (model.snapshot);
    const blocked = model.busy || snap.pendingPlanTicks || !snap.ask?.active;
    return h('ul', { class: 'signoff' }, ...snap.reviews.map(review => {
      const settled = ['accepted', 'skipped'].includes(review.decision);
      return h('li', { class: `review decision-${review.decision}` },
        h('div', { class: 'review-text' }, h('span', { class: 'section-label' }, review.item), h('strong', null, review.title),
          h('span', { class: 'muted' }, review.ready ? 'Done and ready for your review.' : `Status: ${review.status}. You can accept it once it is done.`),
          review.note ? h('span', { class: 'quote' }, review.note) : null),
        h('div', { class: 'review-actions' }, h('span', { class: `pill ${settled ? 'good' : review.decision === 'changes' ? 'warn' : ''}`.trim() },
          { open: 'Open', accepted: 'Accepted', changes: 'Changes requested', skipped: 'Continued without review' }[review.decision] || review.decision),
        button('Accept', 'review', { kind: 'primary', icon: 'check', data: { item: review.item, revision: snap.revision, value: 'accepted' },
          disabled: blocked || settled || !review.ready || snap.planState !== 'synced',
          title: !snap.ask?.active ? 'Make this ask active to sign off' : snap.planState !== 'synced' ? 'Agree the plan first' : undefined }),
        button('Request changes', 'review', { data: { item: review.item, revision: snap.revision, value: 'changes' }, disabled: blocked,
          title: !snap.ask?.active ? 'Make this ask active to sign off' : undefined })));
    }), snap.reviews.length ? null : h('li', { class: 'muted' }, 'No milestones yet.'));
  }

  /** Render the Plan page: the plan as formatted text, its sign-offs and the generated skills section.
   * @param {Model} model
   * @param {UiState} ui
   * @param {number} now
   * @returns {Child[]}
   */
  function plan(model, ui, now) {
    const snap = model.snapshot;
    if (!snap?.ask || !snap.plan) return [empty('No ask yet', 'Create an ask to get a plan you can read, edit and sign off.', button('New ask', 'newAsk', { kind: 'primary', icon: 'plus', disabled: model.busy }))];
    const status = snap.plan.status;
    const [title, detail] = PLAN_STATUS[status];
    return [
      h('div', { class: `plan-status status-${status}` }, icon(status === 'agreed' ? 'check' : 'map'),
        h('div', null, h('strong', null, status === 'agreed' && snap.plan.agreedAt ? `${title} ${ago(snap.plan.agreedAt, now)}` : title), h('span', null, detail)),
        button('Edit plan', 'editPlan', { kind: 'primary', icon: 'pencil', title: 'Open plan.md in an editor beside Mission Control' })),
      snap.pendingPlanTicks ? h('div', { class: 'notice' }, 'You ticked items in plan.md. The agent records them at its next step; sign-off here waits until then.') : null,
      snap.plan.body ? h('article', { class: 'markdown card' }, ...markdown.render(snap.plan.body)) : null,
      card('Sign-off', [signoff(model), snap.options.length ? h('div', { class: 'options' }, h('span', { class: 'muted' }, 'Options:'),
        ...snap.options.map(option => h('span', { class: 'pill' }, `${pretty(option.item.replace(/^opt:/, ''))}: ${option.value}`))) : null]),
      snap.plan.skills ? h('details', { class: 'card', open: !!ui.open['plan-skills'], 'data-key': 'plan-skills' },
        h('summary', null, 'Skills and tools for this ask (generated)'), h('div', { class: 'markdown' }, ...markdown.render(snap.plan.skills))) : null,
    ];
  }

  /** Render the Progress page: stages, feature checks, evidence and decisions.
   * @param {Model} model
   * @param {UiState} ui
   * @param {number} now
   * @returns {Child[]}
   */
  function progress(model, ui, now) {
    const snap = model.snapshot;
    if (!snap?.ask) return [empty('No ask yet', 'Progress appears once an ask starts.')];
    const passing = snap.features.filter(feature => feature.passes).length;
    return [
      card('Stages', h('ol', { class: 'stages' }, ...snap.stages.map(stage => h('li', { class: `stage stage-${stage.status}` }, h('span', { class: 'stage-dot' }),
        h('div', null, h('strong', null, pretty(stage.name)), h('span', { class: 'muted' }, stage.goal), h('span', { class: 'meta' }, `${stage.persona} · ${stage.status}`)))))),
      card('Feature checks (whole project)', snap.features.length ? [bar(passing, snap.features.length, 'Features passing'), h('ul', { class: 'features' }, ...snap.features.map(feature =>
        h('li', { class: 'feature' }, icon(feature.passes ? 'check' : 'clock'), h('div', null, h('strong', null, feature.name), h('span', { class: 'muted' }, feature.description),
          h('code', null, feature.command), feature.ask && feature.ask !== snap.ask?.id ? h('span', { class: 'meta' }, `From ask ${feature.ask}`) : null),
        feature.check ? h('div', { class: 'feature-result' }, h('span', { class: `pill ${feature.check.exitCode === 0 ? 'good' : 'error'}` }, `exit ${feature.check.exitCode}`),
          button('Output', 'openFile', { kind: 'link', data: { path: feature.check.source } })) : h('span', { class: 'pill' }, feature.passes ? 'passing, no record' : 'not run'))))]
        : h('p', { class: 'muted' }, 'No feature checks yet. For larger builds the agent splits the work into features, each with a check that must pass.'),
      h('span', { class: 'muted' }, snap.features.length ? `${passing} of ${snap.features.length} passing` : '')),
      card('Evidence files', snap.files.length ? h('div', { class: 'files' }, ...snap.files.map(file => h('button', { class: 'file', type: 'button', 'data-action': 'openFile', 'data-path': file },
        icon('file'), h('span', null, file.split('\\').join('/'))))) : h('p', { class: 'muted' }, 'No evidence recorded yet.')),
      card('Decisions', snap.decisions.length ? h('ol', { class: 'timeline' }, ...snap.decisions.slice().reverse().map(decision => h('li', { class: 'event' },
        h('span', { class: 'event-icon' }, icon('flag')), h('div', { class: 'event-body' }, h('div', { class: 'event-title' }, `${decision.stage}: ${decision.choice}`),
          decision.why ? h('div', { class: 'event-detail' }, decision.why) : null), h('time', null, ago(decision.ts, now)))))
        : h('p', { class: 'muted' }, 'No decisions recorded yet.')),
    ];
  }

  /** Render the Files page: the folder of the ask on screen as a tree; files open beside Mission Control.
   * @param {Model} model
   * @param {UiState} ui
   * @param {number} now
   * @returns {Child[]}
   */
  function files(model, ui, now) {
    const tree = model.files;
    if (model.filesError) return [h('div', { class: 'notice error' }, model.filesError)];
    if (!tree) return [empty('No ask yet', 'Each ask keeps its request, contract, plan and evidence in its own folder under .hve/asks/.',
      button('New ask', 'newAsk', { kind: 'primary', icon: 'plus', disabled: model.busy }))];
    /** @param {import('../types').FileNode} node @param {number} depth @returns {VNode} */
    const item = (node, depth) => {
      const about = ABOUT[node.name];
      if (node.kind === 'folder') {
        const key = `dir:${node.path}`;
        return h('li', null, h('details', { class: 'folder', open: ui.open[key] ?? depth === 0, 'data-key': key },
          h('summary', null, icon('folder'), h('span', { class: 'name' }, node.name),
            h('span', { class: 'muted' }, [about, node.size ? plural(node.size, 'item') : 'empty'].filter(Boolean).join(' · '))),
          node.children.length ? h('ul', { class: 'tree' }, ...node.children.map(child => item(child, depth + 1))) : null));
      }
      if (node.kind === 'other') return h('li', { class: 'muted other' }, icon('file'), `${node.name}: a link or special file, not opened`);
      return h('li', null, h('button', { class: 'file', type: 'button', 'data-action': 'openFile', 'data-path': node.path, title: `Open ${node.path}` }, icon('file'),
        h('span', { class: 'name' }, node.name), h('span', { class: 'muted' }, [about, size(node.size), ago(node.modified, now)].filter(Boolean).join(' · '))));
    };
    return [card(`${tree.path}/`, [h('ul', { class: 'tree root' }, ...tree.entries.map(node => item(node, 0))),
      tree.truncated ? h('p', { class: 'muted' }, `Showing ${tree.count} entries, up to 6 folders deep. Show the folder in the Explorer to see everything.`) : null],
    button('Show in Explorer', 'revealAsk', { icon: 'folder', title: 'Reveal this ask\'s folder in VS Code\'s Explorer' }))];
  }

  /** Render the Skills and packs page: what loads into every request, and the expertise packs installed.
   * @param {Model} model
   * @returns {Child[]}
   */
  function skills(model) {
    const snap = model.snapshot;
    const load = snap?.skillLoad;
    const session = model.activity?.loadout;
    return [
      card('Skills for this ask', snap?.skills.length && load ? [
        h('div', { class: 'load' }, bar(load.tokens, Math.max(load.maxTokens, load.tokens), 'Skill tokens against the guideline'),
          h('span', { class: load.overBudget ? 'warn-text' : 'muted' }, `${plural(snap.skills.length, 'skill')}, ${count(load.tokens)} tokens of a ${count(load.maxTokens)}-token guideline${load.choice ? ` (you chose: ${load.choice})` : ''}`)),
        h('ul', { class: 'skills' }, ...snap.skills.map(skill => h('li', null, h('button', { class: 'skill', type: 'button', 'data-action': 'openFile', 'data-path': `.hve/skills/${skill.name}/SKILL.md`, title: 'Open SKILL.md' },
          h('strong', null, skill.name), h('span', { class: `pill ${skill.status === 'admitted' ? 'good' : ''}`.trim() }, skill.status),
          h('span', { class: 'muted' }, skill.why || skill.reason), h('span', { class: 'muted num' }, `${count(skill.tokens)} tokens`)))))]
        : h('p', { class: 'muted' }, 'Skills are chosen when an ask starts.'),
      session ? h('span', { class: 'muted' }, `Loaded in the chat shown on Live: ${plural(session.skills, 'skill')}, ${count(session.tokens)} tokens.`) : null),
      card('Always-on harness skills', snap?.pluginSkills.length ? h('div', { class: 'chips' }, ...snap.pluginSkills.map(name => h('span', { class: 'pill' }, name)))
        : h('p', { class: 'muted' }, 'Listed once an ask starts.'), h('span', { class: 'muted' }, 'Shipped with Frontier HVE and available to every agent.')),
      card('Expertise packs', [
        h('p', { class: 'muted' }, 'A pack adds a practice\'s skills, agents, templates and lifecycles. Packs are installed for you, not per workspace.'),
        model.packsError ? h('div', { class: 'notice error' }, model.packsError)
          : model.packs === null ? h('p', { class: 'muted' }, 'Reading installed packs…')
            : model.packs.length ? h('ul', { class: 'packs' }, ...model.packs.map(pack => h('li', { class: 'pack' }, icon('box'),
              h('div', null, h('strong', null, `${pack.name} ${pack.version}`), h('span', { class: 'muted' }, [plural(pack.agents.length, 'agent'), plural(pack.lifecycles.length, 'lifecycle'),
                plural(pack.templates.length, 'template'), plural(pack.knowledge.length, 'knowledge document')].join(' · ')), h('span', { class: 'muted' }, pack.source)),
              h('span', { class: `pill ${pack.enabled ? 'good' : 'warn'}` }, pack.enabled ? 'enabled' : `disabled${pack.disabledReason ? `: ${pack.disabledReason}` : ''}`))))
              : h('p', { class: 'muted' }, 'No packs installed.'),
        h('div', { class: 'actions' }, action('Install a pack…', 'installPack', 'From a folder, a .hveplugin file, a git URL or your organisation\'s index. You see its source, hash and tools before it installs.', model),
          action('Manage packs…', 'managePacks', 'Enable, disable, update or remove installed packs.', model))]),
    ];
  }

  /** Return an explained command button.
   * @param {string} label
   * @param {string} name
   * @param {string} detail
   * @param {Model} model
   * @returns {VNode}
   */
  function action(label, name, detail, model) {
    return h('button', { class: 'action', type: 'button', 'data-action': 'command', 'data-name': name, disabled: model.busy }, h('strong', null, label), h('span', { class: 'muted' }, detail));
  }

  /** Render the Settings page: the folder followed, the harness, telemetry and set-up commands.
   * @param {Model} model
   * @returns {Child[]}
   */
  function settings(model) {
    const guard = model.connection.guard;
    return [
      card('Workspace', h('div', { class: 'stats' }, stat('Folder', model.workspace ? model.workspace.path : 'None selected'),
        stat('Frontier HVE', model.connection.version), stat('Python', model.connection.python || 'not found: install Python 3.11+'),
        stat('Loop guard', guard === 'advise' ? 'Advisory: warns in chat, does not block' : guard === 'enforce' ? 'Enforced: blocks' : 'unknown'),
        stat('Live activity from', model.transcripts || 'no workspace storage')),
      button('Change folder', 'selectWorkspace', { icon: 'folder', disabled: model.busy })),
      card('Research telemetry', [telemetrySwitch(model), h('p', { class: 'muted' }, 'When on, Copilot writes every new chat, with its full content, tokens and cost, to '
        + `${model.telemetry.file || '.hve/runs/copilot-otel.jsonl'}. Mission Control and the ask report use it for token and cost figures. Turn it off when you are done.`)]),
      card('Set-up', h('div', { class: 'actions' }, action('Set up this workspace', 'setup', 'Choose assisted or pro mode, add .hve/ to .gitignore, and see how many tokens load into every request.', model),
        action('Install for other tools', 'installHarnesses', 'Make the HVE agents, skills and guards available in Copilot CLI, Claude Code, Codex, Cursor or the Copilot cloud agent.', model))),
    ];
  }

  /** Render the dashboard: the ask picker and title, page tabs and the selected page.
   * @param {Model} model
   * @param {UiState} ui
   * @param {number} now
   * @returns {VNode}
   */
  function dashboard(model, ui, now) {
    const snap = model.snapshot;
    const pages = { live, plan, progress, files, skills: () => skills(model), settings: () => settings(model) };
    return h('div', { class: `dashboard ${model.busy ? 'busy' : ''}`.trim() },
      h('header', { class: 'dash-head' }, h('div', { class: 'dash-title' }, icon('logo', 'brand'),
        h('div', null, h('span', { class: 'section-label' }, snap?.project ? pretty(snap.project.name) : 'Frontier HVE'), h('h1', null, snap?.ask?.title || 'Mission Control')), chip(model),
        button('New ask', 'newAsk', { icon: 'plus', disabled: model.busy || !model.workspace, title: 'Start a new piece of work in this project' }),
        button('', 'refresh', { kind: 'icon', icon: 'refresh', title: 'Refresh', disabled: model.busy })),
      askPicker(model),
      h('nav', { class: 'tabs', 'aria-label': 'Mission Control pages' }, ...PAGES.map(([page, label, glyph]) => h('button', { class: 'tab', type: 'button', 'data-action': 'go', 'data-page': page,
        'aria-current': ui.page === page ? 'page' : null }, icon(glyph), label)))),
      model.workspaceMessage ? h('div', { class: 'notice' }, model.workspaceMessage, button('Choose folder', 'selectWorkspace')) : null,
      handoffNotice(model),
      viewing(model),
      h('main', { class: `page page-${ui.page}` }, ...pages[ui.page](model, ui, now)));
  }

  const api = { dashboard, live, plan, progress, files, skills, settings };
  if (modular) module.exports = api;
  else root.hvePages = api;
})(globalThis);
