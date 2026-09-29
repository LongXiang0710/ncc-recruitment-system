"""Deployment launcher and operator-documentation tests for NocoBase cutover."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NocoBaseLauncherTests(unittest.TestCase):
    def test_launchers_are_relocatable_and_delegate_to_guarded_cli(self):
        expected = {
            "配置NocoBase.bat": "configure",
            "检查NocoBase连接.bat": "check",
            "启用NocoBase人才库.bat": "enable",
            "停用NocoBase人才库.bat": "disable",
        }
        for filename, command in expected.items():
            with self.subTest(filename=filename):
                text = (ROOT / filename).read_text(encoding="utf-8-sig").lower()
                self.assertIn('%~dp0', text)
                self.assertIn(f"python -m features.nocobase_sync.configure {command}", text)
                self.assertNotIn("cloud.njncc.com", text)
                self.assertNotIn("bearer ", text)

    def test_readme_documents_guarded_fixed_ip_cutover(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for phrase in (
            "设计电脑保持 SQLite",
            "固定 IP 电脑",
            "重新配置",
            "DPAPI",
            "不会迁移",
            "不会回退到 SQLite",
            "检查NocoBase连接.bat",
            "启用NocoBase人才库.bat",
            "停用NocoBase人才库.bat",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_enable_checks_before_persisting_backend_selection(self):
        text = (ROOT / "features" / "nocobase_sync" / "backend.py").read_text(encoding="utf-8")
        block = text[text.index("def enable_nocobase"):text.index("def select_candidate_backend")]
        self.assertLess(block.index("_require_preflight"), block.index('write_backend(data_dir, "nocobase")'))


if __name__ == "__main__":
    unittest.main()
