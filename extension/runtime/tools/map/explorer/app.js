/** Explorer UI: controls, filters with Back and Show whole map, concept cards, node details, search, queries and hash links. */

const $ = id => document.getElementById(id);
const VIEWS = {force: Force, tree: Tree, pack: Pack};
const HINTS = {
  force: "Click: details. Double-click: expand or collapse. Drag: move. Wheel: zoom. Dashed ring: hidden children.",
  tree: "Click a dot: expand or collapse. Click a name: details. Drag: move. Wheel: zoom.",
  pack: "Click a circle: zoom in and see details. Click outside the focus: zoom out. Size: file length."
};
const mouse = {x: 0, y: 0, down: false, moved: false, sx: 0, sy: 0, node: null};

/** Return an element with optional text and class. */
function el(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }

/** Return a coloured dot for an instance or colour. */
function dot(color) { const d = el("span", "", "dot"); d.style.background = color; return d; }

/** Return the active view. */
function V() { return VIEWS[S.view]; }

/** Rebuild the active view, the banner and the control states. */
function refresh(settle) {
  V().refresh();
  if (settle) V().settle();
  const b = $("banner");
  b.classList.toggle("on", !!S.filter);
  if (S.filter) $("bannerText").textContent = "Filtered to: " + S.filter.label + "  \u00b7  " + S.filter.ids.size + " nodes. Everything else is hidden.";
  document.querySelectorAll("[data-hier]").forEach(x => x.classList.toggle("on", x.dataset.hier === S.hier));
  document.querySelectorAll("[data-view]").forEach(x => x.classList.toggle("on", x.dataset.view === S.view));
  document.querySelectorAll("[data-level]").forEach(x => x.classList.toggle("on", +x.dataset.level === S.level));
  $("levels").style.visibility = S.view === "pack" ? "hidden" : "visible";
  canvas.style.display = S.view === "tree" ? "none" : "block";
  svg.style.display = S.view === "tree" ? "block" : "none";
  $("hint").textContent = HINTS[S.view];
  renderLegend();
  dirty = true;
}

/** Switch hierarchy or view and redraw from a settled layout. */
function setMode(hier, view) {
  if (hier && hier !== S.hier) { S.hier = hier; S.selected = null; setLevel(S.level); }
  if (view) S.view = view;
  refresh(true);
}

/** Expand or collapse one instance. */
function toggleInst(i) {
  const t = tree();
  if (!i.children.some(c => c.keep)) return;
  if (t.expanded.has(i.key)) { const stack = [i]; while (stack.length) { const m = stack.pop(); t.expanded.delete(m.key); stack.push(...m.children); } }
  else { t.expanded.add(i.key); for (const c of i.children) delete c.x; }
  refresh(false);
}

/** Filter the map to ids with a label, optionally highlighting them, and redraw. */
function filterTo(label, ids, mark, edges) {
  applyFilter(label, ids);
  $("concept").value = "";
  S.mark = mark ? new Set(mark) : null; S.markEdges = edges || null;
  refresh(true);
}

/** Return to the whole map at two levels. */
function wholeMap() {
  S.filter = null; S.history = []; S.mark = null; S.markEdges = null;
  for (const t of Object.values(S.trees)) markKeep(t);
  $("concept").value = "";
  setLevel(2);
  refresh(true);
}

/** Filter to one concept in the Concepts hierarchy and show its card. */
function openConcept(ids) {
  const cs = ids.map(id => G.concepts.find(c => c.id === id || c.id === "concept:" + id)).filter(Boolean);
  if (!cs.length) return;
  S.hier = "concepts";
  filterTo(cs.map(c => c.name).join(" + "), cs.flatMap(c => scopeOf(c.id)));
  $("concept").value = cs.length === 1 ? cs[0].id : "";
  select(tree().idx.get(cs[0].id)[0]);
}

/** Filter to a map node and its direct connections, switching hierarchy when it is not in the current one. */
function goTo(id) {
  const c = G.concepts.find(x => x.id === id);
  if (c) return openConcept([id]);
  if (!(S.trees[S.hier].idx.get(id) || []).length) S.hier = "architecture";
  filterTo(G.nodes.get(id).name + " and its connections", neighbourhood(id), [id]);
  const i = reveal(id);
  refresh(true);
  if (i) select(i);
}

/** Select an instance and show its details. */
function select(i) {
  S.selected = i;
  renderDetails();
  if (S.view === "tree") Tree.refresh();
  dirty = true;
}

/** Return a link that filters to a map node. */
function link(id, text) { const a = el("a", text || G.nodes.get(id).name); a.title = G.nodes.get(id).source || id; a.onclick = () => goTo(id); return a; }

/** Render the details panel for the selection. */
function renderDetails() {
  const box = $("details"), i = S.selected;
  box.replaceChildren();
  if (!i || i.level === "root" || i.level === "system") return renderHome(box);
  if (i.level === "concept") return renderConcept(box, i.concept);
  const crumbs = el("div", "", "crumbs");
  const chain = [];
  for (let p = i.parent; p; p = p.parent) chain.unshift(p);
  chain.forEach((p, k) => { if (k) crumbs.append(" \u203a "); const a = el("a", p.name); a.onclick = () => select(p); crumbs.append(a); });
  box.append(crumbs, el("div", i.name, "name"));
  if (i.level === "folder") {
    box.append(el("div", "Folder in concept " + i.concept.name + ".", "crumbs"));
    for (const f of i.children) { const d = el("div", "", "file"); d.append(link(f.ref.id), " ", el("span", f.ref.purpose || "", "p")); box.append(d); }
    return;
  }
  const n = i.ref, tags = el("div", "", "chips");
  for (const t of [n.level, n.view, n.kind, n.agg + " connections", n.tokens ? n.tokens.toLocaleString() + " tokens" : ""]) if (t) tags.append(el("span", t, "badge"));
  const c = G.conceptOf.get(fileOf(n.id));
  if (c) { const a = el("a", "concept: " + c.name); a.onclick = () => openConcept([c.id]); tags.append(a); }
  box.append(tags);
  if (n.purpose) box.append(el("div", n.purpose, "explain"));
  if (n.source) box.append(el("div", n.source, "src"));
  const row = el("div", "", "row"), b1 = el("button", tree().expanded.has(i.key) ? "Collapse" : "Expand"), b2 = el("button", "Filter to this and its connections");
  b1.disabled = !i.children.some(x => x.keep); b1.onclick = () => { toggleInst(i); renderDetails(); };
  b2.onclick = () => goTo(n.id);
  row.append(b1, b2);
  box.append(row);
  for (const [title, list, other] of [["Uses", G.out.get(n.id), e => e.t], ["Used by", G.inc.get(n.id), e => e.f]]) {
    const groups = new Map();
    for (const e of list) if (!STRUCTURAL.has(e.type)) (groups.get(e.type) || groups.set(e.type, []).get(e.type)).push(e);
    if (!groups.size) continue;
    box.append(el("h3", title));
    for (const [type, es] of groups) {
      const head = el("div"), sw = el("span", "", "swatch"), ul = el("ul");
      sw.style.background = EDGE_COLORS[type] || "#888";
      head.append(sw, " " + type + " (" + es.length + ")");
      for (const e of es.slice(0, 25)) { const li = el("li"); li.append(link(other(e))); li.title = e.ev; ul.append(li); }
      if (es.length > 25) ul.append(el("li", "+" + (es.length - 25) + " more"));
      box.append(head, ul);
    }
  }
  const kids = G.children.get(n.id).map(id => G.nodes.get(id));
  if (kids.length) {
    box.append(el("h3", (n.level === "file" ? "Functions and classes" : "Contains") + " (" + kids.length + ")"));
    for (const k of kids.slice(0, 40)) { const d = el("div", "", "file"); d.append(link(k.id), " ", el("span", k.purpose || "", "p")); box.append(d); }
  }
  box.append(chatHint(n.name));
}

/** Render the start card: what the map holds and the concepts to open. */
function renderHome(box) {
  const s = MAP.size;
  box.append(el("div", G.nodes.get("system").name, "name"), el("div", G.nodes.get("system").purpose || "", "explain"),
    el("div", `${s.class} app: ${s.code_files} code files, ${s.code_lines.toLocaleString()} code lines, ${s.files} mapped files.`, "crumbs"),
    el("h3", "Concepts: pick one to see its modules, files, functions and connections"));
  for (const c of G.concepts) {
    const d = el("div", "", "file"), a = el("a", c.name);
    a.onclick = () => openConcept([c.id]);
    d.append(dot(G.color.get(c.id)), " ", a, " ", el("span", (c.explain || "").split(". ")[0], "p"));
    box.append(d);
  }
  if (G.concepts.some(c => c.derived)) box.append(el("div", "These concepts are the top-level folders. Add named concepts with explanations in docs/architecture/solution-map.config.json, or ask the agent to propose them.", "chat"));
  box.append(chatHint("<topic>"));
}

/** Render a concept as Concept, Folders, Files, Functions, Connections, Dependencies and Explanation. */
function renderConcept(box, c) {
  const card = conceptCard(c);
  const path = el("div", "", "path");
  for (const [k, v] of [["Concept", c.name], ["Modules", card.folders.size], ["Files", c.members.length], ["Connections", card.connections.length], ["Dependencies", card.external.length]]) {
    path.append(el("b", k), el("span", String(v)), el("span", "\u203a"));
  }
  path.lastChild.remove();
  box.append(el("div", "Concept", "crumbs"), el("div", c.name, "name"), path, el("div", c.explain || "No explanation yet.", "explain"));
  const start = el("div", "Start at: ", "crumbs");
  start.append(link(c.start));
  box.append(start, el("h3", "Modules, files and functions"));
  for (const [dir, files] of card.folders) {
    const fd = el("details");
    fd.open = card.folders.size <= 4;
    fd.append(el("summary", dir + "  (" + files.length + ")"));
    for (const {node, fns} of files) {
      const d = el("div", "", "file");
      d.append(link(node.id), " ", el("span", node.purpose || "", "p"));
      if (fns.length) {
        const fl = el("details", "", "fns");
        fl.append(el("summary", fns.length + " functions: " + fns.slice(0, 4).map(f => f.name).join(", ") + (fns.length > 4 ? ", \u2026" : "")));
        for (const f of fns) { const r = el("div"); r.append(el("code", f.name), " " + (f.purpose || "")); r.title = f.source; fl.append(r); }
        d.append(fl);
      }
      fd.append(d);
    }
    box.append(fd);
  }
  if (card.connections.length) {
    box.append(el("h3", "Connections"));
    const ul = el("ul");
    for (const x of card.connections.slice(0, 16)) {
      const li = el("li"), sw = el("span", "", "swatch"), a = el("a", x.l.name);
      sw.style.background = EDGE_COLORS[x.type] || "#888";
      a.onclick = () => goTo(x.l.key);
      li.append(sw, ` ${x.dir} (${x.type}) `, a, x.items.length > 1 ? " \u00d7" + x.items.length : "");
      li.title = x.items.slice(0, 8).map(e => e.ev).join("\n");
      ul.append(li);
    }
    box.append(ul);
  }
  if (card.external.length) {
    box.append(el("h3", "External dependencies"));
    const chips = el("div", "", "chips");
    card.external.forEach(x => chips.append(el("span", x, "badge")));
    box.append(chips);
  }
  for (const [title, ids] of [["Tests", card.tests], ["Docs", card.docs], ["Decisions", card.decisions]]) {
    if (!ids.length) continue;
    box.append(el("h3", title + " (" + ids.length + ")"));
    const chips = el("div", "", "chips");
    ids.slice(0, 20).forEach(id => { chips.append(link(id), " "); });
    box.append(chips);
  }
  if ((c.questions || []).length) { box.append(el("h3", "Questions this answers")); const ul = el("ul"); c.questions.forEach(q => ul.append(el("li", q))); box.append(ul); }
  box.append(chatHint(c.name));
}

/** Return the note on asking about a topic in chat. */
function chatHint(topic) {
  const d = el("div", "", "chat");
  d.append("Ask in Copilot, Claude Code or Codex: ", el("code", "/solution-map " + topic), " — or say \"help me understand " + topic + "\".");
  return d;
}

/** Show the tooltip for an instance at the mouse. */
function showTip(i) {
  const tip = $("tip");
  tip.replaceChildren(el("b", i.name + "  \u00b7  " + (i.ref ? i.ref.level + (i.ref.kind ? " (" + i.ref.kind + ")" : "") : i.level)), el("span", i.ref ? i.ref.purpose || "" : (i.concept ? i.concept.explain : "")));
  tip.style.left = Math.min(mouse.x + 14, W - 390) + "px"; tip.style.top = (mouse.y + 14) + "px"; tip.style.display = "block";
}

/** Hide the tooltip. */
function hideTip() { $("tip").style.display = "none"; }

/** Render the colour legend of the current hierarchy. */
function renderLegend() {
  const box = $("legend");
  box.replaceChildren();
  $("legendTitle").textContent = S.hier === "concepts" ? "Concepts" : "Views";
  const items = S.hier === "concepts" ? G.concepts.map(c => [c.id, c.name, G.color.get(c.id)])
    : MAP.nodes.filter(n => n.level === "view").map(n => [n.id, n.name, G.color.get(n.id)]);
  for (const [id, name, color] of items) { const row = el("div"); row.append(dot(color), link(id, name)); box.append(row); }
}

// ---------- search ----------
let found = [], foundIdx = 0;

/** Render the search dropdown. */
function renderFound() {
  const box = $("results");
  box.replaceChildren();
  found.forEach((n, k) => {
    const row = el("div");
    if (k === foundIdx) row.className = "sel";
    row.append(dot(n.level === "concept" ? G.color.get(n.id) : G.color.get("view:" + n.view) || "#9aa5b8"), el("span", n.name), el("span", n.level, "badge"), el("small", n.purpose || n.id));
    row.onmousedown = ev => { ev.preventDefault(); pick(n); };
    box.append(row);
  });
  box.style.display = found.length ? "block" : "none";
}

/** Filter to a search result. */
function pick(n) { $("results").style.display = "none"; $("q").blur(); goTo(n.id); }

$("q").addEventListener("input", () => { found = search($("q").value); foundIdx = 0; renderFound(); });
$("q").addEventListener("keydown", ev => {
  if (ev.key === "ArrowDown") { foundIdx = Math.min(found.length - 1, foundIdx + 1); renderFound(); ev.preventDefault(); }
  if (ev.key === "ArrowUp") { foundIdx = Math.max(0, foundIdx - 1); renderFound(); ev.preventDefault(); }
  if (ev.key === "Enter" && found[foundIdx]) pick(found[foundIdx]);
  if (ev.key === "Escape") { $("results").style.display = "none"; $("q").blur(); }
});
$("q").addEventListener("blur", () => { $("results").style.display = "none"; });

// ---------- cypher ----------
/** Run the query box, filter the map to the matched nodes and list the rows. */
function runQuery() {
  const msg = $("qmsg"), out = $("qout");
  out.replaceChildren();
  let q, rows;
  try { q = parseCypher($("cypher").value.trim()); rows = execute(q); } catch (err) { msg.textContent = err.message; msg.className = "err"; return; }
  msg.className = "";
  msg.textContent = rows.length + " row" + (rows.length === 1 ? "" : "s") + (rows.length >= q.limit ? " (limit reached)" : "") + ". The map is filtered to them.";
  if (!rows.length) return;
  const ns = new Set(), es = new Set();
  for (const row of rows) for (const v of Object.values(row)) { if (isEdge(v)) es.add(v); else if (v) ns.add(v.id); }
  if (![...ns].some(id => (S.trees[S.hier].idx.get(id) || []).length)) S.hier = "architecture";
  filterTo("query (" + rows.length + " rows)", [...ns], [...ns], es.size ? es : null);
  const cols = q.ret || [...q.pattern.nodes.map(n => n.v), ...q.pattern.rels.map(r => r.v)].filter(v => !v.startsWith("_")).map(ref => ({ref}));
  const table = el("table"), head = el("tr");
  cols.forEach(c => head.append(el("th", c.prop ? c.ref + "." + c.prop : c.ref)));
  table.append(head);
  for (const row of rows.slice(0, 300)) {
    const tr = el("tr");
    for (const c of cols) {
      const td = el("td"), v = row[c.ref];
      if (c.prop) td.textContent = String(prop(v, c.prop) ?? "");
      else if (isEdge(v)) { td.textContent = v.type; td.title = v.ev; } else if (v) td.append(link(v.id));
      tr.append(td);
    }
    table.append(tr);
  }
  out.append(table);
}

const EXAMPLES = [
  ["Files in a concept and what they import", "MATCH (f:file)-[:imports]->(g)\nWHERE f.concept = '" + (G.concepts[0] ? G.concepts[0].name.replace(/'/g, "") : "") + "'\nRETURN f, g"],
  ["Agents and the hooks that guard them", "MATCH (a:agent)-[:guarded-by]->(h)\nRETURN a, h"],
  ["Who imports a file (edit the name)", "MATCH (a)-[:imports]->(b)\nWHERE b.name CONTAINS 'build'\nRETURN a, b"],
  ["Code that touches a data store", "MATCH (f)-[:uses]->(s:store)\nRETURN f, s"],
  ["Files and the decisions that name them", "MATCH (f:file)-[:decided-in]->(d:decision)\nRETURN f, d\nLIMIT 60"],
  ["Untested code files", "MATCH (f:code)\nWHERE NOT f.name =~ '.*(test|spec).*'\nRETURN f, f.concept\nLIMIT 80"],
  ["Functions about tokens", "MATCH (n:function)\nWHERE n.purpose CONTAINS 'token'\nRETURN n, n.source\nLIMIT 40"],
  ["Two hops: what an agent's tools import", "MATCH (a:agent)-[:invokes]->(t)-[:imports]->(d)\nRETURN a, t, d\nLIMIT 60"],
  ["Most connected files", "MATCH (f:file)\nWHERE f.degree > 25\nRETURN f, f.degree"],
];
EXAMPLES.forEach(([text], k) => { const o = el("option", text); o.value = k; $("examples").append(o); });
$("examples").onchange = () => { $("cypher").value = EXAMPLES[$("examples").value][1]; runQuery(); };
$("cypher").value = EXAMPLES[1][1];
$("examples").value = 1;
$("run").onclick = runQuery;
$("cypher").addEventListener("keydown", ev => { if (ev.key === "Enter" && ev.ctrlKey) runQuery(); });

// ---------- controls ----------
const conceptSel = $("concept");
conceptSel.append(el("option", "All concepts"));
conceptSel.firstChild.value = "";
for (const c of G.concepts) { const o = el("option", c.name); o.value = c.id; conceptSel.append(o); }
conceptSel.onchange = () => conceptSel.value ? openConcept([conceptSel.value]) : wholeMap();
document.querySelectorAll("[data-hier]").forEach(b => b.onclick = () => setMode(b.dataset.hier, null));
document.querySelectorAll("[data-view]").forEach(b => b.onclick = () => setMode(null, b.dataset.view));
document.querySelectorAll("[data-level]").forEach(b => b.onclick = () => { setLevel(+b.dataset.level); refresh(true); });
$("fit").onclick = () => V().fit();
$("back").onclick = () => { back(); S.mark = null; S.markEdges = null; if (!S.filter) $("concept").value = ""; refresh(true); };
$("whole").onclick = wholeMap;
for (const type of Object.keys(EDGE_COLORS)) {
  const count = G.edges.filter(e => e.type === type).length;
  if (!count) continue;
  const lab = el("label"), cb = el("input"), sw = el("span", "", "swatch");
  cb.type = "checkbox"; cb.checked = S.edgesOn.has(type); cb.style.width = "auto";
  cb.onchange = () => { cb.checked ? S.edgesOn.add(type) : S.edgesOn.delete(type); refresh(false); };
  sw.style.background = EDGE_COLORS[type];
  lab.append(cb, sw, type + " (" + count + ")");
  $("types").append(lab);
}
$("title").textContent = "Solution map: " + G.nodes.get("system").name;
$("meta").textContent = "Commit " + MAP.commit + " \u00b7 built " + MAP.built.slice(0, 10) + " \u00b7 " + MAP.nodes.length + " nodes \u00b7 " + MAP.edges.length + " edges";

// ---------- pointer ----------
const stage = $("stage");
stage.addEventListener("mousedown", ev => {
  const r = stage.getBoundingClientRect();
  mouse.down = true; mouse.moved = false; mouse.sx = ev.clientX; mouse.sy = ev.clientY;
  mouse.node = S.view === "force" ? Force.hit(ev.clientX - r.left, ev.clientY - r.top) : null;
  Force.drag = mouse.node;
});
window.addEventListener("mousemove", ev => {
  const r = stage.getBoundingClientRect();
  mouse.x = ev.clientX - r.left; mouse.y = ev.clientY - r.top;
  if (mouse.down) {
    if (Math.abs(ev.clientX - mouse.sx) + Math.abs(ev.clientY - mouse.sy) > 3) mouse.moved = true;
    if (mouse.node && mouse.moved) { const v = Force.v; mouse.node.x = (mouse.x - W / 2 - v.x) / v.k; mouse.node.y = (mouse.y - H / 2 - v.y) / v.k; Force.alpha = Math.max(Force.alpha, 0.25); dirty = true; }
    else if (mouse.moved) V().pan(ev.movementX, ev.movementY);
    return;
  }
  if (S.view === "tree" || ev.target !== canvas) return;
  const hit = S.view === "force" ? Force.hit(mouse.x, mouse.y) : (Pack.hit(mouse.x, mouse.y) || {}).inst;
  if (hit !== S.hover) { S.hover = hit || null; dirty = true; }
  if (hit) showTip(hit); else hideTip();
});
window.addEventListener("mouseup", ev => {
  if (mouse.down && !mouse.moved && ev.target === canvas) {
    if (S.view === "force" && mouse.node) select(mouse.node);
    if (S.view === "pack") Pack.click(mouse.x, mouse.y);
  }
  mouse.down = false; mouse.node = null; Force.drag = null;
});
canvas.addEventListener("dblclick", () => { if (S.view === "force") { const n = Force.hit(mouse.x, mouse.y); if (n) { toggleInst(n); select(n); } } });
stage.addEventListener("wheel", ev => { ev.preventDefault(); V().zoom(mouse.x - (S.view === "tree" ? 0 : W / 2), mouse.y - (S.view === "tree" ? 0 : H / 2), Math.exp(-ev.deltaY * 0.0015)); }, {passive: false});
window.addEventListener("keydown", ev => {
  const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
  if (ev.key === "/" && !typing) { ev.preventDefault(); $("q").focus(); }
  if (ev.key === "Escape" && !typing && S.filter) $("back").click();
});
new ResizeObserver(() => { resize(); if (S.view === "pack" && Pack.focus) Pack.jump(Pack.focus); }).observe(stage);

/** Animation loop: step the active view and redraw every frame while things move or float. */
function frame() {
  const moving = S.view === "force" ? Force.step() : S.view === "pack" ? Pack.tick() : false;
  if (S.view !== "tree" && (moving || dirty || MOTION)) { V().draw(); dirty = false; }
  requestAnimationFrame(frame);
}

/** Open the page as its hash or the build's focus asks: concept=, q=, node= or cypher=. */
function route() {
  const hash = decodeURIComponent((location.hash || "#" + (MAP.focus || "")).slice(1)).replace(/\+/g, " ");
  const [key, value] = [hash.split("=")[0], hash.slice(hash.indexOf("=") + 1)];
  if (key === "concept" && value) return openConcept(value.split(","));
  if (key === "node" && G.nodes.has(value)) return goTo(value);
  if (key === "cypher" && value) { $("cypher").value = value; return runQuery(); }
  if (key === "q" && value) {
    const hits = search(value, 10);
    if (!hits.length) return;
    if (hits[0].level === "concept") return openConcept([hits[0].id]);
    if (!hits.some(h => (S.trees[S.hier].idx.get(h.id) || []).length)) S.hier = "architecture";
    filterTo("search \u201c" + value + "\u201d", hits.flatMap(h => scopeOf(h.id)), hits.map(h => h.id));
    $("q").value = value;
  }
}

resize();
setLevel(2);
refresh(true);
renderDetails();
route();
window.addEventListener("hashchange", route);
requestAnimationFrame(frame);
