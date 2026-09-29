"""HTTP contract tests for the NocoBase candidate route adapter."""

import json
import http.cookiejar
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from features.nocobase_sync.client import NocoBaseError


SCHEMA = {"title": "人才库", "short": "人才", "fields": [
    {"key": "name", "label": "姓名", "required": True},
    {"key": "phone", "label": "联系方式", "required": True},
]}


class FakeService:
    def __init__(self):
        self.calls = []
        self.rows = {1: {"id": 1, "name": "张三", "phone": "13900000001", "created_at": "2026-09-29T10:00:00"}}
        self.failure = None

    def _fail(self):
        if self.failure:
            raise self.failure

    def list_all(self, query=""):
        self.calls.append(("list_all", query)); self._fail(); return list(self.rows.values())
    def get(self, identifier):
        self.calls.append(("get", identifier)); self._fail(); return self.rows.get(identifier)
    def create(self, payload):
        self.calls.append(("create", payload)); self._fail(); return 2
    def update(self, identifier, payload):
        self.calls.append(("update", identifier, payload)); self._fail()
    def delete_preview(self, ids):
        self.calls.append(("delete_preview", ids)); self._fail()
        return {"details": [{"entity": "candidates", "id": value, "name": "张三"} for value in ids]}
    def delete(self, ids, expected):
        self.calls.append(("delete", ids, expected)); self._fail(); return len(ids)
    def validate(self, payload):
        self.calls.append(("validate", payload)); self._fail()
        return {"main": {"phone": payload.get("phone") or "13900000001"}}
    def create_many(self, payloads):
        self.calls.append(("create_many", payloads)); self._fail(); return list(range(10, 10 + len(payloads)))
    def read_attachment(self, identifier):
        self.calls.append(("read_attachment", identifier)); self._fail()
        return b"%PDF", "application/pdf", "简历.pdf"


class FakeHandler:
    def __init__(self, service, bodies=(), prepare=None):
        self._bodies = list(bodies)
        self.responses = []
        self.headers = {"Host": "localhost:8116"}
        self.server = SimpleNamespace(
            candidate_service=service,
            candidate_imports={},
            candidate_schema=SCHEMA,
            candidate_import_preparer=prepare or (lambda payload: payload),
            server_port=8116,
        )

    def body(self):
        return self._bodies.pop(0)

    def session(self):
        return "session-token"

    def send(self, status, data, content_type="application/json; charset=utf-8", headers=None):
        self.responses.append((status, data, content_type, headers or {}))
        return self.responses[-1]


class HttpAdapterTests(unittest.TestCase):
    def call(self, handler, method, identifier=None, query=None):
        from features.nocobase_sync.http_adapter import handle_remote_candidate_request
        self.assertTrue(handle_remote_candidate_request(handler, method, identifier, query or {}))
        return handler.responses[-1]

    def test_crud_list_search_and_detail_contracts(self):
        service = FakeService()
        handler = FakeHandler(service, bodies=[{"name": "李四"}, {"name": "王五"}])
        self.assertEqual(self.call(handler, "GET", query={"q": [" 张 "]})[:2], (200, list(service.rows.values())))
        self.assertEqual(self.call(handler, "GET", "1")[:2], (200, service.rows[1]))
        self.assertEqual(self.call(handler, "POST")[:2], (201, {"id": 2}))
        self.assertEqual(self.call(handler, "PUT", "1")[:2], (200, {"ok": True}))
        self.assertEqual(service.calls[:4], [
            ("list_all", "张"), ("get", 1), ("create", {"name": "李四"}),
            ("update", 1, {"name": "王五"}),
        ])

    def test_delete_preview_confirmed_batch_and_direct_delete(self):
        service = FakeService()
        expected = [{"entity": "candidates", "id": 1, "name": "张三"}]
        handler = FakeHandler(service, bodies=[{"ids": [1]}, {"ids": [1], "expected": expected}, {}])
        self.assertEqual(self.call(handler, "POST", "delete-preview")[:2], (200, {"items": expected, "count": 1}))
        self.assertEqual(self.call(handler, "POST", "batch-delete")[:2], (200, {"count": 1}))
        self.assertEqual(self.call(handler, "DELETE", "1")[:2], (200, {"ok": True}))

    def test_import_preview_and_commit_are_bounded_and_session_scoped(self):
        service = FakeService()
        preview = {
            "sheets": ["Sheet1"], "sheet": "Sheet1", "headers": ["姓名"], "mapping": ["name"],
            "header_row": 1, "rows": [{"line": 2, "values": {"name": "张三"}}], "errors": [],
        }
        handler = FakeHandler(service, bodies=[{"filename": "x.xlsx"}], prepare=lambda _payload: preview)
        status, body, *_ = self.call(handler, "POST", "import-preview")
        self.assertEqual(status, 200)
        self.assertTrue(body["token"])
        token = body["token"]
        handler._bodies.append({"token": token})
        self.assertEqual(self.call(handler, "POST", "import-commit")[:2], (201, {"count": 1, "ids": [10]}))
        self.assertNotIn(token, handler.server.candidate_imports)

    def test_export_qr_and_attachment_proxy(self):
        service = FakeService()
        handler = FakeHandler(service, bodies=[{"ids": [1]}, {"ids": [1]}])
        status, content, mime, headers = self.call(handler, "POST", "export.xlsx")
        self.assertEqual(status, 200)
        self.assertTrue(content.startswith(b"PK"))
        self.assertIn("spreadsheetml", mime)
        self.assertIn("Content-Disposition", headers)
        status, qr, *_ = self.call(handler, "POST", "qr-print")
        self.assertEqual(status, 200)
        self.assertEqual(qr["items"][0]["id"], 1)
        status, content, mime, headers = self.call(handler, "GET", "attachment:7")
        self.assertEqual((status, content, mime), (200, b"%PDF", "application/pdf"))
        self.assertIn("filename*=UTF-8", headers["Content-Disposition"])

    def test_remote_errors_are_sanitized_and_never_fall_through(self):
        from features.nocobase_sync import diagnostics

        for kind, expected_status in (("authentication", 502), ("permission", 502), ("network", 503), ("remote", 503)):
            with self.subTest(kind=kind):
                service = FakeService()
                service.failure = NocoBaseError(kind, 401 if kind == "authentication" else None, "secret:endpoint")
                handler = FakeHandler(service)
                with mock.patch.object(diagnostics.LOGGER, "error") as logged:
                    status, body, *_ = self.call(handler, "GET")
                self.assertEqual(status, expected_status)
                rendered = json.dumps(body, ensure_ascii=False)
                self.assertNotIn("secret:endpoint", rendered)
                self.assertNotIn("Authorization", rendered)
                self.assertIn("诊断编号", rendered)
                log_text = str(logged.call_args)
                self.assertNotIn("secret:endpoint", log_text)
                self.assertNotIn("13900000001", log_text)


class HttpRouteIntegrationTests(unittest.TestCase):
    def setUp(self):
        import server

        self.server_module = server
        self.temp = tempfile.TemporaryDirectory()
        self.original_data = server.DATA
        server.DATA = Path(self.temp.name)
        server.initialize()
        self.service = FakeService()
        self.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.http.candidate_service = self.service
        self.http.candidate_imports = {}
        self.http.candidate_schema = SCHEMA
        self.http.candidate_import_preparer = lambda payload: payload
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.http.server_port}/api/"
        self.client = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        password = (server.DATA / "initial-password.txt").read_text(encoding="utf-8")
        status, _ = self.call("login", {"username": "admin", "password": password})
        self.assertEqual(status, 200)

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.server_module.SESSIONS.clear()
        self.server_module.SESSION_USERS.clear()
        self.server_module.DATA = self.original_data
        self.temp.cleanup()

    def call(self, path, data=None, method=None):
        request = Request(
            self.url + path,
            data=json.dumps(data).encode("utf-8") if data is not None else None,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            response = self.client.open(request)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def local_candidate_count(self):
        with self.server_module.db() as connection:
            return connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]

    def test_selected_remote_backend_handles_route_without_sqlite_write(self):
        before = self.local_candidate_count()
        self.assertEqual(self.call("candidates")[1], list(self.service.rows.values()))
        self.assertEqual(self.call("candidates", {"name": "李四"})[:2], (201, {"id": 2}))
        self.assertEqual(self.local_candidate_count(), before)
        self.assertIn(("create", {"name": "李四"}), self.service.calls)

    def test_remote_failure_returns_error_without_sqlite_fallback(self):
        before = self.local_candidate_count()
        self.service.failure = NocoBaseError("network", None, "private detail")
        status, body = self.call("candidates", {"name": "李四"})
        self.assertEqual(status, 503)
        self.assertIn("诊断编号", body["error"])
        self.assertEqual(self.local_candidate_count(), before)


if __name__ == "__main__":
    unittest.main()
