import http.cookiejar
import json
from pathlib import Path
import tempfile
import sqlite3
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor
import server


class NetworkAddressTests(unittest.TestCase):
    def test_server_port_cannot_be_shared_by_multiple_processes(self):
        first = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        second = None
        try:
            with self.assertRaises(OSError):
                second = server.ThreadingHTTPServer(
                    ('127.0.0.1', first.server_port), server.Handler
                )
        finally:
            if second is not None:
                second.server_close()
            first.server_close()

    def test_active_route_is_preferred_and_unusable_ipv4_addresses_are_removed(self):
        order_addresses = getattr(server, 'order_lan_ipv4_addresses', lambda *_: [])

        self.assertEqual(
            order_addresses(
                '192.168.32.5',
                ['10.8.0.2', '127.0.0.1', '169.254.10.20', '240.0.0.1',
                 '255.255.255.255', '192.168.32.5', '10.8.0.2'],
            ),
            ['192.168.32.5', '10.8.0.2'],
        )

    def test_public_base_url_uses_override_then_request_host_then_detected_ip(self):
        public_base_url = getattr(server, 'public_base_url', lambda *_: '')
        with patch.dict('server.os.environ', {'RECRUIT_PUBLIC_URL': ' https://recruit.example.com/ '}, clear=False):
            self.assertEqual(public_base_url('localhost:8116', 8116), 'https://recruit.example.com')
        with patch.dict('server.os.environ', {}, clear=True), patch('server.local_ipv4_addresses', return_value=['192.168.50.8']):
            self.assertEqual(public_base_url('localhost:8116', 8116), 'http://192.168.50.8:8116')
            self.assertEqual(public_base_url('[::1]:8116', 8116), 'http://192.168.50.8:8116')
            self.assertEqual(public_base_url('10.20.30.40:8116', 8116), 'http://10.20.30.40:8116')


class ArchiveNumberTests(unittest.TestCase):
    def test_recruitment_type_date_and_daily_sequence_form_archive_number(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                with server.db() as conn:
                    identifiers = []
                    for index, recruitment_type in enumerate(('社会招聘', '社会招聘', '校园招聘')):
                        values = server.validate('resume_documents', {'name':f'编号测试{index}', 'recruitment_type':recruitment_type}, conn)
                        identifiers.append(server.insert(conn, 'resume_documents', values))
                    conn.execute("UPDATE resume_documents SET created_at='2026-09-14T12:00:00',archive_no='',source_id='' WHERE id IN (?,?,?)", identifiers)
                    conn.execute('DELETE FROM archive_numbers')
                    server.synchronize_archives(conn)
                    numbers = [conn.execute('SELECT archive_no FROM resume_documents WHERE id=?', (identifier,)).fetchone()[0] for identifier in identifiers]
                self.assertEqual(numbers, ['0120260914001', '0120260914002', '0220260914001'])
            finally:
                server.DATA = original

    def test_old_archive_numbers_are_rebuilt_once_and_source_id_follows(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                with server.db() as conn:
                    values = server.validate('resume_documents', {'name':'历史编号', 'recruitment_type':'社会招聘'}, conn)
                    identifier = server.insert(conn, 'resume_documents', values)
                    conn.execute("UPDATE resume_documents SET created_at='2026-09-14T08:30:00',archive_no='20260914083000',source_id='20260914083000' WHERE id=?", (identifier,))
                    conn.execute("DELETE FROM system_settings WHERE key='archive_number_format'")
                server.initialize()
                with server.db() as conn:
                    row = conn.execute('SELECT archive_no,source_id FROM resume_documents WHERE id=?', (identifier,)).fetchone()
                    first = (row['archive_no'], row['source_id'])
                server.initialize()
                with server.db() as conn:
                    row = conn.execute('SELECT archive_no,source_id FROM resume_documents WHERE id=?', (identifier,)).fetchone()
                    second = (row['archive_no'], row['source_id'])
                self.assertEqual(first, ('0120260914001', '0120260914001'))
                self.assertEqual(second, first)
            finally:
                server.DATA = original


class PoliticalStatusTests(unittest.TestCase):
    def test_short_names_are_normalized_for_all_profile_records(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                payloads = {
                    'candidates': {
                        'name': '人才甲', 'school_name': '测试大学', 'education': '本科',
                        'major': '工程管理', 'phone': '13900000001', 'political_status': '党员',
                    },
                    'applications': {
                        'name': '人才乙', 'school_name': '测试大学',
                        'status': '草稿', 'political_status': '团员',
                    },
                    'interviews': {
                        'name': '人才丙', 'school_name': '测试大学',
                        'status': '草稿', 'political_status': '预备党员',
                    },
                }
                expected = {
                    'candidates': '中共党员',
                    'applications': '共青团员',
                    'interviews': '中共预备党员',
                }
                with server.db() as conn:
                    for entity, payload in payloads.items():
                        self.assertEqual(
                            server.validate(entity, payload, conn)['political_status'],
                            expected[entity],
                        )
            finally:
                server.DATA = original

    def test_existing_short_names_are_migrated_without_deleting_records(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                with server.db() as conn:
                    for entity, value in (
                        ('candidates', '党员'),
                        ('applications', '团员'),
                        ('interviews', '预备党员'),
                    ):
                        now = '2026-09-14T12:00:00'
                        conn.execute(
                            f'INSERT INTO {entity}(political_status,created_at,updated_at) VALUES(?,?,?)',
                            (value, now, now),
                        )
                server.initialize()
                with server.db() as conn:
                    values = {
                        entity: conn.execute(
                            f'SELECT political_status FROM {entity} ORDER BY id DESC LIMIT 1'
                        ).fetchone()['political_status']
                        for entity in ('candidates', 'applications', 'interviews')
                    }
                self.assertEqual(values, {
                    'candidates': '中共党员',
                    'applications': '共青团员',
                    'interviews': '中共预备党员',
                })
            finally:
                server.DATA = original


class CandidateCampusDateMigrationTests(unittest.TestCase):
    def test_social_recruitment_clears_parent_dates_but_keeps_education_dates(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                now = '2026-09-14T12:00:00'
                with server.db() as conn:
                    candidate_id = conn.execute(
                        '''INSERT INTO candidates(recruitment_type,graduation,created_at,updated_at)
                           VALUES('社会招聘','2024-07',?,?)''',
                        (now, now),
                    ).lastrowid
                    conn.execute(
                        '''INSERT INTO candidate_educations(
                           candidate_id,position,education,school_name,major,enrollment,graduation
                           ) VALUES(?,1,'本科','历史大学','工程管理','2020-09','2024-07')''',
                        (candidate_id,),
                    )
                server.initialize()
                with server.db() as conn:
                    parent = conn.execute(
                        'SELECT graduation FROM candidates WHERE id=?', (candidate_id,)
                    ).fetchone()['graduation']
                    child = conn.execute(
                        'SELECT graduation FROM candidate_educations WHERE candidate_id=?',
                        (candidate_id,),
                    ).fetchone()['graduation']
                self.assertEqual(parent, '')
                self.assertEqual(child, '2024-07')
            finally:
                server.DATA = original


class RecruitmentPositionTests(unittest.TestCase):
    def test_free_text_positions_normalize_and_other_requires_detail(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                with server.db() as conn:
                    pipe_result = server.validate('candidates', {
                        'name': '岗位测试', 'school_name': '测试大学', 'education': '本科',
                        'major': '工程', 'phone': '13900000009', 'position': '管道工程师',
                    }, conn)
                    self.assertEqual(pipe_result.get('position'), '管道工程师')
                    self.assertEqual(pipe_result.get('position_detail'), '')
                    equipment_result = server.validate('candidates', {
                        'name': '岗位测试', 'school_name': '测试大学', 'education': '本科',
                        'major': '工程', 'phone': '13900000009', 'position': '设备工程师',
                    }, conn)
                    self.assertEqual(equipment_result.get('position'), '设备工程师')
                    self.assertEqual(equipment_result.get('position_detail'), '')
                    result = server.validate('candidates', {
                        'name': '岗位测试', 'school_name': '测试大学', 'education': '本科',
                        'major': '工程', 'phone': '13900000009', 'position': '焊接工程师',
                    }, conn)
                    self.assertEqual(result.get('position'), '其它')
                    self.assertEqual(result.get('position_detail'), '焊接工程师')
                    with self.assertRaisesRegex(ValueError, '其它岗位名称'):
                        server.validate('candidates', {
                            'name': '岗位测试', 'school_name': '测试大学', 'education': '本科',
                            'major': '工程', 'phone': '13900000009', 'position': '其它',
                        }, conn)
            finally:
                server.DATA = original

    def test_existing_free_text_positions_are_migrated_without_data_loss(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                now = '2026-09-14T12:00:00'
                with server.db() as conn:
                    for entity in ('resume_documents', 'candidates', 'applications', 'interviews', 'employees'):
                        conn.execute(
                            f'INSERT INTO {entity}(position,created_at,updated_at) VALUES(?,?,?)',
                            ('焊接工程师', now, now),
                        )
                server.initialize()
                with server.db() as conn:
                    for entity in ('resume_documents', 'candidates', 'applications', 'interviews', 'employees'):
                        self.assertIn(
                            'position_detail',
                            {column['name'] for column in conn.execute(f'PRAGMA table_info({entity})')},
                        )
                    for entity in ('resume_documents', 'candidates', 'applications', 'interviews', 'employees'):
                        with self.subTest(entity=entity):
                            row = conn.execute(
                                f'SELECT position,position_detail FROM {entity} ORDER BY id DESC LIMIT 1'
                            ).fetchone()
                            self.assertEqual(dict(row), {
                                'position': '其它', 'position_detail': '焊接工程师',
                            })
            finally:
                server.DATA = original

    def test_new_standard_positions_are_recovered_from_legacy_other_detail(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                now = '2026-09-14T12:00:00'
                with server.db() as conn:
                    for entity in ('resume_documents', 'candidates', 'applications', 'interviews', 'employees'):
                        for detail in ('管道工程师', '设备工程师'):
                            conn.execute(
                                f'INSERT INTO {entity}(position,position_detail,created_at,updated_at) VALUES(?,?,?,?)',
                                ('其它', detail, now, now),
                            )
                server.initialize()
                with server.db() as conn:
                    for entity in ('resume_documents', 'candidates', 'applications', 'interviews', 'employees'):
                        rows = conn.execute(
                            f'SELECT position,position_detail FROM {entity} ORDER BY id'
                        ).fetchall()
                        self.assertEqual([dict(row) for row in rows], [
                            {'position': '管道工程师', 'position_detail': ''},
                            {'position': '设备工程师', 'position_detail': ''},
                        ])
            finally:
                server.DATA = original


class RecruitmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.original_data = server.DATA
        server.DATA = Path(cls.temp.name)
        server.initialize()
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.http.server_port)
        cls.client = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        cls.public = build_opener()
        cls.password = (server.DATA / 'initial-password.txt').read_text()
        status, _ = cls.call('login', {'username': 'admin', 'password': cls.password})
        assert status == 200

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        server.DATA = cls.original_data
        cls.temp.cleanup()

    @classmethod
    def call(cls, path, data=None, method=None, public=False, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        request = Request(cls.url + '/api/' + path, data=json.dumps(data).encode() if data is not None else None, method=method, headers=headers)
        try:
            response = (cls.public if public else cls.client).open(request)
        except HTTPError as error:
            response = error
        content = response.read()
        raw = content if response.headers.get_content_type() == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' else content.decode('utf-8-sig')
        status = response.status
        is_json = response.headers.get_content_type() == 'application/json'
        response.close()
        return status, json.loads(raw) if is_json else raw

    def test_public_qr_forms_include_other_position_detail(self):
        for path in ('public/schema', 'public/employee-schema', 'public/resume-schema'):
            with self.subTest(path=path):
                status, result = self.call(path, public=True)
                self.assertEqual(status, 200)
                self.assertIn('position_detail', {field['key'] for field in result['fields']})

    def test_01_private_routes_and_static(self):
        self.assertEqual(self.call('candidates', public=True)[0], 401)
        self.assertEqual(self.call('stats', public=True)[0], 401)
        self.assertEqual(self.call('candidates/export', public=True)[0], 401)
        self.assertEqual(self.call('schema')[0], 200)
        for route in ['/', '/apply', '/app.js', '/style.css', '/corporate-theme.css']:
            with self.public.open(self.url + route) as response:
                self.assertEqual(response.status, 200)
        with self.assertRaises(HTTPError) as batch_error:
            self.public.open(self.url + '/resume-batch')
        self.assertEqual(batch_error.exception.code, 404)
        batch_error.exception.close()
        with self.public.open(self.url + '/') as response:
            homepage = response.read().decode('utf-8-sig')
        self.assertLess(homepage.index('href="/candidate.css"'), homepage.index('href="/corporate-theme.css"'))
        try:
            self.public.open(self.url + '/data/initial-password.txt')
            self.fail('Private file must not be served')
        except HTTPError as error:
            self.assertEqual(error.code, 404)
            error.close()

    def test_02_public_application_transaction_and_duplicate(self):
        payload = {'name': '测试学生', 'phone': '13800138000', 'school_name': '测试大学', 'major': '土木工程', 'education': '本科', 'position': '施工管理', 'status': '已入职', 'notes': '不应保存'}
        self.call('candidates',dict(payload,status='待筛选',notes=''))
        code, record = self.call('public/apply', payload, public=True)
        self.assertEqual(code, 201)
        self.__class__.candidate_id = record['candidate_id']
        rows = self.call('candidates')[1]
        self.assertEqual(rows[0]['status'], '待筛选')
        self.assertEqual(rows[0]['notes'], '')
        applications = self.call('applications')[1]
        self.assertEqual(applications[0]['candidate_id'], record['candidate_id'])
        self.__class__.application_id = applications[0]['id']
        self.assertEqual(self.call('public/apply', payload, public=True)[0], 200)
        self.assertEqual(len(self.call('applications')[1]), 1)
        self.assertEqual(self.call('candidates/delete-preview', {'ids':[record['candidate_id']]})[0], 200)

    def test_03_six_modules_update_search_and_export(self):
        school = {'name': '测试大学', 'province': '江苏', 'cooperation': '已合作'}
        code, result = self.call('schools', school)
        self.assertEqual(code, 201)
        school['name'] = '更新大学'
        self.assertEqual(self.call('schools/' + str(result['id']), school, 'PUT')[0], 200)
        self.assertEqual(self.call('schools?q=nonexistent')[1], [])
        self.assertEqual(self.call('schools')[1][0]['name'], '更新大学')
        candidate = self.candidate_id
        interview = {'candidate_id': candidate, 'name':'测试学生', 'school_name':'测试大学', 'date': '2026-09-07', 'interviewer': '测试面试官', 'score': '88', 'status': '已生效'}
        self.assertEqual(self.call('interviews', interview)[0], 201)
        self.assertEqual(self.call('interviews')[1][0]['candidate_id_label'], '测试学生')
        employee = {'name':'测试学生', 'candidate_id': candidate, 'employee_no': 'TEST-001', 'department': '工程部', 'position': '工程师', 'start_date': '2026-09-08', 'status': '待报到'}
        self.assertEqual(self.call('employees', employee)[0], 201)
        self.assertEqual(self.call('employees', employee)[0], 409)
        question = {'title': '=1+1', 'category': '岗位职责', 'question': '=1+1', 'status': '待答复'}
        self.assertEqual(self.call('questions', question)[0], 201)
        export = self.call('questions/export')[1]
        self.assertIn("'=1+1", export)
        self.assertIn('通用回答话术', export)
        counts = self.call('stats')[1]['counts']
        self.assertTrue(all(counts[key] >= 1 for key in server.SCHEMAS if key != 'resume_documents'))
        self.assertEqual(self.call('schools/' + str(result['id']), method='DELETE')[0], 200)
        self.assertEqual(self.call('schools/' + str(result['id']), method='DELETE')[0], 404)

    def test_04_validation_and_origin(self):
        self.assertEqual(self.call('schools', {'name': '无省市'})[0], 400)
        self.assertEqual(self.call('interviews', {'candidate_id': 99999, 'date': '2026-01-01', 'interviewer': 'A', 'status': '已生效'})[0], 400)
        self.assertEqual(self.call('schools', {'name': 'A', 'province': 'B'}, origin='http://evil.example')[0], 403)
        self.assertEqual(self.call('candidates', {'name': 'A', 'phone': 'bad'})[0], 400)
        self.assertEqual(self.call('interviews', {'candidate_id': self.candidate_id, 'date': '2026-02-30', 'interviewer': 'A', 'status': '已生效'})[0], 400)
        self.assertEqual(self.call('interviews', {'candidate_id': self.candidate_id, 'date': '2026-02-28', 'interviewer': 'A', 'status': '已生效', 'score': '101'})[0], 400)
        self.assertEqual(self.call('interviews', {'candidate_id': self.candidate_id, 'date': '2026-02-28', 'interviewer': 'A', 'status': '已生效', 'score': 'NaN'})[0], 400)

    def test_05_persistence_and_password(self):
        server.initialize()
        self.assertEqual(len(self.call('candidates')[1]), 1)
        self.assertEqual(self.call('password', {'old_password': 'wrong', 'password': 'a-new-password'})[0], 400)
        self.assertEqual(self.call('password', {'old_password': self.password, 'password': 'a-new-password'})[0], 200)
        self.assertEqual(self.call('candidates')[0], 401)
        self.assertEqual(self.call('login', {'username': 'admin', 'password': 'a-new-password'})[0], 200)
        self.assertFalse((server.DATA / 'initial-password.txt').exists())

    def test_04b_school_fields(self):
        school = {'name': '完整字段大学', 'region': '华中', 'business_leader': '测试领导', 'province': '湖北省', 'city': '武汉市', 'level': '本科', 'ownership': '公办', 'is_985': '否', 'is_211': '是', 'is_double_first': '是', 'employment_account': 'school-account', 'employment_password': ' secret-value ', 'employment_url': 'https://example.edu.cn/jobs', 'ranking': '250', 'province_city': '伪造地址'}
        status, created = self.call('schools', school)
        self.assertEqual(status, 201)
        row = self.call('schools')[1][0]
        self.assertEqual(row['province_city'], '湖北省 武汉市')
        for key in school:
            if key != 'province_city':
                self.assertEqual(row[key], school[key])
        self.assertEqual(self.call('schools?q=secret-value')[1], [])
        exported = self.call('schools/export')[1]
        self.assertNotIn('secret-value', exported)
        self.assertNotIn('就业网密码', exported)
        self.assertIn('业务开发领导', exported)
        school.update(city='宜昌市', ranking='1001')
        self.assertEqual(self.call('schools/' + str(created['id']), school, 'PUT')[0], 200)
        self.assertEqual(self.call('schools')[1][0]['province_city'], '湖北省 宜昌市')
        for key, value in [('region', '华东北'), ('level', '硕士'), ('ownership', '其他'), ('is_985', '不确定'), ('ranking', '0'), ('ranking', '2.5'), ('employment_url', 'javascript:alert(1)')]:
            with self.subTest(key=key, value=value):
                self.assertEqual(self.call('schools', dict(school, **{key: value}))[0], 400)

    def test_04c_province_city_options_and_validation(self):
        status, locations = self.call('locations')
        self.assertEqual(status, 200)
        self.assertEqual(len(locations), 34)
        self.assertEqual(locations['北京市'], ['北京市'])
        self.assertIn('南京市', locations['江苏省'])
        self.assertIn('仙桃市', locations['湖北省'])
        self.assertIn('石河子市', locations['新疆维吾尔自治区'])
        self.assertIn('台北市', locations['台湾省'])
        school = {'name': '省市联动测试', 'province': '江苏', 'city': '南京市'}
        status, result = self.call('schools', school)
        self.assertEqual(status, 201)
        row = next(row for row in self.call('schools')[1] if row['id'] == result['id'])
        self.assertEqual(row['province'], '江苏省')
        self.assertEqual(row['province_city'], '江苏省 南京市')
        self.assertEqual(self.call('schools', dict(school, province='湖北省'))[0], 400)
        self.assertEqual(self.call('schools', dict(school, province='无效省份'))[0], 400)
        self.assertEqual(self.call('schools', dict(school, province='北京市', city='北京市'))[0], 201)
        self.assertEqual(self.call('schools/' + str(result['id']), dict(school, province='湖北省', city=''), 'PUT')[0], 200)
        row = next(row for row in self.call('schools')[1] if row['id'] == result['id'])
        self.assertEqual(row['province_city'], '湖北省')


class SchoolMigrationTests(unittest.TestCase):
    def test_candidate_experience_storage_is_unified(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                with server.db() as conn:
                    conn.execute('CREATE TABLE candidate_internship_experiences(id INTEGER PRIMARY KEY)')
                server.initialize()
                with server.db() as conn:
                    tables={row['name'] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    self.assertIn('candidate_work_experiences',tables)
                    self.assertIn('candidate_project_experiences',tables)
                    self.assertNotIn('candidate_internship_experiences',tables)
            finally:
                server.DATA = original

    def test_education_time_migration_moves_parent_dates_to_highest_history(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                with server.db() as conn:
                    application_columns={row['name'] for row in conn.execute('PRAGMA table_info(applications)')}
                    if 'enrollment' not in application_columns:
                        conn.execute("ALTER TABLE applications ADD COLUMN enrollment TEXT NOT NULL DEFAULT ''")
                    if 'graduation' not in application_columns:
                        conn.execute("ALTER TABLE applications ADD COLUMN graduation TEXT NOT NULL DEFAULT ''")
                    application_id=conn.execute(
                        "INSERT INTO applications(name,education,school_name,major,enrollment,graduation,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                        ('历史时间','硕士','历史大学','工程','2022-09','2025-06','2025-01-01','2025-01-01'),
                    ).lastrowid
                    conn.execute(
                        "INSERT INTO application_educations(application_id,position,education,school_name,major) VALUES(?,?,?,?,?)",
                        (application_id,1,'硕士','历史大学','工程'),
                    )
                    candidate_id=conn.execute(
                        "INSERT INTO candidates(name,education,school_name,major,graduation,recruitment_type,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                        ('历史人才','本科','历史本科','土木','2024-06','校园招聘','2025-01-01','2025-01-01'),
                    ).lastrowid
                    conn.execute(
                        "INSERT INTO candidate_educations(candidate_id,position,education,school_name,major) VALUES(?,?,?,?,?)",
                        (candidate_id,1,'本科','历史本科','土木'),
                    )
                    date_only_application_id=conn.execute(
                        "INSERT INTO applications(name,enrollment,graduation,created_at,updated_at) VALUES(?,?,?,?,?)",
                        ('仅有时间的历史登记','2020-09','2024-06','2025-01-01','2025-01-01'),
                    ).lastrowid
                    interview_columns={row['name'] for row in conn.execute('PRAGMA table_info(interviews)')}
                    if 'graduation' not in interview_columns:
                        conn.execute("ALTER TABLE interviews ADD COLUMN graduation TEXT NOT NULL DEFAULT ''")
                    date_only_interview_id=conn.execute(
                        "INSERT INTO interviews(name,graduation,created_at,updated_at) VALUES(?,?,?,?)",
                        ('仅有时间的历史面试','2023-06','2025-01-01','2025-01-01'),
                    ).lastrowid
                server.initialize()
                with server.db() as conn:
                    child_columns={row['name'] for row in conn.execute('PRAGMA table_info(application_educations)')}
                    self.assertIn('enrollment',child_columns)
                    self.assertIn('graduation',child_columns)
                    application=dict(conn.execute('SELECT enrollment,graduation FROM applications WHERE id=?',(application_id,)).fetchone())
                    self.assertEqual(application,{'enrollment':'','graduation':''})
                    history=dict(conn.execute('SELECT enrollment,graduation FROM application_educations WHERE application_id=?',(application_id,)).fetchone())
                    self.assertEqual(history,{'enrollment':'2022-09','graduation':'2025-06'})
                    candidate=dict(conn.execute('SELECT graduation FROM candidates WHERE id=?',(candidate_id,)).fetchone())
                    self.assertEqual(candidate['graduation'],'2024-06')
                    candidate_history=dict(conn.execute('SELECT enrollment,graduation FROM candidate_educations WHERE candidate_id=?',(candidate_id,)).fetchone())
                    self.assertEqual(candidate_history,{'enrollment':'','graduation':'2024-06'})
                    date_only_application=dict(conn.execute('SELECT education,school_name,major,enrollment,graduation FROM application_educations WHERE application_id=?',(date_only_application_id,)).fetchone())
                    self.assertEqual(date_only_application,{'education':'','school_name':'','major':'','enrollment':'2020-09','graduation':'2024-06'})
                    date_only_interview=dict(conn.execute('SELECT education,school_name,major,enrollment,graduation FROM interview_educations WHERE interview_id=?',(date_only_interview_id,)).fetchone())
                    self.assertEqual(date_only_interview,{'education':'','school_name':'','major':'','enrollment':'','graduation':'2023-06'})
            finally:
                server.DATA = original

    def test_interview_migration_retains_original_records(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                with server.db() as conn:
                    candidate = server.insert(conn, 'candidates', server.validate('candidates', {'name':'旧面试人','phone':'13000130000','school_name':'旧学校','major':'工程','education':'本科'}, conn))
                    conn.execute('DROP TABLE interviews')
                    conn.execute('CREATE TABLE interviews(id INTEGER PRIMARY KEY,candidate_id INTEGER,date TEXT,round TEXT,interviewer TEXT,position TEXT,location TEXT,score TEXT,status TEXT,evaluation TEXT,notes TEXT,created_at TEXT,updated_at TEXT)')
                    conn.execute("INSERT INTO interviews VALUES(5,?,'2026-01-01','初试','老师','工程师','南京','80','通过','评价','记录','2026-01-01T12:30:00','2026-01-01T12:30:00')",(candidate,))
                server.initialize()
                server.initialize()
                with server.db() as conn:
                    row = dict(conn.execute('SELECT * FROM interviews WHERE id=5').fetchone())
                    self.assertEqual(row['name'],'旧面试人')
                    self.assertEqual(row['status'],'已生效')
                    self.assertEqual(row['legacy_status'],'通过')
                    self.assertEqual(row['created_at'],'2026-01-01T12:30:00')
                    self.assertEqual(row['date'],'2026-01-01')
                    self.assertIsNone(row['interview_at'])
                    self.assertEqual(row['basic_situation'],'评价\n记录')
                self.assertEqual(len(list(Path(folder).glob('before-interview-update-*.db'))),1)
            finally:
                server.DATA = original

    def test_application_migration_copies_profile_and_retains_ids(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                with server.db() as conn:
                    person = server.insert(conn, 'candidates', server.validate('candidates', {'name':'历史应聘人','school_name':'旧大学','phone':'13000130000','major':'工程','education':'本科','graduation':'2026-07'}, conn))
                    conn.execute('DROP TABLE applications')
                    conn.execute('CREATE TABLE applications(id INTEGER PRIMARY KEY, candidate_id INTEGER REFERENCES candidates(id), date TEXT, position TEXT, batch TEXT, channel TEXT, status TEXT, notes TEXT, created_at TEXT, updated_at TEXT)')
                    conn.execute("INSERT INTO applications VALUES(8,?,'2026-01-01','岗位','旧批次','校园宣讲会','待处理','备注','2026-01-01T01:02:03','2026-01-01T01:02:03')", (person,))
                server.initialize()
                server.initialize()
                with server.db() as conn:
                    row = server.candidate_display(conn.execute('SELECT * FROM applications WHERE id=8').fetchone(), conn, 'applications')
                    self.assertEqual(row['name'], '历史应聘人')
                    self.assertEqual(row['candidate_id'], person)
                    self.assertEqual(row['cohort'], '2026届')
                    self.assertEqual(row['channel'], '校园线下')
                    self.assertEqual(row['legacy_channel'], '校园宣讲会')
                    self.assertEqual(row['status'], '草稿')
                    self.assertEqual(row['legacy_data_status'], '待处理')
                    self.assertEqual(row['created_date'], '2026-01-01 01:02:03')
                self.assertEqual(len(list(Path(folder).glob('before-application-update-*.db'))), 1)
            finally:
                server.DATA = original

    def test_candidate_migration_preserves_timestamp(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                with server.db() as conn:
                    conn.execute('CREATE TABLE candidates(id INTEGER PRIMARY KEY, name TEXT, phone TEXT, education TEXT, graduation TEXT, status TEXT, created_at TEXT, updated_at TEXT)')
                    conn.execute("INSERT INTO candidates VALUES(9,'旧人才','13800138000','大专','2026-07-10','待筛选','2026-01-02T03:04:05','2026-01-02T03:04:05')")
                server.initialize()
                server.initialize()
                with server.db() as conn:
                    row = server.candidate_display(conn.execute('SELECT * FROM candidates WHERE id=9').fetchone(), conn)
                    self.assertEqual(row['created_date'], '2026-01-02 03:04:05')
                    self.assertEqual(row['education'], '专科')
                    self.assertEqual(row['graduation'], '')
                    self.assertEqual(row['cohort'], '')
                    history = conn.execute(
                        'SELECT graduation FROM candidate_educations WHERE candidate_id=9'
                    ).fetchone()
                    self.assertEqual(history['graduation'], '2026-07')
                self.assertEqual(len(list(Path(folder).glob('before-candidate-update-*.db'))), 1)
            finally:
                server.DATA = original

    def test_candidate_age_is_stored_and_not_recalculated_for_display(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                with server.db() as conn:
                    values = server.validate('candidates', {
                        'name': '手工年龄人才',
                        'school_name': '测试大学',
                        'phone': '13800139999',
                        'major': '工程',
                        'education': '本科',
                        'birthdate': '2000-01-01',
                        'age': '42',
                    }, conn)
                    identifier = server.insert(conn, 'candidates', values)
                    row = server.candidate_display(
                        conn.execute('SELECT * FROM candidates WHERE id=?', (identifier,)).fetchone(),
                        conn,
                    )
                    self.assertEqual(row['age'], '42')
                    with self.assertRaisesRegex(ValueError, '年龄'):
                        server.validate('candidates', {**values, 'age': '42.5'}, conn)
                    with self.assertRaisesRegex(ValueError, '年龄'):
                        server.validate('candidates', {**values, 'age': '101'}, conn)
            finally:
                server.DATA = original

    def test_existing_candidates_receive_one_saved_age_during_upgrade(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                today = server.datetime.now().date()
                birthday = today.replace(year=today.year - 20).isoformat()
                with server.db() as conn:
                    conn.execute(
                        'CREATE TABLE candidates('
                        'id INTEGER PRIMARY KEY, name TEXT, phone TEXT, birthdate TEXT, '
                        'created_at TEXT, updated_at TEXT)'
                    )
                    conn.execute(
                        "INSERT INTO candidates VALUES(1,'历史人才','13800138888',?,'2026-01-01','2026-01-01')",
                        (birthday,),
                    )
                server.initialize()
                server.initialize()
                with server.db() as conn:
                    columns = {row['name'] for row in conn.execute('PRAGMA table_info(candidates)')}
                    self.assertIn('age', columns)
                    saved_age = conn.execute('SELECT age FROM candidates WHERE id=1').fetchone()['age']
                    self.assertEqual(saved_age, '20')
            finally:
                server.DATA = original

    def test_age_from_birthdate_uses_year_and_month_only(self):
        today = server.datetime.now().date()
        this_month_twenty_years_ago = f'{today.year - 20:04d}-{today.month:02d}'
        self.assertEqual(server.age_from_birthdate(this_month_twenty_years_ago), 20)
        self.assertEqual(server.age_from_birthdate(this_month_twenty_years_ago + '-28'), 20)

    def test_existing_profile_birthdates_are_truncated_to_year_month(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                server.initialize()
                with server.db() as conn:
                    for entity in ('candidates', 'applications', 'interviews', 'employees'):
                        conn.execute(
                            f"INSERT INTO {entity}(birthdate,created_at,updated_at) VALUES(?,?,?)",
                            ('2000-06-15', '2026-01-01', '2026-01-01'),
                        )
                server.initialize()
                with server.db() as conn:
                    for entity in ('candidates', 'applications', 'interviews', 'employees'):
                        with self.subTest(entity=entity):
                            value = conn.execute(f'SELECT birthdate FROM {entity}').fetchone()['birthdate']
                            self.assertEqual(value, '2000-06')
            finally:
                server.DATA = original

    def test_old_database_migrates_once_without_losing_links(self):
        original = server.DATA
        with tempfile.TemporaryDirectory() as folder:
            try:
                server.DATA = Path(folder)
                with server.db() as conn:
                    conn.execute('CREATE TABLE schools (id INTEGER PRIMARY KEY, name TEXT, province TEXT, level TEXT, contact TEXT, created_at TEXT, updated_at TEXT)')
                    conn.execute("INSERT INTO schools VALUES (7,'原有院校','江苏南京','高职专科','原联系人','2026-01-01','2026-01-01')")
                server.initialize()
                with server.db() as conn:
                    row = dict(conn.execute('SELECT * FROM schools WHERE id=7').fetchone())
                    self.assertEqual(row['name'], '原有院校')
                    self.assertEqual(row['province_city'], '江苏南京')
                    self.assertEqual(row['level'], '专科')
                    self.assertEqual(row['legacy_level'], '高职专科')
                    self.assertEqual(row['contact'], '原联系人')
                    server.insert(conn, 'candidates', server.validate('candidates', {'name':'关联人才','phone':'13900139000','school_id':7,'school_name':'原有院校','major':'工程','education':'大专','position':'技术','status':'待筛选'}, conn))
                server.initialize()
                with server.db() as conn:
                    self.assertEqual(conn.execute('SELECT school_id FROM candidates').fetchone()[0], 7)
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM schools').fetchone()[0], 1)
                backups = list(Path(folder).glob('before-school-update-*.db'))
                self.assertEqual(len(backups), 1)
                backup = sqlite3.connect(backups[0])
                try:
                    self.assertEqual(backup.execute('SELECT level FROM schools WHERE id=7').fetchone()[0], '高职专科')
                finally:
                    backup.close()
            finally:
                server.DATA = original


if __name__ == '__main__':
    unittest.main()
