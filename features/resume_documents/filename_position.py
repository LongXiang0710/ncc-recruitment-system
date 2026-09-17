"""Conservative job-position inference from uploaded resume filenames."""
from pathlib import Path
import re


POSITION_SUFFIXES = (
    '高级工程师', '工程师', '项目经理', '技术员', '施工员', '安全员', '资料员',
    '预算员', '造价员', '管理员', '设计师', '会计', '出纳', '专员', '主管',
    '经理', '总监', '助理', '实习生', '操作工', '焊工', '电工', '钳工',
)
POSITION_PATTERN = re.compile(r'^(.{0,40}?(?:' + '|'.join(map(re.escape, POSITION_SUFFIXES)) + r'))')
AGE_PATTERN = re.compile(r'^(?:1[6-9]|[2-5]\d|6[0-5])岁$')
NOISE_PATTERN = re.compile(r'^(?:\d+|简历|个人简历|校园招聘|社会招聘|校招|社招|智联简历|智联招聘|boss直聘|化工英才网)$', re.I)


def _candidate(segment, allow_plain=False):
    value = segment.strip(' _-—–()（）[]【】')
    if not value or len(value) > 50 or NOISE_PATTERN.fullmatch(value):
        return ''
    matched = POSITION_PATTERN.match(value)
    if matched:
        return matched.group(1)
    return value if allow_plain else ''


def infer_position(filename):
    """Return a likely position, or an empty string when the name is ambiguous."""
    stem = Path(str(filename or '').replace('\\', '/')).stem
    segments = [part for part in re.split(r'[_\-—–\s]+', stem) if part]
    for index, segment in enumerate(segments[:-1]):
        if AGE_PATTERN.fullmatch(segment):
            return _candidate(segments[index + 1], allow_plain=True)
    for segment in segments:
        result = _candidate(segment)
        if result:
            return result
    return ''
