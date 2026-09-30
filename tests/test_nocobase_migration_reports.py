"""Redacted migration report tests."""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tests.test_nocobase_migration_inventory import create_database


class MigrationReportTests(unittest.TestCase):
    def services(self):
        from tests.test_nocobase_migration_inventory import ReadOnlyService
        from types import SimpleNamespace
        return SimpleNamespace(
            candidates=ReadOnlyService([]), resumes=ReadOnlyService([]),
            preflight=SimpleNamespace(ok=True),
        )

    def test_eligible_report_expires_in_24_hours_and_saved_output_is_redacted(self):
        from features.nocobase_sync.migration_reports import check_migration, save_report

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "source.db"
            create_database(database)
            now = datetime(2026, 9, 30, 9, 0, 0)
            report = check_migration(database, self.services(), now=lambda: now)
            self.assertTrue(report.eligible)
            self.assertEqual((report.expires_at - report.generated_at).total_seconds(), 86400)
            path = save_report(root, report)
            rendered = path.read_text(encoding="utf-8")
            text_rendered = path.with_suffix(".txt").read_text(encoding="utf-8")
            parsed = json.loads(rendered)
            self.assertTrue(parsed["eligible"])
            for secret in ("张三", "13900000001", "private resume bytes", "测试单位", "Authorization", "Bearer "):
                self.assertNotIn(secret, rendered)
                self.assertNotIn(secret, text_rendered)

    def test_conflict_report_is_ineligible_and_identifies_only_ids_archive_and_type(self):
        from features.nocobase_sync.migration_reports import check_migration

        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "source.db"
            create_database(database, missing=True)
            report = check_migration(database, self.services(), now=lambda: datetime(2026, 9, 30))
            self.assertFalse(report.eligible)
            issue = report.redacted()["issues"][0]
            self.assertEqual(set(issue), {"kind", "entity", "local_id", "archive_no"})


if __name__ == "__main__":
    unittest.main()
