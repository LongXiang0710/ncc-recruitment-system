const assert = require('assert');

const tableLayout = require('../web/features/table_layout.js');
const {placeActionsAfterSelection} = tableLayout;

assert.strictEqual(typeof tableLayout.listVisibleFields, 'function', 'list-only hidden fields need a shared filter');
assert.deepStrictEqual(
  tableLayout.listVisibleFields([
    {key: 'name'},
    {key: 'channel_detail', listHidden: true},
    {key: 'file_hash', hidden: true},
  ]).map(field => field.key),
  ['name'],
  'main lists should omit hidden and list-only hidden fields',
);

function fakeRow(names, actionClass) {
  const children = names.map(name => ({name, className: name === 'actions' ? actionClass : '', style: {}}));
  return {
    children,
    querySelector(selector) {
      const wanted = selector.split(',').map(item => item.trim().replace('.', ''));
      return this.children.find(child => wanted.includes(child.className)) || null;
    },
    insertBefore(node, before) {
      const oldIndex = this.children.indexOf(node);
      if (oldIndex >= 0) this.children.splice(oldIndex, 1);
      const newIndex = before ? this.children.indexOf(before) : this.children.length;
      this.children.splice(newIndex < 0 ? this.children.length : newIndex, 0, node);
    },
  };
}

for (const actionClass of ['action-column', 'row-actions']) {
  const row = fakeRow(['number', 'selection', 'name', 'status', 'actions'], actionClass);
  placeActionsAfterSelection(row);
  assert.deepStrictEqual(
    row.children.map(cell => cell.name),
    ['number', 'selection', 'actions', 'name', 'status'],
    `${actionClass} should be the third column`,
  );
  const actionCell = row.children[2];
  assert.deepStrictEqual(
    {maxWidth: actionCell.style.maxWidth, overflow: actionCell.style.overflow, textOverflow: actionCell.style.textOverflow},
    {maxWidth: 'none', overflow: 'visible', textOverflow: 'clip'},
    `${actionClass} should show all actions without an ellipsis`,
  );
}

console.log('table layout UI checks passed');
