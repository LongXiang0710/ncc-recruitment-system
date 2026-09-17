"""招聘岗位的统一选项、自由文本兼容和“其它”说明规则。"""

POSITION_OPTIONS = (
    '机械工程师', '电气工程师', '安全工程师', '土建工程师',
    '管道工程师', '设备工程师', '数据分析师', '软件工程师',
    '财务专员', '其它',
)
PROMOTED_POSITION_OPTIONS = ('管道工程师', '设备工程师')
POSITION_ENTITIES = ('resume_documents', 'candidates', 'applications', 'interviews', 'employees')


def normalize_payload(payload):
    result = dict(payload)
    position = str(result.get('position') or '').strip()
    detail = str(result.get('position_detail') or '').strip()
    if position == '其他':
        position = '其它'
    if position == '其它' and detail in PROMOTED_POSITION_OPTIONS:
        position, detail = detail, ''
    elif position and position not in POSITION_OPTIONS:
        detail = detail or position
        position = '其它'
    if position == '其它' and not detail:
        raise ValueError('请填写其它岗位名称')
    if position != '其它':
        detail = ''
    result['position'] = position
    result['position_detail'] = detail
    return result


def migrate(conn):
    placeholders = ','.join('?' for _ in POSITION_OPTIONS)
    for entity in POSITION_ENTITIES:
        conn.execute(
            f'''UPDATE {entity}
                SET position_detail=CASE
                    WHEN COALESCE(TRIM(position_detail),'')='' THEN TRIM(position)
                    ELSE TRIM(position_detail) END,
                    position='其它'
                WHERE COALESCE(TRIM(position),'')!=''
                  AND TRIM(position) NOT IN ({placeholders})''',
            POSITION_OPTIONS,
        )
        promoted_placeholders = ','.join('?' for _ in PROMOTED_POSITION_OPTIONS)
        conn.execute(
            f'''UPDATE {entity}
                SET position=TRIM(position_detail), position_detail=''
                WHERE position='其它'
                  AND TRIM(position_detail) IN ({promoted_placeholders})''',
            PROMOTED_POSITION_OPTIONS,
        )
        conn.execute(
            f"UPDATE {entity} SET position_detail='' WHERE COALESCE(position,'')!='其它'"
        )
