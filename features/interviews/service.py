"""面试资料匹配、带入和字段筛选。"""


def prefill(candidate, conn, application_prefill, education_rows, schema, copy_fields):
    values = application_prefill(candidate, conn)
    values['resume'] = candidate['resume'] or ''
    application = conn.execute('SELECT * FROM applications WHERE candidate_id=? ORDER BY id DESC LIMIT 1', (candidate['id'],)).fetchone()
    if application:
        for key in (*copy_fields, 'identity_card', 'language', 'is_elite', 'transcript', 'certificates', 'resume'):
            if application[key]:
                values[key] = application[key]
        values['education_experiences'] = education_rows(conn, 'applications', application['id'])
    allowed = {field['key'] for field in schema['fields']} | {'education_experiences'}
    return {key: value for key, value in values.items() if key in allowed}


def source(identity, conn, identity_details):
    number = str(identity or '').strip().upper()
    if not number:
        return None
    identity_details(number)
    return conn.execute('SELECT * FROM applications WHERE upper(trim(identity_card))=? ORDER BY id DESC LIMIT 1', (number,)).fetchone()


def source_values(application, language_summary):
    keys = ('candidate_id', 'name', 'major', 'school_name', 'gender', 'hometown', 'birthdate', 'phone', 'education', 'position', 'position_detail', 'political_status', 'identity_card', 'language', 'is_elite', 'resume', 'transcript', 'certificates')
    return {**{key: application[key] for key in keys}, 'language': language_summary(application), 'archive_no': application['archive_no']}


def prepare_validation(payload, conn, identity_details, source_values_callback):
    result = dict(payload)
    if 'identity_card' in result:
        application = source(result['identity_card'], conn, identity_details)
        result['candidate_id'] = application['candidate_id'] if application else None
        if application:
            for key, value in source_values_callback(application).items():
                if key not in result or key in ('name', 'school_name') and not result[key]:
                    result[key] = value
    return result
