/** Explorer views: force diagram, collapsible tree and zoomable circle packing over the current hierarchy. */

const canvas = document.getElementById("c"), ctx = canvas.getContext("2d"), svg = document.getElementById("tree");
const SPRING = [0, 300, 95, 48, 26, 18];
const MOTION = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let W = 0, H = 0, dpr = 1, dirty = true;

/** Size the canvas buffer to the stage, so drawings are never stretched when the banner, panel or window change. */
function resize() {
  const r = document.getElementById("stage").getBoundingClientRect();
  dpr = window.devicePixelRatio || 1;
  W = Math.max(1, r.width); H = Math.max(1, r.height);
  canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr); dirty = true;
}

/** Return a node's gentle floating offset in screen pixels at a time. */
function drift(i, t) {
  if (!MOTION) return [0, 0];
  const ph = i.phase === undefined ? (i.phase = Math.random() * Math.PI * 2) : i.phase;
  return [Math.sin(t * 0.0011 + ph) * 2.2, Math.cos(t * 0.0009 + ph * 1.7) * 2.2];
}

/** Return whether an instance or one under it is marked by a query or filter highlight. */
function marked(i) { return !!(S.mark && i.ref && S.mark.has(i.ref.id)); }

/** Draw a label with a dark halo at screen coordinates. */
function label(text, x, y, bold, dim) {
  ctx.font = (bold ? "600 13px" : "11px") + " Segoe UI, system-ui, sans-serif";
  ctx.lineWidth = 4; ctx.strokeStyle = "#0d1320"; ctx.lineJoin = "round";
  ctx.strokeText(text, x, y);
  ctx.fillStyle = dim ? "#56617a" : bold ? "#ffffff" : "#c9d3e6";
  ctx.fillText(text, x, y);
}

/** Return a name shortened to a length. */
function short(name, n) { return name.length > n ? name.slice(0, n - 1) + "\u2026" : name; }

// ---------- force ----------
const Force = {vis: [], visSet: new Set(), hier: [], links: [], alpha: 1, v: {x: 0, y: 0, k: 1}, drag: null, autoFit: 0};

/** Recompute what the force view shows, seeding new nodes outward from their parent. */
Force.refresh = function () {
  this.vis = visible(); this.visSet = new Set(this.vis);
  for (const n of this.vis) {
    if (n.x !== undefined) continue;
    const p = n.parent;
    if (!p || p.x === undefined) { n.x = 0; n.y = 0; } else {
      const sibs = p.children.filter(c => c.keep), i = sibs.indexOf(n), gp = p.parent;
      const base = gp && gp.x !== undefined ? Math.atan2(p.y - gp.y, p.x - gp.x) : -Math.PI / 2;
      const spread = gp ? Math.min(Math.PI * 0.9, 0.35 * sibs.length) : Math.PI * 2;
      const a = gp ? base - spread / 2 + spread * (i + 0.5) / sibs.length : base + spread * i / sibs.length;
      const d = SPRING[Math.min(n.depth, 5)] + p.r;
      n.x = p.x + Math.cos(a) * d; n.y = p.y + Math.sin(a) * d;
    }
    n.vx = 0; n.vy = 0;
  }
  this.hier = this.vis.filter(n => n.parent && this.visSet.has(n.parent)).map(n => ({a: n.parent, b: n}));
  this.links = links();
  this.alpha = Math.max(this.alpha, 0.7);
  dirty = true;
};

/** Advance the layout one step; return false once it has settled. */
Force.tick = function () {
  if (this.alpha < 0.004) return false;
  const vis = this.vis, n = vis.length;
  for (const a of vis) { a.fx = 0; a.fy = 0; }
  for (let i = 0; i < n; i++) {
    const a = vis[i];
    for (let j = i + 1; j < n; j++) {
      const b = vis[j];
      let dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy;
      if (d2 > 4e6) continue;
      if (d2 < 1) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; d2 = 1; }
      const d = Math.sqrt(d2), f = 2600 * (1 + (a.r + b.r) / 8) / d2;
      a.fx -= dx / d * f; a.fy -= dy / d * f; b.fx += dx / d * f; b.fy += dy / d * f;
    }
  }
  const spring = (a, b, len, s) => {
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1, f = (d - len) * s;
    a.fx += dx / d * f; a.fy += dy / d * f; b.fx -= dx / d * f; b.fy -= dy / d * f;
  };
  for (const h of this.hier) spring(h.a, h.b, SPRING[Math.min(h.b.depth, 5)] + h.a.r, 0.08);
  for (const l of this.links) spring(l.a, l.b, 320, 0.0012 * Math.min(4, 1 + Math.log(l.items.length)));
  for (const a of vis) {
    if (a === this.drag) continue;
    a.fx -= a.x * 0.0015; a.fy -= a.y * 0.0015;
    a.vx = (a.vx + a.fx * this.alpha) * 0.55; a.vy = (a.vy + a.fy * this.alpha) * 0.55;
    a.x += Math.max(-40, Math.min(40, a.vx)); a.y += Math.max(-40, Math.min(40, a.vy));
  }
  this.alpha *= 0.985;
  return true;
};

/** Return the instances to keep bright: a highlight, else the hovered or selected node and its neighbours. */
Force.focus = function () {
  if (S.mark) return new Set(this.vis.filter(i => marked(i) || i.children.some(c => !this.visSet.has(c) && subtreeMarked(c))));
  const n = S.hover || S.selected;
  if (!n || !this.visSet.has(n)) return null;
  const s = new Set([n]);
  if (n.parent) s.add(n.parent);
  for (const c of n.children) if (this.visSet.has(c)) s.add(c);
  for (const l of this.links) { if (l.a === n) s.add(l.b); if (l.b === n) s.add(l.a); }
  return s;
};

/** Return whether an instance or anything under it is marked. */
function subtreeMarked(i) { return marked(i) || i.children.some(subtreeMarked); }

/** Draw the force view. */
Force.draw = function () {
  const v = this.v, focus = this.focus(), lit = n => !focus || focus.has(n), sel = S.hover || S.selected, now = performance.now();
  for (const n of this.vis) { const [dx, dy] = n === this.drag ? [0, 0] : drift(n, now); n.px = n.x + dx / v.k; n.py = n.y + dy / v.k; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
  ctx.translate(W / 2 + v.x, H / 2 + v.y); ctx.scale(v.k, v.k);
  ctx.lineWidth = 1 / v.k;
  for (const h of this.hier) {
    ctx.strokeStyle = lit(h.a) && lit(h.b) ? "#3a4868" : "#1c2436";
    ctx.beginPath(); ctx.moveTo(h.a.px, h.a.py); ctx.lineTo(h.b.px, h.b.py); ctx.stroke();
  }
  for (const l of this.links) {
    const on = S.markEdges ? l.items.some(e => S.markEdges.has(e)) : !focus || (focus.has(l.a) && focus.has(l.b) && (!sel || l.a === sel || l.b === sel));
    ctx.globalAlpha = on ? (focus || S.markEdges ? 0.85 : 0.3) : 0.06;
    ctx.strokeStyle = ctx.fillStyle = EDGE_COLORS[l.type] || "#888";
    ctx.lineWidth = (0.8 + Math.log2(l.items.length + 1) * 0.7) / Math.sqrt(v.k);
    const dx = l.b.px - l.a.px, dy = l.b.py - l.a.py, d = Math.sqrt(dx * dx + dy * dy) || 1, ux = dx / d, uy = dy / d;
    const ex = l.b.px - ux * (l.b.r + 2), ey = l.b.py - uy * (l.b.r + 2), s = 6 / Math.sqrt(v.k);
    ctx.beginPath(); ctx.moveTo(l.a.px, l.a.py); ctx.lineTo(ex, ey); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(ex, ey); ctx.lineTo(ex - ux * s - uy * s * 0.5, ey - uy * s + ux * s * 0.5); ctx.lineTo(ex - ux * s + uy * s * 0.5, ey - uy * s - ux * s * 0.5); ctx.fill();
  }
  ctx.globalAlpha = 1;
  const t = tree();
  for (const n of this.vis) {
    ctx.globalAlpha = lit(n) ? 1 : 0.18;
    ctx.fillStyle = colorOf(n);
    ctx.beginPath(); ctx.arc(n.px, n.py, n.r * (n === S.hover ? 1.15 : 1), 0, Math.PI * 2); ctx.fill();
    ctx.lineWidth = 1.5 / v.k; ctx.strokeStyle = "#0d1320"; ctx.stroke();
    if (n.children.some(c => c.keep) && !t.expanded.has(n.key)) {
      ctx.setLineDash([3 / v.k, 3 / v.k]); ctx.strokeStyle = colorOf(n);
      ctx.beginPath(); ctx.arc(n.px, n.py, n.r + 3.5 / v.k + 1.5, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
    }
    if (S.mark && marked(n)) { ctx.strokeStyle = "#ffe066"; ctx.lineWidth = 3 / v.k; ctx.beginPath(); ctx.arc(n.px, n.py, n.r + 5 / v.k, 0, Math.PI * 2); ctx.stroke(); }
    if (n === S.selected) { ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2.5 / v.k; ctx.beginPath(); ctx.arc(n.px, n.py, n.r + 3 / v.k, 0, Math.PI * 2); ctx.stroke(); }
  }
  ctx.globalAlpha = 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.textAlign = "center"; ctx.textBaseline = "top";
  for (const n of this.vis) {
    const d = n.depth;
    const show = n === S.hover || n === S.selected || (S.mark && marked(n)) || d <= 1 || (d === 2 && v.k > 0.55) || (d === 3 && v.k > 1.4) || d > 3 && v.k > 2.4;
    if (!show || (focus && !focus.has(n) && d > 1)) continue;
    const sx = W / 2 + v.x + n.px * v.k, sy = H / 2 + v.y + (n.py + n.r) * v.k + 3;
    if (sx < -100 || sx > W + 100 || sy < -20 || sy > H + 20) continue;
    label(d <= 1 ? n.name : short(n.name, 34), sx, sy, d <= 1, !lit(n));
  }
};

/** Return the instance under a screen point. */
Force.hit = function (x, y) {
  const v = this.v, wx = (x - W / 2 - v.x) / v.k, wy = (y - H / 2 - v.y) / v.k;
  let best = null, bd = Infinity;
  for (const n of this.vis) { const d = Math.hypot(n.x - wx, n.y - wy); if (d < n.r + 4 / v.k && d < bd) { best = n; bd = d; } }
  return best;
};

/** Fit the view to some instances, or to everything shown; with ease, move part of the way for a smooth follow. */
Force.fit = function (only, ease) {
  const set = only && only.length ? only : this.vis;
  if (!set.length) return;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const n of set) { x0 = Math.min(x0, n.x - n.r); y0 = Math.min(y0, n.y - n.r); x1 = Math.max(x1, n.x + n.r); y1 = Math.max(y1, n.y + n.r); }
  const v = this.v, k = Math.max(0.15, Math.min(2.5, 0.9 * Math.min(W / (x1 - x0 + 160), H / (y1 - y0 + 60))));
  const target = {k, x: -(x0 + x1) / 2 * k, y: -(y0 + y1) / 2 * k}, f = ease || 1;
  v.k += (target.k - v.k) * f; v.x += (target.x - v.x) * f; v.y += (target.y - v.y) * f; dirty = true;
};

/** Let the layout settle on screen while the view follows it, instead of jumping to a finished layout. */
Force.settle = function () {
  this.alpha = 1;
  for (let s = 0; s < 40 && this.tick(); s++);
  this.fit();
  this.autoFit = performance.now() + 2200;
};

/** Step the layout and keep the view framed while it settles; return whether anything moved. */
Force.step = function () {
  const moved = this.tick() && (this.vis.length < 400 || this.tick());
  if (performance.now() < this.autoFit && !mouse.down) this.fit(null, 0.08);
  return moved;
};

/** Move or zoom the force view. */
Force.pan = function (dx, dy) { this.v.x += dx; this.v.y += dy; dirty = true; };
Force.zoom = function (mx, my, f) {
  const v = this.v, k = Math.max(0.1, Math.min(6, v.k * f));
  v.x = mx - (mx - v.x) * k / v.k; v.y = my - (my - v.y) * k / v.k; v.k = k; dirty = true;
};

// ---------- tree ----------
const Tree = {v: {x: 40, y: 30, k: 1}, g: null, rows: 0, shown: new Map()};
const NS = "http://www.w3.org/2000/svg";

/** Return a new SVG element with attributes. */
function svgEl(tag, attrs) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; }

/** Lay out and render the collapsible tree; nodes slide from where they were (or from their parent) to their new place. */
Tree.refresh = function () {
  const t = tree(), before = this.shown, moves = [];
  this.shown = new Map();
  svg.replaceChildren();
  this.g = svgEl("g", {});
  svg.append(this.g);
  let row = 0;
  const place = i => {
    const kids = t.expanded.has(i.key) ? i.children.filter(c => c.keep) : [];
    i.tx = i.depth * 230;
    if (kids.length) { kids.forEach(place); i.ty = (kids[0].ty + kids[kids.length - 1].ty) / 2; } else i.ty = row++ * 24;
    return kids;
  };
  place(t.root);
  this.rows = row;
  const links = svgEl("g", {fill: "none", stroke: "#3a4868", "stroke-width": 1.2, class: "tlinks"}), dots = svgEl("g", {});
  this.g.append(links, dots);
  const start = i => { for (let p = i; p; p = p.parent) if (before.has(p.key)) return before.get(p.key); return [i.tx, i.ty]; };
  const draw = i => {
    const kids = t.expanded.has(i.key) ? i.children.filter(c => c.keep) : [];
    for (const c of kids) {
      const mx = (i.tx + c.tx) / 2;
      links.append(svgEl("path", {d: `M${i.tx},${i.ty} C${mx},${i.ty} ${mx},${c.ty} ${c.tx},${c.ty}`}));
      draw(c);
    }
    const hidden = i.children.some(c => c.keep) && !kids.length;
    const node = svgEl("g", {class: "tnode"});
    const [fx, fy] = MOTION ? start(i) : [i.tx, i.ty];
    node.style.transform = `translate(${fx}px, ${fy}px)`;
    moves.push([node, i]);
    this.shown.set(i.key, [i.tx, i.ty]);
    const r = Math.min(9, 3.5 + Math.sqrt(i.agg) * 0.45);
    node.append(svgEl("circle", {r, fill: hidden ? colorOf(i) : "#0d1320", stroke: colorOf(i), "stroke-width": 2.2}));
    if (marked(i) || i === S.selected) node.append(svgEl("circle", {r: r + 4, fill: "none", stroke: i === S.selected ? "#fff" : "#ffe066", "stroke-width": 2}));
    const text = svgEl("text", {x: r + 6, y: 4, fill: S.mark && !subtreeMarked(i) ? "#56617a" : "#dbe3f2", "font-size": i.depth <= 1 ? 13 : 12, "font-weight": i.depth <= 1 ? 600 : 400});
    const count = i.children.filter(c => c.keep).length;
    text.textContent = short(i.name, 44) + (hidden ? `  (${count})` : "");
    node.append(text);
    node.firstChild.addEventListener("click", ev => { ev.stopPropagation(); toggleInst(i); });
    text.addEventListener("click", ev => { ev.stopPropagation(); select(i); });
    node.addEventListener("mouseenter", () => showTip(i));
    node.addEventListener("mouseleave", hideTip);
    dots.append(node);
  };
  draw(t.root);
  this.apply();
  requestAnimationFrame(() => requestAnimationFrame(() => {
    for (const [node, i] of moves) node.style.transform = `translate(${i.tx}px, ${i.ty}px)`;
    links.classList.add("on");
  }));
};

/** Apply the tree's pan and zoom. */
Tree.apply = function () { if (this.g) this.g.setAttribute("transform", `translate(${this.v.x},${this.v.y}) scale(${this.v.k})`); };
Tree.pan = function (dx, dy) { this.v.x += dx; this.v.y += dy; this.apply(); };
Tree.zoom = function (mx, my, f) {
  const v = this.v, k = Math.max(0.2, Math.min(3, v.k * f));
  v.x = mx - (mx - v.x) * k / v.k; v.y = my - (my - v.y) * k / v.k; v.k = k; this.apply();
};
Tree.fit = function () { const v = this.v; v.k = Math.max(0.7, Math.min(1, (H - 40) / Math.max(1, this.rows * 24))); v.x = 40; v.y = Math.max(24, (H - this.rows * 24 * v.k) / 2); this.apply(); };
Tree.settle = function () { this.fit(); };

// ---------- circle packing ----------
const Pack = {root: null, focus: null, v: {x: 0, y: 0, k: 1}, anim: null, all: [], born: 0};

/** Place sibling circles without overlap, each tangent to two placed ones and as close to the centre as possible. */
function packSiblings(cs) {
  const placed = [];
  for (const c of cs.sort((a, b) => b.r - a.r)) {
    if (!placed.length) { c.x = 0; c.y = 0; } else if (placed.length === 1) { c.x = placed[0].r + c.r; c.y = 0; } else {
      let best = null, bd = Infinity;
      for (let i = 0; i < placed.length; i++) for (let j = i + 1; j < placed.length; j++) {
        const A = placed[i], B = placed[j], dA = A.r + c.r, dB = B.r + c.r, dx = B.x - A.x, dy = B.y - A.y, d = Math.hypot(dx, dy);
        if (d > dA + dB || d < Math.abs(dA - dB) || d === 0) continue;
        const a = (dA * dA - dB * dB + d * d) / (2 * d), h = Math.sqrt(Math.max(0, dA * dA - a * a));
        const px = A.x + a * dx / d, py = A.y + a * dy / d;
        for (const s of [1, -1]) {
          const x = px - s * h * dy / d, y = py + s * h * dx / d, dist = Math.hypot(x, y);
          if (dist >= bd || placed.some(q => Math.hypot(q.x - x, q.y - y) < q.r + c.r - 1e-6)) continue;
          best = {x, y}; bd = dist;
        }
      }
      if (!best) { const R = Math.max(...placed.map(p => Math.hypot(p.x, p.y) + p.r)); best = {x: R + c.r, y: 0}; }
      c.x = best.x; c.y = best.y;
    }
    placed.push(c);
  }
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const c of cs) { x0 = Math.min(x0, c.x - c.r); x1 = Math.max(x1, c.x + c.r); y0 = Math.min(y0, c.y - c.r); y1 = Math.max(y1, c.y + c.r); }
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  for (const c of cs) { c.x -= cx; c.y -= cy; }
  return Math.max(...cs.map(c => Math.hypot(c.x, c.y) + c.r));
}

/** Build the packed circles of the kept hierarchy down to symbols. */
Pack.refresh = function () {
  this.all = [];
  this.born = performance.now();
  const make = (i, parent) => {
    const p = {inst: i, parent, children: []};
    this.all.push(p);
    p.children = i.children.filter(c => c.keep).map(c => make(c, p));
    if (p.children.length) p.r = packSiblings(p.children) + 3;
    else p.r = Math.sqrt(Math.max(40, i.ref && i.ref.tokens ? i.ref.tokens / 4 : 60));
    return p;
  };
  this.root = make(tree().root, null);
  const absolute = (p, x, y) => { p.ax = x; p.ay = y; for (const c of p.children) absolute(c, x + c.x, y + c.y); };
  absolute(this.root, 0, 0);
  const keep = this.focus && this.all.find(p => p.inst === this.focus.inst);
  this.focus = keep || (this.root.children.length === 1 ? this.root.children[0] : this.root);
  this.jump(this.focus);
};

/** Return the view that frames a circle. */
Pack.target = function (p) { return {x: p.ax, y: p.ay, k: Math.min(W, H) * 0.46 / p.r}; };

/** Frame a circle at once. */
Pack.jump = function (p) { this.focus = p; this.v = this.target(p); dirty = true; };

/** Animate the view to frame a circle. */
Pack.zoomTo = function (p) {
  const from = {...this.v}, to = this.target(p), t0 = performance.now();
  this.focus = p;
  this.anim = now => {
    const t = Math.min(1, (now - t0) / 450), e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    const k = from.k * Math.pow(to.k / from.k, e);
    this.v = {x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e, k};
    dirty = true;
    return t < 1;
  };
};

/** Step the zoom animation. */
Pack.tick = function () { if (this.anim && !this.anim(performance.now())) this.anim = null; return !!this.anim; };

/** Draw the packed circles: they inflate level by level after a change, leaves float, and the hovered circle is outlined. */
Pack.draw = function () {
  const v = this.v, now = performance.now(), age = MOTION ? now - this.born : 1e9;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
  const sx = p => W / 2 + (p.ax - v.x) * v.k, sy = p => H / 2 + (p.ay - v.y) * v.k;
  const grow = d => { const t = Math.max(0, Math.min(1, (age - d * 110) / 420)); return 1 - Math.pow(1 - t, 3); };
  const walk = p => {
    const g = grow(p.inst.depth), [fx, fy] = p.children.length ? [0, 0] : drift(p.inst, now);
    const r = p.r * v.k * g, x = sx(p) + fx * 0.6, y = sy(p) + fy * 0.6;
    if (r < 0.7 || x + r < 0 || x - r > W || y + r < 0 || y - r > H) return;
    const dim = S.mark && !subtreeMarked(p.inst);
    ctx.globalAlpha = dim ? 0.25 : 1;
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = colorOf(p.inst);
    ctx.globalAlpha = (dim ? 0.25 : 1) * (p.children.length ? 0.13 + 0.03 * p.inst.depth : 0.8);
    ctx.fill();
    ctx.globalAlpha = dim ? 0.25 : 0.9;
    ctx.lineWidth = p === this.focus ? 2 : 1; ctx.strokeStyle = colorOf(p.inst); ctx.stroke();
    if ((S.mark && marked(p.inst)) || p.inst === S.selected) { ctx.lineWidth = 3; ctx.strokeStyle = p.inst === S.selected ? "#fff" : "#ffe066"; ctx.stroke(); }
    else if (p.inst === S.hover) { ctx.globalAlpha = 1; ctx.lineWidth = 2.5; ctx.strokeStyle = "#ffffff"; ctx.stroke(); }
    ctx.globalAlpha = 1;
    p.children.forEach(walk);
  };
  walk(this.root);
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  const labelled = [...this.focus.children, ...this.focus.children.flatMap(c => c.children.length > 6 ? [] : c.children)];
  for (const p of labelled) {
    const r = p.r * v.k * grow(p.inst.depth);
    if (r < 16) continue;
    const top = p.children.length && r > 50;
    label(short(p.inst.name, Math.max(6, Math.floor(r / 4))), sx(p), top ? sy(p) - r + 14 : sy(p), p.parent === this.focus, S.mark && !subtreeMarked(p.inst));
  }
  ctx.textBaseline = "top";
  label(this.focus.inst.name + (this.focus.parent ? "   (click outside to zoom out)" : ""), W / 2, 8, true, false);
};

/** Return the deepest circle under a screen point. */
Pack.hit = function (x, y) {
  const v = this.v, wx = (x - W / 2) / v.k + v.x, wy = (y - H / 2) / v.k + v.y;
  let found = null;
  const walk = p => { if (Math.hypot(p.ax - wx, p.ay - wy) > p.r || p.r * v.k < 2) return; found = p; p.children.forEach(walk); };
  walk(this.root);
  return found;
};

/** Zoom into a clicked circle, select a clicked leaf, or zoom out from an empty click. */
Pack.click = function (x, y) {
  const p = this.hit(x, y);
  if (!p || p === this.focus) { if (this.focus.parent) this.zoomTo(this.focus.parent); return; }
  let step = p;
  while (step.parent && step.parent !== this.focus && step.parent.children.length) step = step.parent;
  select(step.children.length && step !== this.focus ? step.inst : p.inst);
  if (step.children.length && step !== this.focus) this.zoomTo(step);
};
Pack.pan = function (dx, dy) { this.v.x -= dx / this.v.k; this.v.y -= dy / this.v.k; dirty = true; };
Pack.zoom = function (mx, my, f) { this.v.k = Math.max(0.05, Math.min(400, this.v.k * f)); dirty = true; };
Pack.fit = function () { this.zoomTo(this.root); };
Pack.settle = function () { this.jump(this.focus || this.root); };
