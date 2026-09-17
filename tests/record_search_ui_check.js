const assert = require('assert');

let search = {};
try { search = require('../web/features/record_search.js'); } catch {}

assert.strictEqual(typeof search.filterRecords,'function','shared record search must be available');

const rows = [
  {id:1,archive_no:'0120260914001',name:'张三',position:'工程师',password:'不可搜索999'},
  {id:2,archive_no:'0220260914001',name:'李四',position:'施工员',password:''},
  {id:3,archive_no:'0120260915001',name:'WANG WU',position:'安全员',password:''}
];

assert.deepStrictEqual(search.filterRecords(rows,'0914001',new Set(['password'])).map(row=>row.id),[1,2]);
assert.deepStrictEqual(search.filterRecords(rows,'0220260914001',new Set(['password'])).map(row=>row.id),[2]);
assert.deepStrictEqual(search.filterRecords(rows,'wang',new Set(['password'])).map(row=>row.id),[3]);
assert.deepStrictEqual(search.filterRecords(rows,'不可搜索999',new Set(['password'])).map(row=>row.id),[]);
assert.deepStrictEqual(search.filterRecords(rows,'',new Set(['password'])).map(row=>row.id),[1,2,3]);
