'use strict';
/** Exchange allowlisted UI actions and escaped render updates with the extension host. */
const api = acquireVsCodeApi();
const root = document.getElementById('root');
const announcement = document.getElementById('announcement');
if (!root || !announcement) throw new Error('Mission Control document is incomplete.');

document.addEventListener('click', event => {
  if (!(event.target instanceof Element)) return;
  const button = event.target.closest('button[data-action]');
  if (!(button instanceof HTMLButtonElement) || button.disabled) return;
  const { action, ...data } = button.dataset;
  if (!action) throw new Error('Missing button action.');
  api.postMessage({ action, ...data });
});

window.addEventListener('message', event => {
  const message = event.data;
  if (!message || typeof message !== 'object' || message.type !== 'render' || typeof message.html !== 'string'
      || typeof message.busy !== 'boolean') throw new Error('Unexpected message from the extension host.');
  const active = document.activeElement;
  const focused = active instanceof HTMLButtonElement ? { ...active.dataset } : null;
  const top = document.documentElement.scrollTop;
  root.innerHTML = message.html;
  root.setAttribute('aria-busy', String(message.busy));
  if (focused) {
    const replacement = [...root.querySelectorAll('button')].find(button =>
      Object.entries(focused).every(([key, value]) => button.dataset[key] === value));
    if (replacement && !replacement.disabled) replacement.focus({ preventScroll: true });
  }
  document.documentElement.scrollTop = top;
  announcement.textContent = message.busy ? 'Harness operation in progress.' : 'Mission Control updated.';
});

api.postMessage({ action: 'ready' });
