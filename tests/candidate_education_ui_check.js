const assert = require('assert');
const fs = require('fs');
const path = require('path');

const modulePath = path.join(__dirname, '..', 'web', 'features', 'candidate_education.js');
assert.ok(fs.existsSync(modulePath), '教育经历应由独立组件提供两行布局');
const education = require(modulePath);

const html = education.renderRow({
  education: '本科',
  school_name: '测试大学',
  major: '工程管理',
  enrollment: '2022-09',
  graduation: '2026-07',
}, 0, 2, new Set(['education', 'school_name']));

const primary = html.match(/<div class="education-primary-fields">([\s\S]*?)<\/div>/)?.[1] || '';
const dates = html.match(/<div class="education-period-fields">([\s\S]*?)<\/div>/)?.[1] || '';

assert.deepStrictEqual(
  [...primary.matchAll(/data-education="([^"]+)"/g)].map(match => match[1]),
  ['education', 'school_name', 'major'],
  '第一行必须依次显示学历、院校、专业',
);
assert.deepStrictEqual(
  [...dates.matchAll(/data-education="([^"]+)"/g)].map(match => match[1]),
  ['enrollment', 'graduation'],
  '第二行必须依次显示入学时间、毕业时间',
);
assert.ok(html.indexOf('education-period-fields') < html.indexOf('data-remove-education'), '删除按钮应位于第二行右侧');
assert.match(html, /教育经历 1/);
assert.match(html, /value="测试大学"/);
