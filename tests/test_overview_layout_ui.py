from pathlib import Path
import subprocess
import unittest


class OverviewLayoutUiTests(unittest.TestCase):
    def test_date_and_add_button_use_spaced_action_group(self):
        script = Path(__file__).parent / 'overview_layout_ui_check.js'
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
