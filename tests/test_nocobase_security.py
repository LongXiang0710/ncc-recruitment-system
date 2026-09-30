import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NocoBaseSecurityTests(unittest.TestCase):
    def test_operator_files_do_not_embed_endpoint_or_credentials(self):
        files = list(ROOT.glob('*.bat')) + [ROOT/'NocoBase统一切换说明.md']
        for path in files:
            text=path.read_text(encoding='utf-8-sig').lower()
            self.assertNotIn('authorization: bearer',text,path.name)
            self.assertNotIn('cloud.njncc.com',text,path.name)
            self.assertNotIn('nocobase_password',text,path.name)

    def test_runbook_has_exact_order_and_no_automatic_enable(self):
        text=(ROOT/'NocoBase统一切换说明.md').read_text(encoding='utf-8')
        self.assertEqual(sum(1 for line in text.splitlines() if line[:2] in {f'{i}.' for i in range(1,10)} or line.startswith('10.')),10)
        self.assertIn('迁移本身不会自动启用数据源',text)
        self.assertIn('不处理身份证',text)


if __name__ == '__main__': unittest.main()
