'use strict';
/** Mission Control webview: render the host's model, keep page, filter and section choices, and send allowlisted actions. */
(function () {
  const api = acquireVsCodeApi();
  const { mount } = globalThis.hveVnode;
  const { sidebar } = globalThis.hveViews;
  const { dashboard } = globalThis.hvePages;
  const root = document.getElementById('root');
  const announce = document.getElementById('announce');
  if (!root || !announce) throw new Error('Mission Control document is incomplete.');
  const PAGES = ['live', 'plan', 'progress', 'files', 'others', 'telemetry', 'skills', 'settings'];
  const FILTERS = ['all', 'edits', 'commands', 'conversation', 'problems'];
  const saved = /** @type {Partial<import('../types').UiState> | undefined} */ (api.getState());
  /** @type {import('../types').UiState} */
  const ui = { page: 'live', filter: 'all', open: {}, seq: 0, ...saved };
  /** @type {(import('../types').Model & {navigate: {page: import('../types').Page, seq: number}}) | null} */
  let model = null;
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
    const tree = model.surface === 'sidebar' ? sidebar(model, ui, Date.now()) : dashboard(model, ui, Date.now());
    root.replaceChildren(mount(tree, document));
    root.setAttribute('aria-busy', String(model.busy));
    if (focused) {
      const match = [...root.querySelectorAll('[data-action]')].find(element => controlKey(element) === focused);
      if (match instanceof HTMLElement && !(match instanceof HTMLButtonElement && match.disabled)) match.focus({ preventScroll: true });
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
    if (model?.surface === 'editor' && ui.page === 'telemetry' && model.models === null && !model.modelsError && !modelsAsked) {
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

  document.addEventListener('click', event => {
    const target = event.target instanceof Element ? event.target.closest('[data-action]') : null;
    if (!(target instanceof HTMLElement) || target instanceof HTMLSelectElement || (target instanceof HTMLButtonElement && target.disabled)) return;
    const { action, go: next, ...data } = target.dataset;
    if (action === 'go') go(data.page || '');
    else if (action === 'filter') {
      if (!FILTERS.includes(data.value || '')) throw new Error('Unknown activity filter.');
      ui.filter = /** @type {import('../types').UiState['filter']} */ (data.value);
      draw();
    } else if (action === 'analyze') {
      const pick = document.querySelector('select[data-field="model"]');
      const box = document.querySelector('textarea[data-field="question"]');
      if (!(pick instanceof HTMLSelectElement) || !(box instanceof HTMLTextAreaElement)) throw new Error('The analysis form is incomplete.');
      api.postMessage({ action, model: pick.value, question: box.value.trim() || box.placeholder });
    } else {
      api.postMessage({ action, ...data });
      if (next) go(next);
    }
  });

  document.addEventListener('input', event => {
    if (event.target instanceof HTMLTextAreaElement && event.target.dataset.field === 'question') {
      ui.question = event.target.value;
      api.setState(ui);
    }
  });

  document.addEventListener('change', event => {
    const target = event.target;
    if (target instanceof HTMLSelectElement && target.dataset.field === 'model') {
      ui.model = target.value;
      api.setState(ui);
      return;
    }
    if (!(target instanceof HTMLSelectElement) || target.dataset.action !== 'selectAsk' || !target.value) return;
    api.postMessage({ action: 'selectAsk', ask: target.value });
    target.blur();
  });

  document.addEventListener('focusout', event => {
    if ((event.target instanceof HTMLSelectElement || event.target instanceof HTMLTextAreaElement) && deferred) setTimeout(draw, 0);
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
    askForPacks();
    askForModels();
    draw();
  });

  setInterval(draw, 15000);
  api.postMessage({ action: 'ready' });
})();
