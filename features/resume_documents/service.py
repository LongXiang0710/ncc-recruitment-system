"""简历功能的 Dify 嵌入地址规则。"""
import os
import re
from urllib.parse import urlparse

DEFAULT_DIFY_EMBED_URL = 'http://biaozhun.njncc.com/workflow/e3JaA7Tg8GrWKJi5'


def dify_embed_url():
    value = os.environ.get('DIFY_EMBED_URL', DEFAULT_DIFY_EMBED_URL).strip()
    parsed = urlparse(value)
    if parsed.scheme in ('http', 'https') and re.fullmatch(r'[A-Za-z0-9.\-:\[\]]+', parsed.netloc):
        return value
    return ''


def normalize_recruitment(payload, candidate_service):
    return candidate_service.normalize_recruitment(payload)
