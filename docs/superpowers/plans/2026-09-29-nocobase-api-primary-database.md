# NocoBase API Primary Database Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立安全、可测试的 NocoBase API 基础层和招聘人才库主表仓库，为后续取代 SQLite 做准备。

**Architecture:** 使用 DPAPI 加密的本机配置、与业务无关的 HTTP JSON 客户端、显式字段映射和人才仓库四层结构。第一阶段不切换现有 HTTP 路由，避免关联表未完成时损坏人才数据。

**Tech Stack:** Python 3，标准库 `urllib.request`，Windows DPAPI，`unittest`

**Spec:** `docs/superpowers/specs/2026-09-29-nocobase-api-primary-database-design.md`

## Global Constraints

- API Key 不得出现在前端、日志、Git 或异常文本中。
- 真实 NocoBase 只用于用户手工验收；自动化测试不得访问它。
- 禁止在关联表完成前默认切换现有人才库路由。
- 不修改或覆盖主工作区未提交的 5 个文件。

## Review Focus

- URL 包含 `/api/` 或尾部斜杠时，不能重复生成 `/api/api/`。
- API Key 错误时，异常和日志不能包含 Key 或 Authorization 头。
- `update`/`destroy` 必须只发 `filterByTk`，不发空 `filter`。
- NocoBase 返回非 JSON、缺失 `data` 或 HTTP 错误时，不得将其当作成功。
- 校园/社会招聘渠道字段分流必须符合已确认的 NocoBase 字段。

---

### Task 1: API Key 配置

**Files:**
- Modify: `features/nocobase_sync/config.py`
- Modify: `features/nocobase_sync/configure.py`
- Test: `tests/test_nocobase_config.py`

**Interfaces:**
- Produces: `NocoBaseConfig(url: str, api_key: str, enabled: bool)`
- Produces: `save(data_dir, url, api_key, enabled=True, protect=None)` and `load(data_dir, unprotect=None)`

- [ ] **Step 1: Write failing tests for encrypted API Key round-trip, old-format rejection, URL normalization and secret-safe errors.**
- [ ] **Step 2: Run `python -m unittest tests.test_nocobase_config -v` and verify failures are caused by the old username/password contract.**
- [ ] **Step 3: Implement the new versioned configuration and update the interactive command to request a hidden API Key.**
- [ ] **Step 4: Run `python -m unittest tests.test_nocobase_config -v` and verify it passes.**
- [ ] **Step 5: Commit the task.**

### Task 2: NocoBase HTTP JSON 客户端

**Files:**
- Create: `features/nocobase_sync/client.py`
- Create: `tests/test_nocobase_client.py`

**Interfaces:**
- Consumes: `NocoBaseConfig`
- Produces: `NocoBaseClient.request(action, *, method="GET", params=None, body=None) -> object`
- Produces: `NocoBaseError(kind, status, endpoint, diagnostic_id)`

- [ ] **Step 1: Write a local fake-server test covering Bearer headers, `/api/` URL joining, JSON bodies and omitted empty query parameters.**
- [ ] **Step 2: Run the focused test and verify it fails because the client module does not exist.**
- [ ] **Step 3: Implement the minimal standard-library client with status classification and redacted errors.**
- [ ] **Step 4: Add and pass tests for 401, 403, validation error, 5xx, timeout, invalid JSON and missing `data`.**
- [ ] **Step 5: Commit the task.**

### Task 3: 人才主表字段映射

**Files:**
- Create: `features/nocobase_sync/candidate_mapping.py`
- Create: `tests/test_nocobase_candidate_mapping.py`

**Interfaces:**
- Produces: `to_nocobase(local: dict) -> dict`
- Produces: `from_nocobase(remote: dict) -> dict`

- [ ] **Step 1: Write failing mapping tests for all confirmed fields, unknown-field exclusion, system-field exclusion and recruitment-channel branching.**
- [ ] **Step 2: Run the focused test and verify the module is missing.**
- [ ] **Step 3: Implement explicit forward and reverse maps plus channel branching.**
- [ ] **Step 4: Run the focused mapping tests and verify they pass.**
- [ ] **Step 5: Commit the task.**

### Task 4: 招聘人才库主表仓库

**Files:**
- Create: `features/nocobase_sync/candidate_repository.py`
- Create: `tests/test_nocobase_candidate_repository.py`

**Interfaces:**
- Consumes: `NocoBaseClient`, `candidate_mapping`
- Produces: `list(page=1, page_size=20, query="") -> list[dict]`
- Produces: `get(identifier: int) -> dict | None`
- Produces: `create(values: dict) -> int`
- Produces: `update(identifier: int, values: dict) -> None`
- Produces: `delete(identifier: int) -> bool`

- [ ] **Step 1: Write failing repository tests that assert exact endpoints, methods, bodies and `filterByTk` parameters.**
- [ ] **Step 2: Run the focused test and verify the repository module is missing.**
- [ ] **Step 3: Implement CRUD with response-shape validation and no empty `filter`.**
- [ ] **Step 4: Run repository tests and verify all CRUD cases pass.**
- [ ] **Step 5: Commit the task.**

### Task 5: 配置说明与回归验证

**Files:**
- Modify: `README.md`
- Modify: `配置NocoBase.bat`
- Test: `tests/test_nocobase_config.py`

**Interfaces:**
- Consumes: Tasks 1–4 public interfaces
- Produces: 可重复的本机配置流程和第二阶段接入边界

- [ ] **Step 1: Add a failing documentation/launcher assertion for the API Key workflow and no-Playwright wording.**
- [ ] **Step 2: Update the README and configuration prompts without including a real secret.**
- [ ] **Step 3: Run all NocoBase focused tests.**
- [ ] **Step 4: Run `python -m unittest discover -s tests -p 'test_*.py'` and verify the full suite passes.**
- [ ] **Step 5: Review `git diff` for secrets and unrelated changes, then commit.**
