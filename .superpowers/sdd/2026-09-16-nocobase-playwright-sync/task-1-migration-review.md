# Task 1 迁移修复最终独立复审

## 结论

**CHANGES_REQUESTED**

前三轮审查指出的并发去重、UTC 比较、过期 owner、重试冲突、`local_id` 校验、迁移原子性和亚秒截止时间问题均已通过独立复验；Task 1 的 23 项测试、仓库全量 156 项测试和 `py_compile` 也全部通过。

但本轮新增的历史重复行清理对 `delete` 使用了与 `upsert` 相同的“保留最大 id 整行”规则，会丢失首个 delete 的档案号快照。这与任务书及当前正常入队路径的明确语义冲突，可能使升级后的删除任务指向错误的远端档案。因此当前版本仍不应批准。

## 审查范围与验证

- 完整阅读：`task-1-brief.md`、最新 `task-1-report.md`、`task-1-review.md`、`task-1-rereview.md`、`task-1-final-review.md`。
- 完整审查：`features/nocobase_sync/__init__.py`、`features/nocobase_sync/queue.py`、`tests/test_nocobase_queue.py`。
- 仅新增本复审文件；未修改生产代码或测试代码，未派生子代理。
- 指定测试：`python -m unittest tests.test_nocobase_queue -v`，退出码 0，`Ran 23 tests in 0.343s`，`OK`。
- 全量测试：`python -m unittest discover -s tests -v`，退出码 0，`Ran 156 tests in 12.696s`，`OK`。
- 编译检查：`python -m py_compile features\nocobase_sync\__init__.py features\nocobase_sync\queue.py tests\test_nocobase_queue.py`，退出码 0，无输出。
- 使用独立临时 SQLite 数据库做了额外探针；临时文件均已清理。

## 历史问题复核

- **旧库重复等待 upsert 迁移原子性：通过。** 无索引旧库的两条同键等待 upsert 会确定性变为“旧任务已取消、新任务等待”，随后唯一索引存在。探针输出：`legacy_atomic=PASS`。
- **迁移失败后的索引回滚：通过。** 以旧 `COALESCE` 索引和不可解析历史时间触发迁移中途失败，事务回滚后旧唯一索引仍存在。探针输出：`rollback_keeps_index=PASS`。
- **并发 `ensure_tables`：通过。** 四个线程同时升级含重复行的旧库，无异常，最终一条等待任务且恰有一个唯一索引。探针输出：`concurrent_ensure=PASS threads=4 waiting=1 index=1`。
- **微秒租约完整五分钟：通过。** `10:00:00.999999Z` 领取后存储截止时间为 `10:05:00.999999Z`；提前一微秒不可回收，到精确截止点可以回收。探针输出：`microsecond_lease=PASS 2026-09-16T10:05:00.999999Z`。
- **首次审查问题：通过。** 并发 enqueue 最终仅一条等待 upsert；跨 `+08:00`/`Z` 的绝对时间重试正确；到期 owner 的 complete/fail 均被拒绝。
- **第二次审查问题：通过。** 已有同键新等待任务时，旧失败任务的 retry 被安全跳过；非法 `local_id` 在 SQL 前拒绝且无副作用；delete 入队的取消和新增可随调用方 rollback 一起撤销。
- **审计、状态统计、事务边界：未发现新增问题。** 审计表字段仍为最小集合；`enqueue_*`/`retry_jobs` 不提交调用方事务；独立连接的 claim/complete/fail 仍以 `BEGIN IMMEDIATE` 保护状态转换。

## 问题

### 1. MEDIUM — 历史重复 delete 迁移丢失首个档案号快照

- 文件与行号：`features/nocobase_sync/queue.py:324-336`；相关正常语义见 `features/nocobase_sync/queue.py:90-109`；缺失覆盖见 `tests/test_nocobase_queue.py:123-131`、`tests/test_nocobase_queue.py:161-243`。
- 根因：`_cancel_legacy_waiting_duplicates` 对所有 operation 一律保留最大 `id` 的整行，只把更早行标记为“已取消”。这对 upsert 的“保留最新 revision/archive”是合理的，但 delete 的契约不同：重复 delete 应刷新 revision，却必须保留第一次入队时的 `archive_no` 快照。当前迁移没有把最早 delete 的 `archive_no` 合并到最终等待行。
- 独立复现：在无唯一索引的旧库中插入同键两条等待 delete：较早行为 `('ARCHIVE-ORIGINAL', 'v1')`，较晚行为 `('ARCHIVE-CHANGED', 'v2')`，再调用 `ensure_tables`。实际结果为：

```text
legacy_delete_rows= [
  ('ARCHIVE-ORIGINAL', 'v1', '已取消'),
  ('ARCHIVE-CHANGED', 'v2', '等待')
]
```

- 期望结果：最终唯一等待 delete 应同时保留首个快照 `ARCHIVE-ORIGINAL` 和最新 revision `v2`。当前结果与 `test_repeated_delete_refreshes_revision_but_preserves_original_archive_snapshot` 所保护的正常入队语义相反。
- 影响：升级后 worker 会读取后一个 archive number；若档案号在删除期间发生变化，可能删除错误远端记录或遗留原记录。该缺陷只出现在旧库重复 delete 迁移路径，故定为 MEDIUM，但属于同步数据正确性问题。
- 修复要求：为历史 delete 重复制定操作感知的合并规则，例如保留最大 id/最新 revision 的等待行，但把同组最小 id 的 `archive_no` 写入该行，再取消其余行；或保留最早行并合并最新 revision。新增无索引旧库含两个不同 archive/revision 的等待 delete 升级测试，并继续断言迁移原子性及唯一索引存在。

## 最终判断

此前所有已知缺陷均已关闭，迁移锁、回滚和微秒时间修复本身有效；当前唯一阻塞项是历史重复 delete 的快照合并。修复该项并补充回归测试后，Task 1 才适合改为 `APPROVED`。

---

## 最终修复轮次复审

### 最终结论

**APPROVED**

本结论取代上文修复前的 `CHANGES_REQUESTED`。历史重复 delete 的快照合并已修复，原阻塞项关闭；未发现迁移、唯一索引、并发初始化、租约时间或历史问题的新回归。

### 修复核验

- `ensure_tables` 在通用去重前调用 `_merge_legacy_waiting_deletes`，见 `features/nocobase_sync/queue.py:55-61`。
- 合并逻辑只处理同一 `(entity, local_id)` 的等待 delete，将最小 id 的 `archive_no` 写入最大 id 行；最大 id 行原有的最新 `revision` 保持不变，见 `features/nocobase_sync/queue.py:341-370`。
- 随后的 `_cancel_legacy_waiting_duplicates` 仍取消较早行，并由同一 savepoint 内的唯一索引创建保证最终只有一条同键、同 operation 的等待任务，见 `features/nocobase_sync/queue.py:56-69`、`features/nocobase_sync/queue.py:325-338`。
- 新增回归测试明确断言 `ARCHIVE-ORIGINAL + v2 + 等待` 及唯一索引存在，见 `tests/test_nocobase_queue.py:194-227`。

### 独立迁移探针

使用临时旧库插入三条同键等待 delete：

```text
('ARCHIVE-FIRST', 'v1')
('ARCHIVE-MIDDLE', 'v2')
('ARCHIVE-LAST', 'v3')
```

升级并再次重复调用 `ensure_tables` 后，结果为：

```text
delete_merge_three=PASS
[
  ('ARCHIVE-FIRST', 'v1', '已取消'),
  ('ARCHIVE-MIDDLE', 'v2', '已取消'),
  ('ARCHIVE-FIRST', 'v3', '等待')
]
index=1
```

这同时证明：首次档案号快照得到保留、最新 revision 得到保留、三条以上重复行正确合并、重复迁移幂等，且唯一索引存在并拒绝额外同键等待 delete。

另在含三条历史重复 delete 的文件数据库上同时启动四个 `ensure_tables`：

```text
concurrent_delete_migration=PASS
threads=4
waiting=[('ARCHIVE-FIRST', 'v3', '等待')]
index=1
```

四个初始化线程均无异常，最终仍只有正确合并的一条等待 delete 和一个唯一索引。

### 回归验证

- Task 1：`python -m unittest tests.test_nocobase_queue -v`，退出码 0，`Ran 24 tests in 0.329s`，`OK`。
- 全量：`python -m unittest discover -s tests -v`，退出码 0，`Ran 157 tests in 12.347s`，`OK`。
- 编译：`python -m py_compile features\nocobase_sync\__init__.py features\nocobase_sync\queue.py tests\test_nocobase_queue.py`，退出码 0，无输出。
- 独立回归探针确认：旧 `COALESCE` 索引迁移中途失败时索引仍由回滚保留；微秒输入的租约仍精确持续五分钟，提前一微秒不可回收、到截止点可回收。输出：`rollback_index_and_microlease=PASS`。
- 先前已验证的并发 enqueue、跨时区绝对时间、过期 owner 拒绝、retry 冲突、非法 `local_id` 无副作用、delete rollback、审计最小化和统计行为继续由完整 Task 1 测试覆盖并通过。

### 最终判断

历史重复 delete 迁移现在与正常 `enqueue_delete` 的业务语义一致：保留首次 `archive_no` 快照并采用最新 `revision`。迁移原子性、失败回滚、并发 `ensure_tables`、唯一索引和完整五分钟微秒租约均有独立证据，且 Task 1 与全量测试无回归。Task 1 可批准。
