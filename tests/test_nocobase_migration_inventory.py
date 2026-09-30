"""Read-only migration inventory tests."""

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


class ReadOnlyService:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
    def list_all(self, query=""):
        self.calls.append(("list_all", query))
        return [dict(row) for row in self.rows]
    def create(self, payload):
        raise AssertionError("inventory must not mutate remote data")


def create_database(path: Path, *, bad_hash=False, missing=False):
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE candidates(id INTEGER PRIMARY KEY,archive_no TEXT,name TEXT,phone TEXT,resume TEXT);
        CREATE TABLE resume_documents(id INTEGER PRIMARY KEY,archive_no TEXT,source_id TEXT,file_hash TEXT,resume TEXT);
        CREATE TABLE attachments(id TEXT PRIMARY KEY,name TEXT,content BLOB);
        CREATE TABLE candidate_educations(id INTEGER PRIMARY KEY,candidate_id INTEGER,education TEXT);
        CREATE TABLE candidate_work_experiences(id INTEGER PRIMARY KEY,candidate_id INTEGER,organization TEXT);
        CREATE TABLE candidate_project_experiences(id INTEGER PRIMARY KEY,candidate_id INTEGER,project_name TEXT);
        CREATE TABLE resume_imports(source_id TEXT PRIMARY KEY,candidate_id INTEGER);
        CREATE TABLE applications(id INTEGER PRIMARY KEY,candidate_id INTEGER);
        CREATE TABLE interviews(id INTEGER PRIMARY KEY,candidate_id INTEGER);
        CREATE TABLE employees(id INTEGER PRIMARY KEY,candidate_id INTEGER);
    """)
    content = b"%PDF-1.4\nprivate resume bytes"
    digest = "wrong" if bad_hash else hashlib.sha256(content).hexdigest()
    connection.execute("INSERT INTO candidates VALUES(1,'C-001','张三','13900000001','A1')")
    connection.execute("INSERT INTO resume_documents VALUES(2,'R-001','SRC-001',?,'A2')", (digest,))
    connection.execute("INSERT INTO attachments VALUES('A1','张三简历.pdf',?)", (content,))
    if not missing:
        connection.execute("INSERT INTO attachments VALUES('A2','投递.pdf',?)", (content,))
    connection.execute("INSERT INTO candidate_educations VALUES(1,1,'本科')")
    connection.execute("INSERT INTO candidate_work_experiences VALUES(1,1,'测试单位')")
    connection.execute("INSERT INTO candidate_project_experiences VALUES(1,1,'测试项目')")
    connection.execute("INSERT INTO resume_imports VALUES('SRC-001',1)")
    connection.execute("INSERT INTO applications VALUES(1,1)")
    connection.execute("INSERT INTO interviews VALUES(1,1)")
    connection.execute("INSERT INTO employees VALUES(1,1)")
    connection.commit(); connection.close()


class MigrationInventoryTests(unittest.TestCase):
    def services(self, candidates=(), resumes=(), preflight_ok=True):
        return SimpleNamespace(
            candidates=ReadOnlyService(candidates), resumes=ReadOnlyService(resumes),
            preflight=SimpleNamespace(ok=preflight_ok),
        )

    def test_inventory_counts_relations_hashes_references_and_is_read_only(self):
        from features.nocobase_sync.migration_inventory import build_inventory

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.db"
            create_database(path)
            before = path.read_bytes()
            services = self.services()
            inventory = build_inventory(path, services)
            self.assertEqual(inventory.counts["local_candidates"], 1)
            self.assertEqual(inventory.counts["local_candidate_educations"], 1)
            self.assertEqual(inventory.counts["local_candidate_work_experiences"], 1)
            self.assertEqual(inventory.counts["local_candidate_project_experiences"], 1)
            self.assertEqual(inventory.counts["local_resume_imports"], 1)
            self.assertEqual(inventory.counts["local_attachments"], 2)
            self.assertEqual(set(inventory.digests), {"source_rows", "attachments", "references", "target"})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(services.candidates.calls, [("list_all", "")])
            self.assertEqual(services.resumes.calls, [("list_all", "")])

    def test_missing_corrupt_duplicate_conflict_and_preflight_issues(self):
        from features.nocobase_sync.migration_inventory import build_inventory

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.db"
            create_database(path, bad_hash=True, missing=True)
            connection = sqlite3.connect(path)
            connection.execute("INSERT INTO candidates VALUES(3,'C-003','李四','13900000001','')")
            connection.commit(); connection.close()
            services = self.services(
                candidates=[{"id": 90, "archive_no": "REMOTE", "phone": "13900000001"},
                            {"id": 91, "archive_no": "REMOTE", "phone": "18800000000"}],
                resumes=[{"id": 92, "archive_no": "R-001", "source_id": "OTHER", "file_hash": "remote"}],
                preflight_ok=False,
            )
            inventory = build_inventory(path, services)
            kinds = {issue.kind for issue in inventory.issues}
            self.assertIn("missing_attachment", kinds)
            self.assertIn("local_duplicate_phone", kinds)
            self.assertIn("remote_duplicate_archive_no", kinds)
            self.assertIn("target_conflict_phone", kinds)
            self.assertIn("target_conflict_archive_no", kinds)
            self.assertIn("preflight_failed", kinds)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "corrupt.db"
            create_database(path, bad_hash=True)
            inventory = build_inventory(path, self.services())
            self.assertIn("attachment_hash_mismatch", {issue.kind for issue in inventory.issues})

    def test_canonical_digest_changes_with_business_data_but_is_deterministic(self):
        from features.nocobase_sync.migration_inventory import canonical_digest
        first = {"rows": [{"id": 1, "name": "张三"}], "count": 1}
        reordered = {"count": 1, "rows": [{"name": "张三", "id": 1}]}
        changed = {"rows": [{"id": 1, "name": "李四"}], "count": 1}
        self.assertEqual(canonical_digest(first), canonical_digest(reordered))
        self.assertNotEqual(canonical_digest(first), canonical_digest(changed))


if __name__ == "__main__":
    unittest.main()
