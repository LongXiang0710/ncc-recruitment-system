# NocoBase 简历收集与人才库统一切换 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“简历收集”和“人才库”统一切换为 NocoBase 唯一数据源，并提供只写代码、不立即连接正式环境的检查与迁移工具。

**Architecture:** 保留现有 `NocoBaseClient`、人才仓储和补偿式服务，新增简历仓储、附件仓储与聚合服务，再通过一个统一服务容器和一个统一后端选择器同时启用两个模块。应聘登记、面试、新员工继续使用 SQLite，但其中的 `candidate_id` 改为远端人才 ID；迁移分为只读检查和可恢复执行两个独立命令，执行成功也不自动启用。

**Tech Stack:** Python 3 标准库（`unittest`、`sqlite3`、`urllib`、`hashlib`、`json`）、现有 HTTP 服务器、NocoBase REST API、Dify API、Windows 批处理、现有前端 JavaScript。

**Spec:** `docs/superpowers/specs/2026-09-30-nocobase-resume-and-talent-cutover-design.md`

## Global Constraints

- 本阶段只编写代码、假客户端测试、批处理和文档；不得连接正式 NocoBase、读取固定 IP 电脑真实数据库、执行迁移或自动启用。
- 简历收集与人才库只能同时为 `sqlite` 或同时为 `nocobase`；NocoBase 模式故障时不得回退 SQLite。
- NocoBase 不得由程序自动创建或修改集合、字段、关系或权限。
- `Resume_Collection` 必须具有 `file_hash`、`recognition_result`、`linked_candidate` 三个技术字段，且 `linked_candidate` 指向 `campus_talent_pool`。
- 日志、报告和错误响应不得包含 API Key、Authorization、请求正文、识别结果、简历内容、姓名、手机号或邮箱。
- 写请求结果不明时不得盲目重试；必须先用稳定键核对，再补偿或停止。
- 迁移冲突不得自动覆盖、合并或跳过；任一档案编号、手机号、`source_id` 或 `file_hash` 冲突都使报告不可执行。
- 迁移检查报告有效期为 24 小时；源或目标摘要变化即失效。
- 执行迁移自动选择最新合格报告并重新校验，不要求人工确认词或报告编号，也不自动切换后端。
- 实现期间保留用户当前工作区已有改动，不覆盖与本计划无关的文件。

## Review Focus

- 远端写入超时但实际已经成功：测试必须证明服务先按稳定键核对，不会重复创建或盲目重试。
- 同一人才被两份简历关联：测试必须证明简历级联删除被阻止，且任何一方都未被删除。
- 迁移报告生成后 SQLite 或 NocoBase 发生变化：测试必须证明执行命令在第一笔写入前停止。
- 公开接口伪造状态、ID、技术字段或超大附件：测试必须证明服务端覆盖/拒绝这些输入且不发远端写请求。
- 补偿过程中再次失败：测试必须证明返回脱敏诊断编号、停止自动重试，并且日志不出现凭据和个人信息。

---

### Task 1: 统一后端选择与双模块只读预检

**Files:**
- Modify: `features/nocobase_sync/backend.py`
- Modify: `features/nocobase_sync/preflight.py`
- Modify: `features/nocobase_sync/configure.py`
- Modify: `features/nocobase_sync/http_adapter.py`
- Modify: `tests/test_nocobase_backend.py`
- Modify: `tests/test_nocobase_preflight.py`
- Modify: `tests/test_nocobase_http_adapter.py`
- Modify: `tests/test_nocobase_launchers.py`

**Interfaces:**
- Consumes: `NocoBaseClient.request(action, params=...)` and existing candidate schema discovery.
- Produces: `PreflightReport(ok, checks, relation_fields, resume_fields)` and a versioned `recruitment-backend.json` selector used atomically by both modules. The old `candidate-backend.json` is never treated as a valid unified opt-in.

- [ ] **Step 1: Write failing selector and preflight tests**

  Add tests proving: legacy/malformed/half-switch selectors do not enable either remote module; selecting NocoBase validates both collections; Swagger discovery requires `Resume_Collection` CRUD, `Resume` relation CRUD/set/remove/toggle, all mapped fields, and the three technical fields with the correct relation target; all discovery calls are GET/read-only.

- [ ] **Step 2: Run the focused tests and confirm failure**

  Run: `python -m unittest tests.test_nocobase_backend tests.test_nocobase_preflight tests.test_nocobase_http_adapter tests.test_nocobase_launchers`

  Expected: FAIL because the unified selector and resume schema result do not exist.

- [ ] **Step 3: Implement the unified selector and preflight**

  Add `ResumeFieldMap` and extend `PreflightReport`; require exact remote fields from the spec and reject `linked_candidate` unless it is a many-to-one relation targeting `campus_talent_pool`. Replace candidate-only enable/status text with“简历收集和人才库”; do not mutate schema or make probe writes. Keep `build_candidate_service` unchanged as a temporary compatibility path until Task 7 replaces server startup wiring.

- [ ] **Step 4: Run focused tests**

  Run: `python -m unittest tests.test_nocobase_backend tests.test_nocobase_preflight tests.test_nocobase_http_adapter tests.test_nocobase_launchers`

  Expected: PASS; fake client request logs contain no POST/PUT/DELETE.

- [ ] **Step 5: Commit**

  ```powershell
  git add features/nocobase_sync/backend.py features/nocobase_sync/preflight.py features/nocobase_sync/configure.py features/nocobase_sync/http_adapter.py tests/test_nocobase_backend.py tests/test_nocobase_preflight.py tests/test_nocobase_http_adapter.py tests/test_nocobase_launchers.py
  git commit -m "feat: unify NocoBase backend preflight"
  ```

### Task 2: 简历字段映射与主集合仓储

**Files:**
- Create: `features/nocobase_sync/resume_mapping.py`
- Create: `features/nocobase_sync/resume_repository.py`
- Create: `tests/test_nocobase_resume_mapping.py`
- Create: `tests/test_nocobase_resume_repository.py`

**Interfaces:**
- Consumes: `ResumeFieldMap` from Task 1 and `NocoBaseClient`.
- Produces: `to_nocobase_resume(values: dict) -> dict`; `from_nocobase_resume(row: dict) -> dict`; `ResumeRepository.list_page(...)`, `get(id)`, `create(values)`, `update(id, values)`, `delete(id)`, `find_by_stable_key(field, value)`, and `find_by_linked_candidate(candidate_id)`.

- [ ] **Step 1: Write failing mapping and repository tests**

  Cover the exact field table in the spec, campus/social channel routing, `Processing_Status` versus ignored remote `status`, timestamp normalization, envelope count validation, ID validation, paging/search, and queries for `Number`, `source_id`, `file_hash`, and `linked_candidate`. Assert duplicate stable-key matches raise a protocol error instead of choosing one.

- [ ] **Step 2: Verify failure**

  Run: `python -m unittest tests.test_nocobase_resume_mapping tests.test_nocobase_resume_repository`

  Expected: FAIL with missing modules/classes.

- [ ] **Step 3: Implement minimal mapping and repository**

  Use `Resume_Collection:list|get|create|update|destroy`; never send the remote `status` field. `find_by_stable_key` must accept only the four allow-listed stable fields and request at most two records.

- [ ] **Step 4: Verify pass**

  Run: `python -m unittest tests.test_nocobase_resume_mapping tests.test_nocobase_resume_repository`

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```powershell
  git add features/nocobase_sync/resume_mapping.py features/nocobase_sync/resume_repository.py tests/test_nocobase_resume_mapping.py tests/test_nocobase_resume_repository.py
  git commit -m "feat: add NocoBase resume repository"
  ```

### Task 3: 简历附件关系仓储

**Files:**
- Create: `features/nocobase_sync/resume_attachment_repository.py`
- Create: `tests/test_nocobase_resume_attachment_repository.py`
- Modify: `features/nocobase_sync/client.py`
- Modify: `tests/test_nocobase_client.py`

**Interfaces:**
- Consumes: `NocoBaseClient.upload`, `download`, and `Resume_Collection/{id}/Resume:*` actions.
- Produces: `ResumeAttachmentRepository.list(resume_id)`, `read(attachment_id)`, `replace(resume_id, upload=None, remove=False)`, `restore(resume_id, snapshot)`, and `delete_if_unreferenced(attachment_id)`.

- [ ] **Step 1: Write failing attachment safety tests**

  Cover upload/association, replacement, removal, snapshot restore, shared-file reference checks, orphan cleanup, MIME and filename handling, 50 MB hard limit, header-injection filename filtering, and cross-origin download not carrying Authorization.

- [ ] **Step 2: Verify failure**

  Run: `python -m unittest tests.test_nocobase_resume_attachment_repository tests.test_nocobase_client`

  Expected: FAIL because the resume attachment repository and bounded download contract are missing.

- [ ] **Step 3: Implement repository and bounded download**

  Add `NocoBaseClient.download(url, *, maximum_bytes: int | None = None)` with streamed limit enforcement. Follow existing talent attachment compensation patterns, but use `Resume_Collection/{id}/Resume:*` and delete file-manager records only after proving no remaining reference.

- [ ] **Step 4: Verify pass**

  Run: `python -m unittest tests.test_nocobase_resume_attachment_repository tests.test_nocobase_client`

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```powershell
  git add features/nocobase_sync/resume_attachment_repository.py features/nocobase_sync/client.py tests/test_nocobase_resume_attachment_repository.py tests/test_nocobase_client.py
  git commit -m "feat: add NocoBase resume attachments"
  ```

### Task 4: 远端简历聚合服务与公开投递

**Files:**
- Create: `features/nocobase_sync/remote_resume_service.py`
- Create: `tests/test_nocobase_remote_resume_service.py`
- Modify: `features/resume_documents/schema.json`
- Modify: `features/resume_documents/README.md`

**Interfaces:**
- Consumes: `ResumeRepository`, `ResumeAttachmentRepository`, existing resume field validation/file-type helpers.
- Produces: `RemoteResumeService.list`, `list_all`, `get`, `create`, `update`, `create_public`, `read_attachment`, `pending`, `delete_preview`, and private snapshot/compensation helpers; raises `RemoteResumeConsistencyError` with a diagnostic ID when restoration is incomplete.

- [ ] **Step 1: Write failing aggregate-service tests**

  Test normal CRUD, SHA-256 calculation, duplicate hash rejection before create, 50 MB/type rejection, public-field allow-listing, forced creator “公开投递”, client-forged ID/status/source/recognition/link fields ignored, update snapshot restoration, create compensation, and unknown-outcome stable-key lookup. Include the Review Focus case where a timed-out create is found by `source_id` and cleaned up without a duplicate create.

- [ ] **Step 2: Verify failure**

  Run: `python -m unittest tests.test_nocobase_remote_resume_service`

  Expected: FAIL with missing service.

- [ ] **Step 3: Implement the service**

  Generate archive/source IDs server-side using the existing archive rule; validate the complete payload before the first remote mutation. Create the main record before its attachment; on any later error delete only objects created by this request. Preserve the last valid recognition result on ordinary edits and recognition failures.

- [ ] **Step 4: Verify pass**

  Run: `python -m unittest tests.test_nocobase_remote_resume_service`

  Expected: PASS and fake request logs show no duplicate create after an ambiguous timeout.

- [ ] **Step 5: Commit**

  ```powershell
  git add features/nocobase_sync/remote_resume_service.py features/resume_documents/schema.json features/resume_documents/README.md tests/test_nocobase_remote_resume_service.py
  git commit -m "feat: add remote resume aggregate service"
  ```

### Task 5: Dify 识别与远端识别结果状态机

**Files:**
- Modify: `features/nocobase_sync/remote_resume_service.py`
- Modify: `features/resume_documents/dify_mapping.py`
- Create: `features/nocobase_sync/recognition_service.py`
- Create: `tests/test_nocobase_recognition_service.py`
- Modify: `tests/test_dify_mapping.py`

**Interfaces:**
- Consumes: `RemoteResumeService.get/read_attachment`, `dify_client.recognize`, and `dify_mapping.to_candidate_payload`.
- Produces: `RecognitionService.recognize(resume_id: int) -> dict`; `RecognitionService.result(resume_id: int) -> dict | None`; sanitized JSON stored in `recognition_result`.

- [ ] **Step 1: Write failing recognition tests**

  Cover allowed source statuses (“待识别”/“失败”), single-task lock, remote attachment download, Dify mapping, status transition to “已识别”, failure transition to “失败”, preservation of prior valid result, malformed JSON, and optimistic comparison of `updatedAt` plus key fields. Assert a concurrent edit prevents result overwrite.

- [ ] **Step 2: Verify failure**

  Run: `python -m unittest tests.test_nocobase_recognition_service tests.test_dify_mapping`

  Expected: FAIL with missing recognition service.

- [ ] **Step 3: Implement the recognition state machine**

  Serialize the full mapped payload with `ensure_ascii=False`; do not log it. Re-read the resume immediately before update and compare the captured snapshot. Return a refresh-required conflict if it changed.

- [ ] **Step 4: Verify pass**

  Run: `python -m unittest tests.test_nocobase_recognition_service tests.test_dify_mapping`

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```powershell
  git add features/nocobase_sync/remote_resume_service.py features/nocobase_sync/recognition_service.py features/resume_documents/dify_mapping.py tests/test_nocobase_recognition_service.py tests/test_dify_mapping.py
  git commit -m "feat: persist Dify recognition in NocoBase"
  ```

### Task 6: 识别结果入库与双向删除规则

**Files:**
- Modify: `features/nocobase_sync/remote_candidate_service.py`
- Modify: `features/nocobase_sync/remote_resume_service.py`
- Create: `features/nocobase_sync/resume_candidate_service.py`
- Create: `tests/test_nocobase_resume_candidate_service.py`
- Modify: `tests/test_nocobase_remote_candidate_service.py`

**Interfaces:**
- Consumes: validated recognition JSON, `RemoteCandidateService`, `ResumeRepository.find_by_linked_candidate`, and both attachment repositories.
- Produces: `RemoteCandidateService.find_by_phone(phone: str) -> dict | None`; `ResumeCandidateService.import_candidate(resume_id) -> ImportResult`; `delete_resumes(ids, expected) -> int`; `delete_candidates(ids, expected) -> int` with resume unlink/reset behavior.

- [ ] **Step 1: Write failing idempotency and cascade tests**

  Cover prechecks on `linked_candidate`, phone, archive number, `source_id`, and `file_hash`; already-linked idempotent return; candidate aggregate creation then resume link; rollback if link/status update fails; delete preview contents; resume cascade order; candidate-direct-delete unlink/status reset; unreferenced attachment cleanup. Include the Review Focus tests for two resumes linked to one candidate and for compensation failure returning only a diagnostic ID.

- [ ] **Step 2: Verify failure**

  Run: `python -m unittest tests.test_nocobase_resume_candidate_service tests.test_nocobase_remote_candidate_service`

  Expected: FAIL with missing orchestration behavior.

- [ ] **Step 3: Implement orchestration and compensation**

  `ImportResult` contains `candidate_id` and `already_imported`. Re-read all stable keys immediately before writes. For direct candidate deletion, snapshot linked resumes, clear links/set “已识别”, delete candidate, and restore resume snapshots if candidate deletion fails. For resume cascade, block multiple links before any mutation and stop on the first uncompensated error.

- [ ] **Step 4: Verify pass**

  Run: `python -m unittest tests.test_nocobase_resume_candidate_service tests.test_nocobase_remote_candidate_service`

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```powershell
  git add features/nocobase_sync/remote_candidate_service.py features/nocobase_sync/remote_resume_service.py features/nocobase_sync/resume_candidate_service.py tests/test_nocobase_resume_candidate_service.py tests/test_nocobase_remote_candidate_service.py
  git commit -m "feat: link remote resumes and candidates"
  ```

### Task 7: 简历 HTTP 适配器与统一服务装配

**Files:**
- Create: `features/nocobase_sync/resume_http_adapter.py`
- Modify: `features/nocobase_sync/http_adapter.py`
- Modify: `server.py`
- Create: `tests/test_nocobase_resume_http_adapter.py`
- Modify: `tests/test_nocobase_http_adapter.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: the unified preflight report from Task 1 and services from Tasks 4–6.
- Produces: `RemoteServices(candidates, resumes, recognition, resume_candidates)`; `build_remote_services(data_dir: Path) -> RemoteServices | None`; `handle_remote_resume_request(handler, method, identifier, query) -> bool`; all `/api/resume_documents*`, `/api/public/resumes/*`, recognition/result/import/pending/export/QR/attachment routes handled without SQLite when unified backend is NocoBase.

- [ ] **Step 1: Write failing HTTP contract tests**

  Cover list/page/get/create/update/delete, batch delete preview, public submission, pending, recognize, recognition result, candidate import, CSV/XLSX export, QR, and attachment download. Assert the existing response shapes remain stable, public oversized/forged input is rejected, NocoBase errors map to sanitized 4xx/5xx, and no handler falls through to generic SQLite CRUD in remote mode.

- [ ] **Step 2: Verify failure**

  Run: `python -m unittest tests.test_nocobase_resume_http_adapter tests.test_nocobase_http_adapter tests.test_server`

  Expected: FAIL because resume routes still use SQLite and the server only attaches `candidate_service`.

- [ ] **Step 3: Implement adapters and startup wiring**

  Build one client, one preflight report, and one `RemoteServices` object at startup. Route remote candidate and resume requests before opening SQLite transactions. If selected remote startup validation fails, abort startup; never construct a SQLite fallback service.

- [ ] **Step 4: Verify pass**

  Run: `python -m unittest tests.test_nocobase_resume_http_adapter tests.test_nocobase_http_adapter tests.test_server`

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```powershell
  git add features/nocobase_sync/resume_http_adapter.py features/nocobase_sync/http_adapter.py server.py tests/test_nocobase_resume_http_adapter.py tests/test_nocobase_http_adapter.py tests/test_server.py
  git commit -m "feat: route resumes through NocoBase"
  ```

### Task 8: SQLite 业务表的远端人才引用

**Files:**
- Create: `features/nocobase_sync/candidate_reference.py`
- Modify: `features/applications/schema.json`
- Modify: `features/interviews/schema.json`
- Modify: `features/employees/schema.json`
- Modify: `features/applications/service.py`
- Modify: `features/interviews/service.py`
- Modify: `server.py`
- Modify: `web/app.js`
- Create: `tests/test_remote_candidate_references.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_features.py`

**Interfaces:**
- Consumes: `RemoteCandidateService.get/find_by_phone` and local SQLite connections.
- Produces: `RemoteCandidateReference.exists(id)`, `label(id)`, `find_by_phone(phone)`, `profile(id)`; schema marker `remoteRef: "candidates"`; database upgrader that rebuilds affected tables without local `candidates(id)` foreign keys.

- [ ] **Step 1: Write failing reference and upgrade tests**

  Create temporary legacy databases containing application/interview/employee rows. Test lossless table rebuild, remote IDs larger than local ranges, label/profile lookup, phone match, create/update validation, NocoBase outage failure, and absence of local candidate queries in remote mode. Test public application compensation when remote candidate creation succeeds but local insert fails.

- [ ] **Step 2: Verify failure**

  Run: `python -m unittest tests.test_remote_candidate_references tests.test_server tests.test_features`

  Expected: FAIL because refs and foreign keys still target the local candidates table.

- [ ] **Step 3: Implement remote reference support**

  Replace `ref` with `remoteRef` only for the three affected `candidate_id` fields; teach validation and display code to resolve it through the remote service. Rebuild only tables whose SQL contains the legacy candidate FK, preserving IDs, data, indexes, and unrelated constraints. In SQLite mode retain current local-ref behavior.

- [ ] **Step 4: Verify pass**

  Run: `python -m unittest tests.test_remote_candidate_references tests.test_server tests.test_features`

  Expected: PASS in both SQLite and fake-NocoBase modes.

- [ ] **Step 5: Commit**

  ```powershell
  git add features/nocobase_sync/candidate_reference.py features/applications/schema.json features/interviews/schema.json features/employees/schema.json features/applications/service.py features/interviews/service.py server.py web/app.js tests/test_remote_candidate_references.py tests/test_server.py tests/test_features.py
  git commit -m "feat: use remote candidate references"
  ```

### Task 9: 混合总览、导入导出与无回退保证

**Files:**
- Modify: `server.py`
- Modify: `features/nocobase_sync/http_adapter.py`
- Modify: `features/nocobase_sync/resume_http_adapter.py`
- Create: `tests/test_nocobase_mixed_dashboard.py`
- Modify: `tests/test_nocobase_http_adapter.py`

**Interfaces:**
- Consumes: remote paged counts/lists plus local SQLite module counts.
- Produces: unchanged dashboard response shape whose resume/talent slices come from NocoBase; full-batch validation before remote imports; compensating batch create semantics.

- [ ] **Step 1: Write failing mixed-source tests**

  Test dashboard totals/status/recent rows, recruitment-type grouping, resume/candidate import all-or-nothing compensation, export/QR read-only behavior, and remote outage propagation. Explicitly assert SQLite resume/candidate rows are neither read nor written when remote mode is selected.

- [ ] **Step 2: Verify failure**

  Run: `python -m unittest tests.test_nocobase_mixed_dashboard tests.test_nocobase_http_adapter`

  Expected: FAIL because dashboard aggregation and some generic utilities still query local tables.

- [ ] **Step 3: Implement mixed aggregation and batch guards**

  Fetch remote sections before entering the local read transaction; merge only count/result objects, never mirror records into SQLite. Validate the complete import file and all duplicate keys before the first create.

- [ ] **Step 4: Verify pass**

  Run: `python -m unittest tests.test_nocobase_mixed_dashboard tests.test_nocobase_http_adapter`

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```powershell
  git add server.py features/nocobase_sync/http_adapter.py features/nocobase_sync/resume_http_adapter.py tests/test_nocobase_mixed_dashboard.py tests/test_nocobase_http_adapter.py
  git commit -m "feat: combine remote recruitment dashboard data"
  ```

### Task 10: 迁移只读检查、冲突报告与摘要

**Files:**
- Create: `features/nocobase_sync/migration_models.py`
- Create: `features/nocobase_sync/migration_inventory.py`
- Create: `features/nocobase_sync/migration_reports.py`
- Create: `tests/test_nocobase_migration_inventory.py`
- Create: `tests/test_nocobase_migration_reports.py`

**Interfaces:**
- Consumes: read-only SQLite path, candidate/resume repositories, relationship repositories, and preflight report.
- Produces: `build_inventory(sqlite_path, services) -> MigrationInventory`; `check_migration(...) -> MigrationReport`; `save_report(data_dir, report) -> Path`; canonical SHA-256 digests for source rows, attachments, references, and target inventory.

- [ ] **Step 1: Write failing inventory/report tests**

  Use temporary SQLite and fake paged NocoBase data. Cover every source table and relation count, attachment hash recomputation, missing/corrupt attachment, duplicate/conflict detection on all four keys, remote duplicates, pagination, schema/permission failure, report expiry metadata, and deterministic digests. Assert fake clients receive no mutation call.

- [ ] **Step 2: Verify failure**

  Run: `python -m unittest tests.test_nocobase_migration_inventory tests.test_nocobase_migration_reports`

  Expected: FAIL with missing migration modules.

- [ ] **Step 3: Implement canonical inventory and redacted reports**

  Open SQLite with URI `mode=ro`; reports contain local record IDs, archive numbers, counts, digest values, and conflict types only. Hash canonical sorted source row values in memory so any business-field change invalidates the digest, but write only the digest—not the personal values—to the report. Mark `eligible=false` for any conflict, invalid row, missing attachment, preflight failure, or duplicate.

- [ ] **Step 4: Verify pass and secret scan**

  Run: `python -m unittest tests.test_nocobase_migration_inventory tests.test_nocobase_migration_reports`

  Expected: PASS; generated JSON/text fixtures do not contain test API keys, names, phones, emails, file bytes, or Authorization.

- [ ] **Step 5: Commit**

  ```powershell
  git add features/nocobase_sync/migration_models.py features/nocobase_sync/migration_inventory.py features/nocobase_sync/migration_reports.py tests/test_nocobase_migration_inventory.py tests/test_nocobase_migration_reports.py
  git commit -m "feat: add read-only NocoBase migration checks"
  ```

### Task 11: 可恢复迁移执行器与自动报告选择

**Files:**
- Create: `features/nocobase_sync/migration_apply.py`
- Create: `features/nocobase_sync/migration_cli.py`
- Create: `tests/test_nocobase_migration_apply.py`
- Create: `tests/test_nocobase_migration_cli.py`

**Interfaces:**
- Consumes: Task 10 reports/digests and remote services.
- Produces: `select_latest_eligible_report(data_dir, now) -> MigrationReport`; `apply_migration(sqlite_path, services, report, journal_path) -> MigrationResult`; CLI commands `check` and `apply`.

- [ ] **Step 1: Write failing execution tests**

  Cover latest-report selection, 24-hour expiry, source/target revalidation before writes, exact six-stage order from the spec, local-to-remote ID map, relation/attachment migration, resume links, SQLite business-reference update, final remote verification, journal contents, reverse-order cleanup, and no backend-selector write. Include Review Focus tests for changed digests and cleanup failure with sanitized diagnostics.

- [ ] **Step 2: Verify failure**

  Run: `python -m unittest tests.test_nocobase_migration_apply tests.test_nocobase_migration_cli`

  Expected: FAIL with missing executor/CLI.

- [ ] **Step 3: Implement journaled execution**

  Write the journal atomically after each created remote numeric ID and each migrated local reference, never personal data. On failure, delete only IDs recorded as created by this run, in reverse dependency order; do not touch pre-existing remote objects. Apply SQLite reference changes in one local transaction after remote objects and links exist, and rollback that transaction if final verification fails.

- [ ] **Step 4: Verify pass**

  Run: `python -m unittest tests.test_nocobase_migration_apply tests.test_nocobase_migration_cli`

  Expected: PASS; no test uses network or the workspace `data` directory.

- [ ] **Step 5: Commit**

  ```powershell
  git add features/nocobase_sync/migration_apply.py features/nocobase_sync/migration_cli.py tests/test_nocobase_migration_apply.py tests/test_nocobase_migration_cli.py
  git commit -m "feat: add guarded NocoBase migration executor"
  ```

### Task 12: 运维入口、部署文档与安全回归

**Files:**
- Create: `检查NocoBase迁移.bat`
- Create: `执行NocoBase迁移.bat`
- Create: `启用NocoBase简历与人才库.bat`
- Modify: `启用NocoBase人才库.bat`
- Modify: `停用NocoBase人才库.bat`
- Modify: `检查NocoBase连接.bat`
- Modify: `README.md`
- Create: `NocoBase统一切换说明.md`
- Modify: `tests/test_nocobase_launchers.py`
- Create: `tests/test_nocobase_security.py`

**Interfaces:**
- Consumes: `features.nocobase_sync.configure` and `features.nocobase_sync.migration_cli`.
- Produces: relocatable operator commands for check/apply/enable/disable and a fixed-IP deployment runbook.

- [ ] **Step 1: Write failing launcher, documentation, and redaction tests**

  Require `%~dp0` relocatability, no embedded URL/key, separate check/apply/enable commands, no automatic enable from apply, service-stop/full-data-backup/DPAPI reconfiguration instructions, and the exact ten-step deployment order. Feed fake secrets and PII through every diagnostic/report error path and assert they are absent.

- [ ] **Step 2: Verify failure**

  Run: `python -m unittest tests.test_nocobase_launchers tests.test_nocobase_security`

  Expected: FAIL because the migration launchers and unified runbook do not exist.

- [ ] **Step 3: Add launchers and operator documentation**

  Batch files call `python -m ...` from `%~dp0`, propagate nonzero exit codes, and pause only when launched interactively. Mark the old candidate-only enable launcher as deprecated and delegate it to the unified enable command so a half-switch cannot be created.

- [ ] **Step 4: Run complete verification without external services**

  Run: `python -m unittest discover -s tests -p 'test_*.py'`

  Expected: all Python tests PASS and test fakes confirm zero calls to `cloud.njncc.com`.

  Run: `node --check web/app.js` and `node --check web/features/resume_documents.js` and `node --check web/features/candidates.js`

  Expected: all commands exit 0.

- [ ] **Step 5: Inspect repository changes and commit**

  Run: `git status --short` and `git diff --check`

  Expected: only planned files changed; `git diff --check` exits 0; no `data`, logs, credentials, migration reports, or journals are staged.

  ```powershell
  git add 检查NocoBase迁移.bat 执行NocoBase迁移.bat 启用NocoBase简历与人才库.bat 启用NocoBase人才库.bat 停用NocoBase人才库.bat 检查NocoBase连接.bat README.md NocoBase统一切换说明.md tests/test_nocobase_launchers.py tests/test_nocobase_security.py
  git commit -m "docs: add unified NocoBase cutover workflow"
  ```

### Task 13: 最终回归、设计电脑安全检查与交付审查

**Files:**
- Modify only if tests expose a defect in files already named above.
- Verify: all source, tests, docs, and launchers from Tasks 1–12.

**Interfaces:**
- Consumes: complete implementation.
- Produces: a verified branch that contains executable tooling but has not contacted or mutated real NocoBase/SQLite production data.

- [ ] **Step 1: Run the full automated suite twice**

  Run: `python -m unittest discover -s tests -p 'test_*.py'`

  Expected: PASS on two consecutive runs, proving no order-dependent temporary state.

- [ ] **Step 2: Run static and secret checks**

  Run: `node --check web/app.js`, `node --check web/features/resume_documents.js`, `node --check web/features/candidates.js`, and `git diff --check`.

  Search tracked changes for `Bearer `, the configured host, API-like tokens, Authorization headers in logs, and accidental `data/` additions; expected result is no credential/data leak outside intentional generic code and documentation placeholders.

- [ ] **Step 3: Prove no real operation occurred**

  Verify `git status --short`, selector/config/report/journal timestamps under the isolated worktree, and fake-client counters. Expected: no production selector change, no migration report/journal created in the real `data` directory, and no external HTTP call.

- [ ] **Step 4: Review against the spec**

  Check every design section against tests: unified selector, preflight, resume CRUD, Dify, import/link, both deletion directions, remote references, mixed dashboard, check/apply migration, permissions, security, and deployment. Fix only demonstrated gaps and rerun the owning focused test plus the full suite.

- [ ] **Step 5: Prepare handoff**

  If verification finds a defect, return to the task that owns that file, add a focused regression test, fix it, rerun that task's commit step, and then repeat this final verification. Otherwise create no empty commit. Report the branch/commit, exact test counts, and state clearly that real data migration and enablement remain pending until the fixed-IP data is copied and the operator runs the documented commands.
