'use strict';
/** Render escaped, theme-aware Mission Control content for both extension surfaces. */
const path = require('node:path');
const PAGES = ['overview', 'evidence', 'approvals', 'skills', 'settings'];
const ICONS = {
  logo: '<path d="m12 2 9 5v10l-9 5-9-5V7Z"/><path d="M8 8v8m8-8v8m-8-4h8"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 11 3 3 5-5"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-3c0-6 16-6 16 0v3"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  chat: '<path d="M4 4h16v12H9l-5 4Z"/><path d="M8 8h8m-8 4h5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M4 12h15m-6-6 6 6-6 6"/>',
  box: '<path d="m12 3 9 5v9l-9 5-9-5V8Zm0 10v9M3 8l9 5 9-5M7 5l9 5"/>',
  gear: '<circle cx="12" cy="12" r="4"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2"/>',
  refresh: '<path d="M20 5v5h-5M4 19v-5h5"/><path d="M19 9A7 7 0 0 0 6 6M5 15a7 7 0 0 0 13 3"/>',
  file: '<path d="M5 2h10l4 4v16H5Zm10 0v5h4M8 12h8m-8 4h6"/>',
};

/** Escape text for HTML content and quoted attributes.
 * @param {string | number} value
 * @returns {string}
 */
function escape(value) {
  return String(value).replace(/[&<>"']/g, character => {
    const entities = new Map([['&', '&amp;'], ['<', '&lt;'], ['>', '&gt;'], ['"', '&quot;'], ["'", '&#39;']]);
    return entities.get(character) || character;
  });
}

/** Render a locally defined decorative icon.
 * @param {keyof typeof ICONS} name
 * @returns {string}
 */
function icon(name) { return `<svg aria-hidden="true" viewBox="0 0 24 24">${ICONS[name]}</svg>`; }

/** Render an action button whose payload contains no executable code.
 * @param {string} label
 * @param {string} action
 * @param {{primary?: boolean, disabled?: boolean, icon?: keyof typeof ICONS, data?: Record<string, string>, className?: string}} [options]
 * @returns {string}
 */
function button(label, action, options = {}) {
  const attributes = Object.entries(options.data || {}).map(([key, value]) => `data-${key}="${escape(value)}"`).join(' ');
  return `<button class="button ${options.primary ? 'primary' : ''} ${options.className || ''}" data-action="${escape(action)}" ${attributes}
    ${options.disabled ? 'disabled' : ''}>${options.icon ? icon(options.icon) : ''}<span>${escape(label)}</span></button>`;
}

/** Render a labeled status pill.
 * @param {string} label
 * @param {string} [kind]
 * @returns {string}
 */
function pill(label, kind = '') { return `<span class="pill ${kind}">${escape(label)}</span>`; }

/** Render a titled content panel.
 * @param {string} title
 * @param {string} content
 * @returns {string}
 */
function panel(title, content) { return `<section class="panel"><h2>${escape(title)}</h2><div class="panel-body">${content}</div></section>`; }

/** Render a secondary navigation row.
 * @param {string} page
 * @param {string} selected
 * @param {string} label
 * @param {keyof typeof ICONS} glyph
 * @param {number | null} [count]
 * @returns {string}
 */
function nav(page, selected, label, glyph, count = null) {
  return `<button class="nav-item" data-action="navigate" data-page="${page}" ${selected === page ? 'aria-current="page"' : ''}>
    ${icon(glyph)}<span>${label}</span>${count === null ? '' : `<span class="count">${count}</span>`}</button>`;
}

/** Render error and workflow notices without obscuring their details.
 * @param {import('./types').ViewState} state
 * @returns {string}
 */
function notices(state) {
  if (state.error) return `<div class="notice error" role="alert"><strong>Action required</strong><p>${escape(state.error)}</p>${button('Refresh', 'refresh', { icon: 'refresh' })}</div>`;
  const snapshot = state.snapshot;
  if (state.workspaceMessage) return `<div class="notice"><p>${escape(state.workspaceMessage)}</p>${button('Select workspace', 'selectWorkspace')}</div>`;
  if (snapshot?.pendingPlanTicks) return '<div class="notice warning"><strong>Plan checkboxes changed</strong><p>Continue in Chat to reconcile the edited checklist before recording another sign-off.</p></div>';
  if (snapshot?.planState === 'unsynced') return '<div class="notice warning"><strong>The plan changed</strong><p>Continue in Chat to review and synchronize the plan. Acceptance is held until then.</p></div>';
  return '';
}

/** Render the compact Primary Side Bar.
 * @param {import('./types').ViewState} state
 * @param {string} selected
 * @returns {string}
 */
function sidebar(state, selected) {
  const s = state.snapshot;
  const pending = s ? s.reviews.filter(review => review.ready && !['accepted', 'skipped'].includes(review.decision)).length : 0;
  const passes = s ? s.features.filter(feature => feature.passes).length : 0;
  const disabled = state.busy || !s || !!state.error;
  return `<div class="sidebar">
    <header class="brand">${icon('logo')}<strong>Frontier HVE</strong>${pill('LIVE', 'good')}</header>
    ${notices(state)}
    <section class="project-card"><button class="workspace-picker" data-action="selectWorkspace" title="${escape(s?.workspace || 'Select a local workspace')}">
      <strong>${escape(s?.project?.name || 'Choose your workspace')}</strong><span>${escape(s ? path.basename(s.workspace) : 'No workspace selected')} &rsaquo;</span></button>
      ${button('New task', 'newTask', { primary: true, icon: 'plus', disabled })}</section>
    <nav aria-label="Harness navigation">${nav('overview', selected, 'Overview', 'grid')}${nav('evidence', selected, 'Evidence', 'shield', s?.features.filter(f => f.check).length || 0)}${nav('approvals', selected, 'Approvals', 'user', pending)}</nav>
    <section class="active-task"><div class="section-label">CURRENT TASK</div>
      ${s?.ask ? `<p class="task-title">${escape(s.ask.request)}</p><div class="tag-row">${pill(s.ask.agent, 'accent')}${pill(s.ask.lifecycle)}</div>
        <progress value="${passes}" max="${Math.max(s.features.length, 1)}" aria-label="${passes} of ${s.features.length} features marked passing"></progress>
        <div class="progress-label">${passes} of ${s.features.length} features marked passing</div>
        <div class="feature-list">${s.features.map(feature => `<button class="feature-row" data-action="inspectCheck" data-name="${escape(feature.name)}">${icon(feature.passes ? 'check' : 'clock')}<span>${escape(feature.name)}</span><span class="sr-only">${feature.passes ? 'marked passing' : 'pending'}</span></button>`).join('') || '<p class="muted">No feature checks defined yet. Continue in Chat to plan the work.</p>'}</div>
        ${button('Continue in Chat', 'continue', { icon: 'chat', disabled })}
        <div class="ask-id">${escape(s.ask.id)}</div>` : '<p class="muted">No active task. Start a task to use the existing harness lifecycle.</p>'}
    </section>
    <footer><nav aria-label="Harness configuration">${nav('skills', selected, 'Skills & packs', 'box')}${nav('settings', selected, 'Workspace setup', 'gear')}</nav>
      <div class="runtime"><span>${escape(state.connection)}</span><span>Telemetry ${state.telemetry ? 'on' : 'off'}</span></div>
      ${button('Refresh', 'refresh', { icon: 'refresh', disabled: state.busy, className: 'subtle' })}
    </footer></div>`;
}

/** Render the overview using only recorded project state.
 * @param {import('./types').ViewState} state
 * @returns {string}
 */
function overview(state) {
  const s = state.snapshot;
  if (!s) return '';
  const pending = s.reviews.filter(review => review.ready && !['accepted', 'skipped'].includes(review.decision));
  const heading = !s.ask ? 'Start with an outcome.' : pending.length ? 'Your work is ready for review.' : 'Keep your next step in focus.';
  const description = !s.ask ? 'Create a real task in this workspace using the installed Enterprise Harness.'
    : pending.length ? 'Recorded results are available. Review the evidence before accepting a milestone. Nothing is pushed by this UI.'
      : 'Continue with the existing harness in Copilot Chat. This view updates as its project and evidence files change.';
  const heroAction = !s.ask ? button('New task', 'newTask', { primary: true, icon: 'plus', disabled: state.busy || !!state.error })
    : pending.length ? button('Review milestones', 'navigate', { primary: true, icon: 'arrow', data: { page: 'approvals' } })
      : button('Continue in Chat', 'continue', { primary: true, icon: 'chat', disabled: state.busy || !!state.error });
  return `<div class="page-heading"><div><h1>Mission Control</h1><p>One task. Clear evidence. You decide what ships.</p></div>${s.ask ? button('Continue in Chat', 'continue', { icon: 'chat', disabled: state.busy || !!state.error }) : ''}</div>
    <section class="hero"><div class="section-label">YOUR NEXT MOVE</div><h2>${heading}</h2><p>${description}</p><div class="actions">${heroAction}${s.ask ? button('Inspect evidence', 'navigate', { data: { page: 'evidence' } }) : ''}</div></section>
    <div class="signals"><article><span>Feature status</span><strong>${s.features.filter(f => f.passes).length} <small>/ ${s.features.length} marked passing</small></strong><p>Open evidence for the recorded check.</p></article>
    <article><span>Human review</span><strong>${pending.length} <small>ready for review</small></strong><p>Checks do not equal approval.</p></article>
    <article><span>Research telemetry</span><strong>${state.telemetry ? 'On' : 'Off'}</strong><p>${state.telemetry ? 'Recording is controlled by the original harness.' : 'No usage or cost is inferred.'}</p></article></div>
    <div class="columns">${panel('Current delivery', s.ask ? `<h3>${escape(s.ask.request)}</h3><dl><dt>Agent</dt><dd>${escape(s.ask.agent)}</dd><dt>Lifecycle</dt><dd>${escape(s.ask.lifecycle)}</dd><dt>Plan</dt><dd>${escape(s.planState)}</dd><dt>Loop guard</dt><dd>${escape(state.guard)}</dd></dl><div class="stages">${s.reviews.filter(r => r.item.startsWith('stage:')).map(r => `<div>${pill(r.status, r.status === 'done' ? 'good' : '')}<span>${escape(r.title)}</span></div>`).join('')}</div>` : '<p class="muted">No active task in this workspace.</p>')}
    ${panel('Recorded decisions', s.decisions.length ? `<ol class="timeline">${s.decisions.slice(-5).reverse().map(d => `<li><strong>${escape(d.stage)} &middot; ${escape(d.choice)}</strong><p>${escape(d.why)}</p><time>${escape(d.ts)}</time></li>`).join('')}</ol>` : '<p class="muted">No decisions recorded for the active task.</p>')}</div>`;
}

/** Render recorded check output and approved local file links.
 * @param {import('./types').ViewState} state
 * @param {string | null} selected
 * @returns {string}
 */
function evidencePage(state, selected) {
  const s = state.snapshot;
  if (!s) return '';
  const feature = s.features.find(f => f.name === selected) || s.features[0];
  return `<div class="page-heading"><div><h1>Evidence, not promises.</h1><p>Recorded commands, exit codes, and their source files.</p></div></div>
    <div class="check-list">${s.features.map(f => `<button class="check-row" data-action="inspectCheck" data-name="${escape(f.name)}" aria-pressed="${f === feature}">
      ${icon(f.check?.exitCode === 0 ? 'check' : 'clock')}<span><strong>${escape(f.name)}</strong><small>${escape(f.description)}</small></span>${pill(f.check ? `Recorded exit ${f.check.exitCode}` : 'No result', f.check?.exitCode === 0 ? 'good' : 'warning')}</button>`).join('') || '<div class="notice">No feature checks have been defined for this project.</div>'}</div>
    ${feature ? panel(`${feature.name} - recorded output`, feature.check
      ? `<p class="source">Source: ${escape(feature.check.source)}</p><pre><code>$ ${escape(feature.check.command)}\n\n${escape(feature.check.output)}\n\nRecorded exit code: ${feature.check.exitCode}</code></pre>${button('Open source record', 'openFile', { icon: 'file', data: { path: feature.check.source } })}`
      : `<p>No recorded result is available. The feature is ${feature.passes ? 'marked passing, but that flag is not a substitute for evidence' : 'not marked passing'}.</p><pre><code>${escape(feature.command)}</code></pre>`) : ''}
    <div class="notice">These are stored results, not a fresh test run. This UI does not execute feature check commands or infer success from agent messages.</div>
    ${panel('Files and artifacts', `<div class="artifact-list">${s.files.map(file => button(file, 'openFile', { icon: 'file', data: { path: file }, className: 'artifact' })).join('') || '<p class="muted">No evidence files available yet.</p>'}</div>`)}`;
}

/** Render explicitly confirmed human review actions.
 * @param {import('./types').ViewState} state
 * @returns {string}
 */
function approvals(state) {
  const s = state.snapshot;
  if (!s) return '';
  return `<div class="page-heading"><div><h1>The last word is yours.</h1><p>Live sign-offs use the harness lifecycle.</p></div></div>
    <div class="review-list">${s.reviews.map(review => {
      const data = { item: review.item, revision: s.revision };
      const blocked = state.busy || !!state.error || s.pendingPlanTicks;
      const accepted = ['accepted', 'skipped'].includes(review.decision);
      return `<section class="review-card"><div class="row"><span class="section-label">${escape(review.item)}</span>${pill(review.decision === 'skipped' ? 'Continued without review' : review.decision, accepted ? 'good' : 'warning')}</div>
        <h2>${escape(review.title)}</h2><p class="muted">Recorded status: ${escape(review.status)}. ${review.ready ? 'Ready for human review.' : 'Acceptance is unavailable until this item is complete and its required record exists.'}</p>
        ${review.note ? `<p class="review-note">${escape(review.note)}</p>` : ''}
        <div class="actions">${button('Inspect evidence', 'navigate', { data: { page: 'evidence' } })}
        ${button('Accept', 'review', { primary: true, icon: 'check', data: { ...data, value: 'accepted' }, disabled: blocked || accepted || !review.ready || s.planState !== 'synced' })}
        ${button('Request changes', 'review', { data: { ...data, value: 'changes' }, disabled: blocked })}</div></section>`;
    }).join('') || '<div class="notice">No review items exist yet. Continue in Chat to define and complete the work.</div>'}</div>
    <div class="notice">Accepting records a real human decision. It does not push a branch, merge code, or automatically mark a tracker item validated.</div>`;
}

/** Render live skill selections and existing expertise-pack commands.
 * @param {import('./types').ViewState} state
 * @returns {string}
 */
function skills(state) {
  return `<div class="page-heading"><div><h1>Expertise, on purpose.</h1><p>Selections recorded in the active task's contract.</p></div></div>
    <div class="actions">${button('Install expertise pack', 'baseCommand', { data: { command: 'installPack' }, disabled: state.busy || !!state.error })}${button('Manage packs', 'baseCommand', { data: { command: 'managePacks' }, disabled: state.busy || !!state.error })}</div>
    <div class="skill-list">${state.snapshot?.skills.map(skill => `<article class="review-card">${pill(skill.status, skill.status === 'admitted' ? 'good' : 'warning')}<h2>${escape(skill.name)}</h2><p>${escape(skill.reason)}</p></article>`).join('') || '<div class="notice">No skills are recorded for an active task. A selected skill is not proof that an agent used it.</div>'}</div>`;
}

/** Render connection details and original harness settings commands.
 * @param {import('./types').ViewState} state
 * @returns {string}
 */
function settings(state) {
  const disabled = state.busy || !!state.error;
  return `<div class="page-heading"><div><h1>Know what's active.</h1><p>Existing harness commands; no duplicate configuration.</p></div></div>
    ${panel('Connection', `<dl><dt>Harness</dt><dd>${escape(state.connection)}</dd><dt>Python</dt><dd>${escape(state.python)}</dd><dt>Loop guard</dt><dd>${escape(state.guard)}</dd><dt>Workspace</dt><dd>${escape(state.snapshot?.workspace || 'Not selected')}</dd></dl>
    ${button('Select workspace', 'selectWorkspace')}`)}
    ${panel('Harness controls', `<div class="settings-actions">${button('Set up workspace', 'baseCommand', { data: { command: 'setup' }, disabled })}
    ${button('Install for other harnesses', 'baseCommand', { data: { command: 'installHarnesses' }, disabled })}
    ${button(state.telemetry ? 'Turn research telemetry off' : 'Turn research telemetry on', 'baseCommand', { data: { command: state.telemetry ? 'telemetryOff' : 'telemetryOn' }, disabled })}</div>
    <p class="muted">Research telemetry is opt-in and may record full chat content. The original harness handles its warning and configuration.</p>`)}
    <div class="notice">Task creation and approvals are real project changes; they remain if Mission Control is closed or the extension is updated.</div>`;
}

/** Render either surface with the currently selected page.
 * @param {import('./types').ViewState} state
 * @param {'sidebar' | 'editor'} surface
 * @param {string} page
 * @param {string | null} [selectedCheck]
 * @returns {string}
 */
function render(state, surface, page, selectedCheck = null) {
  if (!PAGES.includes(page)) throw new Error(`Unknown Mission Control page: ${page}`);
  if (surface === 'sidebar') return sidebar(state, page);
  const pages = { overview: () => overview(state), evidence: () => evidencePage(state, selectedCheck), approvals: () => approvals(state),
    skills: () => skills(state), settings: () => settings(state) };
  const body = pages[/** @type {keyof typeof pages} */ (page)]();
  return `<main class="detail"><nav class="tabs" aria-label="Mission Control pages">${PAGES.map(p => nav(p, page, p === 'skills' ? 'Skills & packs' : p[0].toUpperCase() + p.slice(1), p === 'overview' ? 'grid' : p === 'evidence' ? 'shield' : p === 'approvals' ? 'user' : p === 'skills' ? 'box' : 'gear')).join('')}</nav>
    <div class="breadcrumb">${escape(state.snapshot?.project?.name || 'Frontier HVE')} / ${escape(state.snapshot?.ask?.id || 'No active task')}</div>
    ${notices(state)}${body}<footer class="detail-footer">${escape(state.connection)} &middot; Live workspace data ${state.busy ? '&middot; Working...' : ''}</footer></main>`;
}

/** Return the static, CSP-restricted webview document.
 * @param {string} cssUri
 * @param {string} scriptUri
 * @param {string} cspSource
 * @param {string} nonce
 * @returns {string}
 */
function documentHtml(cssUri, scriptUri, cspSource, nonce) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${escape(cspSource)}; style-src ${escape(cspSource)}; script-src 'nonce-${escape(nonce)}';">
    <title>Frontier HVE Mission Control</title><link rel="stylesheet" href="${escape(cssUri)}"></head>
    <body><div id="root" aria-busy="true"><p class="loading">Connecting to the installed harness...</p></div><div id="announcement" class="sr-only" role="status" aria-live="polite"></div>
    <script nonce="${escape(nonce)}" src="${escape(scriptUri)}"></script></body></html>`;
}

module.exports = { PAGES, escape, render, documentHtml };
