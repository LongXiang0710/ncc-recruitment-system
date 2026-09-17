const assert = require('assert');
const fs = require('fs');
const path = require('path');
const cards = require('../web/features/qr_cards.js');

const html = cards.renderQrCard({
  label: '校园<script>招聘简历投递',
  description: '扫码上传简历',
  image: 'data:image/svg+xml;base64,abc',
  imageAlt: '校园招聘二维码',
  primary: '校园招聘入口',
  secondary: '招聘类型自动设为校园招聘',
  url: 'http://example.test/resume?type=campus&next=<bad>',
  downloadName: '校园招聘二维码.svg',
  labelAbove: true,
});

assert.match(html, /class="qr-card\b/);
assert.ok(html.includes('class="qr-image-shell"'));
assert.ok(html.includes('class="qr-card-label"'));
assert.ok(html.includes('qr-label-above'));
assert.ok(html.indexOf('class="qr-card-label"') < html.indexOf('class="qr-image-shell"'));
assert.ok(html.includes('class="qr-card-company"'));
assert.ok(html.includes('class="secondary qr-download"'));
assert.ok(html.includes('南京南化建设有限公司'));
assert.ok(html.includes('校园&lt;script&gt;招聘简历投递'));
assert.ok(!html.includes('扫码上传简历'));
assert.ok(!html.includes('校园招聘入口'));
assert.ok(!html.includes('招聘类型自动设为校园招聘'));
assert.ok(!html.includes('example.test'));
assert.ok(!html.includes('qr-card-header'));
assert.ok(!html.includes('qr-open-link'));
assert.ok(!html.includes('qr-url'));
assert.ok(!html.includes('<script>'));
assert.ok(!html.includes('qr-center-logo'));

const css = fs.readFileSync(path.join(__dirname, '../web/table-tools.css'), 'utf8');
assert.match(css, /\.qr-dialog \.qr-card\{[^}]*padding:12px/);
assert.match(css, /\.qr-dialog \.qr-card \.qr-image-shell img\{[^}]*width:280px;height:280px/);
assert.match(css, /\.qr-dialog \.qr-grid\{[^}]*padding:20px/);
assert.match(css, /\.qr-label-above \.qr-card-label\{[^}]*font-size:20px/);

console.log('QR card UI checks passed');
