# Corporate Blue Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将南化建招聘管理系统全站升级为正式稳重的企业蓝视觉，同时保持现有业务功能、字段、数据和操作流程不变。

**Architecture:** 新建 `web/corporate-theme.css` 作为独立视觉覆盖层，在现有全部样式文件之后加载。主题只通过现有语义选择器覆盖管理后台、公开页面、弹窗和二维码，不修改事件、接口或数据流。

**Tech Stack:** 原生 HTML、CSS、JavaScript，Python 标准库 HTTP 服务，现有 `unittest` 与 Node.js UI 检查脚本。

**Spec:** `docs/superpowers/specs/2026-09-11-corporate-blue-visual-refresh-design.md`

## Global Constraints

- 不改变现有业务功能、字段、数据库结构和数据。
- 不改变菜单顺序、表格字段、分页、导入导出、Dify 识别和人才入库流程。
- 不引入第三方前端框架或新的公司标志图片。
- 工具栏仍位于搜索框下方并保持一排排列；屏幕不足时允许换行。
- 弹窗关闭按钮继续悬浮在右上角。
- 主题代码独立维护，移动端断点保持为 `1150px` 和 `760px`。
- 当前工作目录不是 Git 仓库，任务完成后记录测试结果，不执行 Git 提交。

---

### Task 1: 独立主题入口与设计令牌

**Files:**
- Create: `web/corporate-theme.css`
- Modify: `web/index.html:3`
- Modify: `tests/test_server.py:test_01_private_routes_and_static`

**Interfaces:**
- Consumes: 现有 `/style.css` 基础样式和 `web/index.html` 静态资源加载顺序。
- Produces: `/corporate-theme.css` 可访问的独立主题覆盖层，供后续所有视觉任务使用。

- [ ] **Step 1: 写入失败的主题资源集成测试**

在 `test_01_private_routes_and_static` 的静态路由列表中加入 `/corporate-theme.css`，并读取首页 HTML，断言主题链接位于最后一个现有样式文件之后：

```python
for route in ['/', '/apply', '/resume-batch', '/app.js', '/style.css', '/corporate-theme.css']:
    with self.public.open(self.url + route) as response:
        self.assertEqual(response.status, 200)
with self.public.open(self.url + '/') as response:
    html = response.read().decode('utf-8')
self.assertLess(html.index('/candidate.css'), html.index('/corporate-theme.css'))
```

- [ ] **Step 2: 运行测试并确认因主题文件或链接缺失而失败**

Run: `python -m unittest tests.test_server.RecruitmentTests.test_01_private_routes_and_static -v`

Expected: FAIL，原因是 `/corporate-theme.css` 返回 404 或首页没有该链接。

- [ ] **Step 3: 创建主题令牌并加载主题文件**

在 `web/index.html` 中把主题文件放在现有 `table-tools.css` 和 `candidate.css` 之后：

```html
<link rel="stylesheet" href="/table-tools.css">
<link rel="stylesheet" href="/candidate.css">
<link rel="stylesheet" href="/corporate-theme.css">
```

创建 `web/corporate-theme.css`，先建立全站令牌和基础背景：

```css
:root {
  --brand-950:#071d3d;
  --brand-900:#0b2b59;
  --brand-800:#123f7a;
  --brand-700:#1557b0;
  --brand-600:#1769d2;
  --brand-100:#eaf3ff;
  --brand-50:#f4f8ff;
  --surface:#fff;
  --canvas:#f2f6fb;
  --text-strong:#10233f;
  --text:#30435f;
  --text-muted:#71809a;
  --border:#dfe7f1;
  --shadow-sm:0 2px 10px rgba(9,42,88,.06);
  --shadow-md:0 14px 40px rgba(9,42,88,.12);
  --radius-sm:8px;
  --radius-md:12px;
  --radius-lg:16px;
  --blue:var(--brand-600);
  --line:var(--border);
  --muted:var(--text-muted);
}
body { background:var(--canvas); color:var(--text-strong); }
```

- [ ] **Step 4: 运行主题入口测试**

Run: `python -m unittest tests.test_server.RecruitmentTests.test_01_private_routes_and_static -v`

Expected: PASS。

---

### Task 2: 管理后台外壳与核心组件

**Files:**
- Modify: `web/corporate-theme.css`
- Test: `tests/test_dialog_layout_ui.py`
- Test: `tests/table_layout_ui_check.js`

**Interfaces:**
- Consumes: Task 1 的主题令牌；现有 `.layout`、`aside`、`nav`、`.workspace`、`.panel`、`.toolbar`、`table`、`.pagination`、`dialog` 类。
- Produces: 一致的企业蓝后台外壳、卡片、表格、按钮、表单和弹窗视觉。

- [ ] **Step 1: 运行现有布局基线测试并记录通过状态**

Run: `python -m unittest tests.test_dialog_layout_ui -v` and `node tests/table_layout_ui_check.js`

Expected: 所有现有布局测试 PASS；任何基线失败必须先停止并报告。

- [ ] **Step 2: 实现侧边栏、顶部栏和页面标题视觉**

在主题文件中加入以下覆盖，保持现有尺寸和固定定位逻辑：

```css
aside {
  background:linear-gradient(180deg,var(--brand-950),var(--brand-900));
  border-right:0;
  box-shadow:8px 0 30px rgba(7,29,61,.08);
}
aside .identity, aside .identity strong, .nav-caption, .aside-bottom { color:#fff; }
aside .identity strong, aside .nav-caption, aside .aside-bottom .hint { color:#aebfda; }
aside nav button { color:#c8d5e9; border:1px solid transparent; }
aside nav button:hover { color:#fff; background:rgba(255,255,255,.08); }
aside nav button.active {
  color:#fff;
  background:linear-gradient(135deg,var(--brand-600),#247be5);
  box-shadow:0 10px 24px rgba(0,80,190,.28);
}
header { border-bottom:1px solid var(--border); box-shadow:var(--shadow-sm); }
.page-title { margin-bottom:24px; }
.page-title h1 { color:var(--text-strong); font-weight:750; }
```

- [ ] **Step 3: 实现按钮、输入、卡片和状态视觉**

```css
.panel,.stat { border-color:var(--border); border-radius:var(--radius-md); box-shadow:var(--shadow-sm); }
.primary { background:linear-gradient(135deg,var(--brand-700),var(--brand-600)); box-shadow:0 7px 16px rgba(21,87,176,.18); }
.secondary { border-color:#cfdaea; color:#415673; box-shadow:0 1px 2px rgba(9,42,88,.03); }
input,select,textarea { border-color:#ced9e8; border-radius:var(--radius-sm); }
input:focus,select:focus,textarea:focus { border-color:var(--brand-600); box-shadow:0 0 0 3px rgba(23,105,210,.12); }
.badge { border-radius:999px; font-weight:650; }
```

- [ ] **Step 4: 实现工具栏、表格、分页和弹窗视觉**

```css
.toolbar { background:#fff; padding:18px 20px; }
th { background:#f4f7fb; color:#52647e; font-weight:650; }
td { color:#30435f; }
tbody tr:hover { background:#f6faff; }
.row-actions button { border-radius:6px; }
.row-actions button:hover { background:var(--brand-100); }
.pagination { background:#fbfcfe; }
dialog { border-radius:var(--radius-lg); box-shadow:0 30px 90px rgba(7,29,61,.3); }
dialog::backdrop { background:rgba(7,29,61,.58); backdrop-filter:blur(4px); }
.dialog-head { background:linear-gradient(180deg,#fff,#f8fbff); }
```

- [ ] **Step 5: 重跑后台结构测试**

Run: `python -m unittest tests.test_dialog_layout_ui tests.test_selection_export_ui -v` and `node tests/table_layout_ui_check.js`

Expected: PASS，证明关闭按钮、表格操作列和选择导出结构未被破坏。

---

### Task 3: 总览、登录页和公开投递页面

**Files:**
- Modify: `web/corporate-theme.css`
- Test: `tests/test_qr_cards_ui.py`
- Test: `tests/test_candidate_experiences_ui.py`

**Interfaces:**
- Consumes: Task 1 主题令牌和 Task 2 核心组件；现有 `.overview-banner`、`.stats`、`.auth`、`.apply`、`.form-grid`、`.resume-file-picker-area`。
- Produces: 企业蓝总览、登录、简历投递和批量导入页面，保持既有表单与上传行为。

- [ ] **Step 1: 运行公开页面和功能组件基线测试**

Run: `python -m unittest tests.test_qr_cards_ui tests.test_candidate_experiences_ui -v`

Expected: PASS。

- [ ] **Step 2: 美化总览和数据卡片**

```css
.overview-banner {
  background:linear-gradient(120deg,var(--brand-900),var(--brand-700) 68%,#2177dc);
  border-radius:var(--radius-lg);
  box-shadow:0 18px 45px rgba(9,52,111,.2);
}
.recruitment-overview { margin-bottom:28px; }
.recruitment-overview>.panel-head { border:0; padding:0 2px 14px; }
.stat { transition:transform .18s ease,box-shadow .18s ease; }
.stat:hover { transform:translateY(-2px); box-shadow:0 12px 30px rgba(9,42,88,.11); }
```

- [ ] **Step 3: 美化登录页和公开页面**

```css
.auth-brand { background:linear-gradient(145deg,var(--brand-950),var(--brand-700)); }
.auth-card { background:#fff; border-radius:var(--radius-lg); }
.apply { max-width:940px; }
.apply>.identity { padding:8px 4px; }
.apply-title { padding-top:34px; }
.apply .panel { box-shadow:0 18px 48px rgba(9,42,88,.1); }
.resume-file-picker-area { border:1px dashed #b9c9df; border-radius:var(--radius-md); background:var(--brand-50); padding:18px; }
```

- [ ] **Step 4: 统一教育、工作、项目经历子表**

覆盖三个经历组件的 `fieldset`，不修改其独立功能脚本：

```css
.education-list fieldset,
.candidate-experience-list fieldset,
.candidate-project-experience-list fieldset {
  border-color:#d6e1ef;
  background:#fbfdff;
  box-shadow:inset 3px 0 var(--brand-100);
}
```

- [ ] **Step 5: 重跑公开与经历组件测试**

Run: `python -m unittest tests.test_qr_cards_ui tests.test_candidate_experiences_ui -v`

Expected: PASS。

---

### Task 4: 二维码、响应式和可访问性收尾

**Files:**
- Modify: `web/corporate-theme.css`
- Test: `tests/test_qr_cards_ui.py`
- Test: `tests/test_dialog_layout_ui.py`
- Test: `tests/table_layout_ui_check.js`

**Interfaces:**
- Consumes: 前三项完成的全站主题。
- Produces: 保持可扫描的二维码、桌面与手机响应式覆盖、清晰的键盘焦点和状态反馈。

- [ ] **Step 1: 完善二维码卡片但不改变二维码主体**

```css
.qr-card { border-color:#d8e3f0; border-radius:var(--radius-lg); box-shadow:var(--shadow-md); }
.qr-image-frame { background:#fff; }
.qr-card h3 { color:var(--text-strong); }
.qr-card .secondary { color:var(--brand-700); }
```

不得对二维码 SVG 使用滤镜、缩放裁切或覆盖图层；保持当前二维码安全区和下载逻辑。

- [ ] **Step 2: 补充键盘焦点、减少动画和移动端覆盖**

```css
:focus-visible { outline:3px solid #76aaff; outline-offset:3px; }
@media (prefers-reduced-motion:reduce) { *,*::before,*::after { scroll-behavior:auto!important; transition:none!important; } }
@media (max-width:1150px) { .workspace main { padding:26px 22px; } }
@media (max-width:760px) {
  aside { background:var(--brand-950); }
  nav button.active { box-shadow:none; }
  .toolbar-actions { align-items:stretch; }
  .apply .panel { box-shadow:var(--shadow-sm); }
  dialog { max-height:calc(100vh - 20px); }
}
```

- [ ] **Step 3: 运行结构回归测试**

Run: `python -m unittest tests.test_qr_cards_ui tests.test_dialog_layout_ui -v` and `node tests/table_layout_ui_check.js`

Expected: PASS。

- [ ] **Step 4: 进行浏览器视觉验收**

在桌面宽度检查：招聘总览、简历收集、人才库、登录页、`/resume-submit?type=campus`、`/resume-batch`、二维码弹窗、查看编辑弹窗。确认侧边栏、按钮层级、表格横向滚动、工具栏一排布局和悬浮关闭按钮。

在不提交表单、不删除数据的前提下，把视口临时切换为约 `390×844`，检查公开投递页、批量导入页、管理导航和弹窗无横向溢出；完成后恢复视口。

- [ ] **Step 5: 检查浏览器控制台**

读取当前页面控制台的 error 级别日志。Expected: 没有由主题加载或 DOM 类名调整引入的新错误。

---

### Task 5: 完整回归、服务重载与交付

**Files:**
- Verify: all files above

**Interfaces:**
- Consumes: 完整企业蓝主题。
- Produces: 已验证、已重载并可通过原地址访问的系统。

- [ ] **Step 1: 运行完整测试套件**

Run: `python -m unittest discover -s tests -v`

Expected: 全部 88 项（包含新增的主题入口断言）PASS，0 failures，0 errors。

- [ ] **Step 2: 检查服务端语法**

Run: `python -m py_compile server.py dify_client.py features/resume_documents/filename_position.py`

Expected: exit code 0，无输出。

- [ ] **Step 3: 重载本地服务**

使用 `netstat -ano` 精确确认 `8116` 端口的 Python 进程，停止该 PID，然后通过隐藏窗口在项目目录启动：

```powershell
Start-Process -FilePath 'D:\Miniconda\python.exe' -ArgumentList 'server.py','--host','0.0.0.0','--port','8116' -WorkingDirectory 'D:\工作目录\南化建招聘系统' -WindowStyle Hidden
```

- [ ] **Step 4: 验证部署地址和主题资源**

Run:

```powershell
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8116/'
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8116/corporate-theme.css'
```

Expected: 两个请求均为 HTTP 200；浏览器地址继续为 `http://172.16.30.81:8116/`。

- [ ] **Step 5: 交付结果**

报告修改文件、完整测试数量、页面检查范围和访问网址。明确说明主题样式位于独立文件 `web/corporate-theme.css`，后续可独立调整或移除。
