"""Server-side Dify workflow adapter; credentials never reach the browser."""
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from features.resume_documents import file_types as resume_file_types


WORKFLOW_CHANNELS = {
    'boss直聘': 'Boss直聘',
    '校园线下': '校园招聘',
    '校园平台': '校招平台',
}


def _write_diagnostic(diagnostic_id, stage, attempt, max_attempts, error):
    """Append a privacy-safe Dify failure event without request or response data."""
    reason = error.reason if isinstance(error, URLError) else error
    event = {
        'time': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
        'diagnostic_id': diagnostic_id,
        'stage': stage,
        'attempt': attempt,
        'max_attempts': max_attempts,
        'error_type': type(error).__name__,
        'reason_type': type(reason).__name__,
    }
    if isinstance(error, HTTPError):
        event['http_status'] = error.code
    for name in ('errno', 'winerror'):
        value = getattr(reason, name, None)
        if isinstance(value, int):
            event[name] = value
    default_path = Path(__file__).resolve().parent / 'data' / 'dify-errors.log'
    path = Path(os.environ.get('DIFY_ERROR_LOG', '').strip() or default_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as log:
            log.write(json.dumps(event, ensure_ascii=False) + '\n')
    except OSError:
        # Logging must never replace the original recognition error.
        pass


def configuration():
    values = {key: os.environ.get('DIFY_' + key, '').strip() for key in ('API_URL', 'API_KEY', 'FILE_VARIABLE', 'OUTPUT_VARIABLE')}
    values['API_URL'] = values['API_URL'] or 'http://biaozhun.njncc.com/v1'
    values['FILE_VARIABLE'] = values['FILE_VARIABLE'] or 'resume_file'
    if not values['API_KEY']:
        raise ValueError('尚未配置自动识别，请先运行“配置Dify.bat”设置工作流 API Key')
    if urlparse(values['API_URL']).scheme not in ('http', 'https'):
        raise ValueError('DIFY_API_URL 必须是 http 或 https 地址')
    return values


def _json_object(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _workflow_output(outputs, variable):
    if variable:
        return _json_object(outputs.get(variable)) if isinstance(outputs, dict) else None
    def nested_candidate(value):
        parsed = _json_object(value)
        return parsed if parsed and isinstance(parsed.get('candidate'), dict) else None
    def flat_candidate(value):
        parsed = _json_object(value)
        core = {'name', 'phone', 'school_name', 'education', 'major'}
        return parsed if parsed and len(core & set(parsed)) >= 2 else None
    direct = nested_candidate(outputs)
    if direct:
        return direct
    if isinstance(outputs, dict):
        for value in outputs.values():
            parsed = nested_candidate(value)
            if parsed:
                return parsed
    direct = flat_candidate(outputs)
    if direct:
        return direct
    if isinstance(outputs, dict):
        for value in outputs.values():
            parsed = flat_candidate(value)
            if parsed:
                return parsed
    return None


def recognize(content, source_id, metadata=None, filename='resume.pdf'):
    config = configuration()
    if metadata is not None and metadata.get('recruitment_type') not in ('校园招聘', '社会招聘'):
        raise ValueError('请先在简历记录中填写招聘类型，再执行 Dify 识别')
    base = config['API_URL'].rstrip('/')
    user = 'recruitment-' + source_id

    def post(path, data, content_type, stage, retries=0):
        request = Request(base + path, data=data, headers={'Authorization': 'Bearer ' + config['API_KEY'], 'Content-Type': content_type}, method='POST')
        diagnostic_id = secrets.token_hex(4)
        max_attempts = retries + 1
        for attempt in range(retries + 1):
            try:
                with urlopen(request, timeout=120) as response:
                    return json.load(response)
            except HTTPError as error:
                _write_diagnostic(diagnostic_id, stage, attempt + 1, max_attempts, error)
                raise ValueError(f'Dify {stage}请求失败（HTTP {error.code}，诊断编号：{diagnostic_id}），请检查工作流配置') from None
            except (URLError, TimeoutError, OSError) as error:
                _write_diagnostic(diagnostic_id, stage, attempt + 1, max_attempts, error)
                if attempt < retries:
                    sleep(2 ** attempt)
                    continue
                raise ValueError(f'Dify {stage}失败或超时（诊断编号：{diagnostic_id}），请检查服务地址后重试') from None
            except (ValueError, TypeError) as error:
                _write_diagnostic(diagnostic_id, stage, attempt + 1, max_attempts, error)
                raise ValueError(f'Dify {stage}返回内容不是有效 JSON（诊断编号：{diagnostic_id}）') from None

    boundary = 'Recruitment' + secrets.token_hex(16)
    filename = str(filename or 'resume.pdf').replace('\\', '/').split('/')[-1]
    if not filename or any(ord(character) < 32 or character in '"' for character in filename):
        filename = 'resume' + resume_file_types.extension(filename or 'resume.pdf')
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="user"\r\n\r\n{user}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {resume_file_types.mime_type(filename)}\r\n\r\n').encode() + content + f'\r\n--{boundary}--\r\n'.encode()
    uploaded = post('/files/upload', body, 'multipart/form-data; boundary=' + boundary, '文件上传', retries=2)
    if not isinstance(uploaded, dict) or not uploaded.get('id'):
        raise ValueError('Dify 未返回上传文件标识')
    file = {'type': resume_file_types.dify_kind(filename), 'transfer_method': 'local_file', 'upload_file_id': uploaded['id']}
    inputs = {config['FILE_VARIABLE']: [file] if os.environ.get('DIFY_FILE_LIST') == '1' else file}
    if metadata is not None:
        channel = str(metadata.get('channel') or '').strip()
        if not channel:
            channel = '校园平台' if metadata.get('recruitment_type') == '校园招聘' else '其他'
        channel = WORKFLOW_CHANNELS.get(channel, channel)
        position = metadata.get('position_detail') if metadata.get('position') == '其它' else metadata.get('position')
        inputs.update(recruitment_type=str(metadata.get('recruitment_type') or ''), source_channel=channel, position_name=str(position or ''))
    else:
        source_variable = os.environ.get('DIFY_SOURCE_VARIABLE', '').strip()
        if source_variable:
            inputs[source_variable] = source_id
    result = post('/workflows/run', json.dumps({'inputs': inputs, 'response_mode': 'blocking', 'user': user}).encode(), 'application/json', '工作流连接')
    data = result.get('data', {}) if isinstance(result, dict) else {}
    if not isinstance(data, dict) or data.get('status') != 'succeeded':
        raise ValueError('Dify 工作流未成功完成，请查看 Dify 运行日志')
    outputs = _workflow_output(data.get('outputs', {}), config['OUTPUT_VARIABLE'])
    if not isinstance(outputs, dict) or not outputs:
        raise ValueError('识别结果须为人才字段对象，请配置 DIFY_OUTPUT_VARIABLE')
    return outputs
