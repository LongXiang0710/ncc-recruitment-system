import json
import shutil
import tempfile
import unittest
from pathlib import Path

from features import load_features


ROOT = Path(__file__).resolve().parents[1]


class FeatureRegistryTests(unittest.TestCase):
    def test_all_feature_folders_are_discovered(self):
        features = load_features(ROOT / 'features')
        self.assertEqual(
            list(features),
            ['schools', 'candidates', 'applications', 'interviews', 'employees', 'questions', 'resume_documents'],
        )
        self.assertTrue(all(feature.enabled for feature in features.values()))

    def test_disabling_feature_preserves_definition_for_internal_data(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'features'
            shutil.copytree(ROOT / 'features', target, ignore=shutil.ignore_patterns('__pycache__'))
            (target / 'config.json').write_text(json.dumps({'disabled': ['questions']}), encoding='utf-8')
            features = load_features(target)
            self.assertIn('questions', features)
            self.assertFalse(features['questions'].enabled)
            self.assertTrue(features['candidates'].enabled)

    def test_resume_collection_hides_other_channel_detail_and_removes_notes(self):
        fields = {
            field['key']: field
            for field in load_features(ROOT / 'features')['resume_documents'].schema['fields']
        }
        self.assertNotIn('notes', fields)
        self.assertTrue(fields['channel_detail'].get('listHidden'))

    def test_resume_collection_schema_accepts_requested_documents_and_images(self):
        fields = {
            field['key']: field
            for field in load_features(ROOT / 'features')['resume_documents'].schema['fields']
        }
        self.assertEqual(set(fields['resume']['accept'].split(',')), {
            '.txt', '.md', '.mdx', '.markdown', '.pdf', '.html', '.xlsx', '.xls',
            '.doc', '.docx', '.csv', '.eml', '.msg', '.pptx', '.ppt', '.xml', '.epub',
            '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg',
        })

    def test_resume_creator_is_readonly_and_precedes_upload_time(self):
        schema = load_features(ROOT / 'features')['resume_documents'].schema
        keys = [field['key'] for field in schema['fields']]
        creator = next(field for field in schema['fields'] if field['key'] == 'created_by')
        self.assertTrue(creator['readonly'])
        self.assertEqual(keys.index('created_by') + 1, keys.index('created_date'))

    def test_resume_source_id_is_internal_only(self):
        fields = {
            field['key']: field
            for field in load_features(ROOT / 'features')['resume_documents'].schema['fields']
        }
        self.assertTrue(fields['source_id'].get('hidden'))
        self.assertFalse(fields['source_id'].get('export', True))

    def test_political_status_is_same_optional_dropdown_in_profile_schemas(self):
        expected = ['群众', '共青团员', '中共预备党员', '中共党员']
        features = load_features(ROOT / 'features')
        for entity in ('candidates', 'applications', 'interviews'):
            with self.subTest(entity=entity):
                field = next(
                    field for field in features[entity].schema['fields']
                    if field['key'] == 'political_status'
                )
                self.assertEqual(field.get('options'), expected)
                self.assertFalse(field.get('required', False))

    def test_recruitment_positions_use_one_dropdown_and_hidden_detail_field(self):
        expected = [
            '机械工程师', '电气工程师', '材料工程师', '安全工程师', '土建工程师',
            '管道工程师', '设备工程师', '数据分析师', '软件工程师',
            '财务专员', '其它',
        ]
        features = load_features(ROOT / 'features')
        for entity in ('resume_documents', 'candidates', 'applications', 'interviews', 'employees'):
            with self.subTest(entity=entity):
                fields = {field['key']: field for field in features[entity].schema['fields']}
                self.assertEqual(fields['position'].get('options'), expected)
                self.assertTrue(fields['position_detail'].get('listHidden'))
                self.assertFalse(fields['position_detail'].get('hidden', False))

    def test_candidate_list_hides_graduation_but_keeps_cohort_visible(self):
        fields = {
            field['key']: field
            for field in load_features(ROOT / 'features')['candidates'].schema['fields']
        }
        self.assertTrue(fields['graduation'].get('listHidden'))
        self.assertFalse(fields['cohort'].get('listHidden', False))

    def test_candidate_age_is_an_optional_stored_integer_field(self):
        field = next(
            field for field in load_features(ROOT / 'features')['candidates'].schema['fields']
            if field['key'] == 'age'
        )
        self.assertFalse(field.get('readonly', False))
        self.assertFalse(field.get('virtual', False))
        self.assertEqual(field.get('type'), 'number')
        self.assertEqual((field.get('min'), field.get('max'), field.get('step')), (1, 100, 1))

    def test_candidate_screening_section_matches_requested_dialog_fields(self):
        schema = load_features(ROOT / 'features')['candidates'].schema
        fields = schema['fields']
        expected_keys = [
            'travel_acceptance', 'previous_company_type', 'salary_expectation_k',
            'contract_type', 'employment_status', 'availability_note',
            'expected_arrival_date', 'availability_period', 'screening_result',
            'follow_up_owner', 'screening_reason',
        ]
        self.assertEqual([field['key'] for field in fields[:11]], expected_keys)
        self.assertTrue({
            'corrected_position', 'certificate_status',
            'communication_started_at', 'communication_ended_at',
        }.isdisjoint(field['key'] for field in fields))
        configured = {field['key']: field for field in fields[:11]}
        self.assertEqual(configured['travel_acceptance']['options'], [
            '能接受长差', '不能接受长差', '定向', '能接受短差', '未接通-无法了解',
        ])
        self.assertEqual(configured['previous_company_type']['options'], [
            '业主单位', '管理公司', '监理公司', '化工厂/生产厂', '施工总承包', '分包队',
            '施工班组', '应届生', '无法界定', 'EPC', '未接通-无法了解',
        ])
        self.assertEqual(configured['contract_type']['options'], [
            '实习协议', '项目合同', '正式合同', '项目合同+正式合同',
        ])
        self.assertEqual(configured['employment_status']['options'], [
            '在职', '离职', '离职交接中', '应届生', '未接通-无法了解',
        ])
        self.assertEqual(configured['availability_period']['options'], [
            '1个月内', '1-3个月', '3-6个月', '6-9个月', '9-12个月',
        ])
        self.assertEqual(configured['screening_result']['options'], [
            '可跟进', '排除', '失效', '拒绝', '未接通', '已工作', '观望',
        ])
        self.assertNotIn('options', configured['follow_up_owner'])
        self.assertTrue(configured['follow_up_owner'].get('readonly'))
        self.assertEqual(
            {key for key, field in configured.items() if field.get('editorRequired')},
            {
                'travel_acceptance', 'previous_company_type', 'salary_expectation_k',
                'employment_status', 'screening_result', 'screening_reason', 'follow_up_owner',
            },
        )
        self.assertTrue(all(field.get('listHidden') for field in configured.values()))
        self.assertEqual(configured['travel_acceptance'].get('section'), '一筛情况')
        self.assertEqual(configured['salary_expectation_k'].get('type'), 'number')
        self.assertEqual(configured['expected_arrival_date'].get('type'), 'date')
        self.assertEqual(configured['screening_reason'].get('type'), 'textarea')
        self.assertTrue(configured['screening_reason'].get('fullWidth'))
        recruitment_type = next(field for field in fields if field['key'] == 'recruitment_type')
        self.assertEqual(recruitment_type.get('section'), '基础信息')

    def test_profile_birthdates_use_year_month_fields(self):
        features = load_features(ROOT / 'features')
        for entity in ('candidates', 'applications', 'interviews', 'employees'):
            with self.subTest(entity=entity):
                field = next(
                    field for field in features[entity].schema['fields']
                    if field['key'] == 'birthdate'
                )
                self.assertEqual(field.get('type'), 'month')


if __name__ == '__main__':
    unittest.main()
