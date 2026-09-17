const assert = require('assert');
const tableLayout = require('../web/features/table_layout.js');

assert.strictEqual(typeof tableLayout.floatDialogClose, 'function', 'all dialogs need a shared floating close layout');

function classes(...initial) {
  const values = new Set(initial);
  return {
    add: (...names) => names.forEach(name => values.add(name)),
    remove: (...names) => names.forEach(name => values.delete(name)),
    contains: name => values.has(name),
  };
}

function makeDocument() {
  const document = {
    createElement(name) {
      return {
        name,
        children: [],
        parentNode: null,
        ownerDocument: document,
        classList: classes(),
        attributes: {},
        append(...children) {
          for (const child of children) {
            child.remove();
            this.children.push(child);
            child.parentNode = this;
          }
        },
        insertBefore(child, before) {
          child.remove();
          const index = this.children.indexOf(before);
          this.children.splice(index < 0 ? this.children.length : index, 0, child);
          child.parentNode = this;
        },
        remove() {
          if (!this.parentNode) return;
          const index = this.parentNode.children.indexOf(this);
          if (index >= 0) this.parentNode.children.splice(index, 1);
          this.parentNode = null;
        },
        setAttribute(key, value) { this.attributes[key] = value; },
        querySelector(selector) {
          const className = selector.startsWith('.') ? selector.slice(1) : null;
          const find = node => {
            for (const child of node.children) {
              if (className && child.classList.contains(className)) return child;
              const nested = find(child);
              if (nested) return nested;
            }
            return null;
          };
          return find(this);
        },
      };
    },
  };
  return document;
}

function dialogFixture(withClose) {
  const document = makeDocument();
  const dialog = document.createElement('dialog');
  const header = document.createElement('header');
  header.classList.add('dialog-head');
  const body = document.createElement('main');
  let close = null;
  if (withClose) {
    close = document.createElement('button');
    close.classList.add('close');
    close.disabled = true;
    header.append(close);
  }
  dialog.append(header, body);
  dialog.closed = 0;
  dialog.close = () => { dialog.closed += 1; };
  dialog.addEventListener = (name, listener) => { if (name === 'close') dialog.closeListener = listener; };
  return {dialog, close};
}

const existing = dialogFixture(true);
tableLayout.floatDialogClose(existing.dialog);
assert.deepStrictEqual(existing.dialog.children.map(child => child.name), ['button', 'div']);
assert.deepStrictEqual(existing.dialog.children[1].children.map(child => child.name), ['header', 'main']);
assert.ok(existing.dialog.classList.contains('floating-close-dialog'));
assert.ok(existing.close.classList.contains('floating-dialog-close'));
assert.strictEqual(existing.close.disabled, true, 'busy-state protection must be preserved');
tableLayout.floatDialogClose(existing.dialog);
assert.deepStrictEqual(existing.dialog.children.map(child => child.name), ['button', 'div'], 'repeated setup must stay idempotent');

const missing = dialogFixture(false);
tableLayout.floatDialogClose(missing.dialog);
const generatedClose = missing.dialog.children[0];
assert.ok(generatedClose.classList.contains('close'));
assert.ok(generatedClose.classList.contains('floating-dialog-close'));
assert.strictEqual(generatedClose.textContent, '×');
assert.strictEqual(generatedClose.attributes['aria-label'], '关闭');
generatedClose.onclick();
assert.strictEqual(missing.dialog.closed, 1);
missing.dialog.closeListener();
assert.ok(!missing.dialog.classList.contains('floating-close-dialog'));

console.log('dialog layout UI checks passed');
