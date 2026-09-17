"""Supported resume file types and server-side content checks."""
import io
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET


DOCUMENT_EXTENSIONS = (
    '.txt', '.md', '.mdx', '.markdown', '.pdf', '.html', '.xlsx', '.xls',
    '.doc', '.docx', '.csv', '.eml', '.msg', '.pptx', '.ppt', '.xml', '.epub',
)
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')
ALL_EXTENSIONS = DOCUMENT_EXTENSIONS + IMAGE_EXTENSIONS
ACCEPT = ','.join(ALL_EXTENSIONS)

MIME_TYPES = {
    '.txt': 'text/plain', '.md': 'text/markdown', '.mdx': 'text/markdown',
    '.markdown': 'text/markdown', '.pdf': 'application/pdf', '.html': 'text/html',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xls': 'application/vnd.ms-excel', '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.csv': 'text/csv', '.eml': 'message/rfc822', '.msg': 'application/vnd.ms-outlook',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.ppt': 'application/vnd.ms-powerpoint', '.xml': 'application/xml',
    '.epub': 'application/epub+zip', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp', '.svg': 'image/svg+xml',
}

TEXT_EXTENSIONS = {'.txt', '.md', '.mdx', '.markdown', '.html', '.csv', '.eml'}
OLE_EXTENSIONS = {'.doc', '.xls', '.msg', '.ppt'}
ZIP_MARKERS = {
    '.docx': ('[Content_Types].xml', 'word/document.xml'),
    '.xlsx': ('[Content_Types].xml', 'xl/workbook.xml'),
    '.pptx': ('[Content_Types].xml', 'ppt/presentation.xml'),
    '.epub': ('mimetype', 'META-INF/container.xml'),
}


def extension(filename):
    return Path(str(filename or '')).suffix.lower()


def mime_type(filename):
    return MIME_TYPES.get(extension(filename), 'application/octet-stream')


def dify_kind(filename):
    return 'image' if extension(filename) in IMAGE_EXTENSIONS else 'document'


def decode_text(content):
    for encoding in ('utf-8-sig', 'utf-16', 'gb18030'):
        try:
            text = content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        controls = sum(ord(char) < 32 and char not in '\r\n\t' for char in text)
        if not text or controls > max(2, len(text) // 50):
            continue
        return text
    return None


def _valid_zip(content, markers):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if not set(markers).issubset(names):
                return False
            if 'mimetype' in markers:
                return archive.read('mimetype').strip() == b'application/epub+zip'
            return True
    except (KeyError, OSError, zipfile.BadZipFile):
        return False


def valid_content(file_extension, content):
    file_extension = str(file_extension or '').lower()
    if file_extension not in ALL_EXTENSIONS or not content:
        return False
    if file_extension == '.pdf':
        return content.startswith(b'%PDF-')
    if file_extension in OLE_EXTENSIONS:
        return content.startswith(bytes.fromhex('D0CF11E0A1B11AE1'))
    if file_extension in ZIP_MARKERS:
        return _valid_zip(content, ZIP_MARKERS[file_extension])
    if file_extension in ('.jpg', '.jpeg'):
        return content.startswith(b'\xff\xd8\xff')
    if file_extension == '.png':
        return content.startswith(b'\x89PNG\r\n\x1a\n')
    if file_extension == '.gif':
        return content.startswith((b'GIF87a', b'GIF89a'))
    if file_extension == '.webp':
        return len(content) >= 12 and content.startswith(b'RIFF') and content[8:12] == b'WEBP'
    text = decode_text(content)
    if text is None:
        return False
    if file_extension in ('.xml', '.svg'):
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return False
        if file_extension == '.svg':
            return root.tag.rsplit('}', 1)[-1].lower() == 'svg'
    return True
