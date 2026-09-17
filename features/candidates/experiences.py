"""人才库通用工作经历子表。"""
import re


EXPERIENCE_KEY = 'work_experiences'
EXPERIENCE_TABLE = 'candidate_work_experiences'
EXPERIENCE_LABEL = '工作经历'
FIELDS = ('organization', 'position', 'start_date', 'end_date', 'description')


def ensure_tables(conn):
    conn.execute(f'''CREATE TABLE IF NOT EXISTS {EXPERIENCE_TABLE} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        position_order INTEGER NOT NULL,
        organization TEXT NOT NULL,
        position TEXT NOT NULL,
        start_date TEXT NOT NULL DEFAULT '',
        end_date TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT ''
    )''')
    conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{EXPERIENCE_TABLE}_candidate ON {EXPERIENCE_TABLE}(candidate_id,position_order)')
    legacy = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='candidate_internship_experiences'").fetchone()
    if legacy:
        if conn.execute('SELECT 1 FROM candidate_internship_experiences LIMIT 1').fetchone():
            raise ValueError('检测到旧实习经历数据，请先确认后再统一为工作经历')
        conn.execute('DROP TABLE candidate_internship_experiences')


def _month(value, row_number, kind, label):
    value = str(value or '').strip()
    if not value:
        return ''
    match = re.fullmatch(r'(\d{4})[-/年](\d{1,2})(?:月|[-/]\d{1,2})?', value)
    if not match or int(match[1]) < 1 or not 1 <= int(match[2]) <= 12:
        raise ValueError(f'第{row_number}条{kind}的{label}须为有效年月，如2026-07')
    return f'{int(match[1]):04d}-{int(match[2]):02d}'


def payload_values(payload):
    key, kind = EXPERIENCE_KEY, EXPERIENCE_LABEL
    rows = payload.get(key) if isinstance(payload, dict) else None
    if rows is None:
        return key, None
    if not isinstance(rows, list) or len(rows) > 10:
        raise ValueError(f'{kind}最多填写10条')
    result = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'第{index}条{kind}格式不正确')
        if any(isinstance(row.get(field), (dict, list, bool)) for field in FIELDS):
            raise ValueError(f'第{index}条{kind}格式不正确')
        values = {field: str(row.get(field) or '').strip() for field in FIELDS}
        if not any(values.values()):
            continue
        if not values['organization']:
            raise ValueError(f'请填写第{index}条{kind}的单位')
        if any(len(values[field]) > (5000 if field == 'description' else 300) for field in FIELDS):
            raise ValueError(f'第{index}条{kind}内容过长')
        values['start_date'] = _month(values['start_date'], index, kind, '开始时间')
        values['end_date'] = _month(values['end_date'], index, kind, '结束时间')
        if values['start_date'] and values['end_date'] and values['start_date'] > values['end_date']:
            raise ValueError(f'第{index}条{kind}的开始时间不能晚于结束时间')
        result.append(values)
    return key, result


def save(conn, candidate_id, active_rows):
    if active_rows is None:
        return
    conn.execute(f'DELETE FROM {EXPERIENCE_TABLE} WHERE candidate_id=?', (candidate_id,))
    conn.executemany(
        f'''INSERT INTO {EXPERIENCE_TABLE}(candidate_id,position_order,organization,position,start_date,end_date,description)
            VALUES(?,?,?,?,?,?,?)''',
        [(candidate_id, index, *(row[field] for field in FIELDS)) for index, row in enumerate(active_rows, 1)],
    )


def read(conn, candidate_id):
    return {EXPERIENCE_KEY: [dict(row) for row in conn.execute(
        f'''SELECT organization,position,start_date,end_date,description FROM {EXPERIENCE_TABLE}
            WHERE candidate_id=? ORDER BY position_order,id''',
        (candidate_id,),
    )]}
