from pathlib import Path
import subprocess
import unittest


class CandidateExperienceUiTests(unittest.TestCase):
    def test_other_position_reveals_required_detail_and_standard_position_clears_it(self):
        script = Path(__file__).parent / 'position_fields_ui_check.js'
        result = subprocess.run(['node', str(script)], cwd=Path(__file__).parents[1], capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_candidate_editor_hides_derived_graduation_and_cohort_fields(self):
        script = Path(__file__).parent / 'candidate_profile_ui_check.js'
        result = subprocess.run(['node', str(script)], cwd=Path(__file__).parents[1], capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_education_editor_groups_profile_and_dates_into_two_rows(self):
        script = Path(__file__).parent / 'candidate_education_ui_check.js'
        result = subprocess.run(['node', str(script)], cwd=Path(__file__).parents[1], capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_experience_editor_uses_one_shared_work_experience_payload(self):
        script = Path(__file__).parent / 'candidate_experiences_ui_check.js'
        result = subprocess.run(['node', str(script)], cwd=Path(__file__).parents[1], capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_project_experience_editor_is_social_recruitment_only(self):
        script = Path(__file__).parent / 'candidate_project_experiences_ui_check.js'
        result = subprocess.run(['node', str(script)], cwd=Path(__file__).parents[1], capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_resume_recognition_keeps_child_table_drafts(self):
        script = Path(__file__).parent / 'resume_documents_ui_check.js'
        result = subprocess.run(['node', str(script)], cwd=Path(__file__).parents[1], capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_shared_record_search_supports_partial_archive_numbers(self):
        script = Path(__file__).parent / 'record_search_ui_check.js'
        result = subprocess.run(['node', str(script)], cwd=Path(__file__).parents[1], capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
