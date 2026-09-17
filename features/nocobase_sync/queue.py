"""SQLite-backed, privacy-safe job queue for one-way NocoBase synchronization."""

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import sqlite3


ALLOWED_ENTITIES = {'resume_documents', 'candidates'}
RETRY_DELAYS = (60, 300, 900, 1800, 3600)

WAITING = '等待'
PROCESSING = '处理中'
SUCCESS = '成功'
FAILED = '失败'
PAUSED = '暂停'
CANCELLED = '已取消'
KNOWN_STATUSES = (WAITING, PROCESSING, SUCCESS, FAILED, PAUSED, CANCELLED)


def ensure_tables(conn):
    """Create queue tables on the caller-owned connection without committing it."""
    owns_transaction = not conn.in_transaction
    if owns_transaction:
        conn.execute('BEGIN IMMEDIATE')
    conn.execute('SAVEPOINT nocobase_sync_schema')
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS nocobase_sync_jobs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT NOT NULL,
            local_id INTEGER,
            archive_no TEXT NOT NULL,
            operation TEXT NOT NULL,
            revision TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL,
            lease_owner TEXT NOT NULL DEFAULT '',
            lease_until TEXT NOT NULL DEFAULT '',
            error_stage TEXT NOT NULL DEFAULT '',
            error_type TEXT NOT NULL DEFAULT '',
            diagnostic_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT ''
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS nocobase_sync_audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT NOT NULL,
            archive_no TEXT NOT NULL,
            operation TEXT NOT NULL,
            outcome TEXT NOT NULL,
            diagnostic_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )''')
        _migrate_waiting_job_index(conn)
        _merge_legacy_waiting_deletes(conn)
        _cancel_legacy_waiting_duplicates(conn)
        _normalize_legacy_timestamps(conn)
        conn.execute('''CREATE UNIQUE INDEX IF NOT EXISTS nocobase_sync_waiting_job_unique
            ON nocobase_sync_jobs(entity, local_id, operation)
            WHERE status = '等待' ''')
        conn.execute('RELEASE SAVEPOINT nocobase_sync_schema')
        if owns_transaction:
            conn.commit()
    except Exception:
        conn.execute('ROLLBACK TO SAVEPOINT nocobase_sync_schema')
        conn.execute('RELEASE SAVEPOINT nocobase_sync_schema')
        if owns_transaction:
            conn.rollback()
        raise


def enqueue_upsert(conn, entity, local_id, archive_no, revision):
    """Queue the latest pending upsert, retaining the caller's transaction."""
    entity, local_id, archive_no = _validated_identity(entity, local_id, archive_no)
    timestamp = _current_timestamp()
    conn.execute(
        '''INSERT INTO nocobase_sync_jobs(
            entity, local_id, archive_no, operation, revision, status, attempts,
            next_attempt_at, created_at, updated_at
        ) VALUES (?, ?, ?, 'upsert', ?, ?, 0, '', ?, ?)
        ON CONFLICT DO UPDATE SET
            archive_no = excluded.archive_no,
            revision = excluded.revision,
            updated_at = excluded.updated_at''',
        (entity, local_id, archive_no, str(revision), WAITING, timestamp, timestamp),
    )
    return _waiting_job_id(conn, entity, local_id, 'upsert')


def enqueue_delete(conn, entity, local_id, archive_no, revision):
    """Cancel pending upserts and queue one archive-number-preserving delete."""
    entity, local_id, archive_no = _validated_identity(entity, local_id, archive_no)
    timestamp = _current_timestamp()
    conn.execute(
        "UPDATE nocobase_sync_jobs SET status = ?, updated_at = ? "
        "WHERE entity = ? AND local_id = ? AND operation = 'upsert' AND status = ?",
        (CANCELLED, timestamp, entity, local_id, WAITING),
    )
    conn.execute(
        '''INSERT INTO nocobase_sync_jobs(
            entity, local_id, archive_no, operation, revision, status, attempts,
            next_attempt_at, created_at, updated_at
        ) VALUES (?, ?, ?, 'delete', ?, ?, 0, '', ?, ?)
        ON CONFLICT DO UPDATE SET
            revision = excluded.revision,
            updated_at = excluded.updated_at''',
        (entity, local_id, archive_no, str(revision), WAITING, timestamp, timestamp),
    )
    return _waiting_job_id(conn, entity, local_id, 'delete')


def claim(db_path, worker_id, now):
    """Atomically lease one due job to a worker for five minutes."""
    timestamp = _timestamp(now)
    lease_until = _timestamp(_as_datetime(now) + timedelta(minutes=5))
    conn = _open(db_path)
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute(
            '''SELECT id FROM nocobase_sync_jobs
               WHERE status = ?
                  OR (status = ? AND (next_attempt_at = '' OR next_attempt_at <= ?))
                  OR (status = ? AND lease_until <= ?)
               ORDER BY id LIMIT 1''',
            (WAITING, FAILED, timestamp, PROCESSING, timestamp),
        ).fetchone()
        if not row:
            conn.commit()
            return None
        conn.execute(
            '''UPDATE nocobase_sync_jobs
               SET status = ?, lease_owner = ?, lease_until = ?, updated_at = ?
               WHERE id = ?''',
            (PROCESSING, str(worker_id), lease_until, timestamp, row['id']),
        )
        claimed = conn.execute('SELECT * FROM nocobase_sync_jobs WHERE id = ?', (row['id'],)).fetchone()
        conn.commit()
        return dict(claimed)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def complete(db_path, job_id, worker_id, now):
    """Mark a currently leased job successful; stale owners return ``False``."""
    timestamp = _timestamp(now)
    conn = _open(db_path)
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = _leased_job(conn, job_id, worker_id, timestamp)
        if not row:
            conn.commit()
            return False
        conn.execute(
            '''UPDATE nocobase_sync_jobs
               SET status = ?, lease_owner = '', lease_until = '', updated_at = ?, completed_at = ?
               WHERE id = ?''',
            (SUCCESS, timestamp, timestamp, job_id),
        )
        _audit(conn, row, SUCCESS, '', timestamp)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fail(db_path, job_id, worker_id, failure, now):
    """Record a privacy-safe failure and either pause it or schedule its retry."""
    timestamp = _timestamp(now)
    details = _failure_details(failure)
    conn = _open(db_path)
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = _leased_job(conn, job_id, worker_id, timestamp)
        if not row:
            conn.commit()
            return False
        attempts = row['attempts'] + 1
        paused = details['pausable']
        status = PAUSED if paused else FAILED
        next_attempt = '' if paused else _timestamp(
            _as_datetime(now) + timedelta(seconds=RETRY_DELAYS[min(attempts - 1, len(RETRY_DELAYS) - 1)])
        )
        conn.execute(
            '''UPDATE nocobase_sync_jobs
               SET status = ?, attempts = ?, next_attempt_at = ?, lease_owner = '', lease_until = '',
                   error_stage = ?, error_type = ?, diagnostic_id = ?, updated_at = ?
               WHERE id = ?''',
            (status, attempts, next_attempt, details['stage'], details['error_type'],
             details['diagnostic_id'], timestamp, job_id),
        )
        _audit(conn, row, status, details['diagnostic_id'], timestamp)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def retry_jobs(conn, ids=None):
    """Return selected failed or paused jobs to the waiting state without committing."""
    timestamp = _current_timestamp()
    values = [FAILED, PAUSED]
    where = 'status IN (?, ?)'
    if ids is not None:
        ids = list(ids)
        if not ids:
            return 0
        where += ' AND id IN ({})'.format(', '.join('?' for _ in ids))
        values.extend(ids)
    candidates = conn.execute(
        f'''SELECT id, entity, local_id, operation FROM nocobase_sync_jobs
            WHERE {where} ORDER BY id DESC''',
        values,
    ).fetchall()
    retried = 0
    seen_keys = set()
    for job in candidates:
        key = (job['entity'], job['local_id'], job['operation'])
        if key in seen_keys or _has_waiting_job(conn, key):
            seen_keys.add(key)
            continue
        cursor = conn.execute(
            '''UPDATE OR IGNORE nocobase_sync_jobs
               SET status = ?, attempts = 0, next_attempt_at = '', lease_owner = '', lease_until = '',
                   error_stage = '', error_type = '', diagnostic_id = '', updated_at = ?
               WHERE id = ? AND status IN (?, ?)''',
            (WAITING, timestamp, job['id'], FAILED, PAUSED),
        )
        seen_keys.add(key)
        retried += cursor.rowcount
    return retried


def stats(conn):
    """Return all queue-state counts and the latest successful completion timestamp."""
    counts = {status: 0 for status in KNOWN_STATUSES}
    for row in conn.execute('SELECT status, COUNT(*) AS count FROM nocobase_sync_jobs GROUP BY status'):
        if row['status'] in counts:
            counts[row['status']] = row['count']
    last_completed = conn.execute(
        'SELECT MAX(completed_at) FROM nocobase_sync_jobs WHERE status = ?', (SUCCESS,)
    ).fetchone()[0] or ''
    counts['last_completed_at'] = last_completed
    return counts


def _validated_identity(entity, local_id, archive_no):
    if entity not in ALLOWED_ENTITIES:
        raise ValueError('unsupported sync entity')
    if isinstance(local_id, bool) or not isinstance(local_id, int) or local_id <= 0:
        raise ValueError('local id must be a positive integer')
    archive_no = str(archive_no or '').strip()
    if not archive_no:
        raise ValueError('archive number is required')
    return entity, local_id, archive_no


def _current_timestamp():
    return _timestamp(datetime.now(timezone.utc))


def _as_datetime(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _timestamp(value):
    return _as_datetime(value).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def _open(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _leased_job(conn, job_id, worker_id, now):
    return conn.execute(
        'SELECT id, entity, archive_no, operation, attempts FROM nocobase_sync_jobs '
        'WHERE id = ? AND status = ? AND lease_owner = ? AND lease_until > ?',
        (job_id, PROCESSING, str(worker_id), now),
    ).fetchone()


def _waiting_job_id(conn, entity, local_id, operation):
    row = conn.execute(
        'SELECT id FROM nocobase_sync_jobs '
        'WHERE entity = ? AND local_id IS ? AND operation = ? AND status = ?',
        (entity, local_id, operation, WAITING),
    ).fetchone()
    return row['id']


def _has_waiting_job(conn, key):
    entity, local_id, operation = key
    return conn.execute(
        'SELECT 1 FROM nocobase_sync_jobs '
        'WHERE entity = ? AND local_id IS ? AND operation = ? AND status = ? LIMIT 1',
        (entity, local_id, operation, WAITING),
    ).fetchone() is not None


def _migrate_waiting_job_index(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'nocobase_sync_waiting_job_unique'"
    ).fetchone()
    if row and 'COALESCE' in (row['sql'] or '').upper():
        conn.execute('DROP INDEX nocobase_sync_waiting_job_unique')


def _cancel_legacy_waiting_duplicates(conn):
    conn.execute(
        '''UPDATE nocobase_sync_jobs
           SET status = ?, updated_at = ?
           WHERE status = ? AND EXISTS (
               SELECT 1 FROM nocobase_sync_jobs AS newer
               WHERE newer.status = ?
                 AND newer.entity = nocobase_sync_jobs.entity
                 AND newer.local_id IS nocobase_sync_jobs.local_id
                 AND newer.operation = nocobase_sync_jobs.operation
                 AND newer.id > nocobase_sync_jobs.id
           )''',
        (CANCELLED, _current_timestamp(), WAITING, WAITING),
    )


def _merge_legacy_waiting_deletes(conn):
    conn.execute(
        '''UPDATE nocobase_sync_jobs
           SET archive_no = (
               SELECT earliest.archive_no FROM nocobase_sync_jobs AS earliest
               WHERE earliest.status = ?
                 AND earliest.operation = 'delete'
                 AND earliest.entity = nocobase_sync_jobs.entity
                 AND earliest.local_id IS nocobase_sync_jobs.local_id
               ORDER BY earliest.id ASC LIMIT 1
           )
           WHERE status = ? AND operation = 'delete'
             AND EXISTS (
                 SELECT 1 FROM nocobase_sync_jobs AS older
                 WHERE older.status = ?
                   AND older.operation = 'delete'
                   AND older.entity = nocobase_sync_jobs.entity
                   AND older.local_id IS nocobase_sync_jobs.local_id
                   AND older.id < nocobase_sync_jobs.id
             )
             AND NOT EXISTS (
                 SELECT 1 FROM nocobase_sync_jobs AS newer
                 WHERE newer.status = ?
                   AND newer.operation = 'delete'
                   AND newer.entity = nocobase_sync_jobs.entity
                   AND newer.local_id IS nocobase_sync_jobs.local_id
                   AND newer.id > nocobase_sync_jobs.id
             )''',
        (WAITING, WAITING, WAITING, WAITING),
    )


def _normalize_legacy_timestamps(conn):
    for table, column in (
        ('nocobase_sync_jobs', 'next_attempt_at'),
        ('nocobase_sync_jobs', 'lease_until'),
        ('nocobase_sync_jobs', 'created_at'),
        ('nocobase_sync_jobs', 'updated_at'),
        ('nocobase_sync_jobs', 'completed_at'),
        ('nocobase_sync_audit', 'created_at'),
    ):
        rows = conn.execute(
            f'SELECT id, {column} FROM {table} WHERE {column} != ?', ('',)
        ).fetchall()
        for row in rows:
            timestamp = _timestamp(row[column])
            if timestamp != row[column]:
                conn.execute(f'UPDATE {table} SET {column} = ? WHERE id = ?', (timestamp, row['id']))


def _failure_details(failure):
    if isinstance(failure, Mapping):
        get = failure.get
    else:
        get = lambda name, default='': getattr(failure, name, default)
    return {
        'stage': str(get('stage', '') or ''),
        'error_type': str(get('error_type', '') or ''),
        'diagnostic_id': str(get('diagnostic_id', '') or ''),
        'pausable': bool(get('pausable', False)),
    }


def _audit(conn, job, outcome, diagnostic_id, timestamp):
    conn.execute(
        '''INSERT INTO nocobase_sync_audit(
            entity, archive_no, operation, outcome, diagnostic_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)''',
        (job['entity'], job['archive_no'], job['operation'], outcome, diagnostic_id, timestamp),
    )
