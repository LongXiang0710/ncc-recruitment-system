const assert = require('assert');

const paginationTools = require('../web/features/pagination.js');

assert.deepStrictEqual(
  paginationTools.pageSizeOptions(),
  [10, 20, 50, 100],
  'page-size selector should only offer 10, 20, 50, and 100',
);

const source = Array.from({length: 35}, (_, index) => `row-${index + 1}`);
const secondPage = paginationTools.paginate(source, 2, 10);
assert.strictEqual(secondPage.page, 2);
assert.strictEqual(secondPage.pages, 4);
assert.deepStrictEqual(
  secondPage.rows.map(item => [item.number, item.value]),
  Array.from({length: 10}, (_, index) => [index + 11, `row-${index + 11}`]),
  'the second page should continue numbering from the first page',
);

const largerPage = paginationTools.paginate(source, 2, 20);
assert.deepStrictEqual(
  largerPage.rows.map(item => item.number),
  Array.from({length: 15}, (_, index) => index + 21),
  'continuous numbering should follow the selected page size',
);

const fractionalPage = paginationTools.paginate(source, 1.5, 10);
assert.strictEqual(fractionalPage.page, 1, 'fractional pages should be normalized to an integer');
assert.deepStrictEqual(fractionalPage.rows.map(item => item.number), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);

const values = new Map();
const storage = {
  getItem: key => values.get(key) ?? null,
  setItem: (key, value) => values.set(key, value),
};
paginationTools.savePageSize(storage, 50);
assert.strictEqual(paginationTools.loadPageSize(storage), 50, 'saved supported page size should survive a reload');
storage.setItem('recruitment-page-size', '30');
assert.strictEqual(paginationTools.loadPageSize(storage), 10, 'unsupported page sizes should fall back to 10');

assert.strictEqual(typeof paginationTools.paginationFooter, 'function', 'empty lists should still render pagination controls');
const emptyFooter = paginationTools.paginationFooter(0, {page: 1, pages: 1, pageSize: 10});
assert.match(emptyFooter, /id="page-size"/, 'empty lists should retain the page-size selector');
assert.match(emptyFooter, /id="prev" disabled/, 'empty lists should disable previous-page navigation');
assert.match(emptyFooter, /id="next" disabled/, 'empty lists should disable next-page navigation');

console.log('pagination UI checks passed');
