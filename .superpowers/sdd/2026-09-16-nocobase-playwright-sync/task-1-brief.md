# Task 1: 持久化同步队列、任务合并和租约

## Global constraints

- 第一阶段只同步 `resume_documents` 和 `candidates`，方向仅为招聘系统到 NocoBase。
- 所有本地业务写入和同步任务入队必须处于同一 SQLite 事务。
- 日志不得包含姓名、电话、邮箱、身份证号、附件名称、附件内容、Cookie、密码或完整页面内容。
- 当前工作目录没有 `.git`；不要初始化 Git，不要提交。通过测试和报告形成检查点。
- 严格遵循 TDD：测试先写，观察预期失败，再写最小实现并观察通过。

## Files

- Create: `features/nocobase_sync/__init__.py`
- Create: `features/nocobase_sync/queue.py`
- Create: `tests/test_nocobase_queue.py`

## Interfaces

- Consumes: 现有 `sqlite3.Connection`，连接必须设置 `row_factory=sqlite3.Row`。
- Produces: `ensure_tables(conn)`, `enqueue_upsert(conn, entity, local_id, archive_no, revision)`, `enqueue_delete(conn, entity, local_id, archive_no, revision)`, `claim(db_path, worker_id, now)`, `complete(db_path, job_id, worker_id, now)`, `fail(db_path, job_id, worker_id, failure, now)`, `retry_jobs(conn, ids=None)`, `stats(conn)`。

## Required behavior

1. Define `ALLOWED_ENTITIES = {'resume_documents', 'candidates'}` and `RETRY_DELAYS = (60, 300, 900, 1800, 3600)`.
2. `ensure_tables` creates `nocobase_sync_jobs` with columns: `id`, `entity`, `local_id`, `archive_no`, `operation`, `revision`, `status`, `attempts`, `next_attempt_at`, `lease_owner`, `lease_until`, `error_stage`, `error_type`, `diagnostic_id`, `created_at`, `updated_at`, `completed_at`.
3. `ensure_tables` creates `nocobase_sync_audit` with columns: `id`, `entity`, `archive_no`, `operation`, `outcome`, `diagnostic_id`, `created_at`.
4. `enqueue_upsert` validates entity/archive number, merges an existing waiting upsert for the same entity/local_id to the newest revision, and never commits its caller's transaction.
5. `enqueue_delete` cancels waiting upserts for the same entity/local_id, creates or refreshes one waiting delete, preserves the archive number snapshot, and never commits.
6. `claim` opens its own SQLite connection, uses `BEGIN IMMEDIATE`, leases one eligible waiting/failed job for five minutes, and can reclaim a processing job only after its lease expires.
7. `complete` and `fail` require matching `lease_owner` so a stale worker cannot finish another worker's lease.
8. `fail` accepts a small structured object or mapping containing `stage`, `error_type`, `diagnostic_id`, `pausable`; `pausable=True` sets status `暂停`, otherwise schedules the retry using the declared delays and increments attempts.
9. `retry_jobs` only resets `失败`/`暂停` tasks, optionally limited to explicit IDs. `stats` returns counts for every known status plus the most recent successful completion time.
10. Audit rows contain only entity, archive number, operation, outcome, diagnostic number, and time.

## Mandatory RED tests

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

Also cover: invalid entity, blank archive number, non-expired lease cannot be stolen, stale owner cannot complete/fail, retry delay progression, pausable failure, retry selection, stats, and audit data minimization.

## Verification

Run RED before production code: `python -m unittest tests.test_nocobase_queue -v` and capture the expected missing-module/function failure.

Run GREEN after implementation: `python -m unittest tests.test_nocobase_queue -v` and require pristine PASS output.

## Report

Write the full report to `.superpowers/sdd/2026-09-16-nocobase-playwright-sync/task-1-report.md` with implementation summary, exact RED/GREEN commands and outputs, files changed, self-review, and concerns. Do not spawn subagents.
