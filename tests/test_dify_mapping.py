import unittest

from features.resume_documents import dify_mapping


class DifyMappingTests(unittest.TestCase):
    def test_nested_workflow_result_maps_to_candidate_and_child_tables(self):
        result = {
            'schema_version': '1.0',
            'recruitment_type': '社会招聘',
            'source_channel': '智联招聘',
            'position_name': '管道工程师',
            'candidate': {
                'basic': {
                    'name': '陈芝平', 'gender': '男', 'birth_date': '1991-04',
                    'age': '35岁',
                    'phone': '15559060893', 'email': '61614719@qq.com',
                    'political_status': '群众', 'hometown_raw': '福建泉州'
                },
                'education': [{
                    'school': '青岛科技大学', 'major': '机械设计制造及其自动化',
                    'degree': '本科', 'start_date': '2010-09', 'end_date': '2014-07'
                }],
                'work_experience': [{
                    'company': '中石化第五建设有限公司', 'position': '技术',
                    'start_date': '2019-01', 'end_date': '至今'
                }],
                'projects': [{
                    'project_name': '惠州一期项目', 'role': '专业负责人',
                    'start_date': '2022-07', 'end_date': '至今'
                }]
            }
        }
        source = {'recruitment_type': '社会招聘', 'channel': '其他', 'channel_detail': '行业推荐'}
        self.assertEqual(dify_mapping.to_candidate_payload(result, source), {
            'name': '陈芝平', 'gender': '男', 'birthdate': '1991-04', 'age': '35',
            'phone': '15559060893', 'email': '61614719@qq.com',
            'political_status': '群众', 'hometown': '福建泉州',
            'recruitment_type': '社会招聘', 'channel': '其他',
            'channel_detail': '行业推荐', 'position': '管道工程师',
            'education_experiences': [{
                'education': '本科', 'school_name': '青岛科技大学',
                'major': '机械设计制造及其自动化', 'enrollment': '2010-09',
                'graduation': '2014-07'
            }],
            'work_experiences': [{
                'organization': '中石化第五建设有限公司', 'position': '技术',
                'start_date': '2019-01', 'end_date': '', 'description': ''
            }],
            'project_experiences': [{
                'project_name': '惠州一期项目', 'role': '专业负责人',
                'start_date': '2022-07', 'end_date': '', 'description': ''
            }]
        })

    def test_campus_source_drops_projects_and_preserves_flat_results(self):
        nested = {'candidate': {'basic': {'name': '校园人才'}, 'projects': [{'project_name': '实训', 'role': '成员', 'start_date': '2025-01'}]}}
        source = {'recruitment_type': '校园招聘', 'channel': '校园平台', 'channel_detail': ''}
        mapped = dify_mapping.to_candidate_payload(nested, source)
        self.assertEqual(mapped['recruitment_type'], '校园招聘')
        self.assertNotIn('project_experiences', mapped)
        self.assertEqual(dify_mapping.to_candidate_payload({'name': '原格式', 'phone': '13900000000'}, source)['name'], '原格式')

    def test_empty_or_unknown_candidate_result_is_rejected(self):
        source = {'recruitment_type': '社会招聘', 'channel': '其他', 'channel_detail': '行业推荐'}
        for result in ({'candidate': {'basic': {}}}, {'candidate': {'unknown': 'value'}}, {'unknown': 'value'}):
            with self.subTest(result=result), self.assertRaisesRegex(ValueError, '可用的人才字段'):
                dify_mapping.to_candidate_payload(result, source)

    def test_known_enum_and_month_aliases_are_normalized_without_inventing_birth_day(self):
        result = {'candidate': {
            'basic': {'name': '别名测试', 'gender': '男性', 'birth_date': '1999-08'},
            'education': [{'school': '测试大学', 'major': '工程', 'degree': '学士', 'start_date': '2020/9', 'end_date': '2024年6月'}]
        }}
        mapped = dify_mapping.to_candidate_payload(result, {'recruitment_type': '校园招聘', 'channel': '校园平台'})
        self.assertEqual(mapped['gender'], '男')
        self.assertEqual(mapped['birthdate'], '1999-08')
        self.assertEqual(mapped['education_experiences'][0]['education'], '本科')
        self.assertEqual(mapped['education_experiences'][0]['enrollment'], '2020-09')
        self.assertEqual(mapped['education_experiences'][0]['graduation'], '2024-06')

    def test_year_only_education_dates_use_school_year_default_months(self):
        result = {'candidate': {
            'basic': {'name': '年份补全测试'},
            'education': [
                {'school': '较早学校', 'start_date': '2016年', 'end_date': '2020年'},
                {'school': '无效时间学校', 'start_date': '不详', 'end_date': ''},
                {'school': '最新学校', 'start_date': '2020', 'end_date': '2024'},
            ],
            'work_experience': [
                {'company': '年份工作单位', 'start_date': '2020', 'end_date': '2024年'},
            ],
            'projects': [
                {'project_name': '年份项目', 'start_date': '2021年', 'end_date': '2023'},
            ],
        }}

        mapped = dify_mapping.to_candidate_payload(
            result,
            {'recruitment_type': '社会招聘', 'channel': '其他'},
        )

        self.assertEqual(
            [(row['school_name'], row['enrollment'], row['graduation'])
             for row in mapped['education_experiences']],
            [('最新学校', '2020-09', '2024-07'), ('较早学校', '2016-09', '2020-07'),
             ('无效时间学校', '', '')],
        )
        self.assertEqual(mapped['work_experiences'][0]['start_date'], '')
        self.assertEqual(mapped['work_experiences'][0]['end_date'], '')
        self.assertEqual(mapped['project_experiences'][0]['start_date'], '')
        self.assertEqual(mapped['project_experiences'][0]['end_date'], '')

    def test_flat_aliases_are_normalized_and_empty_rows_do_not_count(self):
        source = {'recruitment_type': '校园招聘', 'channel': '校园平台'}
        mapped = dify_mapping.to_candidate_payload({'name': '平面人才', 'gender': '男性', 'birthdate': '1999-08-27', 'age': '26岁', 'education': '学士', 'phone': '13900000001'}, source)
        self.assertEqual(mapped['gender'], '男')
        self.assertEqual(mapped['education'], '本科')
        self.assertEqual(mapped['birthdate'], '1999-08')
        self.assertEqual(mapped['age'], '26')
        for result in ({'candidate': {'education': [{}]}}, {'candidate': {'basic': {'gender': '未知'}}}):
            with self.subTest(result=result), self.assertRaisesRegex(ValueError, '可用的人才字段'):
                dify_mapping.to_candidate_payload(result, source)

    def test_chinese_flat_labels_use_the_same_normalization(self):
        source = {'recruitment_type': '校园招聘', 'channel': '校园平台'}
        mapped = dify_mapping.to_candidate_payload({'姓名': '中文人才', '联系方式': '13900000002', '性别': '男性', '学历': '学士', '出生日期': '1999-08', '年龄': '27岁'}, source)
        self.assertEqual(mapped['name'], '中文人才')
        self.assertEqual(mapped['phone'], '13900000002')
        self.assertEqual(mapped['gender'], '男')
        self.assertEqual(mapped['education'], '本科')
        self.assertEqual(mapped['birthdate'], '1999-08')
        self.assertEqual(mapped['age'], '27')
        self.assertNotIn('出生日期', mapped)

    def test_invalid_recognized_ages_are_ignored(self):
        source = {'recruitment_type': '校园招聘', 'channel': '校园平台'}
        for age in ('0', '101', '26.5', '二十六'):
            with self.subTest(age=age):
                mapped = dify_mapping.to_candidate_payload({'name': '年龄校验', 'age': age}, source)
                self.assertNotIn('age', mapped)

    def test_experience_rows_are_sorted_newest_first_and_undated_rows_keep_resume_order(self):
        result = {'candidate': {
            'basic': {'name': '排序测试'},
            'education': [
                {'school': '无时间学校一'},
                {'school': '较早学校', 'start_date': '2015-09', 'end_date': '2019-06'},
                {'school': '无时间学校二'},
                {'school': '最新学校', 'start_date': '2021-09', 'end_date': '2025-06'},
                {'school': '仅有入学时间学校', 'start_date': '2023-09'},
            ],
            'work_experience': [
                {'company': '无时间公司一'},
                {'company': '较早公司', 'start_date': '2018-01', 'end_date': '2020-12'},
                {'company': '无时间公司二'},
                {'company': '最新公司', 'start_date': '2023-04'},
                {'company': '仅有结束时间公司', 'end_date': '2022-12'},
            ],
            'projects': [
                {'project_name': '无时间项目一'},
                {'project_name': '较早项目', 'start_date': '2019-03'},
                {'project_name': '无时间项目二'},
                {'project_name': '最新项目', 'start_date': '2024-05'},
                {'project_name': '同月项目一', 'start_date': '2022-01'},
                {'project_name': '同月项目二', 'start_date': '2022-01'},
            ],
        }}
        source = {'recruitment_type': '社会招聘', 'channel': '其他'}

        mapped = dify_mapping.to_candidate_payload(result, source)

        self.assertEqual(
            [row['school_name'] for row in mapped['education_experiences']],
            ['最新学校', '仅有入学时间学校', '较早学校', '无时间学校一', '无时间学校二'],
        )
        self.assertEqual(
            [row['organization'] for row in mapped['work_experiences']],
            ['最新公司', '仅有结束时间公司', '较早公司', '无时间公司一', '无时间公司二'],
        )
        self.assertEqual(
            [row['project_name'] for row in mapped['project_experiences']],
            ['最新项目', '同月项目一', '同月项目二', '较早项目', '无时间项目一', '无时间项目二'],
        )


if __name__ == '__main__':
    unittest.main()
