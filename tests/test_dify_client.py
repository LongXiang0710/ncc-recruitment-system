import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
import dify_client


class DifyClientTests(unittest.TestCase):
    def test_published_workflow_uses_project_defaults(self):
        with patch.dict('os.environ', {'DIFY_API_KEY': 'test-key'}, clear=True):
            self.assertEqual(dify_client.configuration(), {
                'API_URL': 'http://biaozhun.njncc.com/v1',
                'API_KEY': 'test-key',
                'FILE_VARIABLE': 'resume_file',
                'OUTPUT_VARIABLE': ''
            })

    def test_file_upload_and_workflow_output(self):
        requests = []
        def respond(request, timeout):
            requests.append(request)
            result = {'id': 'uploaded-file'} if len(requests) == 1 else {'data': {'status': 'succeeded', 'outputs': {'result': '{"name":"张三"}'}}}
            return io.BytesIO(json.dumps(result).encode())
        env = {'DIFY_API_URL': 'https://dify.example/v1', 'DIFY_API_KEY': 'test-key', 'DIFY_FILE_VARIABLE': 'resume', 'DIFY_OUTPUT_VARIABLE': 'result', 'DIFY_SOURCE_VARIABLE': 'source_id', 'DIFY_FILE_LIST': '1'}
        with patch.dict('os.environ', env, clear=True), patch('dify_client.urlopen', side_effect=respond):
            self.assertEqual(dify_client.recognize(b'%PDF-test', '20260909120000'), {'name': '张三'})
        self.assertTrue(requests[0].full_url.endswith('/files/upload'))
        self.assertIn(b'%PDF-test', requests[0].data)
        payload = json.loads(requests[1].data)
        self.assertEqual(payload['inputs']['resume'][0]['upload_file_id'], 'uploaded-file')
        self.assertEqual(payload['inputs']['source_id'], '20260909120000')
        self.assertEqual(payload['response_mode'], 'blocking')

    def test_file_upload_retries_twice_before_running_workflow_once(self):
        requests = []

        def respond(request, timeout):
            requests.append(request)
            if len(requests) <= 2:
                raise URLError('temporary upload failure')
            result = {'id': 'uploaded-after-retry'} if len(requests) == 3 else {
                'data': {'status': 'succeeded', 'outputs': {'result': '{"name":"重试成功"}'}}
            }
            return io.BytesIO(json.dumps(result, ensure_ascii=False).encode())

        env = {'DIFY_API_KEY': 'test-key', 'DIFY_OUTPUT_VARIABLE': 'result'}
        with patch.dict('os.environ', env, clear=True), \
                patch('dify_client.urlopen', side_effect=respond), \
                patch('dify_client.sleep', create=True):
            try:
                result = dify_client.recognize(b'%PDF-test', 'upload-retry')
            except ValueError as error:
                self.fail(f'文件上传遇到临时错误后未自动重试：{error}')

        self.assertEqual(result, {'name': '重试成功'})
        self.assertEqual([request.full_url.rsplit('/', 2)[-2:] for request in requests], [
            ['files', 'upload'], ['files', 'upload'], ['files', 'upload'], ['workflows', 'run']
        ])

    def test_exhausted_upload_retries_name_the_upload_stage(self):
        requests = []

        def fail_upload(request, timeout):
            requests.append(request)
            raise URLError('upload unavailable')

        with patch.dict('os.environ', {'DIFY_API_KEY': 'test-key'}, clear=True), \
                patch('dify_client.urlopen', side_effect=fail_upload), \
                patch('dify_client.sleep', create=True):
            with self.assertRaisesRegex(ValueError, 'Dify 文件上传失败或超时'):
                dify_client.recognize(b'%PDF-test', 'upload-failure')
        self.assertEqual(len(requests), 3)

    def test_exhausted_upload_writes_safe_diagnostics_with_matching_id(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / 'dify-errors.log'
            env = {
                'DIFY_API_KEY': 'secret-api-key',
                'DIFY_ERROR_LOG': os.fspath(log_path),
            }
            with patch.dict('os.environ', env, clear=True), \
                    patch('dify_client.urlopen', side_effect=URLError('private-upload-details')), \
                    patch('dify_client.sleep', create=True):
                with self.assertRaisesRegex(ValueError, r'Dify 文件上传失败或超时（诊断编号：[0-9a-f]{8}）') as raised:
                    dify_client.recognize(b'%PDF-private-resume-content', 'private-source-id', filename='private-name.pdf')

            self.assertTrue(log_path.exists(), 'Dify 失败时应创建诊断日志')
            events = [json.loads(line) for line in log_path.read_text(encoding='utf-8').splitlines()]
            diagnostic_id = str(raised.exception).split('诊断编号：', 1)[1].split('）', 1)[0]
            self.assertEqual([event['attempt'] for event in events], [1, 2, 3])
            self.assertEqual({event['diagnostic_id'] for event in events}, {diagnostic_id})
            self.assertEqual({event['stage'] for event in events}, {'文件上传'})
            self.assertEqual({event['error_type'] for event in events}, {'URLError'})
            serialized = log_path.read_text(encoding='utf-8')
            for private_value in ('secret-api-key', 'private-upload-details', 'private-resume-content', 'private-source-id', 'private-name.pdf'):
                self.assertNotIn(private_value, serialized)

    def test_workflow_connection_failure_is_not_retried(self):
        requests = []

        def respond(request, timeout):
            requests.append(request)
            if len(requests) == 1:
                return io.BytesIO(json.dumps({'id': 'uploaded-file'}).encode())
            raise URLError('workflow unavailable')

        with patch.dict('os.environ', {'DIFY_API_KEY': 'test-key'}, clear=True), \
                patch('dify_client.urlopen', side_effect=respond):
            with self.assertRaisesRegex(ValueError, 'Dify 工作流连接失败或超时'):
                dify_client.recognize(b'%PDF-test', 'workflow-failure')
        self.assertEqual(len(requests), 2)

    def test_workflow_context_and_nested_json_output_are_detected(self):
        requests = []
        nested = {'schema_version': '1.0', 'candidate': {'basic': {'name': '陈芝平'}}}
        def respond(request, timeout):
            requests.append(request)
            result = {'id': 'uploaded-file'} if len(requests) == 1 else {
                'data': {'status': 'succeeded', 'outputs': {
                    'valid': True, 'parse_status': 'success',
                    'resume_json': json.dumps(nested, ensure_ascii=False), 'warnings': []
                }}
            }
            return io.BytesIO(json.dumps(result, ensure_ascii=False).encode())
        env = {'DIFY_API_URL': 'http://biaozhun.njncc.com/v1', 'DIFY_API_KEY': 'test-key', 'DIFY_FILE_VARIABLE': 'resume_file'}
        metadata = {
            'recruitment_type': '社会招聘', 'channel': '其他', 'channel_detail': '行业推荐',
            'position': '其它', 'position_detail': '管道工程师',
        }
        with patch.dict('os.environ', env, clear=True), patch('dify_client.urlopen', side_effect=respond):
            result = dify_client.recognize(b'%PDF-test', '20260910112233', metadata)
        self.assertEqual(result, nested)
        payload = json.loads(requests[1].data)
        self.assertEqual(payload['inputs'], {
            'resume_file': {'type': 'document', 'transfer_method': 'local_file', 'upload_file_id': 'uploaded-file'},
            'recruitment_type': '社会招聘',
            'source_channel': '其他',
            'position_name': '管道工程师'
        })

    def test_required_recruitment_type_is_checked_before_upload(self):
        env = {'DIFY_API_KEY': 'test-key'}
        with patch.dict('os.environ', env, clear=True), patch('dify_client.urlopen', side_effect=AssertionError('不应上传文件')):
            with self.assertRaisesRegex(ValueError, '招聘类型'):
                dify_client.recognize(b'%PDF-test', '20260910112234', {'recruitment_type': '', 'channel': ''})

    def test_system_channels_are_mapped_to_published_workflow_options(self):
        cases = (
            ('boss直聘', 'Boss直聘'),
            ('校园线下', '校园招聘'),
            ('校园平台', '校招平台'),
        )
        for system_channel, workflow_channel in cases:
            with self.subTest(system_channel=system_channel):
                requests = []

                def respond(request, timeout):
                    requests.append(request)
                    result = {'id': 'uploaded-file'} if len(requests) == 1 else {
                        'data': {'status': 'succeeded', 'outputs': {'result': '{"name":"测试人才"}'}}
                    }
                    return io.BytesIO(json.dumps(result).encode())

                metadata = {'recruitment_type': '社会招聘', 'channel': system_channel}
                env = {'DIFY_API_KEY': 'test-key', 'DIFY_OUTPUT_VARIABLE': 'result'}
                with patch.dict('os.environ', env, clear=True), patch('dify_client.urlopen', side_effect=respond):
                    dify_client.recognize(b'%PDF-test', 'channel-mapping', metadata)
                payload = json.loads(requests[1].data)
                self.assertEqual(payload['inputs']['source_channel'], workflow_channel)

    def test_image_resume_keeps_filename_mime_and_dify_file_kind(self):
        requests = []
        def respond(request, timeout):
            requests.append(request)
            result = {'id': 'uploaded-image'} if len(requests) == 1 else {'data': {'status': 'succeeded', 'outputs': {'result': '{"name":"图片人才"}'}}}
            return io.BytesIO(json.dumps(result).encode())
        env = {'DIFY_API_KEY': 'test-key', 'DIFY_OUTPUT_VARIABLE': 'result'}
        metadata = {'recruitment_type': '校园招聘', 'channel': '校园平台'}
        with patch.dict('os.environ', env, clear=True), patch('dify_client.urlopen', side_effect=respond):
            self.assertEqual(dify_client.recognize(b'\x89PNG\r\n\x1a\nresume', 'image-source', metadata, 'candidate.PNG'), {'name': '图片人才'})
        self.assertIn(b'filename="candidate.PNG"', requests[0].data)
        self.assertIn(b'Content-Type: image/png', requests[0].data)
        payload = json.loads(requests[1].data)
        self.assertEqual(payload['inputs']['resume_file']['type'], 'image')

    def test_legacy_flat_candidate_output_is_auto_detected(self):
        flat = {'name': '旧格式人才', 'phone': '13900000000'}
        self.assertEqual(dify_client._workflow_output(flat, ''), flat)
        self.assertEqual(dify_client._workflow_output({'status': 'success', 'result': json.dumps(flat)}, ''), flat)
        self.assertIsNone(dify_client._workflow_output({'status': 'success', 'message': 'done'}, ''))
        nested = {'candidate': {'basic': {'name': '正确人才'}}}
        self.assertEqual(dify_client._workflow_output({'name': 'parser-status', 'resume_json': json.dumps(nested, ensure_ascii=False)}, ''), nested)
