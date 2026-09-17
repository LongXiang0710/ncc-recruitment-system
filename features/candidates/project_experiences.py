"""社会招聘人才的项目经历子表。"""
import re


FIELDS = ('project_name', 'role', 'start_date', 'end_date', 'description')
TABLE = 'candidate_project_experiences'


def ensure_table(conn):
    conn.execute(f'''CREATE TABLE IF NOT EXISTS {TABLE} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
        position_order INTEGER NOT NULL,
        project_name TEXT NOT NULL,
        role TEXT NOT NULL,
        start_date TEXT NOT NULL DEFAULT '',
        end_date TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT ''
    )''')
    conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{TABLE}_candidate ON {TABLE}(candidate_id,position_order)')


def _month(value, row_number, label):
    value = str(value or '').strip()
    if not value:
        return ''
    match = re.fullmatch(r'(\d{4})-(\d{2})', value)
    if not match or int(match[1]) < 1 or not 1 <= int(match[2]) <= 12:
        raise ValueError(f'第{row_number}条项目经历的{label}须为有效年月，如2026-07')
    return f'{int(match[1]):04d}-{int(match[2]):02d}'


def payload_values(payload, recruitment_type):
    if recruitment_type != '社会招聘':
        return None
    rows = payload.get('project_experiences') if isinstance(payload, dict) else None
    if rows is None:
        return None
    if not isinstance(rows, list) or len(rows) > 10:
        raise ValueError('项目经历最多填写10条')
    result = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or any(isinstance(row.get(field), (dict, list, bool)) for field in FIELDS):
            raise ValueError(f'第{index}条项目经历格式不正确')
        values = {field: str(row.get(field) or '').strip() for field in FIELDS}
        if not any(values.values()):
            continue
        if not values['project_name']:
            raise ValueError(f'请填写第{index}条项目经历的项目名称')
        if not values['start_date']:
            raise ValueError(f'请填写第{index}条项目经历的开始时间')
        if any(len(values[field]) > (5000 if field == 'description' else 300) for field in FIELDS):
            raise ValueError(f'第{index}条项目经历内容过长')
        values['start_date'] = _month(values['start_date'], index, '开始时间')
        values['end_date'] = _month(values['end_date'], index, '结束时间')
        if values['start_date'] and values['end_date'] and values['start_date'] > values['end_date']:
            raise ValueError(f'第{index}条项目经历的开始时间不能晚于结束时间')
        result.append(values)
    return result


def save(conn, candidate_id, recruitment_type, rows):
    if recruitment_type != '社会招聘':
        conn.execute(f'DELETE FROM {TABLE} WHERE candidate_id=?', (candidate_id,))
        return
    if rows is None:
        return
    conn.execute(f'DELETE FROM {TABLE} WHERE candidate_id=?', (candidate_id,))
    conn.executemany(
        f'''INSERT INTO {TABLE}(candidate_id,position_order,project_name,role,start_date,end_date,description)
            VALUES(?,?,?,?,?,?,?)''',
        [(candidate_id, index, *(row[field] for field in FIELDS)) for index, row in enumerate(rows, 1)],
    )


def read(conn, candidate_id):
    return [dict(row) for row in conn.execute(
        f'''SELECT project_name,role,start_date,end_date,description FROM {TABLE}
            WHERE candidate_id=? ORDER BY position_order,id''',
        (candidate_id,),
    )]
