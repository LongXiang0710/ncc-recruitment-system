# Task 1 — 持久化同步队列、任务合并和租约

## 状态

COMPLETE。未初始化 Git、未创建提交，也未执行任何 NocoBase 网络调用或远端写入。

## 实现摘要

- 新增本地 SQLite 队列模块，仅允许 `resume_documents` 与 `candidates`。
- 建立隐私安全的任务表和审计表；审计行只包含实体、档案编号、操作、结果、诊断编号和时间。
- `enqueue_upsert` 合并等待的同记录任务；`enqueue_delete` 取消等待 upsert，并保留首个删除任务的档案编号快照。
- `claim` 通过独立连接和 `BEGIN IMMEDIATE` 原子租约任务五分钟，支持到期租约回收。
- `complete`/`fail` 要求当前租约所有者匹配；失败按 `60, 300, 900, 1800, 3600` 秒递进重试，结构性失败可暂停。
- `retry_jobs` 仅重置失败或暂停任务；`stats` 提供所有已知状态计数和最近成功完成时间。

## TDD 记录

### RED

命令：

```text
python -m unittest tests.test_nocobase_queue -v
```

输出（实现前）：

```text
test_nocobase_queue (unittest.loader._FailedTest.test_nocobase_queue) ... ERROR

======================================================================
ERROR: test_nocobase_queue (unittest.loader._FailedTest.test_nocobase_queue)
----------------------------------------------------------------------
ImportError: Failed to import test module: test_nocobase_queue
Traceback (most recent call last):
  File "D:\����Ŀ¼\�ϻ�����Ƹϵͳ\tests\test_nocobase_queue.py", line 6, in <module>
    from features.nocobase_sync import queue
ModuleNotFoundError: No module named 'features.nocobase_sync'

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (errors=1)
```

该失败符合预期：目标模块尚未创建。

### GREEN

命令：

```text
python -m unittest tests.test_nocobase_queue -v
```

最终输出：

```text
test_delete_cancels_waiting_upsert (tests.test_nocobase_queue.QueueTests.test_delete_cancels_waiting_upsert) ... ok
test_enqueue_keeps_the_callers_transaction_open (tests.test_nocobase_queue.QueueTests.test_enqueue_keeps_the_callers_transaction_open) ... ok
test_expired_processing_job_can_be_claimed_again (tests.test_nocobase_queue.QueueTests.test_expired_processing_job_can_be_claimed_again) ... ok
test_fail_uses_progressive_retry_delays_and_pauses_structural_failures (tests.test_nocobase_queue.QueueTests.test_fail_uses_progressive_retry_delays_and_pauses_structural_failures) ... ok
test_invalid_entity_or_blank_archive_number_is_rejected (tests.test_nocobase_queue.QueueTests.test_invalid_entity_or_blank_archive_number_is_rejected) ... ok
test_latest_upsert_replaces_waiting_revision (tests.test_nocobase_queue.QueueTests.test_latest_upsert_replaces_waiting_revision) ... ok
test_non_expired_processing_job_cannot_be_stolen (tests.test_nocobase_queue.QueueTests.test_non_expired_processing_job_cannot_be_stolen) ... ok
test_repeated_delete_refreshes_revision_but_preserves_original_archive_snapshot (tests.test_nocobase_queue.QueueTests.test_repeated_delete_refreshes_revision_but_preserves_original_archive_snapshot) ... ok
test_retry_selection_only_requeues_failed_or_paused_jobs (tests.test_nocobase_queue.QueueTests.test_retry_selection_only_requeues_failed_or_paused_jobs) ... ok
test_stale_owner_cannot_complete_or_fail_a_reclaimed_lease (tests.test_nocobase_queue.QueueTests.test_stale_owner_cannot_complete_or_fail_a_reclaimed_lease) ... ok
test_stats_includes_every_status_and_last_success_and_audit_is_minimized (tests.test_nocobase_queue.QueueTests.test_stats_includes_every_status_and_last_success_and_audit_is_minimized) ... ok
test_tables_have_only_the_queue_and_privacy_safe_audit_columns (tests.test_nocobase_queue.QueueTests.test_tables_have_only_the_queue_and_privacy_safe_audit_columns) ... ok

----------------------------------------------------------------------
Ran 12 tests in 0.175s

OK
```

另行执行：

```text
python -m py_compile features\nocobase_sync\__init__.py features\nocobase_sync\queue.py tests\test_nocobase_queue.py
```

输出为空，退出码为 0。

## 修改文件

- `features/nocobase_sync/__init__.py`
- `features/nocobase_sync/queue.py`
- `tests/test_nocobase_queue.py`
- `.superpowers/sdd/2026-09-16-nocobase-playwright-sync/task-1-report.md`

## 自审

- 测试覆盖：表字段及审计最小化、实体和档案编号验证、同事务入队、upsert 合并、删除优先与档案快照、租约回收、未到期不可抢占、陈旧所有者拒绝、重试延迟、暂停、选择性重试和统计。
- 所有 SQL 都使用参数绑定；失败详情只保留阶段、错误类型、诊断编号和暂停标志，不存储个人信息或附件内容。
- `enqueue_*` 与 `retry_jobs` 均不调用 `commit`，因此可由业务写入的 SQLite 事务一并提交或回滚。

## 关注点

- 本任务仅实现本地队列，不包含业务路由接入、后台 worker 或任何 NocoBase 写入；这些由后续任务负责。
- `stats` 使用中文状态键（包括内部的“已取消”）及 `last_completed_at`，便于后续 API 层直接映射到状态面板。

## 审查修复轮次（并发、时区与过期租约）

### 修复内容

- `ensure_tables` 新增针对等待任务的部分唯一索引：`(entity, COALESCE(local_id, -1), operation) WHERE status = '等待'`。`enqueue_upsert` 和 `enqueue_delete` 改为单条 SQLite `INSERT … ON CONFLICT DO UPDATE`；upsert 冲突时更新档案编号、版本与更新时间，delete 冲突时只更新版本与时间，因而保留最初的档案号快照。
- 所有持久化与比较时间统一为 UTC 固定宽度 `YYYY-MM-DDTHH:MM:SSZ`。带偏移或 `Z` 的输入先转换为 UTC；无时区输入明确按 UTC 解释。这样 SQLite 的文本比较和 `MAX` 保持绝对时间顺序。
- `complete` 与 `fail` 的所有权判断同时要求 `lease_until > now`，所以租约到期但尚未被其他 worker 领取的旧 owner 也无法完成或失败该任务。
- 新增四项回归测试：数据库跨连接唯一性、并发 upsert、过期 lease owner 的 complete/fail 拒绝，以及跨时区重试/统计。

### RED

命令：

```text
python -m unittest tests.test_nocobase_queue -v
```

实现前输出的关键失败如下（完整运行：`Ran 16 tests in 0.287s`，`FAILED (failures=6, errors=2)`）：

```text
test_concurrent_enqueues_keep_one_waiting_job ... FAIL
  [('upsert', '等待'), ('upsert', '等待')] != [('upsert', '等待')]

test_database_enforces_one_waiting_job_across_independent_connections ... FAIL
  AssertionError: IntegrityError not raised

test_expired_lease_owner_cannot_complete_or_fail_before_reclaim ... FAIL
  AssertionError: True is not false

test_retry_due_and_stats_use_absolute_utc_time_across_offsets ... FAIL
  AssertionError: 2 != 1

test_fail_uses_progressive_retry_delays_and_pauses_structural_failures ... FAIL
  expected '2026-09-16T12:51:00Z', got '2026-09-16T12:51:00'

test_stats_includes_every_status_and_last_success_and_audit_is_minimized ... FAIL
  expected '2026-09-16T10:02:00Z', got '2026-09-16T10:02:00'
```

这次首次 RED 运行还暴露了两处 Windows 测试夹具错误：断言失败会跳过显式 `conn.close()`，导致 `tearDown` 删除临时 SQLite 文件时出现 `PermissionError`。已将这两处读取断言放进 `try/finally`，不改变生产行为；之后的 GREEN 运行无错误。

### GREEN

命令：

```text
python -m unittest tests.test_nocobase_queue -v
```

输出：

```text
test_concurrent_enqueues_keep_one_waiting_job ... ok
test_database_enforces_one_waiting_job_across_independent_connections ... ok
test_delete_cancels_waiting_upsert ... ok
test_enqueue_keeps_the_callers_transaction_open ... ok
test_expired_lease_owner_cannot_complete_or_fail_before_reclaim ... ok
test_expired_processing_job_can_be_claimed_again ... ok
test_fail_uses_progressive_retry_delays_and_pauses_structural_failures ... ok
test_invalid_entity_or_blank_archive_number_is_rejected ... ok
test_latest_upsert_replaces_waiting_revision ... ok
test_non_expired_processing_job_cannot_be_stolen ... ok
test_repeated_delete_refreshes_revision_but_preserves_original_archive_snapshot ... ok
test_retry_due_and_stats_use_absolute_utc_time_across_offsets ... ok
test_retry_selection_only_requeues_failed_or_paused_jobs ... ok
test_stale_owner_cannot_complete_or_fail_a_reclaimed_lease ... ok
test_stats_includes_every_status_and_last_success_and_audit_is_minimized ... ok
test_tables_have_only_the_queue_and_privacy_safe_audit_columns ... ok

----------------------------------------------------------------------
Ran 16 tests in 0.300s

OK
```

编译复验：

```text
python -m py_compile features\nocobase_sync\__init__.py features\nocobase_sync\queue.py tests\test_nocobase_queue.py
```

输出为空，退出码 0。

### 本轮自审

- 数据库唯一约束在并发调用时是最终去重屏障；SQLite 的 conflict update 使两个连接不会留下重复等待任务。
- 部分唯一索引包含 `COALESCE(local_id, -1)`，故 `local_id` 为 `NULL` 时也不能绕过等待任务唯一性。
- 领取回收边界使用 `lease_until <= now`，完成/失败有效边界使用 `lease_until > now`，在到期瞬间没有双重有效窗口。
- 本轮未初始化或使用 Git，未访问或写入 NocoBase；仅修改 Task 1 的队列、测试和本报告。

## 第二修复轮次（重试冲突、local_id 校验与 delete 回滚）

### 修复内容

- `retry_jobs` 现在先按 `id DESC` 读取选中的失败/暂停候选，并按 `(entity, local_id, operation)` 分组：已有同键等待任务时跳过旧任务；没有等待任务时，只恢复最新候选。逐条 `UPDATE OR IGNORE` 使并发新增等待任务也不会使整批重试因唯一索引而中止，返回值为实际恢复数量。
- `enqueue_upsert` 与 `enqueue_delete` 现在在所有 SQL 前验证 `local_id` 是非布尔的正整数；`NULL`、负数、零与布尔值均抛出 `ValueError`，不会修改现有任务。
- 等待任务唯一索引不再用 `COALESCE(local_id, -1)`，而是直接使用 `local_id`。接口已拒绝 `NULL` 与非正整数，因此不存在 `NULL` 和合法 key 的哨兵碰撞。
- 新增 delete 入队 rollback 回归测试，确认取消原 upsert 与新增 delete 均随调用方事务回滚。

### RED

命令：

```text
python -m unittest tests.test_nocobase_queue -v
```

输出（实现前）：

```text
test_invalid_local_id_is_rejected_before_it_changes_existing_tasks ... FAIL
  AssertionError: ValueError not raised

test_retry_restores_only_the_newest_selected_failure_for_one_key ... FAIL
  AssertionError: retrying duplicate failed jobs must choose one safely:
  UNIQUE constraint failed: index 'nocobase_sync_waiting_job_unique'

test_retry_skips_old_failures_or_pauses_when_new_waiting_job_exists ... FAIL
  AssertionError: retrying stale jobs must not abort the batch:
  UNIQUE constraint failed: index 'nocobase_sync_waiting_job_unique'

----------------------------------------------------------------------
Ran 20 tests in 0.279s

FAILED (failures=3)
```

`test_delete_enqueue_keeps_the_callers_transaction_open` 在该 RED 运行中已通过，确认这是已有行为的补充回归覆盖，而非需要生产修复的缺陷。

### GREEN

命令：

```text
python -m unittest tests.test_nocobase_queue -v
```

输出：

```text
test_concurrent_enqueues_keep_one_waiting_job ... ok
test_database_enforces_one_waiting_job_across_independent_connections ... ok
test_delete_cancels_waiting_upsert ... ok
test_delete_enqueue_keeps_the_callers_transaction_open ... ok
test_enqueue_keeps_the_callers_transaction_open ... ok
test_expired_lease_owner_cannot_complete_or_fail_before_reclaim ... ok
test_expired_processing_job_can_be_claimed_again ... ok
test_fail_uses_progressive_retry_delays_and_pauses_structural_failures ... ok
test_invalid_entity_or_blank_archive_number_is_rejected ... ok
test_invalid_local_id_is_rejected_before_it_changes_existing_tasks ... ok
test_latest_upsert_replaces_waiting_revision ... ok
test_non_expired_processing_job_cannot_be_stolen ... ok
test_repeated_delete_refreshes_revision_but_preserves_original_archive_snapshot ... ok
test_retry_due_and_stats_use_absolute_utc_time_across_offsets ... ok
test_retry_restores_only_the_newest_selected_failure_for_one_key ... ok
test_retry_selection_only_requeues_failed_or_paused_jobs ... ok
test_retry_skips_old_failures_or_pauses_when_new_waiting_job_exists ... ok
test_stale_owner_cannot_complete_or_fail_a_reclaimed_lease ... ok
test_stats_includes_every_status_and_last_success_and_audit_is_minimized ... ok
test_tables_have_only_the_queue_and_privacy_safe_audit_columns ... ok

----------------------------------------------------------------------
Ran 20 tests in 0.296s

OK
```

### 本轮自审

- 批量重试在一个冲突键被跳过时继续处理其他键；同键多个候选采用最新任务的版本，避免旧 revision 覆盖较新数据。
- local_id 校验位于实体/档案号校验和任何更新语句之前，异常路径没有队列副作用。
- 两个 enqueue 函数都保持调用方事务控制；upsert 和 delete 的 rollback 行为现在都有测试保护。
- 未执行 Git 操作，未连接或写入 NocoBase，未派生子代理；改动仍限 Task 1 的两份源码/测试文件与本报告。

## 第三修复轮次（索引迁移原子性与亚秒租约）

### 修复内容

- `ensure_tables` 现在在调用方没有活动事务时先取得 `BEGIN IMMEDIATE` 写锁；若调用方已有事务，则只使用嵌套 savepoint，不提交调用方事务。表创建、旧索引迁移、历史去重、时间规范化和唯一索引创建均在同一 savepoint 中；任一步失败会回滚 savepoint（自有事务同时回滚），不会留下“索引已删除但新索引未创建”的中间状态。
- 不再每次删除唯一索引。仅在 `sqlite_master` 检测到历史 `COALESCE` 版本的同名索引时，才在原子迁移中删除并重建；正确索引的重复 `ensure_tables` 调用不再执行 DROP。
- 对历史重复等待任务定义确定性清理：按同一 `(entity, local_id, operation)` 保留最大 `id`（最新）为“等待”，把较早任务标记为“已取消”。索引创建前完成该清理。
- 所有持久化时间统一为固定宽度 UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`；迁移时把既有可解析时间规范化到该格式。因而文本排序仍是绝对时间排序，微秒输入的五分钟租约与重试延迟也不会提前到期。
- 新增遗留重复库升级、并发 `ensure_tables`、微秒 lease/reclaim/complete/retry 边界测试，并把既有整秒断言改为固定六位微秒格式。

### RED

命令：

```text
python -m unittest tests.test_nocobase_queue -v
```

输出（实现前）：

```text
test_concurrent_ensure_tables_resolves_legacy_duplicates_and_keeps_index ... FAIL
  [IntegrityError('UNIQUE constraint failed: nocobase_sync_jobs.entity, ...')]

test_ensure_tables_deduplicates_legacy_waiting_jobs_before_creating_index ... FAIL
  legacy duplicates must be resolved before the unique index is created:
  UNIQUE constraint failed: nocobase_sync_jobs.entity, nocobase_sync_jobs.local_id,
  nocobase_sync_jobs.operation

test_subsecond_lease_and_retry_deadlines_do_not_expire_early ... FAIL
  expected '2026-09-16T10:05:00.999999Z', got '2026-09-16T10:05:00Z'

test_fail_uses_progressive_retry_delays_and_pauses_structural_failures ... FAIL
test_retry_due_and_stats_use_absolute_utc_time_across_offsets ... FAIL
test_stats_includes_every_status_and_last_success_and_audit_is_minimized ... FAIL
  existing second-precision values lacked the required '.000000Z' format

----------------------------------------------------------------------
Ran 23 tests in 0.288s

FAILED (failures=6)
```

首次迁移实现后的 GREEN 尝试仍有一个并发初始化失败：两个 deferred savepoint 同时升级写锁时，一侧得到 `OperationalError('database is locked')`。根因是无事务调用未在 schema 写入前串行化。将自有 schema 迁移改为 `BEGIN IMMEDIATE` 后复验通过。

### GREEN

Task 1 命令：

```text
python -m unittest tests.test_nocobase_queue -v
```

结果：`Ran 23 tests in 0.342s`，`OK`。

全量命令：

```text
python -m unittest discover -s tests -v
```

结果：`Ran 156 tests in 12.624s`，`OK`。

编译命令：

```text
python -m py_compile features\nocobase_sync\__init__.py features\nocobase_sync\queue.py tests\test_nocobase_queue.py
```

输出为空，退出码 0。

### 本轮自审

- 重复清理、索引创建与旧 `COALESCE` 索引替换处在同一 savepoint；失败路径回滚而非捕获后继续，避免失去数据库级去重保障。
- 自有迁移事务持有 SQLite 写锁，使并发初始化串行完成；已有调用方事务不会被内部提交。
- 固定六位微秒 UTC 字符串可按字典序正确比较，且 deadline 保留输入微秒，所以在精确五分钟/60 秒前不会被领取或拒绝完成。
- 未使用 Git、NocoBase 或子代理；修改继续限定为 Task 1 的队列实现、测试和本报告。

## 第四修复轮次（历史重复 delete 快照迁移）

### 修复内容

- 在取消历史重复等待任务之前，迁移先按 delete 的业务语义合并每个重复组：将最早等待 delete 的 `archive_no` 写入最大 `id`（最新）的等待 delete；该最新行本身仍保留最新 `revision`、创建/更新时间及状态。随后通用去重规则取消较早行并建立唯一索引。
- 因此旧库重复 upsert 仍采用“保留最新整行”，而重复 delete 的最终等待行同时保留首个档案号快照和最新版本，和正常 `enqueue_delete` 的合并规则一致。
- 该合并仍处于既有 schema savepoint 内，索引迁移、去重和失败回滚的原子性不变。

### RED

命令：

```text
python -m unittest tests.test_nocobase_queue -v
```

输出（实现前）：

```text
test_ensure_tables_merges_legacy_delete_snapshot_with_newest_revision ... FAIL

expected:
  ('ARCHIVE-ORIGINAL', 'v2', '等待')
actual:
  ('ARCHIVE-CHANGED', 'v2', '等待')

----------------------------------------------------------------------
Ran 24 tests in 0.334s

FAILED (failures=1)
```

失败证明旧迁移只保留最大 id 整行，丢失了 delete 首次入队的档案号快照。

### GREEN

Task 1 命令：

```text
python -m unittest tests.test_nocobase_queue -v
```

结果：`Ran 24 tests in 0.319s`，`OK`。

全量命令：

```text
python -m unittest discover -s tests -v
```

结果：`Ran 157 tests in 12.650s`，`OK`。

编译命令：

```text
python -m py_compile features\nocobase_sync\__init__.py features\nocobase_sync\queue.py tests\test_nocobase_queue.py
```

输出为空，退出码 0。

### 本轮自审

- delete 的合并只触及每个重复等待 delete 组的最新行，并从同组最小 id 提取 archive_no；不同实体、local_id 或 operation 不会混合。
- 最新 delete 的 revision 保持不变，较早行仍标记“已取消”，所以最终仅一条等待任务可通过数据库唯一索引。
- 回归测试同时检查迁移后的两行状态、archive/revision 组合和唯一索引存在，保留了迁移原子性的关键证据。
- 未使用 Git、NocoBase 或子代理；改动继续限定为 Task 1 队列、测试和本报告。
