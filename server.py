"""Campus recruitment LAN service. Python 3.10+, standard library only."""
import argparse
import csv
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import secrets
import sys
import base64
import zipfile
import socket
import ipaddress
import sqlite3
import time
import threading
import dify_client
from features import load_features
from features.candidates import experiences as candidate_experiences
from features.candidates import project_experiences as candidate_project_experiences
from features.candidates import positions as candidate_positions
from features.resume_documents import dify_mapping
from features.resume_documents import file_types as resume_file_types
from features.resume_documents.filename_position import infer_position
from datetime import datetime
from contextlib import contextmanager
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as _ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.runtime'))
from excel_io import prepare_rows, workbook_bytes
import qrcode
import qrcode.image.svg
DATA = Path(os.environ.get('RECRUIT_DATA_DIR', ROOT / 'data'))
FEATURES = load_features(ROOT / 'features')
SCHEMAS = {name: feature.schema for name, feature in FEATURES.items()}
ENABLED_SCHEMAS = {name: feature.schema for name, feature in FEATURES.items() if feature.enabled}
LOCATIONS = json.loads((ROOT / 'web' / 'china-locations.json').read_text(encoding='utf-8'))
SESSIONS = {}
SESSION_USERS = {}
ATTEMPTS = {}
IMPORTS = {}
RECOGNITION_LOCK = threading.Lock()
INTERNAL_APPLICATION_FIELDS = {'screening', 'needs_first_interview', 'status', 'is_elite'}


class ThreadingHTTPServer(_ThreadingHTTPServer):
    """Do not let multiple recruitment servers silently share one Windows port."""
    allow_reuse_address = False
    allow_reuse_port = False


def order_lan_ipv4_addresses(preferred, addresses):
    ordered = [preferred, *addresses]
    result = []
    for value in ordered:
        try:
            address = ipaddress.ip_address(str(value or '').strip())
        except ValueError:
            continue
        if (address.version != 4 or address.is_loopback or address.is_link_local or
                address.is_unspecified or address.is_multicast or address.is_reserved or
                str(address) == '255.255.255.255'):
            continue
        text = str(address)
        if text not in result:
            result.append(text)
    return result


def local_ipv4_addresses():
    preferred = ''
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect(('1.1.1.1', 80))
            preferred = route.getsockname()[0]
    except OSError:
        pass
    try:
        discovered = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        discovered = []
    return order_lan_ipv4_addresses(preferred, discovered)


def public_base_url(request_host, port):
    configured = os.environ.get('RECRUIT_PUBLIC_URL', '').strip().rstrip('/')
    parsed_configured = urlparse(configured)
    if configured and parsed_configured.scheme in ('http', 'https') and parsed_configured.netloc:
        return configured
    request_host = str(request_host or '').strip()
    parsed_host = urlparse('http://' + request_host)
    if parsed_host.hostname and parsed_host.hostname not in ('localhost', '127.0.0.1', '::1'):
        return 'http://' + request_host.rstrip('/')
    addresses = local_ipv4_addresses()
    return f'http://{addresses[0]}:{port}' if addresses else f'http://localhost:{port}'


def export_rows(conn, entity, ids=None, query=''):
    if ids is None:
        rows = [dict(row) for row in conn.execute(f'SELECT * FROM {entity} ORDER BY id DESC')]
    else:
        if not isinstance(ids, list) or not 1 <= len(ids) <= 1000 or any(type(item) is not int or item <= 0 for item in ids):
            raise ValueError('请选择1至1000条有效记录导出')
        ids = list(dict.fromkeys(ids))
        placeholders = ','.join('?' for _ in ids)
        found = {row['id']: dict(row) for row in conn.execute(f'SELECT * FROM {entity} WHERE id IN ({placeholders})', ids)}
        if any(identifier not in found for identifier in ids):
            raise ValueError('所选记录已不存在，请刷新后重新选择')
        rows = [found[identifier] for identifier in ids]
    if entity in ('candidates', 'applications', 'interviews', 'employees', 'resume_documents'):
        rows = [candidate_display(row, conn, entity) for row in rows]
    for field in SCHEMAS[entity]['fields']:
        if field.get('ref'):
            names = {row['id']: row['name'] for row in conn.execute(f"SELECT id,name FROM {field['ref']}")}
            for row in rows:
                row[field['key'] + '_label'] = names.get(row[field['key']], '')
    if query:
        secret_keys = {field['key'] for field in SCHEMAS[entity]['fields'] if field.get('type') == 'password'}
        rows = [row for row in rows if query.lower() in ' '.join(str(value) for key, value in row.items() if key not in secret_keys).lower()]
    return rows
EDUCATION_TABLES = {
    'candidates': ('candidate_educations', 'candidate_id'),
    'applications': ('application_educations', 'application_id'),
    'interviews': ('interview_educations', 'interview_id'),
    'employees': ('employee_educations', 'employee_id'),
}

APPLICATION_COPY_FIELDS = FEATURES['applications'].service.APPLICATION_COPY_FIELDS


def public_application_fields():
    return FEATURES['applications'].service.public_fields(SCHEMAS['applications'], INTERNAL_APPLICATION_FIELDS)


def identity_details(value):
    return FEATURES['candidates'].service.identity_details(value)


def application_prefill(candidate, conn):
    return FEATURES['applications'].service.prefill(candidate, conn, education_rows)


def language_summary(application):
    return FEATURES['applications'].service.language_summary(application)


def interview_prefill(candidate, conn):
    return FEATURES['interviews'].service.prefill(
        candidate, conn, application_prefill, education_rows,
        SCHEMAS['interviews'], APPLICATION_COPY_FIELDS,
    )


def interview_source(identity, conn):
    return FEATURES['interviews'].service.source(identity, conn, identity_details)


def interview_source_values(application):
    return FEATURES['interviews'].service.source_values(application, language_summary)


def employee_source_values(application):
    return FEATURES['employees'].service.source_values(application, language_summary)


def education_rows(conn, entity, record_id):
    table, foreign_key = EDUCATION_TABLES[entity]
    return [dict(row) for row in conn.execute(f'SELECT education,school_name,major,enrollment,graduation FROM {table} WHERE {foreign_key}=? ORDER BY position,id', (record_id,))]

@contextmanager
def db():
    conn = sqlite3.connect(DATA / 'recruitment.db', timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def release_deleted_candidate_imports(conn):
    orphaned = [row['source_id'] for row in conn.execute(
        'SELECT imports.source_id FROM resume_imports imports '
        'LEFT JOIN candidates candidate ON candidate.id=imports.candidate_id WHERE candidate.id IS NULL'
    )]
    if not orphaned:
        return
    for source_id in orphaned:
        live = conn.execute('''SELECT imports.candidate_id
            FROM resume_documents document
            JOIN resume_imports imports ON imports.source_id=document.source_id OR imports.source_id=document.file_hash
            JOIN candidates candidate ON candidate.id=imports.candidate_id
            WHERE document.source_id=? OR document.file_hash=?
            ORDER BY imports.candidate_id LIMIT 1''', (source_id, source_id)).fetchone()
        if live:
            conn.execute('UPDATE resume_imports SET candidate_id=? WHERE source_id=?', (live['candidate_id'], source_id))
    now = datetime.now().isoformat(timespec='microseconds')
    conn.execute(
        """UPDATE resume_documents SET status='待识别',updated_at=?
        WHERE EXISTS (SELECT 1 FROM resume_imports orphan
              LEFT JOIN candidates missing ON missing.id=orphan.candidate_id
              WHERE missing.id IS NULL AND (orphan.source_id=resume_documents.source_id OR orphan.source_id=resume_documents.file_hash))
          AND NOT EXISTS (SELECT 1 FROM resume_imports live
              JOIN candidates present ON present.id=live.candidate_id
              WHERE live.source_id=resume_documents.source_id OR live.source_id=resume_documents.file_hash)""",
        (now,),
    )
    conn.execute('''DELETE FROM resume_imports WHERE source_id IN (
        SELECT imports.source_id FROM resume_imports imports
        LEFT JOIN candidates candidate ON candidate.id=imports.candidate_id WHERE candidate.id IS NULL
    )''')


def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        old_school_columns = {row['name'] for row in conn.execute('PRAGMA table_info(schools)')}
        old_candidate_columns = {row['name'] for row in conn.execute('PRAGMA table_info(candidates)')}
        old_application_columns = {row['name'] for row in conn.execute('PRAGMA table_info(applications)')}
        old_interview_columns = {row['name'] for row in conn.execute('PRAGMA table_info(interviews)')}
        old_employee_columns = {row['name'] for row in conn.execute('PRAGMA table_info(employees)')}
        if old_employee_columns and 'name' not in old_employee_columns:
            backup = sqlite3.connect(DATA / ('before-employee-update-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db'))
            try:
                conn.backup(backup)
            finally:
                backup.close()
        if old_interview_columns and 'name' not in old_interview_columns:
            backup = sqlite3.connect(DATA / ('before-interview-update-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db'))
            try:
                conn.backup(backup)
            finally:
                backup.close()
        if old_application_columns and 'name' not in old_application_columns:
            backup = sqlite3.connect(DATA / ('before-application-update-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db'))
            try:
                conn.backup(backup)
            finally:
                backup.close()
        if old_candidate_columns and 'birthdate' not in old_candidate_columns:
            backup = sqlite3.connect(DATA / ('before-candidate-update-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db'))
            try:
                conn.backup(backup)
            finally:
                backup.close()
        if old_school_columns and 'region' not in old_school_columns:
            # Back up the committed database before the first school schema migration.
            backup_path = DATA / ('before-school-update-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db')
            with sqlite3.connect(backup_path) as backup:
                conn.backup(backup)
            backup.close()
        conn.execute('CREATE TABLE IF NOT EXISTS admin (id INTEGER PRIMARY KEY, salt TEXT, password TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE, salt TEXT NOT NULL, password TEXT NOT NULL, created_at TEXT NOT NULL)')
        if 'is_admin' not in {row['name'] for row in conn.execute('PRAGMA table_info(members)')}:
            conn.execute('ALTER TABLE members ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0')
        for account_table in ('admin', 'members'):
            if 'nickname' not in {row['name'] for row in conn.execute(f'PRAGMA table_info({account_table})')}:
                conn.execute(f"ALTER TABLE {account_table} ADD COLUMN nickname TEXT NOT NULL DEFAULT ''")
            if 'phone' not in {row['name'] for row in conn.execute(f'PRAGMA table_info({account_table})')}:
                conn.execute(f"ALTER TABLE {account_table} ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
        conn.execute('CREATE TABLE IF NOT EXISTS attachments (id TEXT PRIMARY KEY, name TEXT NOT NULL, content BLOB NOT NULL)')
        for entity, spec in SCHEMAS.items():
            columns = []
            stored_fields = [field for field in spec['fields'] if not field.get('virtual')]
            for field in stored_fields:
                column = field['key'] + (' INTEGER' if field.get('ref') else ' TEXT')
                if field.get('ref'):
                    column += ' REFERENCES ' + field['ref'] + '(id) ON DELETE RESTRICT'
                columns.append(column)
            conn.execute(f"CREATE TABLE IF NOT EXISTS {entity} (id INTEGER PRIMARY KEY AUTOINCREMENT, {', '.join(columns)}, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
            existing = {row['name'] for row in conn.execute(f'PRAGMA table_info({entity})')}
            for field, column in zip(stored_fields, columns):
                if field['key'] not in existing:
                    conn.execute(f'ALTER TABLE {entity} ADD COLUMN {column}')
            for field in spec['fields']:
                if field.get('ref'):
                    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{entity}_{field['key']} ON {entity}({field['key']})")
        for entity in ('candidates', 'applications', 'interviews', 'employees'):
            conn.execute(
                f"UPDATE {entity} SET birthdate=substr(birthdate,1,7) "
                "WHERE birthdate GLOB '????-??-*'"
            )
        if old_candidate_columns and 'age' not in old_candidate_columns:
            for row in conn.execute('SELECT id,birthdate FROM candidates').fetchall():
                age = age_from_birthdate(row['birthdate'])
                if age != '':
                    conn.execute('UPDATE candidates SET age=? WHERE id=?', (str(age), row['id']))
        conn.execute("UPDATE resume_documents SET created_by='历史记录' WHERE created_by IS NULL OR created_by=''")
        recruitment_names = (('\u6821\u62db', '校园招聘'), ('\u793e\u62db', '社会招聘'))
        for entity in ('candidates', 'resume_documents'):
            conn.executemany(f'UPDATE {entity} SET recruitment_type=? WHERE recruitment_type=?', ((new, old) for old, new in recruitment_names))
        political_status_names = FEATURES['candidates'].service.POLITICAL_STATUS_ALIASES
        for entity in ('candidates', 'applications', 'interviews'):
            conn.executemany(
                f'UPDATE {entity} SET political_status=? WHERE political_status=?',
                ((formal, short) for short, formal in political_status_names.items()),
            )
        migrated_resumes = []
        for row in conn.execute("SELECT id,resume FROM resume_documents WHERE source_id IS NULL OR source_id='' ").fetchall():
            attachment = conn.execute('SELECT content FROM attachments WHERE id=?', (row['resume'],)).fetchone()
            source_id = hashlib.sha256(attachment['content']).hexdigest() if attachment else 'legacy-' + secrets.token_hex(16)
            if conn.execute('SELECT 1 FROM resume_documents WHERE source_id=?', (source_id,)).fetchone():
                source_id += '-legacy-' + str(row['id'])
            conn.execute('UPDATE resume_documents SET source_id=?,status=? WHERE id=?', (source_id, '待识别', row['id']))
            migrated_resumes.append((row['id'], source_id, row['resume']))
        conn.execute('DROP INDEX IF EXISTS idx_resume_source')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_resume_source_lookup ON resume_documents(source_id)')
        for row in conn.execute("SELECT id,resume FROM resume_documents WHERE file_hash IS NULL OR file_hash='' ").fetchall():
            attachment = conn.execute('SELECT content FROM attachments WHERE id=?', (row['resume'],)).fetchone()
            if attachment:
                conn.execute('UPDATE resume_documents SET file_hash=? WHERE id=?', (hashlib.sha256(attachment['content']).hexdigest(), row['id']))
        conn.execute('CREATE TABLE IF NOT EXISTS resume_imports(source_id TEXT PRIMARY KEY, candidate_id INTEGER REFERENCES candidates(id) ON DELETE SET NULL)')
        release_deleted_candidate_imports(conn)
        for entity, (table, foreign_key) in EDUCATION_TABLES.items():
            conn.execute(f'''CREATE TABLE IF NOT EXISTS {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {foreign_key} INTEGER NOT NULL REFERENCES {entity}(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                education TEXT NOT NULL,
                school_name TEXT NOT NULL,
                major TEXT NOT NULL,
                enrollment TEXT NOT NULL DEFAULT '',
                graduation TEXT NOT NULL DEFAULT ''
            )''')
            education_columns = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})')}
            for column in ('enrollment', 'graduation'):
                if column not in education_columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_record ON {table}({foreign_key},position)')
            conn.execute(f"""INSERT INTO {table}({foreign_key},position,education,school_name,major,enrollment,graduation)
                SELECT id,1,COALESCE(education,''),COALESCE(school_name,''),COALESCE(major,''),'','' FROM {entity} source
                WHERE NOT EXISTS (SELECT 1 FROM {table} history WHERE history.{foreign_key}=source.id)
                  AND (COALESCE(source.education,'')!='' OR COALESCE(source.school_name,'')!='' OR COALESCE(source.major,'')!='')""")
        candidate_experiences.ensure_tables(conn)
        candidate_project_experiences.ensure_table(conn)
        for document_id, source_id, attachment_id in migrated_resumes:
            candidate = conn.execute('SELECT id FROM candidates WHERE resume=? ORDER BY id LIMIT 1', (attachment_id,)).fetchone() if attachment_id else None
            if candidate:
                conn.execute('INSERT OR IGNORE INTO resume_imports(source_id,candidate_id) VALUES(?,?)', (source_id, candidate['id']))
                conn.execute("UPDATE resume_documents SET status='已入库' WHERE id=?", (document_id,))
        if old_school_columns and 'region' not in old_school_columns:
            conn.execute('ALTER TABLE schools ADD COLUMN legacy_level TEXT')
            conn.execute('UPDATE schools SET legacy_level=level')
            conn.execute("UPDATE schools SET level=CASE WHEN level='高职专科' THEN '专科' WHEN level IN ('专科','本科') THEN level ELSE '' END")
            conn.execute("UPDATE schools SET province_city=COALESCE(province,'')")
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_phone ON candidates(phone)')
        if old_candidate_columns and 'birthdate' not in old_candidate_columns:
            conn.execute('ALTER TABLE candidates ADD COLUMN legacy_education TEXT')
            conn.execute('UPDATE candidates SET legacy_education=education')
            conn.execute("UPDATE candidates SET education=CASE WHEN education='大专' THEN '专科' WHEN education IN ('专科','本科','硕士','博士') THEN education ELSE '' END")
            conn.execute("UPDATE candidate_educations SET education='专科' WHERE education='大专'")
            conn.execute("UPDATE candidates SET graduation=substr(graduation,1,7) WHERE length(graduation)=10")
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_employees_candidate ON employees(candidate_id)')
        if old_employee_columns and 'name' not in old_employee_columns:
            for row in conn.execute('SELECT * FROM employees').fetchall():
                candidate = conn.execute('SELECT * FROM candidates WHERE id=?', (row['candidate_id'],)).fetchone()
                if candidate:
                    keys = ('name', 'gender', 'birthdate', 'phone', 'school_name', 'education', 'major', 'hometown', 'language', 'channel')
                    values = {key: candidate[key] for key in keys if key in candidate.keys()}
                    conn.execute(f"UPDATE employees SET {','.join(key+'=?' for key in values)} WHERE id=?", [*values.values(), row['id']])
        if old_application_columns and 'name' not in old_application_columns:
            conn.execute('ALTER TABLE applications ADD COLUMN legacy_channel TEXT')
            conn.execute('UPDATE applications SET legacy_channel=channel')
            for row in conn.execute('SELECT * FROM applications').fetchall():
                candidate = conn.execute('SELECT * FROM candidates WHERE id=?', (row['candidate_id'],)).fetchone()
                values = application_prefill(candidate, conn) if candidate else {}
                histories = values.pop('education_experiences', None)
                values['channel'] = {'校园宣讲会':'校园线下', '校园双选会':'校园线下', '学生自主登记':'校园平台'}.get(row['channel'], values.get('channel', ''))
                values['position'] = row['position'] or values.get('position', '')
                values['resume'] = candidate['resume'] if candidate else ''
                conn.execute(f"UPDATE applications SET {','.join(key+'=?' for key in values)} WHERE id=?", [*values.values(), row['id']])
                if histories:
                    save_education_experiences(conn, 'applications', row['id'], histories, values)
        application_columns = {row['name'] for row in conn.execute('PRAGMA table_info(applications)')}
        if 'legacy_data_status' not in application_columns:
            conn.execute('ALTER TABLE applications ADD COLUMN legacy_data_status TEXT')
        conn.execute("UPDATE applications SET legacy_data_status=status, status=CASE WHEN status IN ('已筛选','已安排面试','已结束') THEN '已生效' ELSE '草稿' END WHERE status IS NULL OR status NOT IN ('草稿','已生效')")
        if old_interview_columns and 'name' not in old_interview_columns:
            conn.execute('ALTER TABLE interviews ADD COLUMN legacy_status TEXT')
            for row in conn.execute('SELECT * FROM interviews').fetchall():
                candidate = conn.execute('SELECT * FROM candidates WHERE id=?', (row['candidate_id'],)).fetchone()
                values = interview_prefill(candidate, conn) if candidate else {}
                values.pop('education_experiences', None)
                values.update(legacy_status=row['status'], status='草稿' if row['status'] in (None, '', '待面试') else '已生效')
                values['position'] = row['position'] or values.get('position', '')
                values['basic_situation'] = '\n'.join(text for text in (row['evaluation'], row['notes']) if text)
                conn.execute(f"UPDATE interviews SET {','.join(key+'=?' for key in values)} WHERE id=?", [*values.values(), row['id']])
        education_parent_times = {
            'candidates': ('graduation',),
            'applications': ('enrollment', 'graduation'),
            'interviews': ('graduation',),
        }
        for entity, time_fields in education_parent_times.items():
            table, foreign_key = EDUCATION_TABLES[entity]
            parent_columns = {row['name'] for row in conn.execute(f'PRAGMA table_info({entity})')}
            available = tuple(field for field in time_fields if field in parent_columns)
            if not available:
                continue
            for record in conn.execute(f'SELECT * FROM {entity}').fetchall():
                highest = conn.execute(f"""SELECT * FROM {table} WHERE {foreign_key}=?
                    ORDER BY CASE education WHEN '博士' THEN 4 WHEN '硕士' THEN 3 WHEN '本科' THEN 2 WHEN '专科' THEN 1 ELSE 0 END DESC,position,id LIMIT 1""", (record['id'],)).fetchone()
                if not highest and any(record[field] for field in available):
                    times = {field: record[field] or '' for field in available}
                    conn.execute(f'''INSERT INTO {table}({foreign_key},position,education,school_name,major,enrollment,graduation)
                        VALUES(?,1,'','','',?,?)''', (record['id'], times.get('enrollment', ''), times.get('graduation', '')))
                    highest = conn.execute(f'SELECT * FROM {table} WHERE {foreign_key}=? ORDER BY position,id LIMIT 1', (record['id'],)).fetchone()
                if highest:
                    updates = {field: record[field] for field in available if record[field] and not highest[field]}
                    if updates:
                        conn.execute(f"UPDATE {table} SET {','.join(field+'=?' for field in updates)} WHERE id=?", [*updates.values(), highest['id']])
            if entity != 'candidates':
                conn.execute(f"UPDATE {entity} SET {','.join(field+"=''" for field in available)}")
        for entity in EDUCATION_TABLES:
            for record in conn.execute(f'SELECT * FROM {entity}').fetchall():
                save_education_experiences(conn, entity, record['id'], None, dict(record))
        candidate_positions.migrate(conn)
        conn.execute('CREATE TABLE IF NOT EXISTS system_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        archive_format = conn.execute("SELECT value FROM system_settings WHERE key='archive_number_format'").fetchone()
        migrate_archive_numbers = not archive_format or archive_format['value'] != 'recruitment-date-sequence-v1'
        if migrate_archive_numbers:
            conn.execute('CREATE TABLE IF NOT EXISTS archive_numbers(number TEXT PRIMARY KEY)')
            conn.execute('DELETE FROM archive_numbers')
            for entity in ARCHIVE_ENTITIES:
                conn.execute(f"UPDATE {entity} SET archive_no='' ")
        synchronize_archives(conn)
        if migrate_archive_numbers:
            conn.execute("INSERT OR REPLACE INTO system_settings(key,value) VALUES('archive_number_format','recruitment-date-sequence-v1')")
        if not conn.execute('SELECT 1 FROM admin').fetchone():
            password = os.environ.get('RECRUIT_ADMIN_PASSWORD') or secrets.token_urlsafe(12)
            salt = secrets.token_hex(16)
            digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 300000).hex()
            conn.execute('INSERT INTO admin(id,salt,password) VALUES(1,?,?)', (salt, digest))
            (DATA / 'initial-password.txt').write_text(password, encoding='utf-8')

def validate(entity, payload, conn):
    if not isinstance(payload, dict):
        raise ValueError('提交内容必须为对象')
    payload = dict(payload)
    if entity in candidate_positions.POSITION_ENTITIES:
        payload = candidate_positions.normalize_payload(payload)
    if entity == 'candidates':
        payload = FEATURES['candidates'].service.normalize_recruitment(payload)
    if entity == 'resume_documents':
        payload = FEATURES['resume_documents'].service.normalize_recruitment(payload, FEATURES['candidates'].service)
    if entity in ('candidates', 'applications', 'interviews'):
        payload.setdefault('status', '待筛选' if entity == 'candidates' else '草稿')
        payload['political_status'] = FEATURES['candidates'].service.normalize_political_status(
            payload.get('political_status')
        )
        if payload.get('education') == '大专':
            payload['education'] = '专科'
    if entity == 'applications':
        payload = FEATURES['applications'].service.prepare_validation(payload, conn, application_prefill)
    if entity == 'interviews':
        payload = FEATURES['interviews'].service.prepare_validation(payload, conn, identity_details, interview_source_values)
    if entity == 'employees':
        payload = FEATURES['employees'].service.prepare_validation(payload, conn, interview_source, employee_source_values)
    if entity in ('applications', 'interviews', 'employees') and payload.get('identity_card'):
        payload.update(identity_details(payload['identity_card']))
    if entity == 'schools':
        payload = FEATURES['schools'].service.normalize_location(payload, LOCATIONS)
    result = {}
    for field in SCHEMAS[entity]['fields']:
        if field.get('virtual'):
            continue
        key = field['key']
        value = '' if key == 'archive_no' else payload.get(key, '')
        if isinstance(value, (dict, list, bool)):
            raise ValueError(field['label'] + '格式不正确')
        value = str(value) if value is not None else ''
        if field.get('type') != 'password':
            value = value.strip()
        if field.get('required') and not value:
            raise ValueError('请填写' + field['label'])
        if len(value) > field.get('maxLength', 5000 if field.get('type') == 'textarea' else 300):
            raise ValueError(field['label'] + '内容过长')
        if value and field.get('options') and value not in field['options']:
            raise ValueError(field['label'] + '选项无效')
        if value and field.get('type') == 'date':
            try:
                datetime.strptime(value, '%Y-%m-%d')
            except ValueError:
                raise ValueError(field['label'] + '日期无效')
            if key == 'birthdate' and datetime.strptime(value, '%Y-%m-%d').date() > datetime.now().date():
                raise ValueError('出生日期不能晚于今天')
        if value and field.get('type') == 'month':
            match = re.fullmatch(r'(\d{4})[-/年](\d{1,2})(?:月|[-/]\d{1,2})?', value)
            if not match or not 1 <= int(match[2]) <= 12 or int(match[1]) < 1:
                raise ValueError(field['label'] + '须为有效年月，如2026-07')
            value = f'{int(match[1]):04d}-{int(match[2]):02d}'
            if key == 'birthdate' and value > datetime.now().strftime('%Y-%m'):
                raise ValueError('出生日期不能晚于本月')
        if value and field.get('type') == 'datetime-local':
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?', value):
                raise ValueError(field['label'] + '须为有效日期时间')
            try:
                value = datetime.fromisoformat(value).isoformat(timespec=field.get('precision', 'seconds'))
            except ValueError:
                raise ValueError(field['label'] + '须为有效日期时间')
        if value and key == 'phone' and not re.fullmatch(r'(?:\+?86[- ]?)?(?:1[3-9]\d{9}|0\d{2,3}[- ]?\d{7,8}(?:-\d{1,6})?)', value):
            raise ValueError('请填写有效手机号或带区号的固定电话')
        if value and field.get('type') == 'email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('邮箱格式不正确')
        if value and field.get('type') == 'url':
            parsed = urlparse(value)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc or re.search(r'\s', value):
                raise ValueError(field['label'] + '须为完整的 http:// 或 https:// 地址')
        if value and field.get('type') == 'integer' and not re.fullmatch(r'[1-9][0-9]*', value):
            raise ValueError(field['label'] + '须为正整数')
        if value and field.get('type') == 'number':
            try:
                number = float(value)
                if not field.get('min', 0) <= number <= field.get('max', 100):
                    raise ValueError()
                if field.get('step') == 1 and not number.is_integer():
                    raise ValueError()
            except ValueError:
                raise ValueError(field['label'] + f"应在{field.get('min', 0)}至{field.get('max', 100)}之间")
            if field.get('step') == 1:
                value = str(int(number))
        if field.get('ref'):
            if value and (not value.isdigit() or not conn.execute(f"SELECT id FROM {field['ref']} WHERE id=?", (value,)).fetchone()):
                raise ValueError(field['label'] + '不存在，请重新选择')
            value = int(value) if value else None
        result[key] = value
    if entity == 'applications' and result.get('enrollment') and result.get('graduation') and result['enrollment'] > result['graduation']:
        raise ValueError('入学时间不能晚于毕业时间')
    return result

def age_from_birthdate(value):
    if not value:
        return ''
    match = re.fullmatch(r'(\d{4})-(\d{2})(?:-\d{2})?', str(value))
    if not match:
        return ''
    year, month = int(match[1]), int(match[2])
    if year < 1 or not 1 <= month <= 12:
        return ''
    today = datetime.now().date()
    return today.year - year - (today.month < month)


def candidate_display(row, conn, entity='candidates'):
    row = dict(row)
    if entity == 'candidates':
        row.pop('experience', None)
    if entity in EDUCATION_TABLES:
        table, foreign_key = EDUCATION_TABLES[entity]
        row['education_experiences'] = [dict(item) for item in conn.execute(f'SELECT education,school_name,major,enrollment,graduation FROM {table} WHERE {foreign_key}=? ORDER BY position,id', (row['id'],))]
        if entity != 'candidates' and row['education_experiences']:
            rank = {'专科': 1, '本科': 2, '硕士': 3, '博士': 4}
            highest = min(enumerate(row['education_experiences']), key=lambda item: (-rank.get(item[1]['education'], 0), item[0]))[1]
            row['graduation'] = highest['graduation']
    if entity == 'candidates':
        row.update(candidate_experiences.read(conn, row['id']))
        if row.get('recruitment_type') == '社会招聘':
            row['project_experiences'] = candidate_project_experiences.read(conn, row['id'])
    if entity in ('applications', 'interviews') and row.get('identity_card'):
        try:
            row.update(identity_details(row['identity_card']))
        except ValueError:
            pass  # Keep legacy values visible until the record is corrected.
    row['created_date'] = row.get('created_at', '').replace('T', ' ')
    if entity == 'candidates':
        row['age'] = row.get('age') or ''
    else:
        row['age'] = age_from_birthdate(row.get('birthdate'))
    row['cohort'] = row['graduation'][:4] + '届' if row.get('graduation') and (entity != 'candidates' or row.get('recruitment_type') == '校园招聘') else ''
    for field in SCHEMAS[entity]['fields']:
        if field.get('type') == 'attachment':
            attachment = conn.execute('SELECT name FROM attachments WHERE id=?', (row.get(field['key']) or '',)).fetchone()
            row[field['key'] + '_name'] = attachment['name'] if attachment else ''
    return row

def candidate_values(payload, conn, existing=None):
    return attachment_values('candidates', payload, conn, existing)

def education_experience_values(payload, entity=None, required_fields=None):
    rows = payload.get('education_experiences') if isinstance(payload, dict) else None
    if rows is None:
        return None
    if not isinstance(rows, list) or len(rows) > 10:
        raise ValueError('教育经历最多填写10条')
    if required_fields is None and entity:
        required_fields = {field['key'] for field in SCHEMAS[entity]['fields'] if field.get('required')} & {'education', 'school_name', 'major'}
    required_fields = set(required_fields or ()) & {'education', 'school_name', 'major'}
    labels = {'education': '学历', 'school_name': '毕业院校', 'major': '专业'}
    result = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'第{index}条教育经历格式不正确')
        values = {key: str(row.get(key) or '').strip() for key in ('education', 'school_name', 'major', 'enrollment', 'graduation')}
        if not any(values.values()):
            continue
        if values['education'] == '大专':
            values['education'] = '专科'
        if values['education'] and values['education'] not in ('专科', '本科', '硕士', '博士'):
            raise ValueError(f'请选择第{index}条教育经历的学历')
        for key in required_fields:
            if not values[key]:
                raise ValueError(f'请填写第{index}条教育经历的{labels[key]}')
        if any(len(value) > 300 for value in values.values()):
            raise ValueError(f'第{index}条教育经历内容过长')
        for key, label in (('enrollment', '入学时间'), ('graduation', '毕业时间')):
            value = values[key]
            match = re.fullmatch(r'(\d{4})[-/年](\d{1,2})(?:月|[-/]\d{1,2})?', value) if value else None
            if value and (not match or not 1 <= int(match[2]) <= 12 or int(match[1]) < 1):
                raise ValueError(f'第{index}条教育经历的{label}须为有效年月，如2026-07')
            if match:
                values[key] = f'{int(match[1]):04d}-{int(match[2]):02d}'
        if values['enrollment'] and values['graduation'] and values['enrollment'] > values['graduation']:
            raise ValueError(f'第{index}条教育经历的入学时间不能晚于毕业时间')
        result.append(values)
    if required_fields and not result:
        raise ValueError('请至少填写一条完整的教育经历')
    return result

def save_education_experiences(conn, entity, record_id, rows, fallback=None):
    table, foreign_key = EDUCATION_TABLES[entity]
    if rows is None:
        existing = conn.execute(f'SELECT id,education FROM {table} WHERE {foreign_key}=? ORDER BY position,id', (record_id,)).fetchall()
        if existing:
            if fallback and all(fallback.get(key) for key in ('education', 'school_name', 'major')):
                matched = next((item for item in existing if item['education'] == fallback['education']), None)
                if matched:
                    conn.execute(f"""UPDATE {table} SET school_name=?,major=?,
                        enrollment=CASE WHEN enrollment='' THEN ? ELSE enrollment END,
                        graduation=CASE WHEN graduation='' THEN ? ELSE graduation END WHERE id=?""",
                        (fallback['school_name'], fallback['major'], fallback.get('enrollment', ''), fallback.get('graduation', ''), matched['id']))
                else:
                    conn.execute(f'INSERT INTO {table}({foreign_key},position,education,school_name,major,enrollment,graduation) VALUES(?,?,?,?,?,?,?)',
                                 (record_id, len(existing) + 1, fallback['education'], fallback['school_name'], fallback['major'], fallback.get('enrollment', ''), fallback.get('graduation', '')))
        else:
            fallback = fallback or {}
            if any(fallback.get(key) for key in ('education', 'school_name', 'major')):
                rows = [{key: fallback.get(key, '') for key in ('education', 'school_name', 'major', 'enrollment', 'graduation')}]
            else:
                return
    if rows is not None:
        conn.execute(f'DELETE FROM {table} WHERE {foreign_key}=?', (record_id,))
        conn.executemany(f'INSERT INTO {table}({foreign_key},position,education,school_name,major,enrollment,graduation) VALUES(?,?,?,?,?,?,?)',
                         [(record_id, index, row['education'], row['school_name'], row['major'], row['enrollment'], row['graduation']) for index, row in enumerate(rows, 1)])
    highest = conn.execute(f"""SELECT education,school_name,major,enrollment,graduation FROM {table} WHERE {foreign_key}=?
        ORDER BY CASE education WHEN '博士' THEN 4 WHEN '硕士' THEN 3 WHEN '本科' THEN 2 WHEN '专科' THEN 1 ELSE 0 END DESC,position,id LIMIT 1""", (record_id,)).fetchone()
    if highest:
        if entity == 'candidates':
            recruitment_type = conn.execute(
                'SELECT recruitment_type FROM candidates WHERE id=?', (record_id,)
            ).fetchone()['recruitment_type']
            graduation = highest['graduation'] if recruitment_type == '校园招聘' else ''
            conn.execute(
                f'UPDATE {entity} SET education=?,school_name=?,major=?,graduation=? WHERE id=?',
                (highest['education'], highest['school_name'], highest['major'], graduation, record_id),
            )
        else:
            conn.execute(f'UPDATE {entity} SET education=?,school_name=?,major=? WHERE id=?', (highest['education'], highest['school_name'], highest['major'], record_id))
    elif rows is not None:
        fields = ('education', 'school_name', 'major', 'graduation') if entity == 'candidates' else ('education', 'school_name', 'major')
        assignments = ','.join(field + "=''" for field in fields)
        conn.execute(f'UPDATE {entity} SET {assignments} WHERE id=?', (record_id,))

def candidate_education_values(payload):
    return education_experience_values(payload, 'candidates')

def save_candidate_educations(conn, candidate_id, rows, fallback=None):
    save_education_experiences(conn, 'candidates', candidate_id, rows, fallback)

def sync_application_educations_to_candidate(conn, application_id):
    application = conn.execute('SELECT candidate_id FROM applications WHERE id=?', (application_id,)).fetchone()
    if application and application['candidate_id']:
        rows = education_rows(conn, 'applications', application_id)
        if rows:
            save_education_experiences(conn, 'candidates', application['candidate_id'], rows)

def attachment_values(entity, payload, conn, existing=None):
    values = dict(existing or {})
    values.update(payload)
    if entity == 'resume_documents':
        upload = payload.get('_resume_upload')
        if isinstance(upload, dict):
            values['name'] = str(upload.get('name', '')).replace('\\', '/').split('/')[-1]
            if not str(values.get('position') or '').strip():
                values['position'] = infer_position(values['name'])
        elif existing:
            attachment = conn.execute('SELECT name FROM attachments WHERE id=?', (existing.get('resume'),)).fetchone()
            if attachment:
                values['name'] = attachment['name']
        else:
            values['name'] = '待上传简历'
    if entity == 'applications' and 'phone' in values:
        match = conn.execute('SELECT id FROM candidates WHERE phone=?', (str(values.get('phone') or '').strip(),)).fetchone()
        values['candidate_id'] = match['id'] if match else None
    attachment_fields = [field for field in SCHEMAS[entity]['fields'] if field.get('type') == 'attachment']
    for field in attachment_fields:
        values[field['key']] = (existing or {}).get(field['key']) or ''
    if entity == 'applications' and (payload.get('_sync_attachments') is True or not existing or str(values.get('phone') or '').strip() != str(existing.get('phone') or '').strip()):
        values['resume'] = ''
        candidate = conn.execute('SELECT resume FROM candidates WHERE id=?', (values.get('candidate_id'),)).fetchone()
        if candidate:
            values['resume'] = candidate['resume'] or ''
    if entity == 'interviews' and (payload.get('_sync_attachments') is True or not existing or str(values.get('identity_card') or '').strip().upper() != str(existing.get('identity_card') or '').strip().upper()):
        source = interview_source(values.get('identity_card'), conn)
        for field in attachment_fields:
            values[field['key']] = source[field['key']] if source else ''
    result = validate(entity, values, conn)
    for field in attachment_fields:
        key = field['key']
        upload = payload.get('_' + key + '_upload')
        if upload is not None:
            result[key] = save_attachment(upload, field, conn)
        elif payload.get('_remove_' + key) is True:
            result[key] = ''
    if entity == 'resume_documents' and not result.get('resume'):
        raise ValueError('请上传简历附件')
    if entity == 'resume_documents':
        changed = existing and result['resume'] != existing.get('resume')
        if existing and existing.get('status') == '已入库' and changed:
            raise ValueError('已入库简历不能替换附件，请新增简历')
        if not existing or changed:
            content = conn.execute('SELECT content FROM attachments WHERE id=?', (result['resume'],)).fetchone()['content']
            result['file_hash'] = hashlib.sha256(content).hexdigest()
            result['source_id'] = (existing or {}).get('source_id') or ''
            if conn.execute('SELECT 1 FROM resume_documents WHERE file_hash=? AND id!=?', (result['file_hash'], (existing or {}).get('id', -1))).fetchone():
                raise ValueError('同一份简历已存在，请使用已有记录')
            result['status'] = '待识别'
        else:
            result['source_id'] = existing['source_id']
            result['file_hash'] = existing['file_hash']
            result['status'] = payload.get('status') or existing['status']
            if existing['status'] == '已入库':
                result['status'] = '已入库'
            elif result['status'] == '已入库':
                raise ValueError('请通过入库操作将简历标记为已入库')
    return result

def save_attachment(upload, field, conn):
    if upload is not None:
        if not isinstance(upload, dict):
            raise ValueError(field['label'] + '附件格式无效')
        name = str(upload.get('name', '')).replace('\\', '/').split('/')[-1]
        extension = Path(name).suffix.lower()
        if extension not in field.get('accept', '.pdf,.doc,.docx').split(',') or len(name) > 180 or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError(field['label'] + '文件类型不支持或文件名超过180字')
        try:
            content = base64.b64decode(upload.get('content', ''), validate=True)
        except Exception:
            raise ValueError(field['label'] + '文件编码无效')
        if not content or len(content) > 50 * 1024 * 1024:
            raise ValueError(field['label'] + '文件须在50MB以内')
        valid = resume_file_types.valid_content(extension, content)
        if not valid:
            raise ValueError(field['label'] + '内容与文件类型不匹配，请选择有效文件')
        attachment_id = secrets.token_urlsafe(24)
        conn.execute('INSERT INTO attachments VALUES(?,?,?)', (attachment_id, name, content))
        return attachment_id

def remove_unused_attachment(conn, attachment_id):
    if not attachment_id:
        return
    for entity in ('candidates', 'applications', 'interviews', 'resume_documents'):
        for field in SCHEMAS[entity]['fields']:
            if field.get('type') == 'attachment' and conn.execute(f"SELECT 1 FROM {entity} WHERE {field['key']}=?", (attachment_id,)).fetchone():
                return
    conn.execute('DELETE FROM attachments WHERE id=?', (attachment_id,))

def cleanup_record_attachments(conn, entity, previous):
    for field in SCHEMAS[entity]['fields']:
        if field.get('type') == 'attachment':
            remove_unused_attachment(conn, previous[field['key']])

def deletion_plan(conn, entity, ids):
    if not isinstance(ids, list) or not 1 <= len(ids) <= 1000 or any(type(item) is not int or item <= 0 for item in ids):
        raise ValueError('请选择1至1000条有效记录')
    roots = []
    for identifier in dict.fromkeys(ids):
        row = conn.execute(f'SELECT * FROM {entity} WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise ValueError('记录已不存在，请刷新后重新删除')
        roots.append(row)
    visited, plan = set(), []
    def visit(table, row):
        key = (table, row['id'])
        if key in visited:
            return
        visited.add(key)
        for child, spec in SCHEMAS.items():
            for field in spec['fields']:
                if field.get('ref') == table:
                    for related in conn.execute(f"SELECT * FROM {child} WHERE {field['key']}=?", (row['id'],)).fetchall():
                        visit(child, related)
        if table == 'candidates' and row['phone']:
            for related in conn.execute('SELECT * FROM applications WHERE phone=?', (row['phone'],)).fetchall():
                visit('applications', related)
        if table == 'applications' and row['identity_card']:
            for child in ('interviews', 'employees'):
                for related in conn.execute(f'SELECT * FROM {child} WHERE upper(trim(identity_card))=?', (row['identity_card'].strip().upper(),)).fetchall():
                    visit(child, related)
        plan.append((table, dict(row)))
    for row in roots:
        visit(entity, row)
    return plan

def deletion_details(plan):
    return [{'entity': table, 'id': row['id'], 'name': row.get('name') or row.get('question') or row.get('title') or str(row['id'])} for table, row in plan]

def execute_deletion(conn, plan):
    deleting = {(table, row['id']) for table, row in plan}
    for table, row in plan:
        for child, spec in SCHEMAS.items():
            for field in spec['fields']:
                if field.get('ref') == table:
                    for related in conn.execute(f"SELECT id FROM {child} WHERE {field['key']}=?", (row['id'],)).fetchall():
                        if (child, related['id']) not in deleting:
                            conn.execute(f"UPDATE {child} SET {field['key']}=NULL WHERE id=?", (related['id'],))
    for table, row in plan:
        conn.execute(f'DELETE FROM {table} WHERE id=?', (row['id'],))
    release_deleted_candidate_imports(conn)
    for table, row in plan:
        cleanup_record_attachments(conn, table, row)

def account_phone(value):
    if not isinstance(value, str):
        raise ValueError('电话号码格式不正确')
    value = value.strip()
    if value and not re.fullmatch(r'(?:\+?86[- ]?)?(?:1[3-9]\d{9}|0\d{2,3}[- ]?\d{7,8}(?:-\d{1,6})?)', value):
        raise ValueError('请填写有效手机号或带区号的固定电话')
    return value


def account_nickname(value):
    if not isinstance(value, str):
        raise ValueError('请填写昵称')
    value = value.strip()
    if len(value) > 30 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('昵称最多30个字符，不能包含换行或控制字符')
    return value


def account_display_name(user, conn):
    table = 'admin' if user['role'] == 'admin' else 'members'
    row = conn.execute(f'SELECT nickname FROM {table} WHERE id=?', (user['id'],)).fetchone()
    return (row['nickname'] if row else '') or user['username']

def dify_embed_url():
    return FEATURES['resume_documents'].service.dify_embed_url()

def sync_application_talent(conn, values, application_id=None):
    phone = str(values.get('phone') or '').strip()
    candidate = conn.execute('SELECT * FROM candidates WHERE phone=?', (phone,)).fetchone() if phone else None
    if not candidate:
        if not phone or any(not values.get(key) for key in ('name', 'school_name', 'major', 'education')):
            return None
        talent = {key: values.get(key, '') for key in APPLICATION_COPY_FIELDS}
        talent.update(recruitment_type='校园招聘', status='待筛选', resume=values.get('resume') or '')
        candidate_id = insert(conn, 'candidates', validate('candidates', talent, conn))
        if application_id:
            conn.execute('UPDATE applications SET candidate_id=? WHERE id=?', (candidate_id, application_id))
        return candidate_id
    merged = dict(candidate)
    for key in APPLICATION_COPY_FIELDS:
        if values.get(key):
            if key == 'channel' and merged.get('recruitment_type') == '社会招聘' and values[key] not in ('智联招聘',):
                continue
            merged[key] = values[key]
    if values.get('resume'):
        merged['resume'] = values['resume']
    updated = validate('candidates', merged, conn)
    updated['archive_no'] = candidate['archive_no']
    updated['updated_at'] = datetime.now().isoformat(timespec='seconds')
    conn.execute(f"UPDATE candidates SET {','.join(key+'=?' for key in updated)} WHERE id=?", [*updated.values(), candidate['id']])
    save_candidate_educations(conn, candidate['id'], None, updated)
    cleanup_record_attachments(conn, 'candidates', candidate)
    if application_id:
        conn.execute('UPDATE applications SET candidate_id=? WHERE id=?', (candidate['id'], application_id))
    return candidate['id']

def insert(conn, entity, values):
    now = datetime.now().isoformat(timespec='seconds')
    values = dict(values, created_at=now, updated_at=now)
    keys = ','.join(values)
    marks = ','.join('?' for _ in values)
    identifier = conn.execute(f'INSERT INTO {entity} ({keys}) VALUES ({marks})', list(values.values())).lastrowid
    if entity in EDUCATION_TABLES:
        save_education_experiences(conn, entity, identifier, None, values)
    if entity == 'applications':
        sync_application_talent(conn, values, identifier)
    if entity in ARCHIVE_ENTITIES:
        synchronize_archives(conn)
    return identifier

ARCHIVE_ENTITIES = ('resume_documents', 'candidates', 'applications', 'interviews', 'employees')

def synchronize_archives(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS archive_numbers(number TEXT PRIMARY KEY)')
    records = {(entity, row['id']): dict(row) for entity in ARCHIVE_ENTITIES for row in conn.execute(f'SELECT * FROM {entity}')}
    parent = {key: key for key in records}
    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    def join(left, right):
        parent[find(left)] = find(right)
    matches = {}
    for key, row in records.items():
        for field in ('phone', 'identity_card', 'resume'):
            value = str(row.get(field) or '').strip().upper()
            if not value:
                continue
            if field == 'phone':
                value = re.sub(r'^(?:\+86|86)[- ]?', '', value) if len(value) > 11 else value
                value = value.replace(' ', '').replace('-', '')
            token = (field, value)
            if token in matches:
                join(key, matches[token])
            else:
                matches[token] = key
        candidate = ('candidates', row.get('candidate_id'))
        if candidate in records:
            join(key, candidate)
    groups = {}
    for key in records:
        groups.setdefault(find(key), []).append(key)
    origins = [(min(group, key=lambda key: (key[0] != 'resume_documents', records[key]['created_at'], key)), group) for group in groups.values()]
    for row in records.values():
        if row.get('archive_no'):
            conn.execute('INSERT OR IGNORE INTO archive_numbers(number) VALUES(?)', (row['archive_no'],))
    reserved = {row['number'] for row in conn.execute('SELECT number FROM archive_numbers')}
    assigned = set()
    for origin, group in sorted(origins, key=lambda item: (records[item[0]]['created_at'], item[0])):
        ordered_group = [origin, *sorted(key for key in group if key != origin)]
        date_code = datetime.fromisoformat(records[origin]['created_at']).strftime('%Y%m%d')
        anchored = next((match for key in ordered_group if (match := re.fullmatch(r'(01|02)' + date_code + r'\d{3}', str(records[key].get('archive_no') or '')))), None)
        recruitment_type = next((records[key].get('recruitment_type') for key in ordered_group if records[key].get('recruitment_type') in ('社会招聘', '校园招聘')), '')
        type_code = anchored.group(1) if anchored else ('02' if recruitment_type == '校园招聘' else '01')
        prefix = type_code + date_code
        archive_no = next((records[key].get('archive_no') for key in ordered_group if re.fullmatch(prefix + r'\d{3}', str(records[key].get('archive_no') or '')) and records[key].get('archive_no') not in assigned), '')
        if not archive_no:
            for suffix in range(1, 1000):
                candidate = f'{prefix}{suffix:03d}'
                if candidate not in reserved and candidate not in assigned:
                    archive_no = candidate
                    break
            if not archive_no:
                raise ValueError(f'{type_code}类{date_code}当日档案数量已超过999条')
        assigned.add(archive_no)
        reserved.add(archive_no)
        conn.execute('INSERT OR IGNORE INTO archive_numbers(number) VALUES(?)', (archive_no,))
        for entity, identifier in group:
            if records[(entity, identifier)].get('archive_no') != archive_no:
                conn.execute(f'UPDATE {entity} SET archive_no=? WHERE id=?', (archive_no, identifier))
            if entity == 'resume_documents':
                old_source = records[(entity, identifier)].get('source_id')
                if old_source and old_source != archive_no:
                    conn.execute('INSERT OR IGNORE INTO resume_imports(source_id,candidate_id) SELECT ?,candidate_id FROM resume_imports WHERE source_id=?', (archive_no, old_source))
                conn.execute('UPDATE resume_documents SET source_id=? WHERE id=?', (archive_no, identifier))

class Handler(BaseHTTPRequestHandler):
    server_version = 'CampusRecruit/1.0'

    def log_message(self, format, *args):
        pass

    def send(self, status, data, content_type='application/json; charset=utf-8', headers=None):
        content = json.dumps(data, ensure_ascii=False).encode() if content_type.startswith('application/json') else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')
        embed = urlparse(dify_embed_url())
        frame_origin = (embed.scheme + '://' + embed.netloc) if embed.netloc else ''
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; frame-src 'self' blob: " + frame_origin + "; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        self.send_header('Cache-Control', 'no-store')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def body(self):
        length = int(self.headers.get('Content-Length', 0))
        limit = 280 * 1024 * 1024 if self.path.startswith(('/api/applications', '/api/interviews', '/api/public/apply')) else 70 * 1024 * 1024 if self.path.startswith(('/api/candidates', '/api/resume_documents', '/api/public/resumes/')) else 12 * 1024 * 1024 if self.path.split('?')[0].endswith('/import-preview') else 65536
        if length > limit or length < 0:
            raise ValueError('提交内容过大')
        if self.headers.get_content_type() != 'application/json':
            raise ValueError('请使用JSON格式提交')
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError('提交内容必须为对象')
        return payload

    def session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            token = cookie['session'].value if 'session' in cookie else ''
        except Exception:
            return None
        if SESSIONS.get(token, 0) > time.time():
            return token
        SESSIONS.pop(token, None)
        SESSION_USERS.pop(token, None)
        return None

    def do_GET(self):
        self.handle_request('GET')

    def do_POST(self):
        self.handle_request('POST')

    def do_PUT(self):
        self.handle_request('PUT')

    def do_DELETE(self):
        self.handle_request('DELETE')

    def handle_request(self, method):
        try:
            self.route(method)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send(400, {'error': str(exc)})
        except sqlite3.IntegrityError as exc:
            message = '该记录已被其他表引用，请先处理关联记录'
            if 'candidates.phone' in str(exc):
                message = '该手机号已登记，请勿重复提交'
            elif 'employees.candidate_id' in str(exc):
                message = '该应聘人已办理入职登记'
            self.send(409, {'error': message})
        except Exception:
            self.send(500, {'error': '服务暂时无法处理，请稍后重试'})

    def route(self, method):
        url = urlparse(self.path)
        path = url.path
        if method != 'GET':
            origin = self.headers.get('Origin')
            if origin and urlparse(origin).netloc != self.headers.get('Host'):
                return self.send(403, {'error': '不允许跨站提交'})
        public_features = {
            '/apply': 'applications',
            '/api/public/schema': 'applications',
            '/api/public/application-prefill': 'applications',
            '/api/public/apply': 'applications',
            '/onboard': 'employees',
            '/api/public/employee-schema': 'employees',
            '/api/public/employees': 'employees',
            '/resume-submit': 'resume_documents',
            '/api/public/resume-schema': 'resume_documents',
        }
        required_feature = public_features.get(path)
        if path.startswith('/api/public/resumes/'):
            required_feature = 'resume_documents'
        protected_features = {
            '/api/resume-collection-qr': 'resume_documents',
            '/api/dify-embed': 'resume_documents',
            '/api/recognition-config': 'resume_documents',
            '/api/employee-prefill': 'employees',
            '/api/student-registration': 'interviews',
            '/api/interview-prefill': 'interviews',
            '/api/application-prefill': 'applications',
        }
        required_feature = required_feature or protected_features.get(path)
        if path.startswith('/api/resume_documents/'):
            required_feature = 'resume_documents'
        if required_feature and required_feature not in ENABLED_SCHEMAS:
            return self.send(404, {'error': '该功能已停用'})
        if path == '/api/login' and method == 'POST':
            ip = self.client_address[0]
            recent = [stamp for stamp in ATTEMPTS.get(ip, []) if stamp > time.time() - 300]
            ATTEMPTS[ip] = recent
            if len(recent) >= 10:
                return self.send(429, {'error': '登录尝试过多，请5分钟后再试'})
            payload = self.body()
            with db() as conn:
                username = str(payload.get('username', '')).strip()
                is_admin = username.lower() == 'admin'
                account = conn.execute('SELECT * FROM admin WHERE id=1').fetchone() if is_admin else conn.execute('SELECT * FROM members WHERE username=?', (username,)).fetchone()
                fallback = conn.execute('SELECT * FROM admin WHERE id=1').fetchone()
            digest = hashlib.pbkdf2_hmac('sha256', str(payload.get('password', '')).encode(), (account or fallback)['salt'].encode(), 300000).hex()
            if not account or not hmac.compare_digest(digest, account['password']):
                recent.append(time.time())
                return self.send(401, {'error': '账号或密码不正确'})
            ATTEMPTS.pop(ip, None)
            token = secrets.token_urlsafe(32)
            SESSIONS[token] = time.time() + 8 * 3600
            SESSION_USERS[token] = {'id': account['id'], 'username': 'admin' if is_admin else account['username'], 'role': 'admin' if is_admin else 'member'}
            return self.send(200, {'ok': True}, headers={'Set-Cookie': f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})
        if path == '/api/public/resume-schema' and method == 'GET':
            return self.send(200, {'fields': [field for field in SCHEMAS['resume_documents']['fields'] if field['key'] in ('position', 'position_detail', 'resume', 'channel', 'channel_detail')]})
        if path in ('/api/public/resumes/campus', '/api/public/resumes/social') and method == 'POST':
            submitted = self.body()
            if not isinstance(submitted, dict):
                raise ValueError('提交内容必须为对象')
            payload = {}
            payload['recruitment_type'] = '校园招聘' if path.endswith('/campus') else '社会招聘'
            payload['channel'] = submitted.get('channel') or ('校园线下' if path.endswith('/campus') else '')
            payload['channel_detail'] = submitted.get('channel_detail') or ''
            payload['position'] = submitted.get('position') or ''
            payload['position_detail'] = submitted.get('position_detail') or ''
            payload['status'] = '待识别'
            payload['created_by'] = '公开投递'
            payload['_resume_upload'] = submitted.get('_resume_upload')
            with db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                values = attachment_values('resume_documents', payload, conn)
                insert(conn, 'resume_documents', values)
            return self.send(201, {'ok': True})
        if path == '/api/public/employee-schema' and method == 'GET':
            fields = [{**field, 'required': field.get('required', False) or field['key'] in ('identity_card', 'phone')} for field in SCHEMAS['employees']['fields'] if not field.get('hidden')]
            return self.send(200, {'fields': fields})
        if path == '/api/public/employees' and method == 'POST':
            submitted = self.body()
            if not isinstance(submitted, dict):
                raise ValueError('提交内容必须为对象')
            education_experiences = education_experience_values(submitted, 'employees')
            values = {field['key']: submitted.get(field['key'], '') for field in SCHEMAS['employees']['fields'] if not field.get('hidden')}
            if education_experiences:
                values.update(education_experiences[0])
            for key, label in (('name', '姓名'), ('identity_card', '身份证'), ('phone', '联系电话')):
                if not str(values.get(key) or '').strip():
                    raise ValueError('请填写' + label)
            with db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                values = validate('employees', values, conn)
                if conn.execute('SELECT 1 FROM employees WHERE upper(trim(identity_card))=?', (values['identity_card'],)).fetchone():
                    return self.send(409, {'error': '该身份证已登记，如需修改请联系招聘工作人员'})
                employee_id = insert(conn, 'employees', values)
                save_education_experiences(conn, 'employees', employee_id, education_experiences, values)
            return self.send(201, {'ok': True})
        if path == '/api/public/schema' and method == 'GET':
            return self.send(200, {'fields': public_application_fields()})
        if path == '/api/public/application-prefill' and method == 'GET':
            phone = account_phone(parse_qs(url.query).get('phone', [''])[0])
            with db() as conn:
                candidate = conn.execute('SELECT * FROM candidates WHERE phone=?', (phone,)).fetchone() if phone else None
                if not candidate:
                    return self.send(200, {'matched': False, 'values': {}})
                allowed = {field['key'] for field in public_application_fields() if field.get('type') != 'attachment' and not field.get('readonly')}
                values = {key: value for key, value in application_prefill(candidate, conn).items() if key in allowed}
                values['education_experiences'] = education_rows(conn, 'candidates', candidate['id'])
            return self.send(200, {'matched': True, 'values': values})
        if path == '/api/public/apply' and method == 'POST':
            submitted = self.body()
            required = {field['key'] for field in public_application_fields() if field.get('required')}
            education_experiences = education_experience_values(submitted, 'applications', required)
            fields = public_application_fields()
            allowed = {field['key'] for field in fields if not field.get('readonly')}
            allowed.update('_' + field['key'] + '_upload' for field in fields if field.get('type') == 'attachment')
            values = {key: value for key, value in submitted.items() if key in allowed}
            if education_experiences:
                values.update(education_experiences[0])
            values.update(screening='', needs_first_interview='', status='已生效', is_elite='', notes='', batch='', candidate_id=None)
            values.setdefault('date', datetime.now().date().isoformat())
            with db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                existing = conn.execute('SELECT * FROM applications WHERE phone=? ORDER BY id DESC LIMIT 1', (str(values.get('phone') or '').strip(),)).fetchone()
                if existing:
                    for key in INTERNAL_APPLICATION_FIELDS:
                        values[key] = existing[key]
                application = attachment_values('applications', values, conn, dict(existing) if existing else None)
                if existing:
                    application_id = existing['id']
                    application['archive_no'] = existing['archive_no']
                    application['updated_at'] = datetime.now().isoformat(timespec='seconds')
                    conn.execute(f"UPDATE applications SET {','.join(key+'=?' for key in application)} WHERE id=?", [*application.values(), application_id])
                    save_education_experiences(conn, 'applications', application_id, education_experiences, application)
                    sync_application_talent(conn, application, application_id)
                    sync_application_educations_to_candidate(conn, application_id)
                    synchronize_archives(conn)
                    cleanup_record_attachments(conn, 'applications', existing)
                else:
                    application_id = insert(conn, 'applications', application)
                    save_education_experiences(conn, 'applications', application_id, education_experiences, application)
                    sync_application_educations_to_candidate(conn, application_id)
                candidate_id = conn.execute('SELECT candidate_id FROM applications WHERE id=?', (application_id,)).fetchone()['candidate_id']
            return self.send(200 if existing else 201, {'ok': True, 'id': application_id, 'application_id': application_id, 'candidate_id': candidate_id})
        if path.startswith('/api/'):
            token = self.session()
            if not token:
                return self.send(401, {'error': '请先登录'})
            user = SESSION_USERS.get(token)
            if not user:
                return self.send(401, {'error': '请重新登录'})
            if path == '/api/resume-collection-qr' and method == 'GET':
                host = self.headers.get('Host', 'localhost:' + str(self.server.server_port))
                base = public_base_url(host, self.server.server_port)
                items = []
                for kind, label in (('campus', '校园招聘'), ('social', '社会招聘')):
                    url = base + '/resume-submit?type=' + kind
                    qr = qrcode.QRCode(box_size=6, border=4)
                    qr.add_data(url); qr.make(fit=True)
                    svg = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).to_string()
                    items.append({'label': label, 'url': url, 'image': 'data:image/svg+xml;base64,' + base64.b64encode(svg).decode()})
                return self.send(200, {'items': items})
            if path == '/api/dify-embed' and method == 'GET':
                return self.send(200, {'url': dify_embed_url()})
            if user['role'] != 'admin':
                with db() as conn:
                    member = conn.execute('SELECT is_admin FROM members WHERE id=?', (user['id'],)).fetchone()
                if not member:
                    return self.send(401, {'error': '账号已注销，请重新登录'})
                user = {**user, 'role': 'manager' if member['is_admin'] else 'member'}
            if re.fullmatch(r'/api/members/[0-9]+/role', path) and method == 'PUT':
                if user['role'] != 'admin':
                    return self.send(403, {'error': '仅admin账号可以任命或取消管理员'})
                payload = self.body()
                role = payload.get('role') if isinstance(payload, dict) else None
                if role not in ('manager', 'member'):
                    raise ValueError('角色无效')
                with db() as conn:
                    changed = conn.execute('UPDATE members SET is_admin=? WHERE id=?', (int(role == 'manager'), int(path.split('/')[3]))).rowcount
                    if not changed:
                        return self.send(404, {'error': '成员账号不存在'})
                return self.send(200, {'ok': True})
            if re.fullmatch(r'/api/members/[0-9]+/password', path) and method == 'PUT':
                if user['role'] != 'admin':
                    return self.send(403, {'error': '仅主管理员可以重置成员密码'})
                payload = self.body()
                password = str(payload.get('password', ''))
                if not 10 <= len(password) <= 128:
                    raise ValueError('新密码长度须为10至128位')
                member_id = int(path.split('/')[3])
                salt = secrets.token_hex(16)
                digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 300000).hex()
                with db() as conn:
                    changed = conn.execute(
                        'UPDATE members SET salt=?,password=? WHERE id=?',
                        (salt, digest, member_id),
                    ).rowcount
                    if not changed:
                        return self.send(404, {'error': '成员账号不存在或已注销'})
                for session_token, owner in list(SESSION_USERS.items()):
                    if owner['role'] == 'member' and owner['id'] == member_id:
                        SESSIONS.pop(session_token, None)
                        SESSION_USERS.pop(session_token, None)
                return self.send(200, {'ok': True})
            if path == '/api/me' and method == 'GET':
                with db() as conn:
                    table = 'admin' if user['role'] == 'admin' else 'members'
                    row = conn.execute(f'SELECT nickname,phone FROM {table} WHERE id=?', (user['id'],)).fetchone()
                return self.send(200, {**user, **dict(row)})
            if path == '/api/recognition-config' and method == 'GET':
                try:
                    dify_client.configuration()
                    return self.send(200, {'configured': True})
                except ValueError as error:
                    return self.send(200, {'configured': False, 'message': str(error)})
            if re.fullmatch(r'/api/resume_documents/[0-9]+/recognize', path) and method == 'POST':
                dify_client.configuration()
                document_id = int(path.split('/')[3])
                if not RECOGNITION_LOCK.acquire(blocking=False):
                    return self.send(409, {'error': '已有简历正在识别，请稍后重试'})
                try:
                    with db() as conn:
                        source = conn.execute('SELECT * FROM resume_documents WHERE id=?', (document_id,)).fetchone()
                        if not source:
                            return self.send(404, {'error': '简历不存在或已删除'})
                        if source['status'] not in ('待识别', '失败'):
                            return self.send(409, {'error': '仅处理待识别或失败简历'})
                        attachment = conn.execute('SELECT name,content FROM attachments WHERE id=?', (source['resume'],)).fetchone()
                        if not attachment:
                            raise ValueError('简历附件不存在')
                        snapshot_fields = ('status', 'resume', 'source_id', 'recruitment_type', 'channel', 'channel_detail', 'position', 'position_detail', 'updated_at')
                        snapshot_where = ' AND '.join(f"COALESCE({field},'')=?" for field in snapshot_fields)
                        snapshot_values = [source[field] or '' for field in snapshot_fields]
                    try:
                        result = dify_client.recognize(attachment['content'], source['source_id'], dict(source), attachment['name'])
                        result = dify_mapping.to_candidate_payload(result, dict(source))
                        result = candidate_positions.normalize_payload(result)
                        keys = {value for field in SCHEMAS['candidates']['fields'] for value in (field['key'], field['label']) if not field.get('hidden') and not field.get('readonly')}
                        keys.update(('education_experiences', 'work_experiences', 'project_experiences'))
                        result = {key: value for key, value in result.items() if key in keys}
                        if not result:
                            raise ValueError('工作流未返回可用的人才字段，请检查输出字段名称')
                        with db() as conn:
                            changed = conn.execute(f"UPDATE resume_documents SET status='已识别',updated_at=? WHERE id=? AND {snapshot_where}", (datetime.now().isoformat(timespec='seconds'), document_id, *snapshot_values)).rowcount
                            if not changed:
                                return self.send(409, {'error': '简历已被修改，请刷新后检查'})
                            conn.execute('CREATE TABLE IF NOT EXISTS resume_recognition(document_id INTEGER PRIMARY KEY, result TEXT NOT NULL)')
                            conn.execute('INSERT OR REPLACE INTO resume_recognition VALUES(?,?)', (document_id, json.dumps(result, ensure_ascii=False)))
                        return self.send(200, {'result': result})
                    except ValueError:
                        with db() as conn:
                            conn.execute(f"UPDATE resume_documents SET status='失败',updated_at=? WHERE id=? AND {snapshot_where}", (datetime.now().isoformat(timespec='seconds'), document_id, *snapshot_values))
                        raise
                finally:
                    RECOGNITION_LOCK.release()
            if re.fullmatch(r'/api/resume_documents/[0-9]+/recognition-result', path) and method == 'GET':
                with db() as conn:
                    conn.execute('CREATE TABLE IF NOT EXISTS resume_recognition(document_id INTEGER PRIMARY KEY, result TEXT NOT NULL)')
                    row = conn.execute("SELECT r.result FROM resume_recognition r JOIN resume_documents d ON d.id=r.document_id WHERE d.id=? AND d.status='已识别'", (int(path.split('/')[3]),)).fetchone()
                return self.send(200, {'result': json.loads(row['result']) if row else None})
            if re.fullmatch(r'/api/resume_documents/[0-9]+/candidate', path) and method == 'POST':
                payload = self.body()
                education_history = candidate_education_values(payload)
                if education_history:
                    payload = {**payload, **education_history[0]}
                document_id = int(path.split('/')[3])
                try:
                    with db() as conn:
                        conn.execute('BEGIN IMMEDIATE')
                        source = conn.execute('SELECT * FROM resume_documents WHERE id=?', (document_id,)).fetchone()
                        if not source:
                            return self.send(404, {'error': '简历不存在或已删除'})
                        release_deleted_candidate_imports(conn)
                        source = conn.execute('SELECT * FROM resume_documents WHERE id=?', (document_id,)).fetchone()
                        previous = conn.execute('''SELECT imports.candidate_id FROM resume_imports imports
                            JOIN candidates candidate ON candidate.id=imports.candidate_id
                            WHERE imports.source_id IN (?,?)''', (source['source_id'], source['file_hash'])).fetchone()
                        if previous:
                            conn.execute("UPDATE resume_documents SET status='已入库' WHERE id=?", (document_id,))
                            return self.send(200, {'id': previous['candidate_id'], 'already_imported': True})
                        payload = dict(payload)
                        for key in ('recruitment_type', 'channel', 'channel_detail'):
                            if source[key]:
                                payload[key] = source[key]
                        values = candidate_values(payload, conn)
                        values['resume'] = source['resume']
                        values['recruitment_type'] = source['recruitment_type'] or values.get('recruitment_type', '')
                        experience_history = candidate_experiences.payload_values(payload)[1]
                        project_history = candidate_project_experiences.payload_values(payload, values['recruitment_type'])
                        identifier = insert(conn, 'candidates', values)
                        save_candidate_educations(conn, identifier, education_history, values)
                        candidate_experiences.save(conn, identifier, experience_history)
                        candidate_project_experiences.save(conn, identifier, values['recruitment_type'], project_history)
                        conn.execute('INSERT INTO resume_imports(source_id,candidate_id) VALUES(?,?)', (source['source_id'], identifier))
                        conn.execute('INSERT OR IGNORE INTO resume_imports(source_id,candidate_id) VALUES(?,?)', (source['file_hash'], identifier))
                        conn.execute("UPDATE resume_documents SET status='已入库',updated_at=? WHERE id=?", (datetime.now().isoformat(timespec='seconds'), document_id))
                    return self.send(201, {'id': identifier})
                except (ValueError, sqlite3.IntegrityError):
                    raise
            if path == '/api/resume_documents/pending' and method == 'GET':
                with db() as conn:
                    rows = [candidate_display(row, conn, 'resume_documents') for row in conn.execute("SELECT * FROM resume_documents WHERE status='待识别' ORDER BY id")]
                return self.send(200, rows)
            if path == '/api/me/phone' and method == 'PUT':
                payload = self.body()
                phone = account_phone(payload.get('phone') if isinstance(payload, dict) else None)
                with db() as conn:
                    table = 'admin' if user['role'] == 'admin' else 'members'
                    conn.execute(f'UPDATE {table} SET phone=? WHERE id=?', (phone, user['id']))
                return self.send(200, {'phone': phone})
            if path == '/api/me' and method == 'PUT':
                payload = self.body()
                nickname = account_nickname(payload.get('nickname') if isinstance(payload, dict) else None)
                with db() as conn:
                    table = 'admin' if user['role'] == 'admin' else 'members'
                    conn.execute(f'UPDATE {table} SET nickname=? WHERE id=?', (nickname, user['id']))
                return self.send(200, {**user, 'nickname': nickname})
            if path.startswith('/api/members/') and method == 'DELETE':
                if user['role'] not in ('admin', 'manager'):
                    return self.send(403, {'error': '仅管理员可以注销成员账号'})
                identifier = path.removeprefix('/api/members/')
                if not identifier.isdigit():
                    raise ValueError('成员账号无效')
                member_id = int(identifier)
                with db() as conn:
                    deleted = conn.execute('DELETE FROM members WHERE id=?', (member_id,)).rowcount
                    if not deleted:
                        return self.send(404, {'error': '成员账号不存在或已注销'})
                for session_token, owner in list(SESSION_USERS.items()):
                    if owner['role'] == 'member' and owner['id'] == member_id:
                        SESSIONS.pop(session_token, None)
                        SESSION_USERS.pop(session_token, None)
                return self.send(200, {'ok': True})
            if path == '/api/members':
                if method == 'GET':
                    with db() as conn:
                        rows = [dict(row) for row in conn.execute("SELECT id,username,nickname,created_at,CASE WHEN is_admin=1 THEN 'manager' ELSE 'member' END AS role FROM members ORDER BY id DESC")]
                    return self.send(200, rows)
                if user['role'] not in ('admin', 'manager'):
                    return self.send(403, {'error': '仅管理员可以管理成员账号'})
                if method == 'POST':
                    payload = self.body()
                    username = str(payload.get('username', '')).strip()
                    password = str(payload.get('password', ''))
                    phone = account_phone(payload.get('phone', ''))
                    nickname = account_nickname(payload.get('nickname', ''))
                    if not re.fullmatch(r'[A-Za-z0-9_\-]{3,32}', username) or username.lower() == 'admin':
                        raise ValueError('成员账号须为3至32位字母、数字、下划线或短横线，不能使用admin')
                    if not 10 <= len(password) <= 128:
                        raise ValueError('密码长度须为10至128位')
                    salt = secrets.token_hex(16)
                    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 300000).hex()
                    with db() as conn:
                        try:
                            conn.execute('INSERT INTO members(username,salt,password,created_at,phone,nickname) VALUES(?,?,?,?,?,?)', (username, salt, digest, datetime.now().isoformat(timespec='seconds'), phone, nickname))
                        except sqlite3.IntegrityError:
                            return self.send(409, {'error': '该成员账号已存在'})
                    return self.send(201, {'ok': True})
                return self.send(405, {'error': '不支持此操作'})
            if path == '/api/employee-prefill' and method == 'GET':
                identity = parse_qs(url.query).get('identity_card', [''])[0]
                with db() as conn:
                    source = interview_source(identity, conn)
                    if not source:
                        return self.send(200, {'matched': False, 'values': {}})
                    values = employee_source_values(source)
                    values['education_experiences'] = education_rows(conn, 'applications', source['id'])
                    values.update(identity_details(identity))
                    return self.send(200, {'matched': True, 'values': values, 'attachments': []})
            if path == '/api/student-registration' and method == 'GET':
                identity = parse_qs(url.query).get('identity_card', [''])[0]
                with db() as conn:
                    source = interview_source(identity, conn)
                    if not source:
                        return self.send(200, {'matched': False})
                    row = candidate_display(source, conn, 'applications')
                    fields = public_application_fields()
                    histories = row.get('education_experiences', [])
                    fields.append({'key': 'education_history', 'label': '全部教育经历', 'type': 'textarea'})
                    keys = {field['key'] for field in fields}
                    keys.update(field['key'] + '_name' for field in fields if field.get('type') == 'attachment')
                    values = {key: row.get(key, '') for key in keys}
                    values['education_history'] = '\n'.join(f"{item['education']} · {item['school_name']} · {item['major']}" for item in histories)
                    return self.send(200, {'matched': True, 'fields': fields, 'values': values})
            if path == '/api/interview-prefill' and method == 'GET':
                identity = parse_qs(url.query).get('identity_card', [''])[0]
                with db() as conn:
                    source = interview_source(identity, conn)
                    if not source:
                        return self.send(200, {'matched': False, 'values': {}})
                    values = interview_source_values(source)
                    values['education_experiences'] = education_rows(conn, 'applications', source['id'])
                    attachments = []
                    attachment_fields = {}
                    for key in ('resume', 'transcript', 'certificates'):
                        attachment_id = values.pop(key) or ''
                        attachment = conn.execute('SELECT name FROM attachments WHERE id=?', (attachment_id,)).fetchone()
                        if attachment:
                            attachments.append(attachment['name'])
                            attachment_fields[key] = {'id': attachment_id, 'name': attachment['name']}
                    values.pop('candidate_id', None)
                    values.update(identity_details(identity))
                    return self.send(200, {'matched': True, 'values': values, 'attachments': attachments, 'attachment_fields': attachment_fields, 'source_id': source['id']})
            if path == '/api/application-prefill' and method == 'GET':
                params = parse_qs(url.query)
                with db() as conn:
                    if 'phone' in params:
                        candidate = conn.execute('SELECT * FROM candidates WHERE phone=?', (params['phone'][0].strip(),)).fetchone()
                        if not candidate:
                            return self.send(200, {'matched': False, 'values': {}})
                        values = application_prefill(candidate, conn) if path == '/api/application-prefill' else interview_prefill(candidate, conn)
                        values = {key: value for key, value in values.items() if key not in ('resume', 'transcript', 'certificates')}
                        attachment = conn.execute('SELECT name FROM attachments WHERE id=?', (candidate['resume'] or '',)).fetchone()
                        return self.send(200, {'matched': True, 'values': values, 'resume': candidate['resume'] or '', 'resume_name': attachment['name'] if attachment else ''})
                    candidate = conn.execute('SELECT * FROM candidates WHERE id=?', (params.get('id', [''])[0],)).fetchone()
                    if not candidate:
                        raise ValueError('关联人才不存在，请重新选择')
                    return self.send(200, application_prefill(candidate, conn))
            if path.startswith('/api/attachments/') and method == 'GET':
                with db() as conn:
                    attachment = conn.execute('SELECT name,content FROM attachments WHERE id=?', (path.rsplit('/', 1)[-1],)).fetchone()
                if not attachment:
                    return self.send(404, {'error': '附件不存在或已删除'})
                if parse_qs(url.query).get('preview') == ['1']:
                    suffix = Path(attachment['name']).suffix.lower()
                    mime = {'.pdf':'application/pdf', '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.gif':'image/gif', '.webp':'image/webp'}.get(suffix)
                    if mime:
                        return self.send(200, attachment['content'], mime)
                    if suffix in resume_file_types.TEXT_EXTENSIONS | {'.xml', '.svg'} and len(attachment['content']) <= 5 * 1024 * 1024:
                        text = resume_file_types.decode_text(attachment['content'])
                        if text is not None:
                            return self.send(200, {'kind':'text', 'text':text, 'note':'文本预览，完整内容请下载查看。'})
                    if suffix == '.docx':
                        import xml.etree.ElementTree as ET
                        try:
                            with zipfile.ZipFile(io.BytesIO(attachment['content'])) as archive:
                                info = archive.getinfo('word/document.xml')
                                if info.file_size > 20 * 1024 * 1024:
                                    raise ValueError()
                                root = ET.fromstring(archive.read(info))
                            ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                            paragraphs = [''.join(node.itertext()) for node in root.findall('.//w:t', ns)]
                            return self.send(200, {'kind':'text', 'text':'\n'.join(paragraphs), 'note':'Word 文本预览，完整排版请下载查看。'})
                        except (ValueError, KeyError, zipfile.BadZipFile, ET.ParseError):
                            pass
                    return self.send(200, {'kind':'unsupported', 'note':'此附件暂不支持在线预览，请下载后查看。'})
                return self.send(200, attachment['content'], 'application/octet-stream', {'Content-Disposition': "attachment; filename*=UTF-8''" + quote(attachment['name'])})
            if path == '/api/logout' and method == 'POST':
                SESSIONS.pop(token, None)
                SESSION_USERS.pop(token, None)
                return self.send(200, {'ok': True}, headers={'Set-Cookie': 'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
            if path == '/api/password' and method == 'POST':
                payload = self.body()
                password = str(payload.get('password', ''))
                if len(password) < 10 or len(password) > 128:
                    raise ValueError('新密码长度须为10至128位')
                with db() as conn:
                    account_table = 'admin' if user['role'] == 'admin' else 'members'
                    admin = conn.execute(f'SELECT * FROM {account_table} WHERE id=?', (user['id'],)).fetchone()
                    old_digest = hashlib.pbkdf2_hmac('sha256', str(payload.get('old_password', '')).encode(), admin['salt'].encode(), 300000).hex()
                    if not hmac.compare_digest(old_digest, admin['password']):
                        return self.send(400, {'error': '原密码不正确'})
                    salt = secrets.token_hex(16)
                    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 300000).hex()
                    conn.execute(f'UPDATE {account_table} SET salt=?,password=? WHERE id=?', (salt, digest, user['id']))
                for session_token, owner in list(SESSION_USERS.items()):
                    if (owner['role'] == 'admin') == (user['role'] == 'admin') and owner['id'] == user['id']:
                        SESSIONS.pop(session_token, None)
                        SESSION_USERS.pop(session_token, None)
                if user['role'] == 'admin':
                    (DATA / 'initial-password.txt').unlink(missing_ok=True)
                return self.send(200, {'ok': True})
            if path == '/api/schema' and method == 'GET':
                return self.send(200, ENABLED_SCHEMAS)
            if path == '/api/locations' and method == 'GET':
                return self.send(200, LOCATIONS)
            if path == '/api/stats' and method == 'GET':
                with db() as conn:
                    counts = {key: conn.execute(f'SELECT COUNT(*) FROM {key}').fetchone()[0] for key in ENABLED_SCHEMAS}
                    statuses = [dict(r) for r in conn.execute('SELECT status,COUNT(*) AS count FROM candidates GROUP BY status')] if 'candidates' in ENABLED_SCHEMAS else []
                    recent = [dict(r) for r in conn.execute('SELECT id,name,school_name,major,position,status,created_at FROM candidates ORDER BY id DESC LIMIT 5')] if 'candidates' in ENABLED_SCHEMAS else []
                    recruitment = {}
                    for kind in ('校园招聘', '社会招聘'):
                        grouped = {key: conn.execute(f'SELECT COUNT(*) FROM {key} WHERE recruitment_type=?', (kind,)).fetchone()[0] for key in ('resume_documents', 'candidates') if key in ENABLED_SCHEMAS}
                        if kind == '校园招聘':
                            grouped.update({key: counts[key] for key in ('schools', 'applications', 'interviews') if key in ENABLED_SCHEMAS})
                        kind_recent = [dict(r) for r in conn.execute('SELECT id,name,school_name,major,position FROM candidates WHERE recruitment_type=? ORDER BY id DESC LIMIT 5', (kind,))] if 'candidates' in ENABLED_SCHEMAS else []
                        recruitment[kind] = {'counts': grouped, 'recent': kind_recent}
                return self.send(200, {'counts': counts, 'statuses': statuses, 'recent': recent, 'recruitment': recruitment})
            parts = path.strip('/').split('/')
            entity = parts[1]
            if entity not in ENABLED_SCHEMAS or len(parts) > 3:
                return self.send(404, {'error': '接口不存在'})
            identifier = parts[2] if len(parts) == 3 else None
            with db() as conn:
                if method == 'POST' and identifier == 'export.xlsx':
                    rows = export_rows(conn, entity, self.body().get('ids'))
                    host = self.headers.get('Host', '')
                    base = public_base_url(host, self.server.server_port)
                    return self.send(200, workbook_bytes(SCHEMAS[entity], rows, attachment_base_url=base), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', {'Content-Disposition': f"attachment; filename*=UTF-8''{quote(SCHEMAS[entity]['title'])}.xlsx"})
                if method == 'POST' and identifier in ('delete-preview', 'batch-delete'):
                    payload = self.body()
                    conn.execute('BEGIN IMMEDIATE')
                    plan = deletion_plan(conn, entity, payload.get('ids'))
                    details = deletion_details(plan)
                    if identifier == 'delete-preview':
                        return self.send(200, {'items': details, 'count': len(plan)})
                    if 'expected' in payload and payload['expected'] != details:
                        raise ValueError('关联数据已变化，请重新预览后确认删除')
                    if 'selected' in payload:
                        selected = payload['selected']
                        if 'expected' not in payload or not isinstance(selected, list) or any(not isinstance(item, dict) or not isinstance(item.get('entity'), str) or type(item.get('id')) is not int for item in selected):
                            raise ValueError('删除选择无效，请重新预览')
                        keys = {(item['entity'], item['id']) for item in selected}
                        available = {(table, row['id']) for table, row in plan}
                        roots = {(entity, identifier) for identifier in payload['ids']}
                        if not roots <= keys or not keys <= available:
                            raise ValueError('删除选择超出预览范围或缺少所选主记录')
                        plan = [(table, row) for table, row in plan if (table, row['id']) in keys]
                    execute_deletion(conn, plan)
                    conn.commit()
                    return self.send(200, {'count': len(plan)})
                if method == 'POST' and identifier == 'import-preview':
                    preview = prepare_rows(entity, SCHEMAS[entity], self.body(), conn, validate)
                    conn.execute('SAVEPOINT import_preview')
                    try:
                        for row in preview['rows']:
                            try:
                                insert(conn, entity, row['values'])
                            except sqlite3.IntegrityError:
                                preview['errors'].append({'line': row['line'], 'error': '记录重复或关联无效，请检查手机号、入职人员等唯一字段'})
                    finally:
                        conn.execute('ROLLBACK TO import_preview')
                        conn.execute('RELEASE import_preview')
                    now = time.time()
                    for key in list(IMPORTS):
                        if IMPORTS[key]['expires'] < now:
                            IMPORTS.pop(key, None)
                    import_token = None
                    if not preview['errors']:
                        if len(IMPORTS) >= 100:
                            raise ValueError('当前待导入任务过多，请稍后重试')
                        import_token = secrets.token_urlsafe(24)
                        IMPORTS[import_token] = {'session': token, 'entity': entity, 'expires': now + 900, 'rows': preview['rows']}
                    masked_rows = []
                    secret_keys = {field['key'] for field in SCHEMAS[entity]['fields'] if field.get('type') == 'password'}
                    for row in preview['rows'][:20]:
                        masked_rows.append({'line': row['line'], 'values': {key: ('••••••' if value else '') if key in secret_keys else value for key, value in row['values'].items()}})
                    return self.send(200, {**preview, 'rows': masked_rows, 'total': len(preview['rows']) + len([error for error in preview['errors'] if error['line'] not in {row['line'] for row in preview['rows']}]), 'token': import_token})
                if method == 'POST' and identifier == 'import-commit':
                    key = str(self.body().get('token', ''))
                    job = IMPORTS.get(key)
                    if not job or job['session'] != token or job['entity'] != entity or job['expires'] < time.time():
                        raise ValueError('预览已过期或已提交，请重新识别文件')
                    job = IMPORTS.pop(key, None)
                    if not job:
                        raise ValueError('导入任务已提交')
                    conn.execute('BEGIN IMMEDIATE')
                    identifiers = []
                    for row in job['rows']:
                        try:
                            identifiers.append(insert(conn, entity, validate(entity, row['values'], conn)))
                        except (ValueError, sqlite3.IntegrityError) as error:
                            raise ValueError(f"第{row['line']}行导入失败（记录重复、关联已变更或字段无效），本次未写入任何数据，请重新预览") from error
                    conn.commit()
                    return self.send(201, {'count': len(identifiers), 'ids': identifiers})
                if method == 'POST' and identifier == 'qr-print':
                    ids = self.body().get('ids')
                    if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(type(item) is not int or item <= 0 for item in ids):
                        raise ValueError('请选择1至100条记录生成二维码')
                    ids = list(dict.fromkeys(ids))
                    host = self.headers.get('Host', '')
                    base = public_base_url(host, self.server.server_port)
                    items = []
                    for record_id in ids:
                        row = conn.execute(f'SELECT * FROM {entity} WHERE id=?', (record_id,)).fetchone()
                        if not row:
                            raise ValueError(f'记录{record_id}已不存在，请刷新列表')
                        row = dict(row)
                        title = row.get('name') or row.get('question') or row.get('title')
                        if not title and row.get('candidate_id'):
                            person = conn.execute('SELECT name FROM candidates WHERE id=?', (row['candidate_id'],)).fetchone()
                            title = person['name'] if person else ''
                        url = base + '/?module=' + entity + '&record=' + str(record_id)
                        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=4)
                        qr.add_data(url)
                        qr.make(fit=True)
                        svg = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).to_string()
                        items.append({'id': record_id, 'title': title or str(record_id), 'url': url, 'image': 'data:image/svg+xml;base64,' + base64.b64encode(svg).decode()})
                    return self.send(200, {'title': SCHEMAS[entity]['title'], 'items': items})
                if method == 'GET' and identifier == 'template.xlsx':
                    return self.send(200, workbook_bytes(SCHEMAS[entity], [], template=True), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', {'Content-Disposition': f"attachment; filename*=UTF-8''{quote(SCHEMAS[entity]['title'] + '-导入模板')}.xlsx"})
                if method == 'GET' and identifier in (None, 'export', 'export.xlsx'):
                    query = parse_qs(url.query).get('q', [''])[0].strip()
                    rows = export_rows(conn, entity, query=query)
                    if identifier == 'export':
                        output = io.StringIO()
                        writer = csv.writer(output)
                        fields = [f for f in SCHEMAS[entity]['fields'] if f.get('export', True) and not f.get('hidden')]
                        writer.writerow(['编号'] + [f['label'] for f in fields] + ['创建时间'])
                        for row in rows:
                            values = [row['id']] + [row.get(f['key'] + '_label' if f.get('ref') else f['key'], '') for f in fields] + [row['created_at']]
                            writer.writerow(["'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v for v in values])
                        return self.send(200, ('\ufeff' + output.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8', {'Content-Disposition': f"attachment; filename*=UTF-8''{quote(SCHEMAS[entity]['title'])}.csv"})
                    if identifier == 'export.xlsx':
                        host = self.headers.get('Host', '')
                        base = public_base_url(host, self.server.server_port)
                        return self.send(200, workbook_bytes(SCHEMAS[entity], rows, attachment_base_url=base), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', {'Content-Disposition': f"attachment; filename*=UTF-8''{quote(SCHEMAS[entity]['title'])}.xlsx"})
                    return self.send(200, rows)
                if method == 'POST' and identifier is None:
                    payload = self.body()
                    if entity == 'resume_documents':
                        payload = {**payload, 'created_by': account_display_name(user, conn)}
                    education_history = education_experience_values(payload, entity) if entity in EDUCATION_TABLES else None
                    if education_history:
                        payload = {**payload, **education_history[0]}
                    values = attachment_values(entity, payload, conn) if entity in ('candidates', 'applications', 'interviews', 'resume_documents') else validate(entity, payload, conn)
                    experience_history = candidate_experiences.payload_values(payload)[1] if entity == 'candidates' else None
                    project_history = candidate_project_experiences.payload_values(payload, values['recruitment_type']) if entity == 'candidates' else None
                    record_id = insert(conn, entity, values)
                    if entity in EDUCATION_TABLES:
                        if entity == 'applications' and education_history is None and values.get('candidate_id'):
                            education_history = education_rows(conn, 'candidates', values['candidate_id'])
                        save_education_experiences(conn, entity, record_id, education_history, values)
                    if entity == 'candidates':
                        candidate_experiences.save(conn, record_id, experience_history)
                        candidate_project_experiences.save(conn, record_id, values['recruitment_type'], project_history)
                    if entity == 'applications':
                        sync_application_educations_to_candidate(conn, record_id)
                    conn.commit()
                    return self.send(201, {'id': record_id})
                if identifier and identifier.isdigit() and method in ('PUT', 'DELETE'):
                    previous = conn.execute(f'SELECT * FROM {entity} WHERE id=?', (identifier,)).fetchone()
                    if not previous:
                        return self.send(404, {'error': '记录不存在'})
                    if method == 'DELETE':
                        conn.execute('BEGIN IMMEDIATE')
                        execute_deletion(conn, deletion_plan(conn, entity, [int(identifier)]))
                    else:
                        payload = self.body()
                        if entity == 'resume_documents':
                            payload = {**payload, 'created_by': previous['created_by'] or '历史记录'}
                        education_history = education_experience_values(payload, entity) if entity in EDUCATION_TABLES else None
                        if education_history:
                            payload = {**payload, **education_history[0]}
                        if entity in ('employees', 'questions'):
                            payload = {**{field['key']: previous[field['key']] for field in SCHEMAS[entity]['fields'] if field.get('hidden')}, **payload}
                        values = attachment_values(entity, payload, conn, dict(previous)) if entity in ('candidates', 'applications', 'interviews', 'resume_documents') else validate(entity, payload, conn)
                        experience_history = candidate_experiences.payload_values(payload)[1] if entity == 'candidates' else None
                        project_history = candidate_project_experiences.payload_values(payload, values['recruitment_type']) if entity == 'candidates' else None
                        if entity in ARCHIVE_ENTITIES:
                            values['archive_no'] = previous['archive_no']
                        values['updated_at'] = datetime.now().isoformat(timespec='seconds')
                        conn.execute(f"UPDATE {entity} SET {','.join(k+'=?' for k in values)} WHERE id=?", [*values.values(), identifier])
                        if entity in EDUCATION_TABLES:
                            save_education_experiences(conn, entity, int(identifier), education_history, values)
                        if entity == 'candidates':
                            candidate_experiences.save(conn, int(identifier), experience_history)
                            candidate_project_experiences.save(conn, int(identifier), values['recruitment_type'], project_history)
                        if entity in ARCHIVE_ENTITIES:
                            synchronize_archives(conn)
                        if entity == 'applications':
                            sync_application_talent(conn, values, int(identifier))
                            sync_application_educations_to_candidate(conn, int(identifier))
                    cleanup_record_attachments(conn, entity, previous)
                    conn.commit()
                    return self.send(200, {'ok': True})
            return self.send(405, {'error': '不支持此操作'})
        if method == 'GET':
            if re.fullmatch(r'/features/[a-z_]+\.js', path):
                feature_file = ROOT / 'web' / path.lstrip('/')
                if feature_file.is_file():
                    return self.send(200, feature_file.read_bytes(), 'text/javascript; charset=utf-8')
            if re.fullmatch(r'/features/[a-z_]+\.css', path):
                feature_file = ROOT / 'web' / path.lstrip('/')
                if feature_file.is_file():
                    return self.send(200, feature_file.read_bytes(), 'text/css; charset=utf-8')
            if path == '/candidate.css':
                return self.send(200, (ROOT / 'web' / 'candidate.css').read_bytes(), 'text/css; charset=utf-8')
            if path == '/corporate-theme.css':
                return self.send(200, (ROOT / 'web' / 'corporate-theme.css').read_bytes(), 'text/css; charset=utf-8')
            if path == '/table-tools.css':
                return self.send(200, (ROOT / 'web' / 'table-tools.css').read_bytes(), 'text/css; charset=utf-8')
            if path == '/table-tools.js':
                return self.send(200, (ROOT / 'web' / 'table-tools.js').read_bytes(), 'text/javascript; charset=utf-8')
            files = {'/resume-submit': ('index.html', 'text/html; charset=utf-8'), '/onboard': ('index.html', 'text/html; charset=utf-8'), '/': ('index.html', 'text/html; charset=utf-8'), '/apply': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path in files:
                filename, content_type = files[path]
                return self.send(200, (ROOT / 'web' / filename).read_bytes(), content_type)
        self.send(404, {'error': '页面不存在'})

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8116)
    args = parser.parse_args()
    initialize()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    local_url = f'http://localhost:{args.port}'
    print(f'Campus recruitment: {local_url}', flush=True)
    access_url = public_base_url('localhost:' + str(args.port), args.port)
    if access_url != local_url:
        print(f'LAN: {access_url}', flush=True)
    print(f'Admin: admin; initial password file: {DATA / "initial-password.txt"}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
