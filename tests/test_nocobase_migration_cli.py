import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class MigrationCliTests(unittest.TestCase):
    def test_usage_does_not_touch_services(self):
        from features.nocobase_sync.migration_cli import main
        self.assertEqual(main([],services_factory=lambda _path: self.fail('called')),2)

    def test_apply_reports_sanitized_failure(self):
        from features.nocobase_sync.migration_cli import main
        with tempfile.TemporaryDirectory() as folder, patch('builtins.print') as output:
            with patch('features.nocobase_sync.migration_cli.default_data_dir',return_value=Path(folder)):
                code=main(['apply',str(Path(folder)/'missing.db')],services_factory=lambda _path: object())
            self.assertEqual(code,1)
            self.assertNotIn('missing.db',' '.join(str(call) for call in output.call_args_list))


if __name__ == '__main__': unittest.main()
