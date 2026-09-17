# Task 1 修复后独立复审

## 结论

**CHANGES_REQUESTED**

首次审查指出的三项核心问题已经按预期关闭：等待任务由数据库级唯一索引与原子 UPSERT 去重，持久化时间统一为 UTC 固定格式，`complete`/`fail` 也拒绝已过期租约的 owner。任务指定的 16 项测试和编译检查均通过。

但新增的等待任务唯一索引与 `retry_jobs` 的跨状态流转不兼容；一个正常可达的“旧失败/暂停任务 + 同键新等待任务”状态会令手工重试直接抛出 `IntegrityError`，并使批量重试整体失败。此外，唯一索引使用 `COALESCE(local_id, -1)`，会把未被接口禁止的 `NULL` 与 `-1` 错误视为同一 local_id，造成 API 抛错前已经修改另一任务。两项均应修复后再接受。

## 审查范围

- 完整阅读：`task-1-brief.md`、最新 `task-1-report.md`、首次 `task-1-review.md`。
- 完整审查：`features/nocobase_sync/__init__.py`、`features/nocobase_sync/queue.py`、`tests/test_nocobase_queue.py`。
- 仅创建本复审报告，未修改生产代码或测试代码，未派生子代理。

## 首次问题复核

1. **并发去重：已修复。** `queue.py:50-52` 建立等待任务部分唯一索引，`queue.py:59-69` 与 `82-91` 使用单条 UPSERT；两个并发连接不能再留下两个同键、同操作的等待任务。现有数据库约束测试与线程并发测试均通过。
2. **带时区绝对时间：已修复。** `queue.py:237-248` 将 aware 时间转换为 UTC、将 naive 时间明确解释为 UTC，并统一输出 `YYYY-MM-DDTHH:MM:SSZ`；领取、失败重试、租约判断与 `stats` 因而可安全使用文本排序。跨 `+08:00`/`Z` 的回归测试通过。
3. **过期租约 owner：已修复。** `queue.py:257-262` 增加 `lease_until > now`，与 claim 的 `lease_until <= now` 回收边界一致；到期但未重领和重领后的旧 owner 均被拒绝。
4. **死锁、独立连接与提交边界：未发现新的死锁或内部 commit 问题。** `claim`/`complete`/`fail` 均在独立连接上用 `BEGIN IMMEDIATE` 并在异常时回滚；`enqueue_*` 与 `retry_jobs` 没有提交调用者事务。下述问题属于唯一约束与状态流转/键设计的兼容性缺陷，而非锁等待死锁。

## 发现的问题

### 1. MEDIUM — `retry_jobs` 与等待任务唯一索引冲突，正常状态下会抛异常并中止批量重试

- 文件与行号：`features/nocobase_sync/queue.py:50-52`、`features/nocobase_sync/queue.py:190-208`；缺失回归覆盖位于 `tests/test_nocobase_queue.py:292-307`。
- 原因：失败或暂停任务不受部分唯一索引约束，所以同一 `entity/local_id/operation` 后续可以合法入队一个新等待任务。`retry_jobs` 随后无条件把旧任务更新为 `等待`，立即与新等待任务冲突。批量 `UPDATE` 中任意一行冲突会使整条语句失败，其他本可重试的任务也无法重置。
- 独立探针：先建立 id=1 的失败 upsert，再为同一记录入队 id=2 的等待 upsert，调用 `retry_jobs(conn, [1])`，得到：

```text
before= [(1, 'v1', '失败'), (2, 'v2', '等待')]
retry_error= IntegrityError UNIQUE constraint failed: index 'nocobase_sync_waiting_job_unique'
after= [(1, 'v1', '失败'), (2, 'v2', '等待')]
```

- 影响：管理端“重试选中/全部失败任务”在常见的后续编辑入队场景中会报错；一次冲突还会阻止同批其他无冲突任务重试。
- 最小修复建议：明确“已有同键等待任务时跳过旧失败/暂停任务”的语义，并把更新改成冲突安全的形式（例如 `UPDATE OR IGNORE`，或用 `NOT EXISTS`/分组选择确保每个键最多恢复一行）；返回实际更新数。补充“失败 + 新等待”“暂停 + 新等待”以及同键多个失败任务的选择性和全量重试测试，并确认一个冲突不会阻断其他键。

### 2. MEDIUM — `COALESCE(local_id, -1)` 产生键碰撞，并在抛错前修改错误的任务

- 文件与行号：`features/nocobase_sync/queue.py:50-52`、`features/nocobase_sync/queue.py:55-70`、`features/nocobase_sync/queue.py:265-271`；相关测试仅覆盖正整数 local_id，见 `tests/test_nocobase_queue.py:50-165`。
- 原因：接口和表结构都没有禁止 `local_id IS NULL` 或负整数，但唯一索引把 `NULL` 映射为 `-1`。已有 NULL 任务时入队 local_id=-1 会错误命中该任务并覆盖其 archive/revision；随后 `_waiting_job_id(..., -1, ...)` 找不到被更新但 local_id 仍为 NULL 的行，抛出 `TypeError`。调用方看到失败，但其尚未回滚的事务已经带有错误修改。
- 独立探针输出：

```text
null_id= 1
negative_error= TypeError 'NoneType' object is not subscriptable
rows= [(1, None, 'A-neg', 'v2', '等待')]
```

- 影响：不同 local_id 被错误合并，且异常路径存在意外事务副作用；调用方若捕获异常后继续提交，会持久化被串改的任务。
- 最小修复建议：不要用合法整数作 NULL 哨兵。可分别建立 `local_id IS NOT NULL` 的 `(entity, local_id, operation)` 唯一索引和 `local_id IS NULL` 的 `(entity, operation)` 唯一索引；或者显式验证并拒绝所有非正整数/NULL local_id（需与业务接口契约一致）。补充 NULL、-1 及异常后事务内容不变的测试。

### 3. LOW — `enqueue_delete` 的“不提交调用者事务”仍缺少对称回归测试

- 文件与行号：`tests/test_nocobase_queue.py:60-70`。
- 原因：当前事务回滚测试只覆盖 `enqueue_upsert`，首次审查要求的 delete rollback 防回归用例仍未加入。静态检查显示当前 `enqueue_delete` 没有 commit，因此这是测试缺口，不是当前生产失败。
- 最小修复建议：在已提交表结构后调用 `enqueue_delete`，断言 `conn.in_transaction`，rollback 后确认取消 upsert 与新增 delete 均未落库。

## 验证证据

任务指定测试：

```text
python -m unittest tests.test_nocobase_queue -v
Ran 16 tests in 0.274s
OK
```

编译检查：

```text
python -m py_compile features\nocobase_sync\__init__.py features\nocobase_sync\queue.py tests\test_nocobase_queue.py
```

退出码 0，无输出。

现有 GREEN 证明首次三项缺陷的回归用例通过，但不覆盖上述两个唯一索引交互问题；独立探针可稳定复现二者，因此当前不能批准。
