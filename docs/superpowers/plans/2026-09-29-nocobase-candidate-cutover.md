# NocoBase 人才库切换实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在设计电脑不写入正式数据的前提下，为招聘人才库实现可预检、可显式切换的 NocoBase 主数据后端，并保留现有页面契约。

**Architecture:** 保留现有 SQLite 实现，通过持久化后端选择器在进程启动时选择唯一实现。NocoBase 实现由 JSON/Multipart 客户端、Swagger 字段预检、主表仓库、关联仓库、附件仓库和组合服务组成；HTTP 路由只依赖统一服务契约，失败时不回退或双写。

**Tech Stack:** Python 3.10+、标准库 `urllib.request`、Windows DPAPI、NocoBase HTTP API、`unittest`

**Spec:** `docs/superpowers/specs/2026-09-29-nocobase-candidate-cutover-design.md`

## Global Constraints

- 设计电脑默认使用 `sqlite`，自动化测试只访问本地假服务，不访问正式 NocoBase。
- `nocobase` 只能在有效配置和只读预检通过后显式启用。
- 禁止双写；NocoBase 失败时不得回退 SQLite。
- API Key 不得出现在前端、日志、异常、测试快照或 Git 中。
- 本计划不迁移固定 IP 电脑已有 SQLite 数据，也不切换人才库之外的业务模块。
- 不修改主工作区未提交文件；所有实现继续在 `codex/nocobase-api` 隔离分支完成。

## Review Focus

- 后端选择文件缺失、损坏或值未知时必须安全回到 `sqlite`，不能意外连接正式服务；Task 1 覆盖。
- Swagger 中中文标题重复、字段缺失或关联类型变化时必须阻止启用；Task 3 覆盖。
- 主表已创建但附件或关联失败时必须补偿，且补偿失败不能自动重复创建；Task 6 覆盖。
- NocoBase 分页 `meta` 缺失、附件上传返回无 ID、下载 URL 非 HTTP(S) 时必须当作协议错误；Tasks 2、5 覆盖。
- NocoBase 故障、401 或 403 时 `/api/candidates` 必须返回脱敏错误且不得触碰 SQLite 人才表；Task 7 覆盖。

---

### Task 1: 持久化数据源选择与安全启用

**Files:**
- Create: `features/nocobase_sync/backend.py`
- Create: `tests/test_nocobase_backend.py`
- Modify: `features/nocobase_sync/configure.py`

**Interfaces:**
- Consumes: `config.load(data_dir) -> NocoBaseConfig`
- Produces: `read_backend(data_dir: Path) -> Literal["sqlite", "nocobase"]`
- Produces: `enable_nocobase(data_dir: Path, preflight: Callable[[], object]) -> None`
- Produces: `select_candidate_backend(data_dir: Path, *, preflight: Callable | None = None) -> str`

- [ ] **Step 1: Write failing tests for safe defaults and explicit activation**

  Add tests named `test_missing_corrupt_and_unknown_backend_default_to_sqlite`, `test_enable_requires_valid_api_configuration_and_successful_preflight`, `test_failed_preflight_never_changes_existing_backend`, and `test_successful_enable_is_atomic_and_persistent`. Assert that the stored file is `candidate-backend.json` version 1 and contains only `backend` plus `version`.

- [ ] **Step 2: Run `python -m unittest tests.test_nocobase_backend -v`**

  Expected: FAIL because `features.nocobase_sync.backend` does not exist.

- [ ] **Step 3: Implement the backend selector**

  Use atomic temp-file replacement. Treat every unreadable or invalid selector as `sqlite`; never infer activation merely because an API Key exists. Extend the CLI with explicit `configure`, `check`, `enable`, and `disable` commands, keeping API Key input hidden.

- [ ] **Step 4: Run focused and existing configuration tests**

  Run: `python -m unittest tests.test_nocobase_backend tests.test_nocobase_config -v`  
  Expected: all tests PASS.

- [ ] **Step 5: Commit**

  ```text
  feat: add explicit candidate backend selection
  ```

### Task 2: 保留分页元数据并支持安全 Multipart/二进制请求

**Files:**
- Modify: `features/nocobase_sync/client.py`
- Modify: `tests/test_nocobase_client.py`

**Interfaces:**
- Produces: `NocoBaseResponse(data: object, meta: dict | None)`
- Produces: `NocoBaseClient.request_envelope(action, *, method="GET", params=None, body=None) -> NocoBaseResponse`
- Preserves: `NocoBaseClient.request(...) -> object`
- Produces: `NocoBaseClient.upload(action, *, filename: str, mime_type: str, content: bytes, params=None) -> object`
- Produces: `NocoBaseClient.download(url: str) -> tuple[bytes, str]`

- [ ] **Step 1: Write failing tests for response metadata, multipart encoding and safe downloads**

  Add `test_request_envelope_preserves_valid_meta`, `test_request_envelope_rejects_non_object_meta`, `test_upload_builds_multipart_without_logging_file_or_token`, `test_upload_rejects_missing_integer_attachment_id`, and `test_download_rejects_non_http_url_and_never_sends_credentials_cross_origin`. Assert existing `request()` behavior remains unchanged and cross-origin HTTP(S) file URLs receive no Authorization header.

- [ ] **Step 2: Run `python -m unittest tests.test_nocobase_client -v`**

  Expected: FAIL because envelope/upload/download APIs are missing.

- [ ] **Step 3: Implement the new client capabilities**

  Build multipart bodies with a random boundary, one `file` part, and escaped basename only. `download` may send Authorization only to the configured NocoBase origin; reject credentials, fragments, non-HTTP schemes and cross-origin URLs. Reuse current sanitized `NocoBaseError` categories.

- [ ] **Step 4: Run `python -m unittest tests.test_nocobase_client -v`**

  Expected: all client tests PASS with no warnings.

- [ ] **Step 5: Commit**

  ```text
  feat: extend NocoBase transport for paging and files
  ```

### Task 3: 只读 Swagger Schema 预检与字段映射解析

**Files:**
- Create: `features/nocobase_sync/preflight.py`
- Create: `tests/test_nocobase_preflight.py`

**Interfaces:**
- Consumes: `NocoBaseClient.request(...)`
- Produces: `RelationFieldMap(education: dict, work: dict, project: dict)`
- Produces: `PreflightReport(ok: bool, checks: tuple[str, ...], relation_fields: RelationFieldMap)`
- Produces: `run_preflight(client: NocoBaseClient) -> PreflightReport`

- [ ] **Step 1: Write failing tests using a fake Swagger document**

  Cover: valid `campus_talent_pool`, all four relation paths, title-to-key resolution for every field in the spec, duplicate Chinese titles, missing fields, missing CRUD actions, wrong association type, and a response containing no OpenAPI schemas. Assert all calls are GET and no `create`, `update`, `destroy`, `set`, or `toggle` action is issued.

- [ ] **Step 2: Run `python -m unittest tests.test_nocobase_preflight -v`**

  Expected: FAIL because the preflight module is missing.

- [ ] **Step 3: Implement strict schema discovery**

  Read `swagger:get` with `ns=collections/campus_talent_pool`. Resolve remote keys from exact Chinese field titles, validate their JSON types/formats, and return immutable maps. Raise a sanitized `NocoBaseError("protocol", ...)` for ambiguity or mismatch.

- [ ] **Step 4: Run `python -m unittest tests.test_nocobase_preflight -v`**

  Expected: all preflight tests PASS.

- [ ] **Step 5: Commit**

  ```text
  feat: validate NocoBase talent schema before activation
  ```

### Task 4: 教育、工作和项目经历关联仓库

**Files:**
- Create: `features/nocobase_sync/relation_repository.py`
- Create: `tests/test_nocobase_relation_repository.py`

**Interfaces:**
- Consumes: `RelationFieldMap`, `NocoBaseClient`
- Produces: `RelationRepository.list(candidate_id: int, relation: str) -> list[dict]`
- Produces: `RelationRepository.sync(candidate_id: int, relation: str, rows: list[dict]) -> None`
- Produces: `RelationRepository.snapshot(candidate_id: int) -> dict[str, list[dict]]`
- Produces: `RelationRepository.restore(candidate_id: int, snapshot: dict[str, list[dict]]) -> None`

- [ ] **Step 1: Write failing exact-call tests for the three relation endpoints**

  Cover mapping both directions, preserving API order, updating existing relation IDs by position, creating additional rows, deleting surplus rows with `filterByTk`, clearing project rows, maximum 10 rows, invalid candidate IDs, and response shapes without a list or integer ID.

- [ ] **Step 2: Run `python -m unittest tests.test_nocobase_relation_repository -v`**

  Expected: FAIL because the repository module is missing.

- [ ] **Step 3: Implement the repository**

  Whitelist relation names to `Education_Background`, `Work_experience`, and `Project_Experience`. Use list/create/update/destroy actions only; do not delete and recreate rows that can be updated. Never send an empty `filter`.

- [ ] **Step 4: Run `python -m unittest tests.test_nocobase_relation_repository -v`**

  Expected: all relation tests PASS.

- [ ] **Step 5: Commit**

  ```text
  feat: persist candidate experience relations in NocoBase
  ```

### Task 5: 简历附件上传、关联和受控读取

**Files:**
- Create: `features/nocobase_sync/attachment_repository.py`
- Create: `tests/test_nocobase_attachment_repository.py`

**Interfaces:**
- Consumes: `NocoBaseClient.upload`, `NocoBaseClient.download`
- Produces: `AttachmentRepository.list(candidate_id: int) -> list[dict]`
- Produces: `AttachmentRepository.replace(candidate_id: int, upload: dict | None, remove: bool = False) -> list[dict]`
- Produces: `AttachmentRepository.read(attachment_id: int) -> tuple[bytes, str, str]`
- Produces: `AttachmentRepository.delete_if_unreferenced(attachment_id: int) -> bool`

- [ ] **Step 1: Write failing attachment workflow tests**

  Cover base64 decoding, 50MB limit, allowed resume MIME/extensions, upload with `attachmentField=campus_talent_pool.biographical_notes`, association via `biographical_notes:set` using `{"values": [id]}`, no-change edits, explicit removal, shared attachment retention, invalid remote URL, and upload response missing an integer ID.

- [ ] **Step 2: Run `python -m unittest tests.test_nocobase_attachment_repository -v`**

  Expected: FAIL because the attachment repository is missing.

- [ ] **Step 3: Implement attachment operations**

  Upload before changing the association. If association fails, attempt to remove only the newly uploaded unattached record. Physical deletion requires a NocoBase query proving no talent record references the attachment; otherwise detach only.

- [ ] **Step 4: Run `python -m unittest tests.test_nocobase_attachment_repository -v`**

  Expected: all attachment tests PASS.

- [ ] **Step 5: Commit**

  ```text
  feat: store candidate resume attachments in NocoBase
  ```

### Task 6: 组合式远端人才服务与失败补偿

**Files:**
- Create: `features/nocobase_sync/remote_candidate_service.py`
- Create: `features/nocobase_sync/candidate_validation.py`
- Create: `tests/test_nocobase_remote_candidate_service.py`
- Modify: `features/nocobase_sync/candidate_repository.py`
- Modify: `tests/test_nocobase_candidate_repository.py`

**Interfaces:**
- Consumes: `CandidateRepository`, `RelationRepository`, `AttachmentRepository`
- Produces: `RemoteCandidateService.list(page: int, page_size: int, query: str) -> dict`
- Produces: `RemoteCandidateService.get(identifier: int) -> dict | None`
- Produces: `RemoteCandidateService.create(payload: dict) -> int`
- Produces: `RemoteCandidateService.create_many(payloads: list[dict]) -> list[int]`
- Produces: `RemoteCandidateService.update(identifier: int, payload: dict) -> None`
- Produces: `RemoteCandidateService.delete_preview(ids: list[int]) -> dict`
- Produces: `RemoteCandidateService.delete(ids: list[int], expected: list[dict]) -> int`

- [ ] **Step 1: Write failing service tests for complete aggregate behavior**

  Cover paginated list with `meta.count`, detail aggregation, exact-phone duplicate rejection, validation before any remote call, campus creation without projects, social creation with all relations, parent-create compensation, all-or-nothing multi-create compensation, update snapshot restoration, restoration failure diagnostic, attachment preservation, stale delete preview rejection, and no SQLite write calls.

- [ ] **Step 2: Run `python -m unittest tests.test_nocobase_remote_candidate_service -v`**

  Expected: FAIL because the service module is missing and repository pagination lacks `meta`.

- [ ] **Step 3: Extend the main repository and implement the aggregate service**

  Add `list_page(...) -> {"rows": list[dict], "count": int}` and `find_by_phone(phone: str) -> dict | None`. Implement `validate_remote_candidate(payload, schema, *, phone_exists) -> dict` without importing `server.py`; reuse the feature-level recruitment, position, education, date, phone and email rules. Normalize and validate all rows before mutation. For unknown write results, query by stable archive number/phone before deciding whether to retry or compensate.

- [ ] **Step 4: Run candidate repository and aggregate service tests**

  Run: `python -m unittest tests.test_nocobase_candidate_repository tests.test_nocobase_remote_candidate_service -v`  
  Expected: all tests PASS.

- [ ] **Step 5: Commit**

  ```text
  feat: compose complete NocoBase candidate operations
  ```

### Task 7: 接入现有人才库 HTTP 路由

**Files:**
- Create: `features/nocobase_sync/http_adapter.py`
- Create: `features/nocobase_sync/diagnostics.py`
- Create: `tests/test_nocobase_http_adapter.py`
- Modify: `server.py`
- Modify: `tests/test_table_tools.py`

**Interfaces:**
- Consumes: `select_candidate_backend`, `RemoteCandidateService`
- Produces: `build_candidate_service(data_dir: Path) -> RemoteCandidateService | None`
- Produces: `handle_remote_candidate_request(handler, method: str, identifier: str | None, query: dict) -> bool`

- [ ] **Step 1: Write failing route contract tests**

  Verify remote mode supports list/search/pagination, detail, create, update, delete preview, confirmed batch delete, import preview/commit with all-or-nothing compensation, CSV/XLSX export inputs, QR record lookup, and attachment preview/download while preserving current status codes and JSON shapes. Add failures for 401, 403, 5xx and network timeout; assert the SQLite `candidates` table remains unchanged and no SQLite fallback occurs. Capture diagnostics and assert they contain only diagnostic ID, action, status and elapsed time—not API keys, request bodies, names, phone numbers or email addresses.

- [ ] **Step 2: Run route-focused tests**

  Run: `python -m unittest tests.test_nocobase_http_adapter -v`  
  Expected: FAIL because the adapter and route branch do not exist.

- [ ] **Step 3: Implement one early candidate-route branch in `server.py`**

  Build the selected backend once during server startup. Route only the `candidates` entity and its NocoBase attachment reads through the adapter; leave all other entities on existing SQLite code. Keep import tokens in the existing bounded in-memory store, but commit rows through `create_many`. Convert `NocoBaseError` to stable HTTP statuses and write sanitized structured diagnostics without exposing endpoint secrets or record bodies.

- [ ] **Step 4: Run route tests and full legacy tests**

  Run: `python -m unittest tests.test_nocobase_http_adapter tests.test_table_tools -v`  
  Expected: all tests PASS in both default SQLite and injected remote modes.

- [ ] **Step 5: Commit**

  ```text
  feat: switch talent routes through selected backend
  ```

### Task 8: 固定 IP 部署、只读检查和最终回归

**Files:**
- Modify: `README.md`
- Modify: `配置NocoBase.bat`
- Create: `检查NocoBase连接.bat`
- Create: `启用NocoBase人才库.bat`
- Create: `停用NocoBase人才库.bat`
- Create: `tests/test_nocobase_launchers.py`

**Interfaces:**
- Consumes: Tasks 1–7 command-line interfaces
- Produces: fixed-IP deployment workflow with an explicit read-only gate

- [ ] **Step 1: Write failing launcher/documentation tests**

  Assert each batch file invokes the intended module command, uses `%~dp0`, contains no URL or API Key, and that enablement calls preflight before writing `nocobase`. Assert README says design computer remains SQLite, DPAPI config must be recreated on the IP computer, no migration occurs, and failure never falls back.

- [ ] **Step 2: Run `python -m unittest tests.test_nocobase_launchers -v`**

  Expected: FAIL because the new launchers and wording are absent.

- [ ] **Step 3: Add deployment commands and operator instructions**

  The check command must be read-only and print one line per check without secrets. The enable command must stop on any failed check. The disable command only changes the next-start backend to SQLite and must not delete either database or configuration.

- [ ] **Step 4: Run all NocoBase tests**

  Run: `python -m unittest tests.test_nocobase_config tests.test_nocobase_backend tests.test_nocobase_client tests.test_nocobase_preflight tests.test_nocobase_candidate_mapping tests.test_nocobase_candidate_repository tests.test_nocobase_relation_repository tests.test_nocobase_attachment_repository tests.test_nocobase_remote_candidate_service tests.test_nocobase_http_adapter tests.test_nocobase_launchers -v`  
  Expected: all focused tests PASS.

- [ ] **Step 5: Run the complete regression suite**

  Run: `python -m unittest discover -s tests -p 'test_*.py'`  
  Expected: all tests PASS, no warnings or external NocoBase calls.

- [ ] **Step 6: Review for secrets and unrelated changes, then commit**

  ```text
  docs: add guarded NocoBase deployment workflow
  ```

## Completion Boundary

完成本计划表示代码已具备安全切换能力，但设计电脑仍保持 `sqlite`，且不会自动迁移或写入正式数据。真正启用只在固定 IP 电脑执行部署流程，并在用户现场确认虚构数据验收后进行。
