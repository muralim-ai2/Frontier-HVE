/** Cypher subset over the solution map: MATCH patterns, WHERE, RETURN and LIMIT. */

/** Split a query into tokens. */
function tokenize(src) {
  const re = /\s+|(\/\/[^\n]*)|('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?)|(`[^`]+`|[A-Za-z_](?:\w|-(?=\w))*)|(<-|->|<>|!=|>=|<=|=~|\.\.|[()[\]{}:,.|\-*=<>])/y;
  const out = [];
  re.lastIndex = 0;
  while (re.lastIndex < src.length) {
    const at = re.lastIndex, m = re.exec(src);
    if (!m) throw new Error("Unexpected character at " + at + ": " + src.slice(at, at + 12));
    if (m[2]) out.push({t: "str", v: m[2].slice(1, -1).replace(/\\(.)/g, "$1")});
    else if (m[3]) out.push({t: "num", v: Number(m[3])});
    else if (m[4]) out.push({t: "id", v: m[4].replace(/`/g, "")});
    else if (m[5]) out.push({t: "sym", v: m[5]});
  }
  return out;
}

/** Parse the supported Cypher subset into {pattern, where, ret, limit}. */
function parseCypher(src) {
  const T = tokenize(src);
  let i = 0, anon = 0;
  const peek = () => T[i];
  const isKw = w => T[i] && T[i].t === "id" && T[i].v.toUpperCase() === w;
  const isSym = v => T[i] && T[i].t === "sym" && T[i].v === v;
  const fail = what => { throw new Error("Expected " + what + " at token " + (i + 1) + (T[i] ? " ('" + T[i].v + "')" : " (end)")); };
  const sym = v => { if (!isSym(v)) fail("'" + v + "'"); i++; };
  const kw = w => { if (!isKw(w)) fail(w); i++; };
  const ident = () => { if (!T[i] || T[i].t !== "id") fail("a name"); return T[i++].v; };
  const value = () => {
    const t = T[i];
    if (t && (t.t === "str" || t.t === "num")) { i++; return t.v; }
    if (t && t.t === "id" && /^(true|false)$/i.test(t.v)) { i++; return t.v.toLowerCase() === "true"; }
    return fail("a value");
  };
  const props = () => {
    const p = {};
    if (!isSym("{")) return p;
    i++;
    while (!isSym("}")) { const k = ident(); sym(":"); p[k] = value(); if (isSym(",")) i++; else break; }
    sym("}");
    return p;
  };
  const labels = into => { if (isSym(":")) { i++; into.push(ident()); while (isSym("|")) { i++; if (isSym(":")) i++; into.push(ident()); } } };
  const node = () => {
    sym("(");
    const n = {v: null, labels: [], props: {}};
    if (peek() && peek().t === "id") n.v = ident();
    labels(n.labels);
    n.props = props();
    sym(")");
    n.v = n.v || "_n" + anon++;
    return n;
  };
  const rel = () => {
    const r = {v: null, types: [], dir: "any", props: {}};
    const left = isSym("<-");
    if (left) i++; else sym("-");
    if (isSym("[")) {
      i++;
      if (peek() && peek().t === "id") r.v = ident();
      labels(r.types);
      r.props = props();
      sym("]");
    }
    if (left) { sym("-"); r.dir = "in"; } else if (isSym("->")) { i++; r.dir = "out"; } else sym("-");
    r.v = r.v || "_r" + anon++;
    return r;
  };
  const operand = () => {
    if (peek() && peek().t === "id" && !/^(true|false)$/i.test(peek().v)) {
      const v = ident();
      if (isSym(".")) { i++; return {ref: v, prop: ident()}; }
      return {ref: v, prop: "id"};
    }
    return {lit: value()};
  };
  const comparison = () => {
    const left = operand();
    let op;
    if (isKw("CONTAINS")) { i++; op = "CONTAINS"; }
    else if (isKw("STARTS")) { i++; kw("WITH"); op = "STARTS"; }
    else if (isKw("ENDS")) { i++; kw("WITH"); op = "ENDS"; }
    else if (isKw("IN")) { i++; op = "IN"; }
    else if (peek() && peek().t === "sym" && ["=", "<>", "!=", "=~", ">", "<", ">=", "<="].includes(peek().v)) op = T[i++].v;
    else fail("an operator");
    if (op !== "IN") return {op, left, right: operand()};
    sym("[");
    const list = [];
    while (!isSym("]")) { list.push(value()); if (isSym(",")) i++; else break; }
    sym("]");
    return {op, left, right: {lit: list}};
  };
  const factor = () => {
    if (isKw("NOT")) { i++; return {not: factor()}; }
    if (isSym("(")) { i++; const e = expr(); sym(")"); return e; }
    return comparison();
  };
  const term = () => { let e = factor(); while (isKw("AND")) { i++; e = {and: [e, factor()]}; } return e; };
  const expr = () => { let e = term(); while (isKw("OR")) { i++; e = {or: [e, term()]}; } return e; };

  kw("MATCH");
  const pattern = {nodes: [node()], rels: []};
  while (isSym("-") || isSym("<-")) { pattern.rels.push(rel()); pattern.nodes.push(node()); }
  let where = null, ret = null, limit = 200;
  if (isKw("WHERE")) { i++; where = expr(); }
  if (isKw("RETURN")) {
    i++; ret = [];
    if (isKw("DISTINCT")) i++;
    do { if (isSym(",")) i++; const v = ident(); ret.push(isSym(".") ? (i++, {ref: v, prop: ident()}) : {ref: v}); } while (isSym(","));
  }
  if (isKw("LIMIT")) { i++; limit = value(); }
  if (i < T.length) fail("end of query");
  return {pattern, where, ret, limit};
}

/** Return whether a value is a bound edge rather than a node. */
function isEdge(x) { return x && "f" in x && "t" in x; }

/** Return a property of a bound node or edge; concept returns the file's first concept name. */
function prop(x, p) {
  if (!x) return undefined;
  if (isEdge(x)) return {type: x.type, evidence: x.ev, from: x.f, to: x.t}[p];
  if (p === "degree" || p === "connections") return x.agg;
  if (p === "children") return G.children.get(x.id).length;
  if (p === "concept") { const c = G.conceptOf.get(fileOf(x.id)); return c ? c.name : undefined; }
  return x[p];
}

/** Return whether a node carries a label: its level, kind, view, language, id prefix or a concept it belongs to. */
function hasLabel(n, l) {
  l = l.toLowerCase();
  if (n.level === l || n.kind === l || n.view === l || n.lang === l || n.id.toLowerCase().startsWith(l + ":")) return true;
  const c = G.concepts.find(x => x.id === "concept:" + l);
  return !!c && c.members.includes(fileOf(n.id));
}

/** Return whether a node or edge matches inline properties. */
function propsOk(x, props) { return Object.entries(props).every(([k, v]) => String(prop(x, k)) === String(v)); }

/** Evaluate a WHERE expression on a binding; text operators ignore case. */
function evaluate(e, b) {
  if (e.and) return evaluate(e.and[0], b) && evaluate(e.and[1], b);
  if (e.or) return evaluate(e.or[0], b) || evaluate(e.or[1], b);
  if (e.not) return !evaluate(e.not, b);
  const get = o => "lit" in o ? o.lit : prop(b[o.ref], o.prop);
  const a = get(e.left), c = get(e.right);
  if (a === undefined || a === null) return e.op === "<>" || e.op === "!=";
  const s = String(a).toLowerCase(), t = String(c).toLowerCase();
  switch (e.op) {
    case "=": return String(a) === String(c);
    case "<>": case "!=": return String(a) !== String(c);
    case "CONTAINS": return s.includes(t);
    case "STARTS": return s.startsWith(t);
    case "ENDS": return s.endsWith(t);
    case "=~": return new RegExp("^(?:" + c + ")$", "i").test(String(a));
    case "IN": return c.map(String).includes(String(a));
    case ">": return +a > +c;
    case "<": return +a < +c;
    case ">=": return +a >= +c;
    case "<=": return +a <= +c;
  }
  return false;
}

/** Run a parsed query and return its rows of bindings. */
function execute(q) {
  const {pattern, where, limit} = q, rows = [], b = {};
  const nodeOk = (n, np) => (!np.labels.length || np.labels.some(l => hasLabel(n, l))) && propsOk(n, np.props) && (!b[np.v] || b[np.v] === n);
  const step = (k, cur) => {
    if (rows.length >= limit) return;
    if (k === pattern.rels.length) { if (!where || evaluate(where, b)) rows.push({...b}); return; }
    const r = pattern.rels[k], np = pattern.nodes[k + 1], cands = [];
    if (r.dir !== "in") for (const e of G.out.get(cur.id)) cands.push([e, e.t]);
    if (r.dir !== "out") for (const e of G.inc.get(cur.id)) cands.push([e, e.f]);
    for (const [e, oid] of cands) {
      if ((r.types.length && !r.types.includes(e.type)) || !propsOk(e, r.props) || (b[r.v] && b[r.v] !== e)) continue;
      const o = G.nodes.get(oid);
      if (!nodeOk(o, np)) continue;
      const pn = b[np.v], pr = b[r.v];
      b[np.v] = o; b[r.v] = e;
      step(k + 1, o);
      b[np.v] = pn; b[r.v] = pr;
      if (rows.length >= limit) return;
    }
  };
  for (const n of G.nodes.values()) {
    if (!nodeOk(n, pattern.nodes[0])) continue;
    b[pattern.nodes[0].v] = n;
    step(0, n);
    delete b[pattern.nodes[0].v];
    if (rows.length >= limit) break;
  }
  return rows;
}
