'use strict';
/** Build view trees as plain objects with allowlisted tags and attributes, and mount them as DOM nodes. */
(function (root) {
  const TAGS = new Set(['div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'ul', 'ol', 'li', 'strong', 'em', 'code', 'pre', 'table', 'thead', 'tbody', 'tr',
    'th', 'td', 'blockquote', 'hr', 'button', 'nav', 'section', 'header', 'footer', 'main', 'article', 'details', 'summary', 'small', 'time',
    'label', 'select', 'option', 'svg', 'path', 'circle', 'rect', 'polyline', 'line']);
  const SVG = new Set(['svg', 'path', 'circle', 'rect', 'polyline', 'line']);
  const ATTRIBUTE = /^(class|role|title|tabindex|disabled|open|type|value|selected|viewBox|d|cx|cy|r|x|y|x1|x2|y1|y2|rx|width|height|points|style-width|aria-[a-z-]+|data-[a-z-]+)$/;

  /** @typedef {import('../types').VNode} VNode */
  /** @typedef {import('../types').Child} Child */

  /** Return children without empty values, with nested arrays flattened and numbers as text.
   * @param {Child[]} children
   * @returns {(VNode | string)[]}
   */
  function flatten(children) {
    /** @type {(VNode | string)[]} */
    const out = [];
    for (const child of children) {
      if (Array.isArray(child)) out.push(...flatten(child));
      else if (typeof child === 'number') out.push(String(child));
      else if (child) out.push(child);
    }
    return out;
  }

  /** Create a view node; attribute values are text and never markup.
   * @param {string} tag
   * @param {Record<string, string | number | boolean | null | undefined> | null} attrs
   * @param {...Child} children
   * @returns {VNode}
   */
  function h(tag, attrs, ...children) {
    if (!TAGS.has(tag)) throw new Error(`View tag not allowed: ${tag}`);
    /** @type {Record<string, string>} */
    const clean = {};
    for (const [name, value] of Object.entries(attrs || {})) {
      if (!ATTRIBUTE.test(name)) throw new Error(`View attribute not allowed: ${name}`);
      if (value !== false && value !== null && value !== undefined) clean[name] = value === true ? '' : String(value);
    }
    return { tag, attrs: clean, children: flatten(children) };
  }

  /** Return the text a view node displays.
   * @param {VNode | string} node
   * @returns {string}
   */
  function text(node) {
    return typeof node === 'string' ? node : node.children.map(text).join('');
  }

  /** Create DOM nodes for a view node; text always becomes text nodes.
   * @param {VNode | string} node
   * @param {Document} doc
   * @returns {Node}
   */
  function mount(node, doc) {
    if (typeof node === 'string') return doc.createTextNode(node);
    const element = SVG.has(node.tag) ? doc.createElementNS('http://www.w3.org/2000/svg', node.tag) : doc.createElement(node.tag);
    for (const [name, value] of Object.entries(node.attrs)) {
      if (name === 'style-width') /** @type {HTMLElement} */ (element).style.width = `${Math.max(0, Math.min(100, Number(value)))}%`;
      else element.setAttribute(name, value);
    }
    for (const child of node.children) element.appendChild(mount(child, doc));
    return element;
  }

  const api = { h, text, mount };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.hveVnode = api;
})(globalThis);
