"""Map the published Dify resume schema to the talent-library payload."""
import re
from datetime import date


LABEL_FIELDS = {
    '招聘类型': 'recruitment_type', '姓名': 'name', '性别': 'gender', '出生日期': 'birthdate', '年龄': 'age',
    '毕业院校': 'school_name', '学历': 'education', '专业': 'major', '联系方式': 'phone',
    '电子邮箱': 'email', '政治面貌': 'political_status', '籍贯/居住地': 'hometown',
    '招聘渠道': 'channel', '其他渠道详情': 'channel_detail', '投递时间': 'applied_at', '投递岗位': 'position'
}
FLAT_FIELDS = {
    'recruitment_type', 'name', 'gender', 'birthdate', 'age', 'school_name', 'education',
    'major', 'phone', 'email', 'political_status', 'hometown', 'channel',
    'channel_detail', 'applied_at', 'position', 'status', 'notes'
} | set(LABEL_FIELDS)


def _text(value):
    return '' if value is None or isinstance(value, (dict, list, bool)) else str(value).strip()


def _rows(value):
    return value if isinstance(value, list) else []


def _month(value, year_default=''):
    value = _text(value)
    year_only = re.fullmatch(r'(\d{4})年?', value)
    if year_only:
        year = int(year_only[1])
        return f'{year:04d}-{year_default}' if year >= 1 and year_default else ''
    match = re.fullmatch(r'(\d{4})(?:-|/|年)(\d{1,2})月?', value)
    if not match:
        full = re.fullmatch(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', value)
        if not full:
            return ''
        try:
            date(int(full[1]), int(full[2]), int(full[3]))
        except ValueError:
            return ''
        match = full
    year, month = int(match[1]), int(match[2])
    return f'{year:04d}-{month:02d}' if year >= 1 and 1 <= month <= 12 else ''


def _birthdate(value):
    return _month(value)


def _age(value):
    match = re.fullmatch(r'(\d{1,3})\s*岁?', _text(value))
    if not match:
        return ''
    age = int(match[1])
    return str(age) if 1 <= age <= 100 else ''


def _gender(value):
    value = _text(value)
    value = {'男性': '男', 'male': '男', 'Male': '男', '女性': '女', 'female': '女', 'Female': '女'}.get(value, value)
    return value if value in ('男', '女', '不便透露') else ''


def _education(value):
    value = _text(value)
    value = {'大专': '专科', '学士': '本科', '本科毕业': '本科', '硕士研究生': '硕士', '博士研究生': '博士'}.get(value, value)
    return value if value in ('专科', '本科', '硕士', '博士') else ''


def _end(value, year_default=''):
    value = _text(value)
    return '' if value in ('至今', '现在', '当前', 'present', 'Present') else _month(value, year_default)


def _latest_first(rows, primary_field, fallback_field):
    return sorted(
        rows,
        key=lambda row: (
            bool(row.get(primary_field) or row.get(fallback_field)),
            row.get(primary_field) or row.get(fallback_field) or '',
        ),
        reverse=True,
    )


def _flat_result(result):
    payload = {LABEL_FIELDS.get(key, key): _text(value) for key, value in result.items() if key in FLAT_FIELDS and not isinstance(value, (dict, list))}
    if 'gender' in payload:
        payload['gender'] = _gender(payload['gender'])
    if 'education' in payload:
        payload['education'] = _education(payload['education'])
    if 'birthdate' in payload:
        payload['birthdate'] = _birthdate(payload['birthdate'])
    if 'age' in payload:
        payload['age'] = _age(payload['age'])
    return {key: value for key, value in payload.items() if value}


def to_candidate_payload(result, source):
    if not isinstance(result, dict):
        raise ValueError('Dify 识别结果须为 JSON 对象')
    candidate = result.get('candidate')
    if not isinstance(candidate, dict):
        payload = _flat_result(result)
    else:
        basic = candidate.get('basic') if isinstance(candidate.get('basic'), dict) else {}
        aliases = {
            'name': 'name', 'gender': 'gender',
            'phone': 'phone', 'email': 'email', 'political_status': 'political_status',
            'hometown_raw': 'hometown'
        }
        payload = {target: _text(basic.get(source_key)) for source_key, target in aliases.items() if _text(basic.get(source_key))}
        gender = _gender(payload.get('gender'))
        if gender:
            payload['gender'] = gender
        else:
            payload.pop('gender', None)
        birthdate = _birthdate(basic.get('birth_date'))
        if birthdate:
            payload['birthdate'] = birthdate
        age = _age(basic.get('age'))
        if age:
            payload['age'] = age
        education = []
        for row in _rows(candidate.get('education')):
            if isinstance(row, dict):
                degree = _education(row.get('degree'))
                mapped = {
                    'education': degree, 'school_name': _text(row.get('school')),
                    'major': _text(row.get('major')), 'enrollment': _month(row.get('start_date'), '09'),
                    'graduation': _end(row.get('end_date'), '07')
                }
                if any(mapped.values()):
                    education.append(mapped)
        if education:
            payload['education_experiences'] = _latest_first(education, 'graduation', 'enrollment')
        work = []
        for row in _rows(candidate.get('work_experience')):
            if isinstance(row, dict):
                mapped = {
                    'organization': _text(row.get('company')), 'position': _text(row.get('position')),
                    'start_date': _month(row.get('start_date')), 'end_date': _end(row.get('end_date')),
                    'description': _text(row.get('description')) or _text(row.get('responsibilities'))
                }
                if any(mapped.values()):
                    work.append(mapped)
        if work:
            payload['work_experiences'] = _latest_first(work, 'start_date', 'end_date')
        if source.get('recruitment_type') == '社会招聘':
            projects = []
            for row in _rows(candidate.get('projects')):
                if isinstance(row, dict):
                    mapped = {
                        'project_name': _text(row.get('project_name')), 'role': _text(row.get('role')),
                        'start_date': _month(row.get('start_date')), 'end_date': _end(row.get('end_date')),
                        'description': _text(row.get('description'))
                    }
                    if any(mapped.values()):
                        projects.append(mapped)
            if projects:
                payload['project_experiences'] = _latest_first(projects, 'start_date', 'end_date')
    if not payload:
        raise ValueError('工作流未返回可用的人才字段，请检查 Dify 输出')
    payload['recruitment_type'] = _text(source.get('recruitment_type') or result.get('recruitment_type'))
    payload['channel'] = _text(source.get('channel'))
    payload['channel_detail'] = _text(source.get('channel_detail'))
    position = _text(source.get('position') or result.get('position_name'))
    if position:
        payload['position'] = position
        position_detail = _text(source.get('position_detail'))
        if position_detail:
            payload['position_detail'] = position_detail
    return payload
