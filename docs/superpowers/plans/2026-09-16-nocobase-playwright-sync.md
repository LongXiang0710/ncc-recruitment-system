# NocoBase Playwright 同步实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为简历收集和人才库增加“本地保存后立即入队、独立 Playwright 后台逐条同步至 NocoBase、失败自动重试”的单向同步能力。

**Architecture:** 招聘系统仍以本地 SQLite 为唯一数据源，每次成功新增、修改或删除后在同一事务内写入持久化同步队列。独立 worker 使用后台 Microsoft Edge 登录 NocoBase，按档案编号执行幂等新增、更新或删除；配置、映射、队列、浏览器适配器和两个业务适配器相互隔离。

**Tech Stack:** Python 3.10+、SQLite、Playwright 1.62.0、Microsoft Edge、Windows DPAPI、现有原生 HTML/CSS/JavaScript 管理端、`unittest`

**Spec:** `docs/superpowers/specs/2026-09-16-nocobase-playwright-sync-design.md`

## Global Constraints

- 第一阶段只同步 `resume_documents` 和 `candidates`，方向仅为招聘系统到 NocoBase。
- NocoBase 默认地址是 `http://cloud.njncc.com:443/`，必须可配置，不能散落在业务代码中。
- 后台浏览器固定使用 `playwright.chromium.launch(channel="msedge", headless=True)`。
- 档案编号是唯一远端匹配键；零条时新增，一条时更新或删除，多条时暂停并报警。
- 所有本地业务写入和同步任务入队必须处于同一 SQLite 事务。
- 密码必须使用当前 Windows 用户的 DPAPI 加密，禁止写入源码、SQLite 业务表、日志或 Playwright 脚本。
- 日志不得包含姓名、电话、邮箱、身份证号、附件名称、附件内容、Cookie、密码或完整页面内容。
- 自动化测试不得向真实 NocoBase 写数据；Playwright 测试只访问本地夹具站点。
- 首次历史同步必须经过“连接测试 → 两条专用测试记录 → 用户确认 → 批量启动”。
- 当前工作目录没有 `.git`，执行时不得自行初始化仓库；每个任务以测试通过和人工审阅作为检查点。若用户之后建立 Git 仓库，再按任务边界补交提交。

---

## 文件结构

新增 `features/nocobase_sync/`：

- `__init__.py`：导出服务器调用的稳定接口。
- `queue.py`：同步队列表、审计表、任务合并、租约、重试和统计。
- `config.py`：网址规范化、DPAPI 凭据保存和读取。
- `configure.py`：命令行配置及只读连接测试入口。
- `mapping.py`：从本地数据库构建简历和人才同步模型。
- `browser.py`：Playwright 生命周期、登录、导航、筛选和稳定控件操作。
- `resume_documents.py`：NocoBase 简历收集 upsert/delete。
- `candidates.py`：NocoBase 人才及经历子表 upsert/delete。
- `worker.py`：独立进程、单实例租约、执行、重试和安全日志。
- `api.py`：同步状态、历史同步和重试所需的服务器服务函数。

新增测试：

- `tests/test_nocobase_queue.py`
- `tests/test_nocobase_config.py`
- `tests/test_nocobase_mapping.py`
- `tests/nocobase_fixture.py`
- `tests/test_nocobase_browser.py`
- `tests/test_nocobase_adapters.py`
- `tests/test_nocobase_worker.py`
- `tests/test_nocobase_api.py`
- `tests/nocobase_sync_ui_check.js`

修改现有文件：

- `server.py`：初始化队列、业务事务入队、同步管理 API。
- `web/app.js`：侧栏入口和同步状态页面路由。
- `web/style.css`：同步状态页面样式。
- `start.bat`、`start.ps1`：同时管理 HTTP 服务和同步 worker 生命周期。
- `README.md`、`功能模块说明.md`、`scripts/build_operation_manual.py`：配置、使用、排错和操作手册。
- `requirements.txt`：保留已锁定的 `playwright==1.62.0`，不新增不必要依赖。

---

### Task 1: 持久化同步队列、任务合并和租约

**Files:**
- Create: `features/nocobase_sync/__init__.py`
- Create: `features/nocobase_sync/queue.py`
- Create: `tests/test_nocobase_queue.py`

**Interfaces:**
- Consumes: 现有 `sqlite3.Connection`，连接必须设置 `row_factory=sqlite3.Row`。
- Produces: `ensure_tables(conn)`, `enqueue_upsert(conn, entity, local_id, archive_no, revision)`, `enqueue_delete(conn, entity, local_id, archive_no, revision)`, `claim(db_path, worker_id, now)`, `complete(db_path, job_id, worker_id, now)`, `fail(db_path, job_id, worker_id, failure, now)`, `retry_jobs(conn, ids=None)`, `stats(conn)`。

- [ ] **Step 1: 写队列表和任务合并失败测试**

```python
class QueueTests(unittest.TestCase):
    def test_latest_upsert_replaces_waiting_revision(self):
        conn = memory_db()
        queue.ensure_tables(conn)
        queue.enqueue_upsert(conn, 'candidates', 7, '0120260916001', '2026-09-16T09:00:00')
        queue.enqueue_upsert(conn, 'candidates', 7, '0120260916001', '2026-09-16T09:01:00')
        rows = conn.execute("SELECT operation,revision,status FROM nocobase_sync_jobs").fetchall()
        self.assertEqual([tuple(row) for row in rows], [('upsert', '2026-09-16T09:01:00', '等待')])

    def test_delete_cancels_waiting_upsert(self):
        conn = memory_db()
        queue.ensure_tables(conn)
        queue.enqueue_upsert(conn, 'resume_documents', 9, '0120260916009', 'v1')
        queue.enqueue_delete(conn, 'resume_documents', 9, '0120260916009', 'v2')
        rows = conn.execute("SELECT operation,status FROM nocobase_sync_jobs ORDER BY id").fetchall()
        self.assertEqual([tuple(row) for row in rows], [('upsert', '已取消'), ('delete', '等待')])
```

- [ ] **Step 2: 运行测试并确认因模块或表不存在而失败**

Run: `python -m unittest tests.test_nocobase_queue -v`  
Expected: FAIL，提示 `features.nocobase_sync.queue` 或目标表/函数不存在。

- [ ] **Step 3: 实现建表、合并和删除优先规则**

```python
ALLOWED_ENTITIES = {'resume_documents', 'candidates'}
RETRY_DELAYS = (60, 300, 900, 1800, 3600)

def ensure_tables(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS nocobase_sync_jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity TEXT NOT NULL,
        local_id INTEGER,
        archive_no TEXT NOT NULL,
        operation TEXT NOT NULL,
        revision TEXT NOT NULL,
        status TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TEXT NOT NULL,
        lease_owner TEXT NOT NULL DEFAULT '',
        lease_until TEXT NOT NULL DEFAULT '',
        error_stage TEXT NOT NULL DEFAULT '',
        error_type TEXT NOT NULL DEFAULT '',
        diagnostic_id TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT NOT NULL DEFAULT ''
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS nocobase_sync_audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity TEXT NOT NULL,
        archive_no TEXT NOT NULL,
        operation TEXT NOT NULL,
        outcome TEXT NOT NULL,
        diagnostic_id TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )''')
```

`enqueue_upsert` 必须合并同一实体和 `local_id` 的等待任务；`enqueue_delete` 必须取消等待 upsert 后新增 delete。函数只写当前连接，不自行 commit。

- [ ] **Step 4: 增加领取、租约恢复和重试测试**

```python
def test_expired_processing_job_can_be_claimed_again(self):
    conn = file_db(self.db_path)
    queue.ensure_tables(conn)
    job_id = queue.enqueue_upsert(conn, 'candidates', 3, 'A-3', 'v1')
    conn.commit(); conn.close()
    first = queue.claim(self.db_path, 'worker-a', '2026-09-16T10:00:00')
    self.assertEqual(first['id'], job_id)
    second = queue.claim(self.db_path, 'worker-b', '2026-09-16T10:06:00')
    self.assertEqual(second['id'], job_id)
```

- [ ] **Step 5: 实现原子 claim、complete、fail、retry_jobs 和 stats**

`claim` 使用独立 SQLite 连接和 `BEGIN IMMEDIATE`，租约 5 分钟；`fail` 根据 `RETRY_DELAYS` 设置下一次执行时间，第五次以后每小时重试。结构性错误由调用者传入 `pausable=True` 并置为“暂停”。所有审计事件只保存实体、档案编号、操作、结果和诊断编号。

- [ ] **Step 6: 运行队列测试**

Run: `python -m unittest tests.test_nocobase_queue -v`  
Expected: PASS，覆盖任务合并、删除优先、租约恢复、成功、重试、暂停和统计。

- [ ] **Step 7: 检查点**

Run: `python -m unittest tests.test_nocobase_queue -v`，保存通过输出供审阅；当前无 Git 仓库，不执行提交。

---

### Task 2: 可修改网址和 DPAPI 凭据配置

**Files:**
- Create: `features/nocobase_sync/config.py`
- Create: `features/nocobase_sync/configure.py`
- Create: `配置NocoBase.bat`
- Create: `tests/test_nocobase_config.py`

**Interfaces:**
- Consumes: `RECRUIT_DATA_DIR` 或项目 `data` 目录。
- Produces: `NocoBaseConfig(url, username, password)`, `normalize_url(value)`, `save(data_dir, url, username, password)`, `load(data_dir)`, `configured(data_dir)`。

- [ ] **Step 1: 写网址规范化和凭据不落明文测试**

```python
def test_save_uses_protector_and_never_writes_plain_password(self):
    with TemporaryDirectory() as directory:
        config.save(Path(directory), 'http://cloud.njncc.com:443/', 'sync-user', 'secret-value',
                    protect=lambda value: b'ciphertext')
        raw = (Path(directory) / 'nocobase-config.json').read_text(encoding='utf-8')
        self.assertNotIn('secret-value', raw)
        loaded = config.load(Path(directory), unprotect=lambda value: b'secret-value')
        self.assertEqual((loaded.url, loaded.username, loaded.password),
                         ('http://cloud.njncc.com:443', 'sync-user', 'secret-value'))
```

- [ ] **Step 2: 运行配置测试并确认失败**

Run: `python -m unittest tests.test_nocobase_config -v`  
Expected: FAIL，提示配置模块不存在。

- [ ] **Step 3: 实现配置模型和 Windows DPAPI**

```python
@dataclass(frozen=True)
class NocoBaseConfig:
    url: str
    username: str
    password: str

def normalize_url(value):
    parsed = urlparse(str(value or '').strip().rstrip('/'))
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('NocoBase 地址必须是有效的 HTTP 或 HTTPS 地址')
    return parsed.geturl()
```

使用 `ctypes.windll.crypt32.CryptProtectData` 和 `CryptUnprotectData`，密文以 Base64 保存到 `data/nocobase-config.json`。解密失败时返回明确的“请在当前 Windows 账户重新配置”，不能回退为明文。

- [ ] **Step 4: 实现交互式配置程序和批处理入口**

`configure.py` 使用 `input()` 读取网址和用户名、`getpass.getpass()` 读取密码，先保存再通过 `browser.test_login()` 执行只读连接测试。`配置NocoBase.bat` 只包含：

```bat
@echo off
cd /d "%~dp0"
python -m features.nocobase_sync.configure
pause
```

- [ ] **Step 5: 运行配置测试**

Run: `python -m unittest tests.test_nocobase_config -v`  
Expected: PASS，且测试文件中不存在真实网址凭据以外的秘密数据。

- [ ] **Step 6: 检查点**

人工检查配置 JSON 只有 URL、用户名和密文；当前无 Git 仓库，不执行提交。

---

### Task 3: 本地记录映射和附件 FilePayload

**Files:**
- Create: `features/nocobase_sync/mapping.py`
- Create: `tests/test_nocobase_mapping.py`

**Interfaces:**
- Consumes: SQLite `resume_documents`, `candidates`, `attachments`, `candidate_educations`, `candidate_work_experiences`, `candidate_project_experiences`。
- Produces: `load_record(conn, entity, local_id) -> SyncRecord`, `SyncRecord(entity, local_id, archive_no, fields, attachment, educations, work_experiences, project_experiences)`，其中 `attachment` 是 Playwright `FilePayload` 或 `None`。

- [ ] **Step 1: 写简历、人才和条件字段映射测试**

```python
def test_candidate_mapping_keeps_social_projects_and_omits_campus_only_fields(self):
    record = mapping.load_record(self.conn, 'candidates', self.social_candidate_id)
    self.assertEqual(record.archive_no, '0120260916001')
    self.assertEqual(record.fields['招聘类型'], '社会招聘')
    self.assertNotIn('毕业时间', record.fields)
    self.assertEqual(record.project_experiences[0]['项目名称'], '测试项目')
    self.assertEqual(record.attachment['mimeType'], 'application/pdf')
    self.assertIsInstance(record.attachment['buffer'], bytes)
```

- [ ] **Step 2: 运行映射测试并确认失败**

Run: `python -m unittest tests.test_nocobase_mapping -v`  
Expected: FAIL，提示 `mapping.load_record` 不存在。

- [ ] **Step 3: 实现白名单映射**

```python
RESUME_FIELDS = {
    'archive_no': '档案编号', 'status': '处理状态', 'recruitment_type': '招聘类型',
    'channel': '招聘渠道', 'channel_detail': '其他渠道详细', 'position': '应聘岗位',
    'position_detail': '其他岗位名称', 'name': '简历名称', 'created_by': '创建人',
    'created_at': '上传时间',
}

CANDIDATE_FIELDS = {
    'name': '姓名', 'gender': '性别', 'birthdate': '出生日期', 'age': '年龄',
    'political_status': '政治面貌', 'archive_no': '档案编号', 'education': '学历',
    'school_name': '毕业院校', 'major': '专业', 'phone': '联系方式', 'email': '邮箱',
    'hometown': '籍贯/居住地', 'recruitment_type': '招聘类型', 'channel': '招聘渠道',
    'channel_detail': '其他渠道详细', 'position': '投递岗位',
    'position_detail': '其他岗位名称',
}
```

从附件 BLOB 构建 `{'name': safe_name, 'mimeType': mime, 'buffer': bytes(content)}`，不写临时明文文件。校园招聘加入毕业时间/应届字段并清空项目经历；社会招聘省略校园专属字段并读取项目经历。教育、工作、项目经历保持数据库 `position_order,id` 顺序。

- [ ] **Step 4: 增加缺失档案号、记录已删除和附件不存在测试**

期望分别抛出 `SyncDataError(code='missing_archive_no')`、返回 `None` 供 worker 转换 delete/skip、抛出 `SyncDataError(code='missing_attachment')`。

- [ ] **Step 5: 运行映射测试**

Run: `python -m unittest tests.test_nocobase_mapping -v`  
Expected: PASS。

- [ ] **Step 6: 检查点**

Run: `python -m unittest tests.test_nocobase_mapping -v` 并审阅映射白名单；当前无 Git 仓库，不执行提交。

---

### Task 4: 本地 NocoBase 夹具和浏览器基础适配器

**Files:**
- Create: `tests/nocobase_fixture.py`
- Create: `features/nocobase_sync/browser.py`
- Create: `tests/test_nocobase_browser.py`

**Interfaces:**
- Consumes: `NocoBaseConfig`、Playwright sync API。
- Produces: `NocoBaseBrowser(config, headless=True)`, `start()`, `close()`, `ensure_login()`, `open_collection(label)`, `filter_archive(archive_no) -> int`, `open_add()`, `open_only_result(action)`, `submit_dialog()`, `cancel_dialog()`, `test_login(config) -> None`。

- [ ] **Step 1: 建立只在本机运行的夹具站点**

夹具必须提供与录制相同的可访问名称：用户名/邮箱、密码、登录、业务中心、人力资源管理、校园招聘、简历收集、招聘人才库、筛选、添加条件、选择字段、输入值、提交、编辑、删除、确定。数据只保存在夹具进程内存。

- [ ] **Step 2: 写登录和档案筛选失败测试**

```python
def test_login_and_exact_archive_filter(self):
    with fixture_server() as fixture:
        browser = NocoBaseBrowser(NocoBaseConfig(fixture.url, 'user', 'pass'), headless=True)
        browser.start()
        browser.ensure_login()
        browser.open_collection('简历收集')
        self.assertEqual(browser.filter_archive('A-001'), 1)
        browser.close()
```

- [ ] **Step 3: 运行测试并确认失败**

Run: `python -m unittest tests.test_nocobase_browser -v`  
Expected: FAIL，提示浏览器适配器不存在。

- [ ] **Step 4: 实现 Edge 生命周期、登录和导航**

```python
self._playwright = sync_playwright().start()
self.browser = self._playwright.chromium.launch(channel='msedge', headless=self.headless)
self.context = self.browser.new_context()
self.page = self.context.new_page()
```

登录使用 `get_by_role('textbox', name='用户名/邮箱')`、密码文本框和登录按钮。每个动作后等待明确元素出现；禁止 `time.sleep()`。连接测试登录成功后立即关闭浏览器，不进入业务表、不提交表单。

- [ ] **Step 5: 实现限定范围的筛选和唯一结果检查**

筛选控件必须限定在筛选浮层中，不能使用录制代码的裸 `nth(1)`。`filter_archive` 返回结果行数；多于一条抛出 `NocoBaseStructureError(stage='档案筛选', code='duplicate_archive')`。

- [ ] **Step 6: 增加会话过期和页面结构变化测试**

夹具支持一次 401/重定向登录页和缺失按钮页面；验证前者自动重新登录一次，后者抛结构性错误且不点击其他按钮。

- [ ] **Step 7: 运行浏览器测试**

Run: `python -m unittest tests.test_nocobase_browser -v`  
Expected: PASS，测试只访问 `127.0.0.1` 夹具。

- [ ] **Step 8: 检查点**

确认测试运行时没有访问 `cloud.njncc.com`；当前无 Git 仓库，不执行提交。

---

### Task 5: 简历收集 NocoBase 适配器

**Files:**
- Create: `features/nocobase_sync/resume_documents.py`
- Create: `tests/test_nocobase_adapters.py`
- Modify: `tests/nocobase_fixture.py`

**Interfaces:**
- Consumes: `NocoBaseBrowser`, `SyncRecord`。
- Produces: `ResumeDocumentsAdapter(browser).upsert(record)`, `.delete(archive_no)`。

- [ ] **Step 1: 写新增、更新、附件和删除测试**

```python
def test_resume_upsert_is_idempotent_and_uploads_attachment(self):
    adapter.upsert(resume_record(archive_no='R-001', name='第一次'))
    adapter.upsert(resume_record(archive_no='R-001', name='第二次'))
    self.assertEqual(fixture.count('简历收集', 'R-001'), 1)
    saved = fixture.record('简历收集', 'R-001')
    self.assertEqual(saved['简历名称'], '第二次')
    self.assertEqual(saved['attachment_bytes'], b'%PDF-test')
```

- [ ] **Step 2: 运行适配器测试并确认失败**

Run: `python -m unittest tests.test_nocobase_adapters.ResumeDocumentsAdapterTests -v`  
Expected: FAIL，提示 `ResumeDocumentsAdapter` 不存在。

- [ ] **Step 3: 实现按档案编号 upsert**

零条时点击“添加”，一条时打开该结果行的“编辑”。用字段 label 填入处理状态、招聘类型、招聘渠道、其他渠道详细、应聘岗位、其他岗位名称、简历名称、创建人和上传时间。附件使用 `set_input_files(record.attachment)`。

- [ ] **Step 4: 实现招聘类型/渠道/岗位条件字段**

选择招聘类型后等待对应渠道选项出现；选择“其他”时填详情。选择非“其他”时清空隐藏详情值，避免旧值残留。提交后重新按档案号筛选，必须仍然只有一条。

- [ ] **Step 5: 实现安全删除**

`delete` 先筛选档案编号，仅结果恰好一条时点击该行删除并确认；零条视为幂等成功；多条暂停，不得批量删除。

- [ ] **Step 6: 运行简历适配器测试**

Run: `python -m unittest tests.test_nocobase_adapters.ResumeDocumentsAdapterTests -v`  
Expected: PASS。

- [ ] **Step 7: 检查点**

审阅所有编辑/删除按钮都限定在唯一结果行或当前对话框；当前无 Git 仓库，不执行提交。

---

### Task 6: 人才库及经历子表适配器

**Files:**
- Create: `features/nocobase_sync/candidates.py`
- Modify: `tests/test_nocobase_adapters.py`
- Modify: `tests/nocobase_fixture.py`

**Interfaces:**
- Consumes: `NocoBaseBrowser`, `SyncRecord`。
- Produces: `CandidatesAdapter(browser).upsert(record)`, `.delete(archive_no)`, `_replace_educations(rows)`, `_replace_work_experiences(rows)`, `_replace_projects(rows, recruitment_type)`。

- [ ] **Step 1: 写人才新增、更新和三个经历子表测试**

```python
def test_social_candidate_replaces_experiences_without_duplicates(self):
    adapter.upsert(social_candidate('C-001', educations=[education('甲大学')], works=[work('甲公司')], projects=[project('甲项目')]))
    adapter.upsert(social_candidate('C-001', educations=[education('乙大学')], works=[work('乙公司')], projects=[project('乙项目')]))
    saved = fixture.record('招聘人才库', 'C-001')
    self.assertEqual(saved['教育经历'], [{'毕业院校': '乙大学'}])
    self.assertEqual(saved['工作经历'], [{'工作单位': '乙公司'}])
    self.assertEqual(saved['项目经历'], [{'项目名称': '乙项目'}])
    self.assertEqual(fixture.count('招聘人才库', 'C-001'), 1)
```

- [ ] **Step 2: 运行人才适配器测试并确认失败**

Run: `python -m unittest tests.test_nocobase_adapters.CandidatesAdapterTests -v`  
Expected: FAIL，提示 `CandidatesAdapter` 不存在。

- [ ] **Step 3: 实现基础字段和附件 upsert**

按 label 填写姓名、性别、出生年月、年龄、政治面貌、档案编号、学历、毕业院校、专业、联系方式、邮箱、籍贯/居住地、招聘类型、渠道、岗位及条件详情。不得重放录制中的测试值、`CapsLock` 或重复 Enter。

- [ ] **Step 4: 实现稳定年月控件**

创建 `_fill_month(container, label, value)`：定位当前对话框/当前子表行中的日期输入，填入 `YYYY-MM`，按 Tab，等待日期弹层消失并断言输入值。禁止通过多次点击“上一年”选择日期。

- [ ] **Step 5: 实现子表完整替换**

编辑时先逐行删除现有教育、工作和项目经历，仅操作当前表单的子表区域；再按本地顺序新增。工作岗位和项目角色允许空值。每次添加后通过子表当前行数增长来等待，不使用固定睡眠。

- [ ] **Step 6: 实现招聘类型动态区域等待**

选择社会招聘后等待项目经历区域可见；选择校园招聘后等待项目经历区域隐藏并填入毕业时间/应届字段。该逻辑替代 Codegen 在“社会招聘”和“工作经历开始时间”处的卡顿动作。

- [ ] **Step 7: 实现人才安全删除并增加条件字段测试**

零条删除幂等成功，一条删除，多条暂停。增加测试验证校园招聘不写项目经历、社会招聘不保留校园专属字段。

- [ ] **Step 8: 运行人才适配器测试**

Run: `python -m unittest tests.test_nocobase_adapters.CandidatesAdapterTests -v`  
Expected: PASS。

- [ ] **Step 9: 检查点**

审阅日期、动态区域和子表操作均以当前对话框/行限定；当前无 Git 仓库，不执行提交。

---

### Task 7: 独立 worker、失败分类和浏览器恢复

**Files:**
- Create: `features/nocobase_sync/worker.py`
- Create: `tests/test_nocobase_worker.py`

**Interfaces:**
- Consumes: `queue.claim`, `mapping.load_record`, 两个 adapter、`config.load`。
- Produces: `run_once(data_dir, worker_id, browser_factory) -> bool`, `run_forever(data_dir, stop_event=None)`, CLI `python -m features.nocobase_sync.worker`。

- [ ] **Step 1: 写任务路由、成功和可重试失败测试**

```python
def test_run_once_routes_resume_upsert_and_completes_job(self):
    self.enqueue('resume_documents', 8, 'R-008', 'upsert')
    worked = worker.run_once(self.data_dir, 'test-worker', self.fake_browser_factory)
    self.assertTrue(worked)
    self.assertEqual(self.resume_adapter.calls, [('upsert', 'R-008')])
    self.assertEqual(self.job_status(), '成功')
```

- [ ] **Step 2: 运行 worker 测试并确认失败**

Run: `python -m unittest tests.test_nocobase_worker -v`  
Expected: FAIL，提示 worker 不存在。

- [ ] **Step 3: 实现单任务执行和隐私安全错误模型**

```python
@dataclass(frozen=True)
class SyncFailure:
    stage: str
    error_type: str
    diagnostic_id: str
    pausable: bool = False
```

网络错误、超时和浏览器崩溃进入自动重试；重复档案号、字段缺失、附件缺失和 NocoBase 校验拒绝进入暂停。禁止把原始异常字符串直接写入日志。

- [ ] **Step 4: 实现浏览器重建和连续处理**

同一浏览器顺序处理任务；出现 Playwright 浏览器断开时关闭并重建一次，然后让当前任务按队列规则失败。空队列使用条件等待/短轮询，支持 stop event 安全退出。

- [ ] **Step 5: 增加日志脱敏和删除任务测试**

测试向异常中注入姓名、电话、文件名和密码，断言 `data/nocobase-sync.log` 不包含这些值；删除任务在本地记录不存在时仍由 archive_no 执行。

- [ ] **Step 6: 运行 worker 测试**

Run: `python -m unittest tests.test_nocobase_worker -v`  
Expected: PASS。

- [ ] **Step 7: 检查点**

Run: `python -m unittest tests.test_nocobase_worker -v` 并检查没有残留 Edge 进程；当前无 Git 仓库，不执行提交。

---

### Task 8: 业务事务入队和删除快照

**Files:**
- Modify: `server.py`（`initialize`, `insert`, `sync_application_talent`, 识别状态更新，通用 POST/PUT/DELETE，批量删除）
- Modify: `features/nocobase_sync/__init__.py`
- Create: `tests/test_nocobase_integration.py`

**Interfaces:**
- Consumes: `queue.ensure_tables`, `enqueue_upsert`, `enqueue_delete`。
- Produces: 每个受支持业务事务的持久化任务；不改变现有 API 响应格式。

- [ ] **Step 1: 写新增、修改、删除同事务入队测试**

```python
def test_candidate_create_update_delete_enqueue_expected_jobs(self):
    status, created = self.call('candidates', self.candidate_payload())
    self.assertEqual(status, 201)
    self.assertJob('candidates', created['id'], 'upsert')
    self.call(f"candidates/{created['id']}", {'hometown': '南京'}, method='PUT')
    self.assertLatestJob('candidates', created['id'], 'upsert')
    self.call(f"candidates/{created['id']}", method='DELETE')
    self.assertLatestJob('candidates', created['id'], 'delete')
```

- [ ] **Step 2: 运行集成测试并确认失败**

Run: `python -m unittest tests.test_nocobase_integration -v`  
Expected: FAIL，查不到队列任务。

- [ ] **Step 3: 初始化同步表并在通用 CRUD 中入队**

`initialize()` 调用 `queue.ensure_tables(conn)`。POST/PUT 在所有业务字段和经历子表保存完成后、`conn.commit()` 前调用 `enqueue_upsert`。DELETE/批量删除在记录仍存在时，从 deletion plan 提取受支持实体的 `id/archive_no/updated_at`，调用 `enqueue_delete` 后再删除和 commit。

- [ ] **Step 4: 覆盖非通用运行时更新**

在 Dify 识别把简历改为已识别/失败、识别结果入库把简历改为已入库、人才由应聘登记自动新增或更新后，同一事务内入队相应简历或人才。初始化迁移期间不逐条入队，历史同步任务负责当前全量状态。

- [ ] **Step 5: 验证事务回滚不会残留任务**

增加测试：制造唯一约束/字段校验失败，断言业务记录和队列任务都没有提交；导入预览 SAVEPOINT 回滚后不保留任务。

- [ ] **Step 6: 运行集成和原有服务器测试**

Run: `python -m unittest tests.test_nocobase_integration tests.test_server tests.test_table_tools -v`  
Expected: PASS。

- [ ] **Step 7: 检查点**

审阅每个 `commit()` 前的入队位置和删除快照；当前无 Git 仓库，不执行提交。

---

### Task 9: 同步管理 API 和历史同步控制

**Files:**
- Create: `features/nocobase_sync/api.py`
- Modify: `server.py`
- Create: `tests/test_nocobase_api.py`

**Interfaces:**
- Produces authenticated routes: `GET /api/nocobase-sync/status`, `POST /api/nocobase-sync/test-connection`, `POST /api/nocobase-sync/retry`, `POST /api/nocobase-sync/history/preview`, `POST /api/nocobase-sync/history/start`, `POST /api/nocobase-sync/history/pause`, `POST /api/nocobase-sync/history/resume`。

- [ ] **Step 1: 写认证、状态和历史预览测试**

```python
def test_history_preview_counts_records_and_attachments_without_enqueuing(self):
    status, result = self.call('nocobase-sync/history/preview', method='POST')
    self.assertEqual(status, 200)
    self.assertEqual(result, {'resume_documents': 3, 'candidates': 2, 'attachments': 4})
    self.assertEqual(self.job_count(), 0)
```

- [ ] **Step 2: 运行 API 测试并确认失败**

Run: `python -m unittest tests.test_nocobase_api -v`  
Expected: FAIL，路由返回 404。

- [ ] **Step 3: 实现只读状态、预览和连接测试**

所有路由复用现有登录认证。连接测试在后台短生命周期浏览器中只登录，不打开新增弹窗。状态返回聚合数量、最近成功时间、历史任务状态和去敏错误字段。

- [ ] **Step 4: 实现历史启动、暂停和继续**

`history/start` 要求请求体 `{'confirmed': True}` 且已存在两条成功的专用测试审计记录；在一个事务中为所有现存简历和人才生成/合并 upsert。系统设置表保存 `nocobase_history_state` 为运行/暂停/完成。暂停只阻止历史任务被 claim，不阻止日常增量任务。

- [ ] **Step 5: 实现重试接口**

`retry` 接受一个有效任务 ID 或 `all_failed=True`，只把失败/暂停任务恢复为等待，不复制业务数据，不允许修改成功任务。

- [ ] **Step 6: 运行 API 测试**

Run: `python -m unittest tests.test_nocobase_api -v`  
Expected: PASS，包含未登录 401、非法 ID 400、预览不入队和确认门槛。

- [ ] **Step 7: 检查点**

审阅真实写入只能由显式历史启动触发；当前无 Git 仓库，不执行提交。

---

### Task 10: 同步状态管理页面

**Files:**
- Create: `web/features/nocobase_sync.js`
- Create: `web/features/nocobase_sync.css`
- Modify: `web/app.js`
- Modify: `web/index.html`（仅在需要新增静态资源引用时）
- Create: `tests/nocobase_sync_ui_check.js`

**Interfaces:**
- Consumes: Task 9 的 API。
- Produces: 侧栏“NocoBase同步”入口、状态卡片、失败列表、重试、测试连接、历史预览/开始/暂停/继续操作。

- [ ] **Step 1: 写 UI 渲染和操作路由测试**

```javascript
assert.match(renderSyncStatus({waiting:3,running:1,succeeded:8,failed:2,paused:1}), /等待同步/);
assert.match(renderSyncStatus({waiting:3,running:1,succeeded:8,failed:2,paused:1}), /3/);
assert.strictEqual(historyStartPayload(), JSON.stringify({confirmed:true}));
```

- [ ] **Step 2: 运行 UI 测试并确认失败**

Run: `node tests/nocobase_sync_ui_check.js`  
Expected: FAIL，模块或函数不存在。

- [ ] **Step 3: 实现侧栏入口和独立页面渲染**

在 schemas 生成的业务模块按钮之外添加 `data-nav="nocobase_sync"`。`render()` 在读取 schema 前处理该页面，避免把它误当普通数据表。状态卡显示等待、处理中、成功、失败、暂停和最近成功时间。

- [ ] **Step 4: 实现危险操作前确认**

历史全量同步按钮先请求 preview，弹窗展示两个模块和附件数量，用户再次确认后才调用 start。删除 NocoBase 记录不在管理页面提供批量按钮。测试连接明确说明“不修改数据”。

- [ ] **Step 5: 实现失败列表和重试交互**

失败行仅显示实体、档案编号、阶段、简化错误、诊断编号和时间；不显示姓名/电话。单条重试和全部失败重试完成后刷新状态。

- [ ] **Step 6: 运行 UI 测试和现有 JS 检查**

Run: `node tests/nocobase_sync_ui_check.js`  
Run: `node tests/resume_documents_ui_check.js`  
Run: `node tests/table_layout_ui_check.js`  
Expected: 全部 PASS。

- [ ] **Step 7: 检查点**

人工检查窄屏和表格独立滚动下按钮可用；当前无 Git 仓库，不执行提交。

---

### Task 11: 启动、停止和单实例生命周期

**Files:**
- Modify: `start.ps1`
- Modify: `start.bat`
- Modify: `features/nocobase_sync/worker.py`
- Create: `tests/test_nocobase_startup.py`

**Interfaces:**
- Produces: 一次启动 HTTP 服务和一个 worker；HTTP 服务退出时停止其对应 worker；已有 worker 持锁时不启动第二个执行循环。

- [ ] **Step 1: 写 worker 单实例锁测试**

测试同一 data 目录同时运行两个 worker 入口：第一个获得 `nocobase-worker.lock`，第二个返回明确退出码且不领取任务；异常退出后过期锁可恢复。

- [ ] **Step 2: 运行启动测试并确认失败**

Run: `python -m unittest tests.test_nocobase_startup -v`  
Expected: FAIL，单实例锁或启动函数不存在。

- [ ] **Step 3: 实现 PowerShell 生命周期管理**

`start.ps1` 读取 Python，启动隐藏 worker，前台运行 `server.py --host 0.0.0.0 --port 8116`，在 `finally` 中只停止自己启动且 PID 精确匹配的 worker。不得按进程名批量结束 Python。

- [ ] **Step 4: 让 start.bat 统一调用 start.ps1**

`start.bat` 保留从用户环境读取 Dify Key，然后调用：

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
pause
```

worker 未配置 NocoBase 时保持空闲并记录“未配置”，不能导致招聘系统启动失败。

- [ ] **Step 5: 运行启动测试并手工验证精确进程数**

Run: `python -m unittest tests.test_nocobase_startup -v`  
Expected: PASS。  
手工启动后使用 `netstat -ano -p tcp` 确认 8116 只有一个监听进程，并确认只有一个 worker 锁持有者。

- [ ] **Step 6: 检查点**

停止脚本后确认对应 worker 退出，其他 Python 进程不受影响；当前无 Git 仓库，不执行提交。

---

### Task 12: 全套验证、真实两条测试记录和文档/Word手册

**Files:**
- Modify: `README.md`
- Modify: `功能模块说明.md`
- Modify: `scripts/build_operation_manual.py`
- Regenerate: `南化建招聘管理系统操作手册.docx`

**Interfaces:**
- Consumes: 所有前述任务。
- Produces: 经验证的功能、部署说明、配置说明、同步管理说明和更新后的 Word 操作手册。

- [ ] **Step 1: 运行全部自动化测试**

Run: `python -m unittest discover -s tests`  
Expected: 现有及新增 Python 测试全部 PASS。  
Run: `Get-ChildItem tests\*_ui_check.js | ForEach-Object { node $_.FullName }`  
Expected: 所有 JS 检查退出码为 0。

- [ ] **Step 2: 验证自动化测试未访问真实 NocoBase**

测试夹具记录所有 Host，断言只有 `127.0.0.1`/`localhost`；扫描测试日志，确认不存在 `cloud.njncc.com` 的 POST、真实附件上传或业务字段值。

- [ ] **Step 3: 更新文本说明**

README 和功能说明必须包含：单向同步范围、配置 NocoBase、后台模式、队列/重试、诊断编号、首次历史同步确认门槛、网址更换、停止/重启恢复和 API 替换路径。

- [ ] **Step 4: 更新 Word 操作手册生成脚本**

新增“NocoBase 数据同步”章节，覆盖：运行配置批处理、测试连接、两条测试记录、检查附件和经历、启动历史同步、暂停继续、失败重试、查看诊断编号、修改网址和常见故障。

- [ ] **Step 5: 生成并视觉验证 Word 文档**

执行文档技能要求的生成及渲染流程，使用 `render_docx.py` 将手册渲染为逐页 PNG，检查标题层级、分页、表格、中文换行和截图/示意内容；发现布局问题后修改生成脚本并重新渲染，直至无截断或重叠。

- [ ] **Step 6: 在真实 NocoBase 执行连接测试**

由用户在本机运行 `配置NocoBase.bat` 输入凭据。只读连接测试必须成功；不在聊天、命令输出或日志显示密码。

- [ ] **Step 7: 执行两条专用真实测试记录验收**

使用明显测试档案编号和虚构个人信息创建一条简历、一条人才，验证新增、更新、附件、教育/工作/项目经历和同步删除。每个对 NocoBase 的写入步骤都由用户在当时明确确认后执行。

- [ ] **Step 8: 用户确认后启动历史同步**

先展示实际简历、人才和附件数量；用户确认后调用历史启动。等待队列完成或出现暂停任务，报告成功、失败、暂停和跳过数量，不宣称未实际验证的记录已同步。

- [ ] **Step 9: 最终检查点**

重新运行全套测试，确认本地 HTTP 200、8116 单监听、worker 单实例、NocoBase 状态页可用、Word 手册视觉验证通过。当前无 Git 仓库，不执行提交；提供所有新增和修改文件清单供用户备份部署。
