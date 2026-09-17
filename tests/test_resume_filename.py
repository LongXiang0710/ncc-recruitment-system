import unittest

from features.resume_documents.filename_position import infer_position


class ResumeFilenamePositionTests(unittest.TestCase):
    def test_extracts_position_after_age(self):
        self.assertEqual(
            infer_position('张坤洋_26岁_电气工程师_南京_智联简历_41274.pdf'),
            '电气工程师',
        )

    def test_stops_at_position_suffix_before_location(self):
        self.assertEqual(
            infer_position('陈艺平_25岁_管道安装工程师福建漳州_智联招聘.pdf'),
            '管道安装工程师',
        )

    def test_finds_position_without_age_when_keyword_is_present(self):
        self.assertEqual(infer_position('李四-安全员-社会招聘.pdf'), '安全员')

    def test_leaves_ambiguous_filename_empty(self):
        self.assertEqual(infer_position('张三个人简历.pdf'), '')


if __name__ == '__main__':
    unittest.main()
