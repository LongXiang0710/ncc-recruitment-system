# Task 1 独立审查

## 结论

**CHANGES_REQUESTED**

任务书指定的 12 个测试全部通过，主要接口、表字段、状态流转和审计最小化也与规格基本一致；但当前实现存在可复现的并发去重失效和时区时间比较错误，可能导致重复同步或到期任务长期无法领取。租约到期后的完成/失败保护也不完整。因此不建议以当前状态接受 Task 1。

## 审查范围与方法

- 完整阅读了 `task-1-brief.md`、`task-1-report.md`、`features/nocobase_sync/__init__.py`、`features/nocobase_sync/queue.py`、`tests/test_nocobase_queue.py`。
- 当前无 Git；按任务要求将三个生产/测试文件全部视为本任务增量。
- 只修改本审查文件；未修改生产代码或测试代码。
- 运行任务书 GREEN 验证命令：

```text
python -m unittest tests.test_nocobase_queue -v
```

结果：退出码 0，`Ran 12 tests in 0.153s`，`OK`。

- RED 阶段属于历史 TDD 证据，当前文件已存在，无法在不修改工作区的前提下独立重放；报告记录的缺模块失败与预期一致。
- 另使用系统临时目录中的 SQLite 文件执行了三个独立边界探针，均已清理。

## A. 规格符合性

已符合的主要项目：

- `ALLOWED_ENTITIES`、`RETRY_DELAYS` 与规格一致。
- 两张表的列集合与任务书一致，审计表未加入额外敏感字段。
- 正常串行路径下，upsert 合并、delete 取消等待 upsert、delete 档案号快照、五分钟租约、到期回收、owner 不匹配拒绝、递进重试、暂停、选择性重试、统计及成功审计均已实现。
- `enqueue_upsert`、`enqueue_delete`、`retry_jobs` 不提交调用者事务；`claim`、`complete`、`fail` 使用独立连接和 `BEGIN IMMEDIATE`。

未达到可接受程度的项目见下列问题。其中并发去重问题直接破坏“合并等待任务/只有一个等待 delete”的行为保证；时间规范化问题破坏失败任务到期重试和过期租约回收。

## B. 代码质量、并发/事务、时间解析、边界与测试

### 1. HIGH — 等待任务的“查询后插入”不是原子的，并发入队会生成重复任务

- 文件与行号：`features/nocobase_sync/queue.py:56-76`、`features/nocobase_sync/queue.py:88-108`；表定义缺少相应唯一约束的位置为 `features/nocobase_sync/queue.py:22-40`。
- 原因：两个连接可以同时执行 `SELECT` 并都观察到“不存在等待任务”，随后依次成功 `INSERT`。调用者事务不能在函数内部安全地再次 `BEGIN IMMEDIATE`，而数据库又没有唯一约束，因此 check-then-insert 无法保证合并语义。
- 独立探针结果：两个真实 SQLite 连接在同一 `entity/local_id` 上并发调用现有 `enqueue_upsert`，输出为 `concurrent_waiting_upserts= 2`、`errors= []`。
- 影响：同一业务版本可能被同步两次；并发 delete 也可能生成多个等待删除任务，后续远端操作次序和审计结果不再可靠。
- 最小修复建议：为等待任务建立数据库级唯一性（例如针对 `status='等待'` 的 `(entity, local_id, operation)` 部分唯一索引），并将查询后插入改为单条原子 UPSERT；delete 的冲突更新只刷新 revision/updated_at，不能覆盖 archive_no 快照。若允许 `local_id=None`，还需拒绝空 local_id 或采用能对 NULL 生效的唯一键设计。新增两个独立连接并发 upsert/delete 的回归测试。

### 2. HIGH — 接受带时区时间却按 ISO 文本字典序比较，等价时刻可被判为未到期

- 文件与行号：`features/nocobase_sync/queue.py:113-124`、`features/nocobase_sync/queue.py:173-187`、`features/nocobase_sync/queue.py:253-260`；同一问题还会影响 `stats` 的文本 `MAX`，见 `features/nocobase_sync/queue.py:233-235`。
- 原因：`datetime.fromisoformat` 明确接受 `Z`/偏移量输入，`_timestamp` 却保留原偏移后直接存为文本；SQLite 的 `<=` 和 `MAX` 是字典序，不是绝对时间比较。不同偏移的 ISO 字符串不能按字典序比较先后。
- 独立探针结果：任务在 `2026-09-16T10:00:00+08:00` 失败并安排 60 秒后重试；使用绝对时间已经更晚的 `2026-09-16T02:02:00+00:00` 领取时，输出 `equivalent_utc_due_claimed= False`。
- 影响：失败任务或过期 processing 任务可能长期无法领取；反向偏移组合也可能提前领取。最近成功时间也可能不是绝对时间上的最新值。
- 最小修复建议：在所有持久化和比较前把 aware datetime 统一转换为 UTC，并输出一种固定宽度格式；同时明确 naive datetime 的语义（统一解释为 UTC/本地时区或直接拒绝），避免在同一库中混用。新增 `Z`、`+00:00`、`+08:00` 表示同一时刻，以及跨偏移先后顺序的重试、租约和 stats 测试。

### 3. MEDIUM — 已过期但尚未被重新领取的 owner 仍能完成或失败任务

- 文件与行号：`features/nocobase_sync/queue.py:145-162`、`features/nocobase_sync/queue.py:171-197`、`features/nocobase_sync/queue.py:269-274`。
- 原因：`_leased_job` 只检查 `status` 和 `lease_owner`，不检查 `lease_until`。函数文档称其处理“currently leased job”，但过期租约仍被视为有效。
- 独立探针结果：worker-a 在 10:00 获得五分钟租约，未发生重新领取，10:06 调用 `complete` 返回 `expired_owner_complete= True`。
- 影响：超时 worker 可与准备回收任务的 worker 竞争并以旧租约提交最终状态；owner 字符串匹配不足以证明租约仍有效。
- 最小修复建议：让 `_leased_job` 接收已规范化的 `now`，并在完成/失败条件中加入 `lease_until > now`（边界规则与 claim 保持一致）。增加“到期但未重领时 complete/fail 都返回 False”测试；现有“被其他 owner 重领后拒绝”测试仍应保留。

### 4. LOW — 现有测试对关键并发与时间边界没有防回归覆盖

- 文件与行号：`tests/test_nocobase_queue.py:49-208`。
- 原因：当前测试仅覆盖串行合并、同一种 naive 时间格式和“已被另一 owner 重领”场景；没有覆盖并发去重、跨时区等价/先后比较、租约到期但未重领，以及 `enqueue_delete` 的调用者事务回滚。
- 最小修复建议：修复前三项后为每个复现路径添加测试；另补一个 delete 入队后 rollback 的断言，以对称覆盖“两个 enqueue API 均不提交”的明确规格。

## 总结

当前 12 个测试的 PASS 是有效证据，但测试集合没有触达上述三个关键边界。至少完成问题 1、2、3 的实现和回归测试后，再重新运行任务书的完整验证命令并更新报告，才适合改为 APPROVED。
