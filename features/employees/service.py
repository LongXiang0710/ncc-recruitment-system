"""新员工登记从应聘资料带入字段的规则。"""


def source_values(application, language_summary):
    keys = ('name', 'identity_card', 'gender', 'ethnicity', 'birthdate', 'phone', 'school_name', 'education', 'major', 'is_elite', 'position', 'position_detail', 'enrollment_type', 'language', 'channel', 'hometown')
    return {**{key: application[key] for key in keys}, 'language': language_summary(application), 'archive_no': application['archive_no']}


def prepare_validation(payload, conn, interview_source, employee_source_values):
    result = dict(payload)
    if 'identity_card' in result:
        application = interview_source(result['identity_card'], conn)
        if application:
            for key, value in employee_source_values(application).items():
                if key not in result or key == 'name' and not result[key]:
                    result[key] = value
    return result
