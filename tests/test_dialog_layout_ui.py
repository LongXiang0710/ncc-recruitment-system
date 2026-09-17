from pathlib import Path
import subprocess
import unittest


class DialogLayoutUiTests(unittest.TestCase):
    def test_all_dialogs_use_one_floating_close_layout(self):
        script = Path(__file__).parent / 'dialog_layout_ui_check.js'
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
