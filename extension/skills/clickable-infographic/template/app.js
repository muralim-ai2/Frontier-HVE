/* Infographic engine: layouts, connectors, click targets, detail sheet and theme routes. Author all content in data.js; this file should not need edits. */
(() => {
'use strict';

/* Infographic engine. Author all content in data.js; this file should not need edits. */
const D = window.INFOGRAPHIC;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* One icon family: 24px grid, 1.8 stroke, rounded caps. Add more in data.js `icons` in the same style. */
const P = Object.assign({
  home: '<path d="M3 10.1 12 3l9 7.1V20a1 1 0 0 1-1 1h-5.2v-6.3H9.2V21H4a1 1 0 0 1-1-1z"/>',
  search: '<circle cx="10.6" cy="10.6" r="7.1"/><path d="m15.9 15.9 5.3 5.3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  user: '<circle cx="12" cy="8.2" r="4.2"/><path d="M4 20.5c1.1-4 4.3-6 8-6s6.9 2 8 6"/>',
  users: '<circle cx="9" cy="8.5" r="3.6"/><path d="M2.5 19.5c.9-3.4 3.5-5.2 6.5-5.2s5.6 1.8 6.5 5.2"/><path d="M15.5 5.2a3.6 3.6 0 0 1 0 6.6M18 14.6c1.8.7 3 2.4 3.5 4.9"/>',
  doc: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="8.5" cy="9.5" r="1.8"/><path d="m21 16-5-5-9 9"/>',
  link: '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.2 1.2"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1.2-1.2"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m8 12.3 2.7 2.7L16 9.7"/>',
  flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3l-5.5 2.9 1-6.2L3 9.6l6.2-.9z"/>',
  bolt: '<path d="M13.5 2.5 5.5 13.5h6l-1 8 8-11h-6z"/>',
  gear: '<circle cx="12" cy="12" r="3.2"/><path d="M12 2.8v2.6M12 18.6v2.6M2.8 12h2.6M18.6 12h2.6M5.5 5.5l1.8 1.8M16.7 16.7l1.8 1.8M5.5 18.5l1.8-1.8M16.7 7.3l1.8-1.8"/>',
  lock: '<rect x="4.5" y="10.5" width="15" height="10.5" rx="2.5"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
  shield: '<path d="M12 2.8 19.5 6v5.5c0 4.6-3.2 8.3-7.5 9.7-4.3-1.4-7.5-5.1-7.5-9.7V6z"/>',
  db: '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.8"/><path d="M4.5 5.5v13c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8v-13M4.5 12c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8"/>',
  cloud: '<path d="M7 18.5a4.5 4.5 0 0 1-.6-9 6 6 0 0 1 11.5 1.6A3.8 3.8 0 0 1 17.5 18.5z"/>',
  api: '<path d="M8 6 2.5 12 8 18M16 6l5.5 6-5.5 6M14 4l-4 16"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m7.5 9 3 3-3 3M12.5 15h4"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m3.5 7 8.5 6 8.5-6"/>',
  chat: '<path d="M20.7 16.6A9.1 9.1 0 1 0 17.4 20l4.1 1.2z"/>',
  cart: '<path d="M3 4h2.5l2.2 11h10.6l2-8H6.6"/><circle cx="9" cy="19.5" r="1.5"/><circle cx="17" cy="19.5" r="1.5"/>',
  map: '<path d="m9 4-6 2.5v13.5l6-2.5 6 2.5 6-2.5V3.5L15 6z"/><path d="M9 4v13.5M15 6v13.5"/>',
  grid: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18M15 3v18M3 9h18M3 15h18"/>',
  menu: '<path d="M3.5 6h17M3.5 12h17M3.5 18h17"/>',
  more: '<circle cx="5.5" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="18.5" cy="12" r="1.6" fill="currentColor" stroke="none"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
  contrast: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17a8.5 8.5 0 0 0 0-17z" fill="currentColor"/>',
}, D.icons || {});
const ic = (n, s = 20) => `<svg class="ic" width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[n] || P.doc}</svg>`;

/* Node kinds map a meaning to one of five encodings: accent, solid, bar, dashed, muted. */
const KINDS = D.kinds || {
  primary: { label: 'Primary', style: 'accent' },
  step: { label: 'Step', style: 'bar' },
  optional: { label: 'Optional', style: 'dashed' },
  planned: { label: 'Planned', style: 'muted' },
};
const kindOf = n => KINDS[n.kind] || { label: '', style: 'solid' };
const THEMES = [['light', 'Light'], ['dark', 'Dark'], ['hc', 'High contrast'], ['system', 'System']];
const ROW = 56, GAP = 12, PAD = 16;

let theme = 'light';
const all = [];

/* Click target: a page route in the project's app, else a related file or URL, else an in-page detail sheet. */
function target(n) {
  if (n.route != null && D.app) {
    const q = D.app.themeParam ? `?${D.app.themeParam}=${theme}` : '';
    return { href: `${D.app.page}${q}${n.route}`, what: 'Opens the page' };
  }
  if (n.href && !n.detail) return { href: n.href, what: 'Opens the linked item' };
  return { detail: true, what: 'Shows details' };
}

/* ---------- Render ---------- */
function open(n, inner, cls) {
  all.push(n);
  const t = target(n), label = `${n.title}${n.via ? ': ' + n.via : ''}. ${t.what}.`;
  return t.href
    ? `<a class="${cls}" id="${n.id}" href="${t.href}" target="_blank" rel="noopener" aria-label="${label}">${inner}</a>`
    : `<button type="button" class="${cls}" id="${n.id}" data-detail="${n.id}" aria-label="${label}">${inner}</button>`;
}
function nodeHTML(n, sm) {
  const k = kindOf(n), tag = n.tag ?? k.label;
  const inner = `<span class="tile">${ic(n.icon)}</span>
    <span class="tx"><span class="t">${n.title}</span><span class="v">${n.via || ''}</span></span>
    ${sm || !tag ? '' : `<span class="tag">${tag}</span>`}`;
  return open(n, inner, `node ${k.style} ${sm ? 'sm' : ''}`);
}
function mainHTML(m) {
  const k = KINDS[m.kind] || { label: '', style: 'accent' }, tag = m.tag ?? k.label;
  const inner = `<span class="hd"><span class="tile">${ic(m.icon)}</span><span class="tx"><span class="t">${m.title}</span><span class="v">${m.via || ''}</span></span>${tag ? `<span class="tag">${tag}</span>` : ''}</span>
    ${m.cap ? `<span class="cap">${m.cap}</span>` : ''}
    ${m.items ? `<span class="list">${m.items.map(([i, t]) => `<span class="li">${ic(i, 16)}<span>${t}</span></span>`).join('')}</span>` : ''}`;
  return open(m, inner, `node main ${k.style}`);
}
function laneHTML(l) {
  const rail = `<div class="rail">${l.entries.map(e => `<div class="rail-item" id="${e.id}" data-to="${e.to}">${ic(e.icon, 24)}<span>${e.label}</span>${e.start ? `<span class="start">${ic(e.startIcon || 'flag', 14)}${e.start}</span>` : ''}</div>`).join('')}</div>`;
  if (l.direct) {
    return `<div class="lane">${rail}<span></span><div class="band direct">
      <div class="col-main">${l.direct.map(p => nodeHTML(p.node)).join('')}</div>
      <div class="col-targets">${l.direct.map(p => `<div class="row"><p class="note">${p.note || ''}</p></div>`).join('')}</div>
    </div></div>`;
  }
  const rows = l.rows.map(r => `<div class="row">${r.chain
    ? `<div class="chain">${nodeHTML(r.node)}${nodeHTML(r.chain, true)}</div>`
    : nodeHTML(r.node)}${r.note ? `<p class="note">${r.note}</p>` : ''}</div>`).join('');
  return `<div class="lane">${rail}<span></span><div class="band">
    <div class="col-main">${mainHTML(l.main)}</div>
    <div class="col-targets" data-from="${l.main.id}">${rows}</div>
  </div></div>`;
}
function laneWeight(l) {
  const n = l.direct ? l.direct.length : Math.max(l.rows.length, Math.ceil(((l.main.items || []).length + 2) / 2));
  return n * ROW + (n - 1) * GAP + 2 * PAD;
}
function renderLanes(c) {
  c.className = 'lanes';
  c.innerHTML = `<div class="rail-bg"></div><p class="rail-title">${D.rail?.title || ''}</p><p class="rail-foot">${D.rail?.foot || ''}</p>` + D.lanes.map(laneHTML).join('');
  // Lanes share the height by row count but never shrink below their content.
  c.style.gridTemplateRows = D.lanes.map(l => `minmax(min-content, ${laneWeight(l)}fr)`).join(' ');
}
function renderColumns(c) {
  c.className = 'cols';
  c.innerHTML = D.columns.map(col => `<div class="col">${mainHTML(col.main)}${(col.nodes || []).map(n => nodeHTML(n)).join('')}${col.note ? `<p class="note">${col.note}</p>` : ''}</div>`).join('');
}
function panelHTML(p) {
  const fig = p.image ? `<figure class="fig"><img src="${p.image.src}" alt="${p.image.alt || ''}">${p.image.caption ? `<figcaption>${p.image.caption}</figcaption>` : ''}</figure>` : '';
  return `<div class="p-hd"><span class="tile">${ic(p.icon)}</span><div><h2 id="panel-title">${p.title}</h2><p>${p.sub || ''}</p></div></div>
    ${fig}
    ${p.nodes ? `<div class="pnodes">${p.nodes.map(n => nodeHTML(n)).join('')}</div>` : ''}
    ${p.facts ? `<ul class="facts">${p.facts.map(([i, t]) => `<li>${ic(i, 16)}<span>${t}</span></li>`).join('')}</ul>` : ''}`;
}
function legendHTML() {
  return Object.values(KINDS).filter(k => k.label && k.legend !== false)
    .map(k => `<li><span class="lg ${k.style}"></span>${k.label}</li>`).join('')
    + `<li><svg class="lg-arrow" width="28" height="12" viewBox="0 0 28 12" aria-hidden="true"><path d="M0 6h22" stroke="currentColor" stroke-width="1.5"/><path d="M21 1.5 27 6l-6 4.5z" fill="currentColor"/></svg>${D.arrow || 'Leads to'}</li>`;
}

$('#mark').innerHTML = ic(D.meta.mark || 'star', 32);
$('#eyebrow').textContent = D.meta.eyebrow || '';
$('#title').textContent = D.meta.title;
$('#sub').textContent = D.meta.sub || '';
document.title = D.meta.title;
$('#legend').innerHTML = legendHTML();
(D.layout === 'columns' ? renderColumns : renderLanes)($('#content'));
if (D.panel) $('#panel').innerHTML = panelHTML(D.panel);
else $('#body').classList.add('no-panel');
$('#seg').innerHTML = THEMES.map(([id, t]) => `<button type="button" data-set="${id}" aria-pressed="false">${t}</button>`).join('');

/* ---------- Detail sheet ---------- */
const dlg = $('#detail');
$('#d-close').innerHTML = ic('close', 18);
$('#d-close').addEventListener('click', () => dlg.close());
dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
function showDetail(n) {
  const d = n.detail || {};
  const links = [...(d.links || []), ...(n.href ? [['Open', n.href]] : [])];
  $('#d-icon').innerHTML = ic(n.icon);
  $('#d-title').textContent = n.title;
  $('#d-body').innerHTML = `${n.via ? `<p class="note">${n.via}</p>` : ''}
    ${d.text ? `<p>${d.text}</p>` : ''}
    ${d.image ? `<img src="${d.image}" alt="${d.alt || ''}">` : ''}
    ${links.length ? `<div class="d-links">${links.map(([t, h]) => `<a href="${h}" target="_blank" rel="noopener">${ic('external', 14)}${t}</a>`).join('')}</div>` : ''}`;
  dlg.showModal();
}
$('#stage').addEventListener('click', e => {
  const b = e.target.closest('[data-detail]');
  if (b) showDetail(all.find(n => n.id === b.dataset.detail));
});

/* ---------- Connectors ---------- */
const stage = $('#stage');
const svg = $('#edges');
let scale = 1;
function box(el) {
  const s = stage.getBoundingClientRect(), r = el.getBoundingClientRect();
  const x = (r.left - s.left) / scale, y = (r.top - s.top) / scale, w = r.width / scale, h = r.height / scale;
  return { l: x, r: x + w, t: y, b: y + h, cx: x + w / 2, cy: y + h / 2 };
}
const head = (x, y, to) => `<path class="head" data-to="${to}" d="M${x - 7} ${y - 4.5}L${x} ${y}L${x - 7} ${y + 4.5}Z"/>`;
const line = (x0, y, x1, from, to) => `<path data-from="${from}" data-to="${to}" d="M${x0} ${y}H${x1 - 6}"/>${head(x1, y, to)}`;
// Orthogonal branch: out of the source, along a shared bus, into the target, with rounded corners.
function branch(x0, y0, bx, x1, y1, from, to) {
  const r = Math.min(10, Math.abs(y1 - y0) / 2);
  if (r < 1) return line(x0, y0, x1, from, to);
  const d = y1 > y0 ? 1 : -1;
  return `<path data-from="${from}" data-to="${to}" d="M${x0} ${y0}H${bx - r}Q${bx} ${y0} ${bx} ${y0 + d * r}V${y1 - d * r}Q${bx} ${y1} ${bx + r} ${y1}H${x1 - 6}"/>${head(x1, y1, to)}`;
}
function drawEdges() {
  let out = '';
  $$('.rail-item').forEach(t => {
    const a = box(t), b = box($('#' + t.dataset.to));
    out += line(a.r + 8, b.cy, b.l, t.id, t.dataset.to);
  });
  $$('.col-targets[data-from]').forEach(col => {
    const src = $('#' + col.dataset.from), s = box(src);
    $$('.row > .node, .row > .chain > .node:first-child', col)
      .forEach(n => { const b = box(n); out += branch(s.r, s.cy, s.r + 44, b.l, b.cy, src.id, n.id); });
  });
  $$('.chain').forEach(c => {
    const ns = $$('.node', c), [a, b] = ns.map(box);
    out += line(a.r, a.cy, b.l, ns[0].id, ns[1].id);
  });
  if (D.layout === 'columns' && D.sequence !== false) {
    const heads = $$('.col > .node.main .hd');
    heads.slice(1).forEach((h, i) => {
      const a = box(heads[i]), b = box(h), from = heads[i].parentElement.id, to = h.parentElement.id;
      out += line(a.r + 1, a.cy, b.l - 1, from, to);
    });
  }
  $$('.elabel').forEach(e => e.remove());
  if (D.panel?.from) {
    const ap = box($('#' + D.panel.from)), th = box($('#panel'));
    out += line(ap.r, ap.cy, th.l, D.panel.from, 'panel');
    if (D.panel.label) {
      const lab = document.createElement('span');
      lab.className = 'elabel'; lab.textContent = D.panel.label;
      lab.style.left = `${(ap.r + th.l) / 2}px`; lab.style.top = `${ap.cy}px`;
      stage.appendChild(lab);
    }
  }
  svg.innerHTML = out;
}
const hot = (id, on) => $$(`[data-to="${id}"], [data-from="${id}"]`, svg).forEach(p => p.classList.toggle('hot', on));
$$('.node').forEach(n => {
  ['mouseenter', 'focus'].forEach(e => n.addEventListener(e, () => hot(n.id, true)));
  ['mouseleave', 'blur'].forEach(e => n.addEventListener(e, () => hot(n.id, false)));
});

/* ---------- Fit, theme and hash routes: #/light|dark|hc|system, add /export for the PNG ---------- */
function fit() {
  scale = Math.min(innerWidth / 1920, innerHeight / 1080);
  stage.style.transform = `translate(${(innerWidth - 1920 * scale) / 2}px, ${(innerHeight - 1080 * scale) / 2}px) scale(${scale})`;
}
function spill() {
  return Math.max(0, ...[$('#content'), $('#panel'), ...$$('.col')].map(el => el.scrollHeight - el.clientHeight));
}
const dark = matchMedia('(prefers-color-scheme: dark)');
function apply() {
  const [t, mode] = location.hash.replace(/^#\/?/, '').split('/');
  theme = THEMES.some(x => x[0] === t) ? t : 'light';
  document.documentElement.dataset.theme = theme === 'system' ? (dark.matches ? 'dark' : 'light') : theme;
  stage.classList.toggle('export', mode === 'export');
  const over = spill(), note = $('#foot-note');
  note.textContent = over > 1 ? `Over the canvas budget by ${over}px: cut content or split into two infographics.`
    : (mode === 'export' ? D.meta.exportFoot || D.meta.foot : D.meta.foot) || '';
  note.classList.toggle('warn', over > 1);
  all.forEach(n => { const el = $('#' + n.id), t = target(n); if (t.href && el.tagName === 'A') el.href = t.href; });
  $$('#seg button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.set === theme)));
  fit();
  drawEdges();
}
$('#seg').addEventListener('click', e => {
  const b = e.target.closest('button');
  if (b) location.hash = '#/' + b.dataset.set;
});
addEventListener('hashchange', apply);
addEventListener('resize', () => { fit(); drawEdges(); });
dark.addEventListener('change', apply);
if (!location.hash) history.replaceState(null, '', '#/light');
apply();
})();
