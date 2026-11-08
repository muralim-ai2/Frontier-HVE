'use strict';
/** Mission Control webview: render the host's model, keep page, filter and section choices, and send allowlisted actions. */
(function () {
  const api = acquireVsCodeApi();
  const { mount } = globalThis.hveVnode;
  const { sidebar } = globalThis.hveViews;
  const { dashboard } = globalThis.hvePages;
  const { uiState, NODE, PAGE_ROWS } = globalThis.hveTrajectory;
  const root = document.getElementById('root');
  const announce = document.getElementById('announce');
  if (!root || !announce) throw new Error('Mission Control document is incomplete.');
  const region = announce;
  const PAGES = ['live', 'plan', 'progress', 'files', 'others', 'telemetry', 'trajectory', 'visuals', 'skills', 'settings'];
  const FILTERS = ['all', 'edits', 'commands', 'conversation', 'problems'];
  const saved = /** @type {Partial<import('../types').UiState> | undefined} */ (api.getState());
  /** @type {import('../types').UiState} */
  const ui = { page: 'live', filter: 'all', open: {}, seq: 0, ...saved };
  if (!ui.traj && window.innerWidth < 640) ui.traj = { ...uiState(ui), view: 'timeline' };
  /** @type {(import('../types').Model & {navigate: {page: import('../types').Page, seq: number}}) | null} */
  let model = null;
  /** @type {import('../types').Trajectory | null} The picture kept while live updates are paused. */
  let frozen = null;
  /** @type {NodeJS.Timeout | undefined} */
  let searchTimer;
  /** @type {{x: number, y: number, zx: number, zy: number} | null} */
  let drag = null;
  let errors = 0;
  let status = '';
  let packsAsked = false;
  let modelsAsked = false;
  let deferred = false;

  /** Return a key that finds the same control after a redraw.
   * @param {Element | null} element
   * @returns {string | null}
   */
  function controlKey(element) {
    return element instanceof HTMLElement && element.dataset.action ? JSON.stringify(element.dataset) : null;
  }

  /** Redraw the whole view from the model, keeping focus and scroll position; an open dropdown is redrawn once it closes.
   * @returns {void}
   */
  function draw() {
    if (!model || !root) return;
    if (document.activeElement instanceof HTMLSelectElement || document.activeElement instanceof HTMLTextAreaElement) {
      deferred = true;
      return;
    }
    deferred = false;
    const focused = controlKey(document.activeElement);
    const scroller = document.scrollingElement || document.documentElement;
    const top = scroller.scrollTop;
    if (frozen && model.trajectory?.chat !== frozen.chat) frozen = model.trajectory;
    const shown = ui.traj?.paused && frozen ? { ...model, trajectory: frozen, trajectoryPending: Math.max(0, (model.trajectory?.events.length || 0) - frozen.events.length) } : model;
    const tree = model.surface === 'sidebar' ? sidebar(model, ui, Date.now()) : dashboard(shown, ui, Date.now());
    root.replaceChildren(mount(tree, document));
    root.setAttribute('aria-busy', String(model.busy));
    if (focused) {
      const match = [...root.querySelectorAll('[data-action]')].find(element => controlKey(element) === focused);
      if (match instanceof HTMLElement && !(match instanceof HTMLButtonElement && match.disabled)) match.focus({ preventScroll: true });
      if (match instanceof HTMLInputElement) match.setSelectionRange(match.value.length, match.value.length);
    }
    scroller.scrollTop = top;
    api.setState(ui);
  }

  /** Show a page here on the dashboard, or ask the host to open the dashboard from the sidebar.
   * @param {string} page
   * @returns {void}
   */
  function go(page) {
    if (!PAGES.includes(page)) throw new Error(`Unknown page: ${page}`);
    if (model?.surface === 'sidebar') {
      api.postMessage({ action: 'openDashboard', page });
      return;
    }
    ui.page = /** @type {import('../types').Page} */ (page);
    document.documentElement.scrollTop = 0;
    askForPacks();
    askForModels();
    draw();
  }

  /** Ask the host for the Copilot models the first time the Telemetry page shows.
   * @returns {void}
   */
  function askForModels() {
    if (model?.surface === 'editor' && ['telemetry', 'progress'].includes(ui.page) && model.models === null && !model.modelsError && !modelsAsked) {
      modelsAsked = true;
      api.postMessage({ action: 'loadModels' });
    }
  }

  /** Ask the host for the installed packs the first time the Skills and packs page shows.
   * @returns {void}
   */
  function askForPacks() {
    if (model?.surface === 'editor' && ui.page === 'skills' && model.packs === null && !model.packsError && !packsAsked) {
      packsAsked = true;
      api.postMessage({ action: 'loadPacks' });
    }
  }

  /** Return the trajectory page's view state, kept in the webview state so it survives tab switches and redraws.
   * @returns {import('../types').TrajectoryUi}
   */
  function traj() {
    ui.traj = uiState(ui);
    return ui.traj;
  }

  /** Return the graph's box and drawn size, or null when the graph is not on screen.
   * @returns {{box: HTMLElement, width: number, height: number} | null}
   */
  function graphBox() {
    const box = document.querySelector('.tgraph');
    return box instanceof HTMLElement ? { box, width: Number(box.dataset.width), height: Number(box.dataset.height) } : null;
  }

  /** Apply the pan and zoom to the graph without redrawing, and keep it.
   * @returns {void}
   */
  function applyZoom() {
    const { k, x, y } = traj().zoom;
    document.querySelector('.tviewport')?.setAttribute('transform', `translate(${x} ${y}) scale(${k})`);
    api.setState(ui);
  }

  /** Zoom the graph by a factor around a point of its box.
   * @param {number} factor
   * @param {number} px
   * @param {number} py
   * @returns {void}
   */
  function zoomAt(factor, px, py) {
    const s = traj();
    const k = Math.min(3, Math.max(0.1, s.zoom.k * factor));
    s.zoom = { k, x: px - (px - s.zoom.x) * k / s.zoom.k, y: py - (py - s.zoom.y) * k / s.zoom.k };
    applyZoom();
  }

  /** Center a graph node in view at the current zoom.
   * @param {string} id
   * @returns {void}
   */
  function center(id) {
    const graph = graphBox();
    const node = graph?.box.querySelector(`[data-action="trajSelect"][data-id="${CSS.escape(id)}"]`);
    if (!graph || !(node instanceof SVGElement)) return;
    const s = traj();
    s.zoom = { k: s.zoom.k, x: graph.box.clientWidth / 2 - (Number(node.dataset.x) + NODE.w / 2) * s.zoom.k,
      y: graph.box.clientHeight / 2 - (Number(node.dataset.y) + NODE.h / 2) * s.zoom.k };
    applyZoom();
  }

  /** Select a trajectory step everywhere, focus it in the view it was chosen from, and say what it is.
   * @param {string} id
   * @param {string} where The view's container selector.
   * @returns {void}
   */
  function select(id, where) {
    traj().sel = id;
    draw();
    const element = document.querySelector(`${where} [data-action="trajSelect"][data-id="${CSS.escape(id)}"]`)
      || document.querySelector(`[data-action="trajSelect"][data-id="${CSS.escape(id)}"]:not(.btn)`);
    if (!(element instanceof HTMLElement || element instanceof SVGElement)) return;
    element.focus({ preventScroll: element instanceof SVGElement });
    const graph = graphBox();
    if (element instanceof SVGElement && graph) {
      const box = graph.box.getBoundingClientRect();
      const rect = element.getBoundingClientRect();
      if (rect.left < box.left || rect.right > box.right || rect.top < box.top || rect.bottom > box.bottom) center(id);
    }
    region.textContent = `Selected. ${element.getAttribute('aria-label') || ''}`;
  }

  /** Run a trajectory page action inside the webview; none of them reach the extension host.
   * @param {string} action
   * @param {DOMStringMap} data
   * @param {Element} target
   * @returns {void}
   */
  function trajAction(action, data, target) {
    const s = traj();
    const graph = graphBox();
    if (action === 'trajSelect') return select(data.id || '', target.closest('.tgraph') ? '.tgraph' : '.ttimeline');
    if (action === 'trajCopy') {
      void navigator.clipboard.writeText(data.value || '').then(() => { region.textContent = 'Copied.'; });
      return;
    }
    if (action === 'trajToggle') s.collapsed[data.id || ''] = !s.collapsed[data.id || ''];
    else if (action === 'trajView') s.view = data.value === 'timeline' ? 'timeline' : 'graph';
    else if (action === 'trajTime') s.time = s.time === 'clock' ? 'elapsed' : 'clock';
    else if (action === 'trajErrors') { s.errors = !s.errors; s.limit = PAGE_ROWS; }
    else if (action === 'trajClear') Object.assign(s, { q: '', status: 'all', kind: 'all', agent: 'all', errors: false, limit: PAGE_ROWS });
    else if (action === 'trajMore') s.limit += PAGE_ROWS;
    else if (action === 'trajCollapseAll') s.collapsed = Object.fromEntries((model?.trajectory?.events || []).filter(e => e.depth > 0 && e.children.length).map(e => [e.id, true]));
    else if (action === 'trajExpandAll') s.collapsed = {};
    else if (action === 'trajPause') {
      s.paused = !s.paused;
      frozen = s.paused ? model?.trajectory || null : null;
      region.textContent = s.paused ? 'Live updates paused.' : 'Live updates resumed.';
    } else if (action === 'trajCenter') return s.sel ? center(s.sel) : undefined;
    else if (action === 'trajHome') { s.zoom = { k: 1, x: 16, y: 16 }; return applyZoom(); }
    else if (action === 'trajZoomIn' || action === 'trajZoomOut') {
      return graph ? zoomAt(action === 'trajZoomIn' ? 1.25 : 0.8, graph.box.clientWidth / 2, graph.box.clientHeight / 2) : undefined;
    } else if (action === 'trajFit') {
      if (!graph) return;
      const k = Math.min(1.5, Math.max(0.1, Math.min((graph.box.clientWidth - 32) / graph.width, (graph.box.clientHeight - 32) / graph.height)));
      s.zoom = { k, x: (graph.box.clientWidth - graph.width * k) / 2, y: Math.max(16, (graph.box.clientHeight - graph.height * k) / 2) };
      return applyZoom();
    } else return;
    draw();
  }

  document.addEventListener('click', event => {
    const target = event.target instanceof Element ? event.target.closest('[data-action]') : null;
    if (target && (target instanceof HTMLElement || target instanceof SVGElement) && target.dataset.action?.startsWith('traj')) {
      if (!(target instanceof HTMLButtonElement && target.disabled) && !(target instanceof HTMLInputElement)) {
        const { action, ...data } = target.dataset;
        trajAction(action || '', data, target);
      }
      return;
    }
    if (!(target instanceof HTMLElement) || target instanceof HTMLSelectElement || (target instanceof HTMLButtonElement && target.disabled)) return;
    const { action, go: next, ...data } = target.dataset;
    if (action === 'go') go(data.page || '');
    else if (action === 'filter') {
      if (!FILTERS.includes(data.value || '')) throw new Error('Unknown activity filter.');
      ui.filter = /** @type {import('../types').UiState['filter']} */ (data.value);
      draw();
    } else if (action === 'analyze' || action === 'summarize') {
      const pick = document.querySelector('select[data-field="model"]');
      if (!(pick instanceof HTMLSelectElement)) throw new Error('The model list is missing.');
      if (action === 'summarize') api.postMessage({ action, model: pick.value });
      else {
        const preset = document.querySelector('select[data-field="preset"]');
        const box = document.querySelector('textarea[data-field="question"]');
        if (!(preset instanceof HTMLSelectElement)) throw new Error('The question list is missing.');
        const question = preset.value === 'custom' ? (box instanceof HTMLTextAreaElement ? box.value.trim() : '') : preset.selectedOptions[0].textContent || '';
        if (!question) throw new Error('Type your question first.');
        api.postMessage({ action, model: pick.value, question });
      }
    } else {
      api.postMessage({ action, ...data });
      if (next) go(next);
    }
  });

  document.addEventListener('input', event => {
    if (event.target instanceof HTMLInputElement && event.target.dataset.action === 'trajQuery') {
      const value = event.target.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { Object.assign(traj(), { q: value, limit: PAGE_ROWS }); draw(); }, 200);
      return;
    }
    if (event.target instanceof HTMLTextAreaElement && event.target.dataset.field === 'question') {
      ui.question = event.target.value;
      api.setState(ui);
    }
  });

  document.addEventListener('change', event => {
    const target = event.target;
    if (target instanceof HTMLSelectElement && target.dataset.action === 'trajFilter') {
      const field = target.dataset.field;
      if (field !== 'status' && field !== 'kind' && field !== 'agent') throw new Error('Unknown trajectory filter.');
      Object.assign(traj(), { [field]: target.value, limit: PAGE_ROWS });
      target.blur();
      draw();
      return;
    }
    if (target instanceof HTMLSelectElement && target.dataset.field === 'model') {
      ui.model = target.value;
      api.setState(ui);
      return;
    }
    if (target instanceof HTMLSelectElement && target.dataset.field === 'preset') {
      ui.preset = target.value;
      target.blur();
      draw();
      return;
    }
    if (target instanceof HTMLSelectElement && target.dataset.action === 'selectChat' && target.value) {
      api.postMessage({ action: 'selectChat', chat: target.value });
      target.blur();
      return;
    }
    if (!(target instanceof HTMLSelectElement) || target.dataset.action !== 'selectAsk' || !target.value) return;
    api.postMessage({ action: 'selectAsk', ask: target.value });
    target.blur();
  });

  document.addEventListener('focusout', event => {
    if ((event.target instanceof HTMLSelectElement || event.target instanceof HTMLTextAreaElement) && deferred) setTimeout(draw, 0);
  });

  document.addEventListener('keydown', event => {
    const target = event.target instanceof Element ? event.target.closest('[data-action="trajSelect"]') : null;
    if (!(target instanceof HTMLElement || target instanceof SVGElement) || target.classList.contains('btn')) return;
    const where = target.closest('.tgraph') ? '.tgraph' : '.ttimeline';
    const list = /** @type {(HTMLElement | SVGElement)[]} */ ([...document.querySelectorAll(`${where} [data-action="trajSelect"]`)]);
    const index = list.indexOf(target);
    const own = target instanceof SVGElement && (event.key === 'Enter' || event.key === ' ') ? target.dataset.id : undefined;
    /** @type {Record<string, string | undefined>} */
    const keys = { ArrowDown: list[index + 1]?.dataset.id, ArrowUp: list[index - 1]?.dataset.id, ArrowLeft: target.dataset.parent, ArrowRight: target.dataset.child,
      Home: list[0]?.dataset.id, End: list[list.length - 1]?.dataset.id };
    const id = own || keys[event.key];
    if (!id) return;
    event.preventDefault();
    select(id, where);
  });

  document.addEventListener('wheel', event => {
    const graph = graphBox();
    if (!graph || !(event.target instanceof Element) || !graph.box.contains(event.target)) return;
    event.preventDefault();
    const rect = graph.box.getBoundingClientRect();
    zoomAt(event.deltaY < 0 ? 1.15 : 1 / 1.15, event.clientX - rect.left, event.clientY - rect.top);
  }, { passive: false });

  document.addEventListener('pointerdown', event => {
    const graph = graphBox();
    if (!graph || !(event.target instanceof Element) || !graph.box.contains(event.target) || event.target.closest('[data-action]')) return;
    const { x, y } = traj().zoom;
    drag = { x: event.clientX, y: event.clientY, zx: x, zy: y };
    graph.box.setPointerCapture(event.pointerId);
  });

  document.addEventListener('pointermove', event => {
    if (!drag) return;
    const s = traj();
    s.zoom = { k: s.zoom.k, x: drag.zx + event.clientX - drag.x, y: drag.zy + event.clientY - drag.y };
    document.querySelector('.tviewport')?.setAttribute('transform', `translate(${s.zoom.x} ${s.zoom.y}) scale(${s.zoom.k})`);
  });

  document.addEventListener('pointerup', () => {
    if (!drag) return;
    drag = null;
    api.setState(ui);
  });

  document.addEventListener('toggle', event => {
    const target = event.target;
    if (target instanceof HTMLDetailsElement && target.dataset.key) {
      ui.open[target.dataset.key] = target.open;
      api.setState(ui);
    }
  }, true);

  window.addEventListener('message', event => {
    const message = event.data;
    if (!message || typeof message !== 'object' || message.type !== 'model' || !message.model || typeof message.model !== 'object') {
      throw new Error('Unexpected message from the extension host.');
    }
    model = message.model;
    if (!model) return;
    if (model.surface === 'editor' && model.navigate.seq !== ui.seq) {
      ui.seq = model.navigate.seq;
      ui.page = model.navigate.page;
    }
    const next = model.activity?.session?.status || 'none';
    if (next !== status) {
      announce.textContent = { working: 'The agent is working.', waiting: 'The agent is waiting for your answer in Chat.', idle: 'The agent is idle.', none: '' }[next] || '';
      status = next;
    }
    if (ui.traj?.paused && !frozen) frozen = model.trajectory;
    const failed = model.trajectory?.errors || 0;
    if (ui.page === 'trajectory' && failed > errors) announce.textContent = `${failed} failed or timed-out ${failed === 1 ? 'step' : 'steps'} in the trajectory.`;
    errors = failed;
    askForPacks();
    askForModels();
    draw();
  });

  setInterval(draw, 15000);
  api.postMessage({ action: 'ready' });
})();
