"""Remote candidate references and legacy SQLite foreign-key upgrades."""

import sqlite3
import unittest
import json
from pathlib import Path


class FakeCandidates:
    def __init__(self):
        self.rows = {9000000001: {"id": 9000000001, "name": "远端人才", "phone": "13900000001",
                                  "education_experiences": [{"school_name": "远端大学"}]}}
    def get(self, identifier):
        row = self.rows.get(identifier)
        return dict(row) if row else None
    def find_by_phone(self, phone):
        return next(({"id": row["id"], "name": row["name"], "phone": row["phone"]}
                     for row in self.rows.values() if row["phone"] == phone), None)


class RemoteCandidateReferenceTests(unittest.TestCase):
    def test_lookup_supports_remote_ids_labels_phone_and_profiles(self):
        from features.nocobase_sync.candidate_reference import RemoteCandidateReference
        reference = RemoteCandidateReference(FakeCandidates())
        self.assertTrue(reference.exists(9000000001))
        self.assertFalse(reference.exists(9))
        self.assertEqual(reference.label(9000000001), "远端人才")
        found = reference.find_by_phone("13900000001")
        self.assertEqual(found["id"], 9000000001)
        self.assertEqual(found["education_experiences"][0]["school_name"], "远端大学")
        self.assertEqual(reference.profile(9000000001)["education_experiences"][0]["school_name"], "远端大学")
        with self.assertRaisesRegex(ValueError, "编号无效"):
            reference.profile("9000000001")

    def test_upgrade_removes_only_candidate_foreign_keys_without_losing_rows_or_indexes(self):
        from features.nocobase_sync.candidate_reference import upgrade_remote_candidate_foreign_keys
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE candidates(id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("CREATE TABLE departments(id INTEGER PRIMARY KEY, name TEXT)")
        for table in ("applications", "interviews", "employees"):
            connection.execute(f"""CREATE TABLE {table}(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER REFERENCES candidates(id) ON DELETE RESTRICT,
                department_id INTEGER REFERENCES departments(id), note TEXT NOT NULL DEFAULT '')""")
            connection.execute(f"CREATE INDEX idx_{table}_candidate ON {table}(candidate_id)")
        connection.execute("INSERT INTO candidates VALUES(1,'本地旧人才')")
        connection.execute("INSERT INTO departments VALUES(2,'工程部')")
        for table in ("applications", "interviews", "employees"):
            connection.execute(f"INSERT INTO {table}(candidate_id,department_id,note) VALUES(1,2,'保留')")
        connection.commit()

        self.assertEqual(upgrade_remote_candidate_foreign_keys(connection), 3)

        for table in ("applications", "interviews", "employees"):
            row = connection.execute(f"SELECT * FROM {table}").fetchone()
            self.assertEqual((row["id"], row["candidate_id"], row["department_id"], row["note"]),
                             (1, 1, 2, "保留"))
            foreign = {(item["from"], item["table"]) for item in connection.execute(f"PRAGMA foreign_key_list({table})")}
            self.assertNotIn(("candidate_id", "candidates"), foreign)
            self.assertIn(("department_id", "departments"), foreign)
            connection.execute(f"UPDATE {table} SET candidate_id=9000000001")
            indexes = {item["name"] for item in connection.execute(f"PRAGMA index_list({table})")}
            self.assertIn(f"idx_{table}_candidate", indexes)

        self.assertEqual(upgrade_remote_candidate_foreign_keys(connection), 0)
        connection.close()

    def test_remote_schema_markers_and_server_validation_never_query_local_candidates(self):
        import server
        from features.nocobase_sync.candidate_reference import RemoteCandidateReference

        for feature in ("applications", "interviews", "employees"):
            schema = json.loads((Path(__file__).parents[1] / "features" / feature / "schema.json").read_text(encoding="utf-8"))
            field = next(item for item in schema["fields"] if item["key"] == "candidate_id")
            self.assertEqual(field.get("remoteRef"), "candidates")
            self.assertNotIn("ref", field)

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE schools(id INTEGER PRIMARY KEY,name TEXT)")
        previous = server.REMOTE_CANDIDATES
        server.REMOTE_CANDIDATES = RemoteCandidateReference(FakeCandidates())
        try:
            values = server.validate("applications", {
                "candidate_id": 9000000001, "name": "远端人才", "school_name": "远端大学",
                "status": "草稿",
            }, connection)
            self.assertEqual(values["candidate_id"], 9000000001)
        finally:
            server.REMOTE_CANDIDATES = previous
            connection.close()

    def test_remote_outage_is_propagated_without_local_fallback(self):
        from features.nocobase_sync.candidate_reference import RemoteCandidateReference
        class FailedCandidates:
            def get(self, identifier):
                raise RuntimeError("remote unavailable")
            def find_by_phone(self, phone):
                raise RuntimeError("remote unavailable")
        reference = RemoteCandidateReference(FailedCandidates())
        with self.assertRaisesRegex(RuntimeError, "remote unavailable"):
            reference.exists(8)

    def test_local_application_failure_rolls_back_new_remote_candidate(self):
        import server

        class CandidateService:
            def __init__(self):
                self.rolled_back = []
            def create(self, payload):
                return 9000000002
            def rollback_created(self, identifier):
                self.rolled_back.append(identifier)

        class CandidateReference:
            def __init__(self):
                self.candidates = CandidateService()
            def find_by_phone(self, phone):
                return None

        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE applications(id INTEGER PRIMARY KEY, candidate_id INTEGER)")
        previous = server.REMOTE_CANDIDATES
        reference = CandidateReference()
        server.REMOTE_CANDIDATES = reference
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "local insert failed"):
                with server.remote_candidate_compensation() as created:
                    server.sync_application_talent(connection, {
                        "phone": "13900000002", "name": "补偿测试", "school_name": "远端大学",
                        "major": "测试", "education": "本科",
                    }, remote_created=created)
                    raise sqlite3.IntegrityError("local insert failed")
            self.assertEqual(reference.candidates.rolled_back, [9000000002])
        finally:
            server.REMOTE_CANDIDATES = previous
            connection.close()


if __name__ == "__main__":
    unittest.main()
