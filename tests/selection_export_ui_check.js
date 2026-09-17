const assert = require('assert');
const selectionExport = require('../web/features/selection_export.js');

const button = {textContent: '', disabled: false};
selectionExport.updateButton(button, new Set());
assert.strictEqual(button.textContent, '导出所选（0）');
assert.strictEqual(button.disabled, true);

selectionExport.updateButton(button, new Set([8, 3]));
assert.strictEqual(button.textContent, '导出所选（2）');
assert.strictEqual(button.disabled, false);

const request = selectionExport.request('candidates', new Set([8, 3]), [{id: 9}, {id: 8}, {id: 3}]);
assert.strictEqual(request.path, 'candidates/export.xlsx');
assert.deepStrictEqual(JSON.parse(request.options.body), {ids: [8, 3]});
assert.strictEqual(request.options.method, 'POST');

console.log('selection export UI checks passed');
