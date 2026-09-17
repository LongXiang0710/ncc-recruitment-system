"""应聘登记的公开字段、人才资料带入和语言摘要。"""

APPLICATION_COPY_FIELDS = ('name', 'school_name', 'major', 'gender', 'hometown', 'birthdate', 'phone', 'email', 'education', 'political_status', 'position', 'position_detail', 'channel')


def public_fields(schema, internal_fields):
    return [dict(field, required=True) if field['key'] in ('phone', 'major', 'education') else dict(field)
            for field in schema['fields']
            if not field.get('hidden') and field['key'] not in internal_fields]


def language_summary(application):
    fields = (('language', '语言能力'), ('english_level', '英语等级'), ('other_language', '其他语言能力'), ('language_scores', '雅思/托福成绩'))
    return '；'.join(label + '：' + str(application[key]).strip() for key, label in fields if application[key] and str(application[key]).strip())


def prefill(candidate, conn, education_rows):
    values = {key: candidate[key] or '' for key in APPLICATION_COPY_FIELDS}
    values['education_experiences'] = education_rows(conn, 'candidates', candidate['id'])
    values['archive_no'] = candidate['archive_no'] or ''
    if candidate['school_id']:
        school = conn.execute('SELECT * FROM schools WHERE id=?', (candidate['school_id'],)).fetchone()
    else:
        matches = conn.execute('SELECT * FROM schools WHERE name=?', (candidate['school_name'],)).fetchall()
        school = matches[0] if len(matches) == 1 else None
    if school:
        values.update({key: school[key] or '' for key in ('is_985', 'is_211', 'is_double_first')})
    return values


def prepare_validation(payload, conn, application_prefill):
    result = dict(payload)
    if 'phone' in result:
        match = conn.execute('SELECT id FROM candidates WHERE phone=?', (str(result.get('phone') or '').strip(),)).fetchone()
        result['candidate_id'] = match['id'] if match else None
    if result.get('candidate_id'):
        candidate = conn.execute('SELECT * FROM candidates WHERE id=?', (result['candidate_id'],)).fetchone()
        if candidate:
            for key, value in application_prefill(candidate, conn).items():
                if key not in result or key in ('name', 'school_name') and not result[key]:
                    result[key] = value
    return result
