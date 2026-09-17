import os
import sqlite3
import tempfile
import threading
import unittest

from features.nocobase_sync import queue


def memory_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    return conn


def file_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


class QueueTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix='.sqlite3')
        os.close(handle)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_tables_have_only_the_queue_and_privacy_safe_audit_columns(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)

        jobs = [row['name'] for row in conn.execute('PRAGMA table_info(nocobase_sync_jobs)')]
        audit = [row['name'] for row in conn.execute('PRAGMA table_info(nocobase_sync_audit)')]

        self.assertEqual(jobs, [
            'id', 'entity', 'local_id', 'archive_no', 'operation', 'revision',
            'status', 'attempts', 'next_attempt_at', 'lease_owner', 'lease_until',
            'error_stage', 'error_type', 'diagnostic_id', 'created_at', 'updated_at',
            'completed_at',
        ])
        self.assertEqual(audit, [
            'id', 'entity', 'archive_no', 'operation', 'outcome', 'diagnostic_id',
            'created_at',
        ])

    def test_latest_upsert_replaces_waiting_revision(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)
        queue.enqueue_upsert(conn, 'candidates', 7, '0120260916001', '2026-09-16T09:00:00')
        queue.enqueue_upsert(conn, 'candidates', 7, '0120260916001', '2026-09-16T09:01:00')

        rows = conn.execute('SELECT operation, revision, status FROM nocobase_sync_jobs').fetchall()
        self.assertEqual([tuple(row) for row in rows], [('upsert', '2026-09-16T09:01:00', '等待')])

    def test_enqueue_keeps_the_callers_transaction_open(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)
        conn.commit()

        queue.enqueue_upsert(conn, 'candidates', 7, 'A-7', 'v1')
        self.assertTrue(conn.in_transaction)
        conn.rollback()

        self.assertEqual(conn.execute('SELECT COUNT(*) FROM nocobase_sync_jobs').fetchone()[0], 0)

    def test_delete_enqueue_keeps_the_callers_transaction_open(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)
        queue.enqueue_upsert(conn, 'candidates', 7, 'A-7', 'v1')
        conn.commit()

        queue.enqueue_delete(conn, 'candidates', 7, 'A-7', 'v2')
        self.assertTrue(conn.in_transaction)
        conn.rollback()

        rows = conn.execute('SELECT operation, revision, status FROM nocobase_sync_jobs').fetchall()
        self.assertEqual([tuple(row) for row in rows], [('upsert', 'v1', '等待')])

    def test_invalid_entity_or_blank_archive_number_is_rejected(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)

        with self.assertRaises(ValueError):
            queue.enqueue_upsert(conn, 'employees', 1, 'A-1', 'v1')
        with self.assertRaises(ValueError):
            queue.enqueue_delete(conn, 'candidates', 1, '   ', 'v1')

    def test_invalid_local_id_is_rejected_before_it_changes_existing_tasks(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)
        queue.enqueue_upsert(conn, 'candidates', 7, 'A-7', 'v1')
        conn.commit()

        with self.assertRaises(ValueError):
            queue.enqueue_upsert(conn, 'candidates', None, 'A-null', 'v2')
        with self.assertRaises(ValueError):
            queue.enqueue_delete(conn, 'candidates', -1, 'A-negative', 'v3')

        rows = conn.execute(
            'SELECT local_id, archive_no, revision, operation, status FROM nocobase_sync_jobs'
        ).fetchall()
        self.assertEqual([tuple(row) for row in rows], [(7, 'A-7', 'v1', 'upsert', '等待')])

    def test_delete_cancels_waiting_upsert(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)
        queue.enqueue_upsert(conn, 'resume_documents', 9, '0120260916009', 'v1')
        queue.enqueue_delete(conn, 'resume_documents', 9, '0120260916009', 'v2')

        rows = conn.execute('SELECT operation, status FROM nocobase_sync_jobs ORDER BY id').fetchall()
        self.assertEqual([tuple(row) for row in rows], [('upsert', '已取消'), ('delete', '等待')])

    def test_repeated_delete_refreshes_revision_but_preserves_original_archive_snapshot(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)
        queue.enqueue_delete(conn, 'candidates', 9, 'A-9', 'v1')
        queue.enqueue_delete(conn, 'candidates', 9, 'CHANGED-9', 'v2')

        rows = conn.execute('SELECT archive_no, revision, operation, status FROM nocobase_sync_jobs').fetchall()
        self.assertEqual([tuple(row) for row in rows], [('A-9', 'v2', 'delete', '等待')])

    def test_database_enforces_one_waiting_job_across_independent_connections(self):
        conn = file_db(self.db_path)
        queue.ensure_tables(conn)
        conn.commit()
        conn.close()

        first = file_db(self.db_path)
        first.execute(
            "INSERT INTO nocobase_sync_jobs(entity, local_id, archive_no, operation, revision, status, "
            "attempts, next_attempt_at, created_at, updated_at) "
            "VALUES ('candidates', 7, 'A-7', 'upsert', 'v1', '等待', 0, '', '2026-09-16T00:00:00Z', "
            "'2026-09-16T00:00:00Z')"
        )
        first.commit()
        first.close()

        second = file_db(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                second.execute(
                    "INSERT INTO nocobase_sync_jobs(entity, local_id, archive_no, operation, revision, status, "
                    "attempts, next_attempt_at, created_at, updated_at) "
                    "VALUES ('candidates', 7, 'A-7', 'upsert', 'v2', '等待', 0, '', '2026-09-16T00:00:01Z', "
                    "'2026-09-16T00:00:01Z')"
                )
        finally:
            second.close()

    def test_ensure_tables_deduplicates_legacy_waiting_jobs_before_creating_index(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)
        conn.commit()
        conn.execute('DROP INDEX nocobase_sync_waiting_job_unique')
        conn.execute(
            "INSERT INTO nocobase_sync_jobs(entity, local_id, archive_no, operation, revision, status, "
            "attempts, next_attempt_at, created_at, updated_at) "
            "VALUES ('candidates', 7, 'A-7', 'upsert', 'old', '等待', 0, '', '2026-09-16T00:00:00Z', "
            "'2026-09-16T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO nocobase_sync_jobs(entity, local_id, archive_no, operation, revision, status, "
            "attempts, next_attempt_at, created_at, updated_at) "
            "VALUES ('candidates', 7, 'A-7', 'upsert', 'new', '等待', 0, '', '2026-09-16T00:00:01Z', "
            "'2026-09-16T00:00:01Z')"
        )
        conn.commit()

        try:
            queue.ensure_tables(conn)
        except sqlite3.IntegrityError as error:
            self.fail(f'legacy duplicates must be resolved before the unique index is created: {error}')

        rows = conn.execute('SELECT revision, status FROM nocobase_sync_jobs ORDER BY id').fetchall()
        index_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' "
            "AND name = 'nocobase_sync_waiting_job_unique'"
        ).fetchone()[0]
        self.assertEqual([tuple(row) for row in rows], [('old', '已取消'), ('new', '等待')])
        self.assertEqual(index_count, 1)

    def test_ensure_tables_merges_legacy_delete_snapshot_with_newest_revision(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)
        conn.commit()
        conn.execute('DROP INDEX nocobase_sync_waiting_job_unique')
        conn.execute(
            "INSERT INTO nocobase_sync_jobs(entity, local_id, archive_no, operation, revision, status, "
            "attempts, next_attempt_at, created_at, updated_at) "
            "VALUES ('candidates', 9, 'ARCHIVE-ORIGINAL', 'delete', 'v1', '等待', 0, '', "
            "'2026-09-16T00:00:00Z', '2026-09-16T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO nocobase_sync_jobs(entity, local_id, archive_no, operation, revision, status, "
            "attempts, next_attempt_at, created_at, updated_at) "
            "VALUES ('candidates', 9, 'ARCHIVE-CHANGED', 'delete', 'v2', '等待', 0, '', "
            "'2026-09-16T00:00:01Z', '2026-09-16T00:00:01Z')"
        )
        conn.commit()

        queue.ensure_tables(conn)

        rows = conn.execute(
            'SELECT archive_no, revision, status FROM nocobase_sync_jobs ORDER BY id'
        ).fetchall()
        index_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' "
            "AND name = 'nocobase_sync_waiting_job_unique'"
        ).fetchone()[0]
        self.assertEqual([tuple(row) for row in rows], [
            ('ARCHIVE-ORIGINAL', 'v1', '已取消'),
            ('ARCHIVE-ORIGINAL', 'v2', '等待'),
        ])
        self.assertEqual(index_count, 1)

    def test_concurrent_ensure_tables_resolves_legacy_duplicates_and_keeps_index(self):
        conn = file_db(self.db_path)
        queue.ensure_tables(conn)
        conn.commit()
        conn.execute('DROP INDEX nocobase_sync_waiting_job_unique')
        for revision in ('old', 'new'):
            conn.execute(
                "INSERT INTO nocobase_sync_jobs(entity, local_id, archive_no, operation, revision, status, "
                "attempts, next_attempt_at, created_at, updated_at) "
                "VALUES ('candidates', 8, 'A-8', 'upsert', ?, '等待', 0, '', '2026-09-16T00:00:00Z', "
                "'2026-09-16T00:00:00Z')",
                (revision,),
            )
        conn.commit()
        conn.close()
        start = threading.Barrier(2)
        errors = []

        def initialize():
            connection = file_db(self.db_path)
            try:
                connection.execute('PRAGMA busy_timeout = 5000')
                start.wait()
                queue.ensure_tables(connection)
                connection.commit()
            except Exception as error:
                errors.append(error)
            finally:
                connection.close()

        threads = [threading.Thread(target=initialize) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        conn = file_db(self.db_path)
        try:
            rows = conn.execute(
                'SELECT revision, status FROM nocobase_sync_jobs WHERE local_id = 8 ORDER BY id'
            ).fetchall()
            index_count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' "
                "AND name = 'nocobase_sync_waiting_job_unique'"
            ).fetchone()[0]
            self.assertEqual([tuple(row) for row in rows], [('old', '已取消'), ('new', '等待')])
            self.assertEqual(index_count, 1)
        finally:
            conn.close()

    def test_concurrent_enqueues_keep_one_waiting_job(self):
        conn = file_db(self.db_path)
        queue.ensure_tables(conn)
        conn.commit()
        conn.close()
        start = threading.Barrier(2)
        errors = []

        def enqueue(revision):
            connection = file_db(self.db_path)
            try:
                connection.execute('PRAGMA busy_timeout = 5000')
                start.wait()
                queue.enqueue_upsert(connection, 'candidates', 8, 'A-8', revision)
                connection.commit()
            except Exception as error:
                errors.append(error)
            finally:
                connection.close()

        threads = [threading.Thread(target=enqueue, args=(revision,)) for revision in ('v1', 'v2')]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        conn = file_db(self.db_path)
        try:
            rows = conn.execute(
                "SELECT operation, status FROM nocobase_sync_jobs "
                "WHERE entity = 'candidates' AND local_id = 8"
            ).fetchall()
            self.assertEqual([tuple(row) for row in rows], [('upsert', '等待')])
        finally:
            conn.close()

    def test_expired_processing_job_can_be_claimed_again(self):
        conn = file_db(self.db_path)
        queue.ensure_tables(conn)
        job_id = queue.enqueue_upsert(conn, 'candidates', 3, 'A-3', 'v1')
        conn.commit()
        conn.close()

        first = queue.claim(self.db_path, 'worker-a', '2026-09-16T10:00:00')
        second = queue.claim(self.db_path, 'worker-b', '2026-09-16T10:06:00')

        self.assertEqual(first['id'], job_id)
        self.assertEqual(second['id'], job_id)
        self.assertEqual(second['lease_owner'], 'worker-b')

    def test_subsecond_lease_and_retry_deadlines_do_not_expire_early(self):
        conn = file_db(self.db_path)
        queue.ensure_tables(conn)
        lease_id = queue.enqueue_upsert(conn, 'candidates', 40, 'A-40', 'v1')
        conn.commit()
        conn.close()

        claimed = queue.claim(self.db_path, 'worker-a', '2026-09-16T10:00:00.999999Z')
        self.assertEqual(claimed['lease_until'], '2026-09-16T10:05:00.999999Z')
        self.assertIsNone(queue.claim(self.db_path, 'worker-b', '2026-09-16T10:05:00.999998Z'))
        self.assertTrue(queue.complete(self.db_path, lease_id, 'worker-a', '2026-09-16T10:05:00.999998Z'))

        conn = file_db(self.db_path)
        retry_id = queue.enqueue_upsert(conn, 'candidates', 41, 'A-41', 'v1')
        conn.commit()
        conn.close()
        queue.claim(self.db_path, 'worker-a', '2026-09-16T11:00:00.999999Z')
        self.assertTrue(queue.fail(self.db_path, retry_id, 'worker-a', {
            'stage': 'upload', 'error_type': 'network', 'diagnostic_id': 'D-micro', 'pausable': False,
        }, '2026-09-16T11:00:00.999999Z'))
        self.assertIsNone(queue.claim(self.db_path, 'worker-b', '2026-09-16T11:01:00.999998Z'))
        retry = queue.claim(self.db_path, 'worker-b', '2026-09-16T11:01:00.999999Z')
        self.assertEqual(retry['id'], retry_id)

    def test_non_expired_processing_job_cannot_be_stolen(self):
        conn = file_db(self.db_path)
        queue.ensure_tables(conn)
        queue.enqueue_upsert(conn, 'candidates', 3, 'A-3', 'v1')
        conn.commit()
        conn.close()

        self.assertIsNotNone(queue.claim(self.db_path, 'worker-a', '2026-09-16T10:00:00'))
        self.assertIsNone(queue.claim(self.db_path, 'worker-b', '2026-09-16T10:04:59'))

    def test_expired_lease_owner_cannot_complete_or_fail_before_reclaim(self):
        conn = file_db(self.db_path)
        queue.ensure_tables(conn)
        complete_id = queue.enqueue_upsert(conn, 'candidates', 11, 'A-11', 'v1')
        conn.commit()
        conn.close()

        queue.claim(self.db_path, 'worker-a', '2026-09-16T10:00:00Z')
        self.assertFalse(queue.complete(self.db_path, complete_id, 'worker-a', '2026-09-16T10:06:00Z'))

        conn = file_db(self.db_path)
        fail_id = queue.enqueue_upsert(conn, 'candidates', 12, 'A-12', 'v1')
        conn.commit()
        conn.close()
        self.assertIsNotNone(queue.claim(self.db_path, 'worker-a', '2026-09-16T10:01:00Z'))
        self.assertFalse(queue.fail(self.db_path, fail_id, 'worker-a', {
            'stage': 'upload', 'error_type': 'network', 'diagnostic_id': 'D-expired', 'pausable': False,
        }, '2026-09-16T10:07:00Z'))

        conn = file_db(self.db_path)
        try:
            rows = conn.execute(
                'SELECT id, status, attempts FROM nocobase_sync_jobs WHERE id IN (?, ?) ORDER BY id',
                (complete_id, fail_id),
            ).fetchall()
            self.assertEqual([tuple(row) for row in rows], [
                (complete_id, '处理中', 0), (fail_id, '处理中', 0),
            ])
        finally:
            conn.close()

    def test_stale_owner_cannot_complete_or_fail_a_reclaimed_lease(self):
        conn = file_db(self.db_path)
        queue.ensure_tables(conn)
        job_id = queue.enqueue_upsert(conn, 'candidates', 3, 'A-3', 'v1')
        conn.commit()
        conn.close()
        queue.claim(self.db_path, 'worker-a', '2026-09-16T10:00:00')
        queue.claim(self.db_path, 'worker-b', '2026-09-16T10:06:00')

        self.assertFalse(queue.complete(self.db_path, job_id, 'worker-a', '2026-09-16T10:06:01'))
        self.assertFalse(queue.fail(self.db_path, job_id, 'worker-a', {
            'stage': 'upload', 'error_type': 'network', 'diagnostic_id': 'D-1', 'pausable': False,
        }, '2026-09-16T10:06:01'))

        conn = file_db(self.db_path)
        row = conn.execute('SELECT status, lease_owner FROM nocobase_sync_jobs WHERE id = ?', (job_id,)).fetchone()
        self.assertEqual(tuple(row), ('处理中', 'worker-b'))
        conn.close()

    def test_fail_uses_progressive_retry_delays_and_pauses_structural_failures(self):
        conn = file_db(self.db_path)
        queue.ensure_tables(conn)
        job_id = queue.enqueue_upsert(conn, 'candidates', 3, 'A-3', 'v1')
        pause_id = queue.enqueue_upsert(conn, 'resume_documents', 4, 'A-4', 'v1')
        conn.commit()
        conn.close()

        queue.claim(self.db_path, 'worker-a', '2026-09-16T10:00:00')
        self.assertTrue(queue.fail(self.db_path, job_id, 'worker-a', {
            'stage': 'upload', 'error_type': 'network', 'diagnostic_id': 'D-1', 'pausable': False,
        }, '2026-09-16T10:00:00'))
        queue.claim(self.db_path, 'worker-a', '2026-09-16T10:01:00')
        self.assertTrue(queue.fail(self.db_path, job_id, 'worker-a', {
            'stage': 'upload', 'error_type': 'network', 'diagnostic_id': 'D-2', 'pausable': False,
        }, '2026-09-16T10:01:00'))
        queue.claim(self.db_path, 'worker-a', '2026-09-16T10:06:00')
        self.assertTrue(queue.fail(self.db_path, job_id, 'worker-a', {
            'stage': 'upload', 'error_type': 'network', 'diagnostic_id': 'D-3', 'pausable': False,
        }, '2026-09-16T10:06:00'))
        queue.claim(self.db_path, 'worker-a', '2026-09-16T10:21:00')
        self.assertTrue(queue.fail(self.db_path, job_id, 'worker-a', {
            'stage': 'upload', 'error_type': 'network', 'diagnostic_id': 'D-4', 'pausable': False,
        }, '2026-09-16T10:21:00'))
        queue.claim(self.db_path, 'worker-a', '2026-09-16T10:51:00')
        self.assertTrue(queue.fail(self.db_path, job_id, 'worker-a', {
            'stage': 'upload', 'error_type': 'network', 'diagnostic_id': 'D-5', 'pausable': False,
        }, '2026-09-16T10:51:00'))

        queue.claim(self.db_path, 'worker-a', '2026-09-16T11:51:00')
        self.assertTrue(queue.fail(self.db_path, job_id, 'worker-a', {
            'stage': 'upload', 'error_type': 'network', 'diagnostic_id': 'D-6', 'pausable': False,
        }, '2026-09-16T11:51:00'))
        self.assertIsNotNone(queue.claim(self.db_path, 'worker-a', '2026-09-16T11:51:00'))
        self.assertTrue(queue.fail(self.db_path, pause_id, 'worker-a', {
            'stage': 'mapping', 'error_type': 'duplicate', 'diagnostic_id': 'D-P', 'pausable': True,
        }, '2026-09-16T11:51:00'))

        conn = file_db(self.db_path)
        try:
            rows = conn.execute(
                'SELECT id, status, attempts, next_attempt_at, error_stage, error_type, diagnostic_id '
                'FROM nocobase_sync_jobs ORDER BY id'
            ).fetchall()
            self.assertEqual([tuple(row) for row in rows], [
                (job_id, '失败', 6, '2026-09-16T12:51:00.000000Z', 'upload', 'network', 'D-6'),
                (pause_id, '暂停', 1, '', 'mapping', 'duplicate', 'D-P'),
            ])
        finally:
            conn.close()

    def test_retry_selection_only_requeues_failed_or_paused_jobs(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)
        failed = queue.enqueue_upsert(conn, 'candidates', 1, 'A-1', 'v1')
        paused = queue.enqueue_upsert(conn, 'candidates', 2, 'A-2', 'v1')
        waiting = queue.enqueue_upsert(conn, 'candidates', 3, 'A-3', 'v1')
        conn.execute("UPDATE nocobase_sync_jobs SET status = '失败' WHERE id = ?", (failed,))
        conn.execute("UPDATE nocobase_sync_jobs SET status = '暂停' WHERE id = ?", (paused,))

        self.assertEqual(queue.retry_jobs(conn, [failed, waiting]), 1)
        self.assertEqual(queue.retry_jobs(conn), 1)
        rows = conn.execute('SELECT id, status, attempts, error_stage FROM nocobase_sync_jobs ORDER BY id').fetchall()
        self.assertEqual([tuple(row) for row in rows], [
            (failed, '等待', 0, ''), (paused, '等待', 0, ''), (waiting, '等待', 0, ''),
        ])

    def test_retry_skips_old_failures_or_pauses_when_new_waiting_job_exists(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)
        failed = queue.enqueue_upsert(conn, 'candidates', 30, 'A-30', 'old-failed')
        conn.execute("UPDATE nocobase_sync_jobs SET status = '失败' WHERE id = ?", (failed,))
        waiting_after_failure = queue.enqueue_upsert(conn, 'candidates', 30, 'A-30', 'new-waiting')
        paused = queue.enqueue_upsert(conn, 'candidates', 31, 'A-31', 'old-paused')
        conn.execute("UPDATE nocobase_sync_jobs SET status = '暂停' WHERE id = ?", (paused,))
        waiting_after_pause = queue.enqueue_upsert(conn, 'candidates', 31, 'A-31', 'new-waiting')
        independent = queue.enqueue_upsert(conn, 'candidates', 32, 'A-32', 'retry-me')
        conn.execute("UPDATE nocobase_sync_jobs SET status = '失败' WHERE id = ?", (independent,))

        try:
            retried = queue.retry_jobs(conn, [failed, paused, independent])
        except sqlite3.IntegrityError as error:
            self.fail(f'retrying stale jobs must not abort the batch: {error}')
        self.assertEqual(retried, 1)
        rows = conn.execute('SELECT id, revision, status FROM nocobase_sync_jobs ORDER BY id').fetchall()
        self.assertEqual([tuple(row) for row in rows], [
            (failed, 'old-failed', '失败'),
            (waiting_after_failure, 'new-waiting', '等待'),
            (paused, 'old-paused', '暂停'),
            (waiting_after_pause, 'new-waiting', '等待'),
            (independent, 'retry-me', '等待'),
        ])

    def test_retry_restores_only_the_newest_selected_failure_for_one_key(self):
        conn = memory_db()
        self.addCleanup(conn.close)
        queue.ensure_tables(conn)
        older = queue.enqueue_upsert(conn, 'candidates', 33, 'A-33', 'old')
        conn.execute("UPDATE nocobase_sync_jobs SET status = '失败' WHERE id = ?", (older,))
        newer = queue.enqueue_upsert(conn, 'candidates', 33, 'A-33', 'new')
        conn.execute("UPDATE nocobase_sync_jobs SET status = '暂停' WHERE id = ?", (newer,))

        try:
            retried = queue.retry_jobs(conn, [older, newer])
        except sqlite3.IntegrityError as error:
            self.fail(f'retrying duplicate failed jobs must choose one safely: {error}')
        self.assertEqual(retried, 1)
        rows = conn.execute('SELECT id, revision, status FROM nocobase_sync_jobs ORDER BY id').fetchall()
        self.assertEqual([tuple(row) for row in rows], [
            (older, 'old', '失败'), (newer, 'new', '等待'),
        ])

    def test_stats_includes_every_status_and_last_success_and_audit_is_minimized(self):
        conn = file_db(self.db_path)
        queue.ensure_tables(conn)
        success_id = queue.enqueue_upsert(conn, 'candidates', 1, 'A-1', 'v1')
        queue.enqueue_upsert(conn, 'candidates', 2, 'A-2', 'v1')
        queue.enqueue_upsert(conn, 'candidates', 3, 'A-3', 'v1')
        queue.enqueue_upsert(conn, 'candidates', 4, 'A-4', 'v1')
        queue.enqueue_upsert(conn, 'candidates', 5, 'A-5', 'v1')
        conn.execute("UPDATE nocobase_sync_jobs SET status = '处理中' WHERE local_id = 2")
        conn.execute("UPDATE nocobase_sync_jobs SET status = '失败' WHERE local_id = 3")
        conn.execute("UPDATE nocobase_sync_jobs SET status = '暂停' WHERE local_id = 4")
        conn.execute("UPDATE nocobase_sync_jobs SET status = '已取消' WHERE local_id = 5")
        conn.commit()
        conn.close()

        queue.claim(self.db_path, 'worker-a', '2026-09-16T10:00:00')
        self.assertTrue(queue.complete(self.db_path, success_id, 'worker-a', '2026-09-16T10:02:00'))

        conn = file_db(self.db_path)
        try:
            result = queue.stats(conn)
            self.assertEqual(
                result,
                {'等待': 0, '处理中': 1, '成功': 1, '失败': 1, '暂停': 1, '已取消': 1,
                 'last_completed_at': '2026-09-16T10:02:00.000000Z'},
            )
            audit = conn.execute('SELECT * FROM nocobase_sync_audit').fetchone()
            self.assertEqual(
                tuple(audit),
                (1, 'candidates', 'A-1', 'upsert', '成功', '', '2026-09-16T10:02:00.000000Z'),
            )
        finally:
            conn.close()

    def test_retry_due_and_stats_use_absolute_utc_time_across_offsets(self):
        conn = file_db(self.db_path)
        queue.ensure_tables(conn)
        retry_id = queue.enqueue_upsert(conn, 'candidates', 20, 'A-20', 'v1')
        first_success_id = queue.enqueue_upsert(conn, 'candidates', 21, 'A-21', 'v1')
        second_success_id = queue.enqueue_upsert(conn, 'candidates', 22, 'A-22', 'v1')
        conn.commit()
        conn.close()

        queue.claim(self.db_path, 'worker-a', '2026-09-16T10:00:00+08:00')
        self.assertTrue(queue.fail(self.db_path, retry_id, 'worker-a', {
            'stage': 'upload', 'error_type': 'network', 'diagnostic_id': 'D-tz', 'pausable': False,
        }, '2026-09-16T10:00:00+08:00'))
        retry = queue.claim(self.db_path, 'worker-a', '2026-09-16T02:02:00+00:00')
        self.assertEqual(retry['id'], retry_id)
        self.assertEqual(retry['lease_until'], '2026-09-16T02:07:00.000000Z')
        self.assertTrue(queue.complete(
            self.db_path, retry_id, 'worker-a', '2026-09-16T02:03:00+00:00'
        ))

        self.assertIsNotNone(queue.claim(self.db_path, 'worker-a', '2026-09-16T09:59:00+08:00'))
        self.assertTrue(queue.complete(
            self.db_path, first_success_id, 'worker-a', '2026-09-16T10:00:00+08:00'
        ))
        self.assertIsNotNone(queue.claim(self.db_path, 'worker-a', '2026-09-16T02:59:00Z'))
        self.assertTrue(queue.complete(
            self.db_path, second_success_id, 'worker-a', '2026-09-16T03:00:00Z'
        ))

        conn = file_db(self.db_path)
        try:
            failed = conn.execute(
                'SELECT next_attempt_at FROM nocobase_sync_jobs WHERE id = ?', (retry_id,)
            ).fetchone()
            self.assertEqual(failed['next_attempt_at'], '2026-09-16T02:01:00.000000Z')
            self.assertEqual(queue.stats(conn)['last_completed_at'], '2026-09-16T03:00:00.000000Z')
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
