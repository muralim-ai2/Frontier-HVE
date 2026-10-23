/** Solution map explorer data model: indexes, the Concepts and Architecture hierarchies, filters, links, search and concept cards. */

const PALETTE = ["#4f8cff", "#2ed3a0", "#ff5fa2", "#ffa94d", "#a77bff", "#29c5f6", "#f6c453", "#ff4d5e", "#c9e265", "#ff8c61",
  "#9fb3cf", "#e879f9", "#7dd3fc", "#fda4af", "#86efac", "#fcd34d", "#c48e9a", "#5eead4"];
const EDGE_COLORS = {
  imports: "#4f8cff", invokes: "#ffa94d", "guarded-by": "#ff4d5e", uses: "#9fb3cf", writes: "#f6c453", "delegates-to": "#ff5fa2",
  "tested-by": "#7d8597", "documented-in": "#c48e9a", "decided-in": "#ff8c61"
};
const STRUCTURAL = new Set(["contains", "includes"]);
const DEPTH_BASE = [20, 12, 7, 4.5, 3, 2.5];

const G = {nodes: new Map(), edges: [], out: new Map(), inc: new Map(), parent: new Map(), children: new Map(),
  concepts: MAP.concepts, conceptOf: new Map(), color: new Map()};
const S = {hier: "concepts", view: "force", edgesOn: new Set(["imports", "invokes", "guarded-by", "uses", "writes", "delegates-to"]),
  filter: null, history: [], selected: null, hover: null, mark: null, markEdges: null, level: 2, trees: {}};

for (const n of MAP.nodes) { n.agg = 0; G.nodes.set(n.id, n); G.out.set(n.id, []); G.inc.set(n.id, []); G.children.set(n.id, []); }
for (const [f, t, type, ev] of MAP.edges) {
  const e = {f, t, type, ev};
  G.edges.push(e);
  G.out.get(f).push(e); G.inc.get(t).push(e);
  if (type === "contains" && !G.parent.has(t)) { G.parent.set(t, f); G.children.get(f).push(t); }
}
for (const e of G.edges) {
  if (STRUCTURAL.has(e.type)) continue;
  const seen = new Set();
  for (const id of [e.f, e.t]) for (let p = id; p; p = G.parent.get(p)) if (!seen.has(p)) { seen.add(p); G.nodes.get(p).agg++; }
}
MAP.nodes.filter(n => n.level === "view").forEach((n, i) => G.color.set("view:" + n.view, PALETTE[i % PALETTE.length]));
MAP.concepts.forEach((c, i) => {
  G.color.set(c.id, PALETTE[(i * 5) % PALETTE.length]);
  const node = G.nodes.get(c.id);
  node.agg = c.members.reduce((s, m) => s + G.nodes.get(m).agg, 0);
  for (const m of c.members) if (!G.conceptOf.has(m)) G.conceptOf.set(m, c);
});

/** Return the file node id that holds a node, or the node itself. */
function fileOf(id) { return id.startsWith("file:") ? id.split("#")[0] : id; }

/** Return a new hierarchy instance of a map node or a virtual group. */
function inst(tree, ref, name, level, parent, key) {
  const i = {key, ref, name, level, parent, children: [], depth: parent ? parent.depth + 1 : 0, concept: parent ? parent.concept : null};
  if (ref) (tree.idx.get(ref.id) || tree.idx.set(ref.id, []).get(ref.id)).push(i);
  if (parent) parent.children.push(i);
  return i;
}

/** Add a map node and its contained nodes under a parent instance. */
function subtree(tree, ref, parent, prefix) {
  const i = inst(tree, ref, ref.name, ref.level, parent, prefix + ref.id);
  for (const c of G.children.get(ref.id)) subtree(tree, G.nodes.get(c), i, prefix);
  return i;
}

/** Return the Architecture hierarchy: system, views, modules, files, symbols. */
function architectureTree() {
  const tree = {name: "architecture", idx: new Map()};
  tree.root = subtree(tree, G.nodes.get("system"), null, "");
  return finish(tree);
}

/** Return the group a concept member sits in: its module with the module's folder, or the data stores group. */
function groupOf(n) {
  if (n.level !== "file") return {key: "stores", name: "Data stores"};
  const m = G.nodes.get(n.module), dir = n.source.includes("/") ? n.source.slice(0, n.source.lastIndexOf("/")) : ".";
  return {key: n.module, name: m && !m.id.startsWith("mod:") ? m.name : dir};
}

/** Return the Concepts hierarchy: concepts, modules, files, symbols. */
function conceptTree() {
  const tree = {name: "concepts", idx: new Map()};
  tree.root = inst(tree, null, "Concepts", "root", null, "concepts");
  for (const c of G.concepts) {
    const ci = inst(tree, G.nodes.get(c.id), c.name, "concept", tree.root, c.id);
    ci.concept = c;
    const groups = new Map();
    for (const m of c.members) {
      const n = G.nodes.get(m), g = groupOf(n);
      if (!groups.has(g.key)) groups.set(g.key, inst(tree, null, g.name, "folder", ci, c.id + "|" + g.key));
      subtree(tree, n, groups.get(g.key), c.id + "|");
    }
  }
  return finish(tree);
}

/** Sum connections into virtual groups and set every instance's radius. */
function finish(tree) {
  const walk = i => {
    i.children.forEach(walk);
    i.agg = i.ref && i.level !== "concept" ? i.ref.agg : i.children.reduce((s, c) => s + c.agg, 0);
    i.r = DEPTH_BASE[Math.min(i.depth, 5)] + Math.min(i.depth === 0 ? 14 : 16, Math.sqrt(i.agg) * (i.depth > 3 ? 0.9 : 1.1));
  };
  walk(tree.root);
  tree.expanded = new Set();
  return tree;
}

/** Return the colour of an instance: its concept in the Concepts hierarchy, its view otherwise. */
function colorOf(i) {
  if (i.level === "root" || i.level === "system") return "#ffffff";
  if (S.hier === "concepts" && i.concept) return G.color.get(i.concept.id);
  const n = i.ref;
  return n ? (G.color.get("view:" + n.view) || "#9aa5b8") : "#9aa5b8";
}

/** Return the current hierarchy. */
function tree() { return S.trees[S.hier]; }

/** Mark which instances survive the active filter: scoped nodes, their ancestors and everything under them. */
function markKeep(t) {
  const only = S.filter && S.filter.concepts.size ? S.filter.concepts : null;
  const drop = i => { i.keep = false; i.children.forEach(drop); return false; };
  const walk = (i, inside) => {
    if (only && i.concept && !only.has(i.concept.id)) return drop(i);
    const self = !S.filter || inside || (i.ref && S.filter.ids.has(i.ref.id));
    let any = self;
    for (const c of i.children) if (walk(c, self && !!S.filter)) any = true;
    i.keep = any;
    return any;
  };
  walk(t.root, false);
}

/** Open every instance shallower than the level. */
function setLevel(level) {
  S.level = level;
  const t = tree();
  t.expanded.clear();
  const walk = i => { if (i.depth < level && i.children.length) { t.expanded.add(i.key); i.children.forEach(walk); } };
  walk(t.root);
  revealScope();
}

/** Open the ancestors of every filtered node so the filter's nodes are on screen. */
function revealScope() {
  if (!S.filter) return;
  const t = tree();
  for (const id of S.filter.ids) for (const i of t.idx.get(id) || []) for (let p = i.parent; p; p = p.parent) t.expanded.add(p.key);
}

/** Expand ancestors so a map node shows, and return its first instance in the current hierarchy. */
function reveal(id) {
  const t = tree(), list = (t.idx.get(id) || []).filter(i => i.keep !== false);
  if (!list.length) return null;
  for (let p = list[0].parent; p; p = p.parent) t.expanded.add(p.key);
  return list[0];
}

/** Return the instances on screen: kept, and under expanded parents only. */
function visible() {
  const t = tree(), out = [];
  const walk = i => { if (!i.keep) return; out.push(i); if (t.expanded.has(i.key)) i.children.forEach(walk); };
  walk(t.root);
  return out;
}

/** Return the nearest on-screen ancestor-or-self of an instance. */
function rep(i) {
  const t = tree(), chain = [];
  for (let p = i; p; p = p.parent) chain.push(p);
  for (let k = chain.length - 1; k > 0; k--) if (!t.expanded.has(chain[k].key)) return chain[k];
  return i;
}

/** Return the map's typed links rolled up to the instances on screen. */
function links() {
  const t = tree(), agg = new Map();
  for (const e of G.edges) {
    if (STRUCTURAL.has(e.type) || !S.edgesOn.has(e.type)) continue;
    for (const a of t.idx.get(e.f) || []) {
      if (!a.keep) continue;
      for (const b of t.idx.get(e.t) || []) {
        if (!b.keep) continue;
        const ra = rep(a), rb = rep(b);
        if (ra === rb) continue;
        const key = ra.key + "|" + rb.key + "|" + e.type;
        (agg.get(key) || agg.set(key, {a: ra, b: rb, type: e.type, items: []}).get(key)).items.push(e);
      }
    }
  }
  return [...agg.values()];
}

/** Apply a filter of map node ids, remembering the previous one for Back. */
function applyFilter(label, ids) {
  S.history.push(S.filter);
  S.filter = ids ? {label, ids: new Set(ids), concepts: new Set(ids.filter(id => id.startsWith("concept:")))} : null;
  for (const t of Object.values(S.trees)) markKeep(t);
  setLevel(S.level);
}

/** Return to the previous filter, or the whole map when there is none. */
function back() {
  S.filter = S.history.pop() || null;
  for (const t of Object.values(S.trees)) markKeep(t);
  setLevel(S.level);
}

/** Return a node id with its direct, non-structural neighbours. */
function neighbourhood(id) {
  const ids = [id];
  for (const e of G.out.get(id)) if (!STRUCTURAL.has(e.type)) ids.push(e.t);
  for (const e of G.inc.get(id)) if (!STRUCTURAL.has(e.type)) ids.push(e.f);
  return ids;
}

/** Return the ids a node stands for when filtering: a concept's members, else the node and its neighbours. */
function scopeOf(id) {
  const c = G.concepts.find(x => x.id === id);
  return c ? [c.id, ...c.members] : neighbourhood(id);
}

/** Return a fuzzy score of a query word against a text, or -1. */
function fuzzy(q, s) {
  s = (s || "").toLowerCase();
  const i = s.indexOf(q);
  if (i >= 0) return 60 + q.length * 4 - i * 0.2 + (i === 0 || /[\W_]/.test(s[i - 1]) ? 25 : 0) - s.length * 0.05;
  let si = 0, score = 0, run = 0;
  for (const ch of q) {
    const j = s.indexOf(ch, si);
    if (j < 0) return -1;
    run = j === si ? run + 1 : 0;
    score += 1 + run * 2 + (j === 0 || /[\W_]/.test(s[j - 1]) ? 4 : 0) - Math.min(3, (j - si) * 0.1);
    si = j + 1;
  }
  return score - s.length * 0.05;
}

/** Return the map nodes that best match free text, concepts first on ties. */
function search(text, limit) {
  const words = text.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const rank = {concept: 6, system: 0, view: 4, module: 3, file: 2, symbol: 1};
  const scored = [];
  for (const n of G.nodes.values()) {
    let total = 0;
    for (const w of words) {
      const s = Math.max(fuzzy(w, n.name), fuzzy(w, n.id) * 0.8, (n.purpose || "").toLowerCase().includes(w) ? 30 : -1,
        n.level === "concept" && (G.concepts.find(c => c.id === n.id).keywords || []).some(k => k.toLowerCase().includes(w)) ? 90 : -1);
      if (s < 0) { total = -1; break; }
      total += s;
    }
    if (total >= 0) scored.push([total + rank[n.level] * 3, n]);
  }
  return scored.sort((a, b) => b[0] - a[0]).slice(0, limit || 14).map(s => s[1]);
}

/** Return a concept as folders, files, functions, connections, dependencies, tests, docs and decisions. */
function conceptCard(c) {
  const members = new Set(c.members), folders = new Map();
  for (const m of c.members) {
    const n = G.nodes.get(m);
    if (n.level !== "file") continue;
    const dir = groupOf(n).name;
    const fns = G.children.get(m).map(id => G.nodes.get(id)).filter(s => s.kind === "function" || s.kind === "class");
    (folders.get(dir) || folders.set(dir, []).get(dir)).push({node: n, fns});
  }
  const conn = new Map(), deps = new Set(), tests = new Set(), docs = new Set(), decisions = new Set();
  const label = id => { const k = G.conceptOf.get(fileOf(id)); return k ? {key: k.id, name: k.name} : {key: id, name: G.nodes.get(id).name}; };
  for (const m of members) {
    for (const e of G.out.get(m)) {
      if (e.type === "tested-by") tests.add(e.t);
      else if (e.type === "documented-in") docs.add(e.t);
      else if (e.type === "decided-in") decisions.add(e.t);
      else if (!STRUCTURAL.has(e.type) && !members.has(e.t)) { const l = label(e.t); const k = "out|" + e.type + "|" + l.key; (conn.get(k) || conn.set(k, {dir: "uses", type: e.type, l, items: []}).get(k)).items.push(e); }
    }
    for (const e of G.inc.get(m)) {
      if (["imports", "invokes", "guarded-by", "delegates-to"].includes(e.type) && !members.has(e.f)) { const l = label(e.f); const k = "in|" + e.type + "|" + l.key; (conn.get(k) || conn.set(k, {dir: "used by", type: e.type, l, items: []}).get(k)).items.push(e); }
    }
    for (const x of G.nodes.get(m).external || []) deps.add(x);
  }
  return {folders, connections: [...conn.values()].sort((a, b) => b.items.length - a.items.length), external: [...deps].sort(),
    tests: [...tests], docs: [...docs], decisions: [...decisions]};
}

S.trees = {concepts: conceptTree(), architecture: architectureTree()};
for (const t of Object.values(S.trees)) markKeep(t);
