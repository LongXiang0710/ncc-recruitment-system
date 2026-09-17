from pathlib import Path
import subprocess
import unittest


class SelectionExportUiTests(unittest.TestCase):
    def test_export_button_and_request_follow_selected_records(self):
        script = Path(__file__).parent / 'selection_export_ui_check.js'
        result = subprocess.run(
            ['node', str(script)],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
