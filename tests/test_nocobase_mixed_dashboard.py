"""Mixed NocoBase/SQLite dashboard contract tests."""

import sqlite3
import unittest
from types import SimpleNamespace


class ListService:
    def __init__(self, rows=None, failure=None):
        self.rows = rows or []
        self.failure = failure
        self.calls = []

    def list_all(self, query=""):
        self.calls.append(("list_all", query))
        if self.failure:
            raise self.failure
        return [dict(row) for row in self.rows]


class MixedDashboardTests(unittest.TestCase):
    def services(self):
        candidates = ListService([
            {"id": 91, "name": "校园甲", "school_name": "甲大学", "major": "机械",
             "position": "工程师", "status": "待筛选", "recruitment_type": "校园招聘",
             "created_at": "2026-09-29T10:00:00"},
            {"id": 93, "name": "社会乙", "school_name": "乙大学", "major": "安全",
             "position": "安全员", "status": "已录用", "recruitment_type": "社会招聘",
             "created_at": "2026-09-30T10:00:00"},
            {"id": 92, "name": "校园丙", "school_name": "丙大学", "major": "电气",
             "position": "技术员", "status": "待筛选", "recruitment_type": "校园招聘",
             "created_at": "2026-09-30T09:00:00"},
        ])
        resumes = ListService([
            {"id": 201, "status": "待识别", "recruitment_type": "校园招聘"},
            {"id": 202, "status": "已入库", "recruitment_type": "社会招聘"},
        ])
        return SimpleNamespace(candidates=candidates, resumes=resumes)

    def connection(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE applications(id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE interviews(id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE schools(id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE employees(id INTEGER PRIMARY KEY)")
        connection.executemany("INSERT INTO applications VALUES(?)", [(1,), (2,)])
        connection.execute("INSERT INTO interviews VALUES(1)")
        connection.execute("INSERT INTO schools VALUES(1)")
        connection.execute("INSERT INTO employees VALUES(1)")
        return connection

    def test_remote_sections_are_combined_with_local_business_counts(self):
        import server

        services = self.services()
        remote = server.load_remote_dashboard(services)
        connection = self.connection()
        statements = []
        connection.set_trace_callback(statements.append)
        try:
            result = server.build_dashboard(
                connection,
                {name: {} for name in ("resume_documents", "candidates", "applications",
                                        "interviews", "schools", "employees")},
                remote,
            )
        finally:
            connection.close()

        self.assertEqual(result["counts"], {
            "resume_documents": 2, "candidates": 3, "applications": 2,
            "interviews": 1, "schools": 1, "employees": 1,
        })
        self.assertEqual(result["statuses"], [
            {"status": "待筛选", "count": 2}, {"status": "已录用", "count": 1},
        ])
        self.assertEqual([row["id"] for row in result["recent"]], [93, 92, 91])
        self.assertEqual(result["recruitment"]["校园招聘"]["counts"]["resume_documents"], 1)
        self.assertEqual(result["recruitment"]["校园招聘"]["counts"]["candidates"], 2)
        self.assertEqual(result["recruitment"]["社会招聘"]["counts"]["candidates"], 1)
        self.assertEqual([row["id"] for row in result["recruitment"]["校园招聘"]["recent"]], [92, 91])
        rendered_sql = "\n".join(statements).lower()
        self.assertNotIn(" from candidates", rendered_sql)
        self.assertNotIn(" from resume_documents", rendered_sql)
        self.assertEqual(services.candidates.calls, [("list_all", "")])
        self.assertEqual(services.resumes.calls, [("list_all", "")])

    def test_remote_outage_is_propagated_without_local_fallback(self):
        import server

        failure = RuntimeError("remote unavailable")
        services = SimpleNamespace(candidates=ListService(failure=failure), resumes=ListService())
        with self.assertRaisesRegex(RuntimeError, "remote unavailable"):
            server.load_remote_dashboard(services)
        self.assertEqual(services.resumes.calls, [])


if __name__ == "__main__":
    unittest.main()
