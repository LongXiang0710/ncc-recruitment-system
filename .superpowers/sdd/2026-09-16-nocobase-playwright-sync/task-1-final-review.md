# Task 1 最终独立复审

## 结论

**CHANGES_REQUESTED**

当前实现已关闭两轮历史审查中的主要问题，Task 1 的 20 项测试、仓库全量 153 项测试和 `py_compile` 均通过；但 `ensure_tables` 的唯一索引迁移仍会在历史重复数据或并发重复初始化时失败，并在失败后永久留下无唯一索引的数据库。另有一个可复现的亚秒租约/重试边界偏差。因此当前版本不能批准。

## 复审范围与验证

- 完整阅读 `task-1-brief.md`、最新 `task-1-report.md`、`task-1-review.md`、`task-1-rereview.md`，以及 `features/nocobase_sync/__init__.py`、`features/nocobase_sync/queue.py`、`tests/test_nocobase_queue.py`。
- 仅写入本报告；未修改生产代码或测试，未派生子代理。
- 指定测试：`python -m unittest tests.test_nocobase_queue -v`，退出码 0，`Ran 20 tests in 0.311s`，`OK`。
- 全量测试：`python -m unittest discover -s tests -v`，退出码 0，`Ran 153 tests in 13.295s`，`OK`。
- 编译检查：`python -m py_compile features\nocobase_sync\__init__.py features\nocobase_sync\queue.py tests\test_nocobase_queue.py`，退出码 0，无输出。

## 历史问题复核

- 并发等待任务去重：当前部分唯一索引与原子 UPSERT 可防止正常 enqueue 并发产生重复任务；现有跨连接和线程测试通过。下述问题 1 是索引自身的迁移/重复初始化缺陷。
- UTC 时间比较：aware 时间会转换为 UTC，naive 时间明确按 UTC 解释，固定秒级格式可安全用于现有文本排序；跨偏移回归测试通过。
- 过期租约 owner：`complete`/`fail` 使用 `lease_until > now`，与 claim 的 `lease_until <= now` 边界互斥；到期未重领及重领后旧 owner 均被拒绝。
- `retry_jobs` 唯一键冲突：已有同键等待任务会跳过旧失败/暂停任务；同键多个失败候选只恢复最新一项，返回实际更新数，相关回归测试通过。
- `local_id`：`None`、布尔值、零和负数均在 SQL 前拒绝，未再复现旧哨兵碰撞和异常前副作用。
- 事务与审计：两个 enqueue API 均由调用方控制提交，delete 的取消和新增可一起回滚；`claim`/`complete`/`fail` 使用独立连接和 `BEGIN IMMEDIATE`，状态更新与最小化审计写入同一事务。未发现新的提交泄漏、死锁或审计字段扩张。

## 问题

### 1. HIGH — 唯一索引迁移不是原子的，旧重复数据或并发初始化会使索引重建失败并永久失去去重约束

- 文件与行号：`features/nocobase_sync/queue.py:20-53`，直接根因为 `features/nocobase_sync/queue.py:50-53`；缺失覆盖见 `tests/test_nocobase_queue.py:133-196`。
- 根因：`ensure_tables` 每次调用都无条件执行 `DROP INDEX`，再以另一条语句执行 `CREATE UNIQUE INDEX`。当调用方尚未开启事务时，这两条 DDL 分别在自动提交状态执行；因此删除索引已经持久化后，创建索引可能因遗留重复行失败，且不会自动恢复旧索引。两条语句之间也存在其他连接可写入重复行的窗口。
- 历史可达性：首次审查确认原始 Task 1 实现没有数据库唯一约束，并可由两个连接留下同键等待任务；因此“旧库已有重复等待任务”不是人为破坏数据库，而是本任务已有版本可以产生的升级状态。
- 独立迁移探针：在当前表结构上删除索引以模拟原始无索引版本，插入两个 `(candidates, 7, upsert, 等待)` 行并提交，再调用 `ensure_tables`。稳定得到：

```text
legacy_duplicate_migration= IntegrityError UNIQUE constraint failed: nocobase_sync_jobs.entity, nocobase_sync_jobs.local_id, nocobase_sync_jobs.operation
legacy_waiting_rows= 2
```

- 独立并发探针：从一个索引正确的数据库开始，在第二次 `ensure_tables` 已完成 `DROP INDEX`、尚未执行 `CREATE UNIQUE INDEX` 时，让另一连接提交两个同键等待任务。稳定得到：

```text
concurrent_repeat_errors= [('IntegrityError', 'UNIQUE constraint failed: nocobase_sync_jobs.entity, nocobase_sync_jobs.local_id, nocobase_sync_jobs.operation')]
concurrent_repeat_duplicates= 2 index_count= 0
```

- 对照结果：干净数据库串行调用两次 `ensure_tables` 得到 `clean_repeat_index_count= 1`，说明问题不是普通重复调用，而是迁移数据与并发边界。
- 影响：升级/初始化会报错；更严重的是失败后数据库已经没有 `nocobase_sync_waiting_job_unique`，后续 enqueue 可再次产生重复等待任务，破坏任务合并和单次同步保证。
- 修复要求：索引定义迁移必须在一个原子写事务或等效迁移机制中完成，并在创建约束前以明确、可测试的规则归并历史重复等待任务；失败必须保留原约束或完整回滚。新增“原始无索引库含重复行升级”“重复初始化并发写入”和“迁移失败后索引仍存在/事务回滚”的回归测试。不能只捕获 `IntegrityError`，因为那会保留无约束状态。

### 2. LOW — 秒级格式在运算后截断微秒，使五分钟租约和声明的重试延迟最多提前近一秒到期

- 文件与行号：`features/nocobase_sync/queue.py:96-100`、`features/nocobase_sync/queue.py:170-172`、`features/nocobase_sync/queue.py:254-265`；现有边界测试使用整秒输入，见 `tests/test_nocobase_queue.py:198-220`、`tests/test_nocobase_queue.py:272-304`。
- 根因：`claim` 和 `fail` 先在保留微秒的输入时间上加五分钟/重试秒数，随后 `_timestamp` 以 `replace(microsecond=0)` 向下截断结果。API 明确接受 `datetime` 或 `fromisoformat` 可解析的带小数秒字符串，因此这不是不可达输入。
- 独立探针：在 `2026-09-16T10:00:00.999999Z` 领取任务，结果为：

```text
stored_lease_until= 2026-09-16T10:05:00Z
effective_lease_seconds= 299.000001
reclaim_before_exact_five_minutes= True
```

- 影响：另一 worker 可以在承诺的五分钟尚差约一秒时回收任务；失败重试同样可早于 `RETRY_DELAYS` 指定秒数。当前 `complete`/`claim` 的互斥比较仍避免同一存储时间点上的双 owner，但实际租约时长不满足五分钟契约。
- 修复要求：统一定义并实现亚秒输入策略，使 deadline 不早于输入绝对时间加声明时长；同时保持可按文本正确排序的固定宽度 UTC 表示。补充微秒输入下 claim/reclaim、complete 和 60 秒重试的边界测试。

## 最终判断

API 主路径、重试选择、审计最小化、事务回滚和整秒租约边界均已有良好覆盖；问题 1 仍会直接破坏数据库级去重保障，必须修复并用旧库升级与并发初始化测试验证后，Task 1 才可改为 `APPROVED`。
