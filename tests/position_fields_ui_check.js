const assert = require('assert');
const fs = require('fs');
const path = require('path');
const modulePath = path.join(__dirname, '..', 'web', 'features', 'position_fields.js');
assert.ok(fs.existsSync(modulePath), '岗位下拉框应由独立的显隐组件管理');
const positionFields = require(modulePath);

const listeners = {};
const label = {hidden: null, classList: {toggle: (_, hidden) => { label.hidden = hidden; }}};
const position = {value: '其它', addEventListener: (name, callback) => { listeners[name] = callback; }};
const detail = {value: '管道工程师', required: false, closest: () => label};
const form = {elements: {position, position_detail: detail}};

positionFields.bind(form);
assert.strictEqual(label.hidden, false);
assert.strictEqual(detail.required, true);

position.value = '机械工程师';
listeners.change();
assert.strictEqual(label.hidden, true);
assert.strictEqual(detail.required, false);
assert.strictEqual(detail.value, '');

positionFields.setRecognized(form, '管道工程师');
assert.strictEqual(position.value, '管道工程师');
assert.strictEqual(detail.value, '');
assert.strictEqual(label.hidden, true);

positionFields.setRecognized(form, '设备工程师');
assert.strictEqual(position.value, '设备工程师');
assert.strictEqual(detail.value, '');
assert.strictEqual(label.hidden, true);

positionFields.setRecognized(form, '电气工程师');
assert.strictEqual(position.value, '电气工程师');
assert.strictEqual(detail.value, '');
