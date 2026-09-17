"""人才库的身份证解析等专用业务规则。"""
import re
from datetime import datetime


POLITICAL_STATUS_ALIASES = {
    '团员': '共青团员',
    '预备党员': '中共预备党员',
    '党员': '中共党员',
}


def normalize_political_status(value):
    """将历史简称统一为系统中的正式政治面貌名称。"""
    text = str(value or '').strip()
    return POLITICAL_STATUS_ALIASES.get(text, text)


def identity_details(value):
    number = str(value or '').strip().upper()
    if not re.fullmatch(r'[1-9]\d{16}[0-9X]', number):
        raise ValueError('身份证须为18位号码，末位可为X')
    try:
        birthday = datetime.strptime(number[6:14], '%Y%m%d').date()
    except ValueError:
        raise ValueError('身份证中的出生日期无效')
    if birthday > datetime.now().date():
        raise ValueError('身份证中的出生日期不能晚于今天')
    if number[14:17] == '000':
        raise ValueError('身份证顺序码不能为000')
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    checksum = '10X98765432'[sum(int(digit) * weight for digit, weight in zip(number[:17], weights)) % 11]
    if number[-1] != checksum:
        raise ValueError('身份证校验码不正确，请核对完整号码')
    return {'identity_card': number, 'birthdate': birthday.strftime('%Y-%m'), 'gender': '男' if int(number[16]) % 2 else '女'}


def normalize_recruitment(payload):
    result = dict(payload)
    channel = str(result.get('channel') or '').strip()
    kind = result.get('recruitment_type') or ('社会招聘' if channel in ('boss直聘', '化工英才网', '其他') else '校园招聘' if channel else '')
    kind = {'\u6821\u62db': '校园招聘', '\u793e\u62db': '社会招聘'}.get(kind, kind)
    result['recruitment_type'] = kind
    choices = {'校园招聘': ('校园线下', '校园平台', '智联招聘'), '社会招聘': ('boss直聘', '智联招聘', '化工英才网', '其他')}
    if channel and channel not in choices.get(kind, ()):
        raise ValueError('招聘渠道与招聘类型不匹配')
    if channel == '其他' and not str(result.get('channel_detail') or '').strip():
        raise ValueError('请填写其他渠道详情')
    if channel != '其他':
        result['channel_detail'] = ''
    return result
