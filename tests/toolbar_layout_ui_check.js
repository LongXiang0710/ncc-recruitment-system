const assert = require('assert');

let arrangeListToolbar = () => {};
try {
  const loaded = require('../web/features/table_layout.js');
  if (typeof loaded.arrangeListToolbar === 'function') arrangeListToolbar = loaded.arrangeListToolbar;
} catch (_error) {
  // The first TDD run intentionally exercises the not-yet-implemented behavior.
}

function element(name, className = '') {
  return {
    name,
    className,
    children: [],
    parentNode: null,
    append(...nodes) {
      nodes.forEach(node => {
        node.remove();
        node.parentNode = this;
        this.children.push(node);
      });
    },
    prepend(node) {
      node.remove();
      node.parentNode = this;
      this.children.unshift(node);
    },
    remove() {
      if (!this.parentNode) return;
      const index = this.parentNode.children.indexOf(this);
      if (index >= 0) this.parentNode.children.splice(index, 1);
      this.parentNode = null;
    },
    querySelector(selector) {
      const className = selector.startsWith('.') ? selector.slice(1) : '';
      for (const child of this.children) {
        if (child.className.split(' ').includes(className)) return child;
        const nested = child.querySelector(selector);
        if (nested) return nested;
      }
      return null;
    },
  };
}

const toolbar = element('toolbar');
toolbar.ownerDocument = {createElement: () => element('top')};
const summary = element('summary', 'record-summary');
const actions = element('actions', 'toolbar-actions');
const search = element('search');
actions.append(search, element('new'), element('refresh'), element('export'));
toolbar.append(summary, actions);

arrangeListToolbar(toolbar, search);

assert.deepStrictEqual(toolbar.children.map(node => node.name), ['top', 'actions']);
assert.strictEqual(toolbar.querySelector('.record-summary'), null, 'record summary should be removed');
assert.deepStrictEqual(toolbar.children[0].children.map(node => node.name), ['search']);
assert.deepStrictEqual(actions.children.map(node => node.name), ['new', 'refresh', 'export']);

console.log('toolbar layout UI checks passed');
