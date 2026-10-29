'use strict';
/** Render Markdown as view trees: headings, paragraphs, lists with task boxes, tables, quotes, code and inline emphasis; HTML stays text. */
(function (root) {
  /** @type {typeof globalThis.hveVnode} */
  const { h } = typeof module === 'object' && module.exports ? require('./vnode') : root.hveVnode;
  const INLINE = /(`+)(.+?)\1|\*\*(.+?)\*\*|__(.+?)__|\[([^\]]+)\]\(([^)\s]+)[^)]*\)|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])/g;
  const LIST = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
  const TASK = /^\[([ xX])\]\s+(.*)$/;
  const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
  const RULE = /^\s*([-*_])(\s*\1){2,}\s*$/;
  const FENCE = /^\s*(```|~~~)/;

  /** @typedef {import('../types').VNode} VNode */
  /** @typedef {import('../types').Child} Child */
  /** @typedef {{ordered: boolean, text: string, children: Item[]}} Item */

  /** Render inline emphasis, code and links; link targets show as a tooltip and are not followed.
   * @param {string} source
   * @returns {Child[]}
   */
  function inline(source) {
    /** @type {Child[]} */
    const out = [];
    let last = 0;
    for (const match of source.matchAll(INLINE)) {
      const at = match.index || 0;
      if (at > last) out.push(source.slice(last, at));
      if (match[1]) out.push(h('code', null, match[2]));
      else if (match[3] || match[4]) out.push(h('strong', null, ...inline(match[3] || match[4])));
      else if (match[5]) out.push(h('span', { class: 'md-link', title: match[6] }, ...inline(match[5])));
      else out.push(h('em', null, ...inline(match[7] || match[8])));
      last = at + match[0].length;
    }
    if (last < source.length) out.push(source.slice(last));
    return out;
  }

  /** Return whether a line starts a block other than a paragraph.
   * @param {string} line
   * @returns {boolean}
   */
  function blockStart(line) {
    return HEADING.test(line) || FENCE.test(line) || LIST.test(line) || RULE.test(line) || /^\s*>/.test(line) || line.trim().startsWith('|');
  }

  /** Build a nested list from list lines, continuation lines joining the item above.
   * @param {string[]} lines
   * @returns {VNode}
   */
  function list(lines) {
    /** @type {Item[]} */
    const top = [];
    /** @type {{indent: number, children: Item[], item: Item | null}[]} */
    const stack = [{ indent: -1, children: top, item: null }];
    for (const line of lines) {
      const match = LIST.exec(line);
      const parent = stack[stack.length - 1];
      if (!match) {
        if (parent.item) parent.item.text += ` ${line.trim()}`;
        continue;
      }
      const indent = match[1].replace(/\t/g, '    ').length;
      while (stack.length > 1 && indent <= stack[stack.length - 1].indent) stack.pop();
      const item = { ordered: /\d/.test(match[2]), text: match[3], children: [] };
      stack[stack.length - 1].children.push(item);
      stack.push({ indent, children: item.children, item });
    }
    return items(top);
  }

  /** Render list items, showing task boxes as done or open.
   * @param {Item[]} rows
   * @returns {VNode}
   */
  function items(rows) {
    return h(rows[0].ordered ? 'ol' : 'ul', null, ...rows.map(row => {
      const task = TASK.exec(row.text);
      const done = !!task && task[1] !== ' ';
      return h('li', task ? { class: 'md-task' } : null,
        task ? h('span', { class: done ? 'md-box done' : 'md-box', role: 'img', 'aria-label': done ? 'Done' : 'Not done' }) : null,
        ...inline(task ? task[2] : row.text), row.children.length ? items(row.children) : null);
    }));
  }

  /** Return the cells of a table row.
   * @param {string} line
   * @returns {string[]}
   */
  function cells(line) {
    return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim());
  }

  /** Render Markdown text as a list of block view nodes; HTML comments are dropped and other markup is shown as text.
   * @param {string} source
   * @returns {VNode[]}
   */
  function render(source) {
    const lines = source.replace(/\r\n?/g, '\n').replace(/<!--[\s\S]*?-->/g, '').split('\n');
    /** @type {VNode[]} */
    const blocks = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      const fence = FENCE.exec(line);
      const heading = HEADING.exec(line);
      if (!line.trim()) i += 1;
      else if (fence) {
        const body = [];
        for (i += 1; i < lines.length && !lines[i].trim().startsWith(fence[1]); i += 1) body.push(lines[i]);
        i += 1;
        blocks.push(h('pre', null, h('code', null, body.join('\n'))));
      } else if (heading) {
        blocks.push(h(['h2', 'h3', 'h4'][Math.min(heading[1].length, 3) - 1], null, ...inline(heading[2])));
        i += 1;
      } else if (RULE.test(line)) {
        blocks.push(h('hr', null));
        i += 1;
      } else if (line.trim().startsWith('|') && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] || '')) {
        const head = cells(line);
        const rows = [];
        for (i += 2; i < lines.length && lines[i].trim().startsWith('|'); i += 1) rows.push(cells(lines[i]));
        blocks.push(h('div', { class: 'md-table' }, h('table', null, h('thead', null, h('tr', null, ...head.map(cell => h('th', null, ...inline(cell))))),
          h('tbody', null, ...rows.map(row => h('tr', null, ...row.map(cell => h('td', null, ...inline(cell)))))))));
      } else if (/^\s*>/.test(line)) {
        const quote = [];
        for (; i < lines.length && /^\s*>/.test(lines[i]); i += 1) quote.push(lines[i].replace(/^\s*>\s?/, ''));
        blocks.push(h('blockquote', null, ...render(quote.join('\n'))));
      } else if (LIST.test(line)) {
        const rows = [];
        for (; i < lines.length && (LIST.test(lines[i]) || /^\s{2,}\S/.test(lines[i])); i += 1) rows.push(lines[i]);
        blocks.push(list(rows));
      } else {
        const paragraph = [];
        for (; i < lines.length && lines[i].trim() && (!paragraph.length || !blockStart(lines[i])); i += 1) paragraph.push(lines[i].trim());
        blocks.push(h('p', null, ...inline(paragraph.join(' '))));
      }
    }
    return blocks;
  }

  const api = { render, inline };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.hveMarkdown = api;
})(globalThis);
