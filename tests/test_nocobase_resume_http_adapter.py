"""HTTP contracts for the remote resume collection."""

import json
import unittest
from types import SimpleNamespace


class FakeResumes:
    def __init__(self):
        self.rows = {1: {"id": 1, "name": "一.pdf", "status": "待识别"}}
        self.calls = []
        self.failure = None
    def list_all(self, query=""):
        self.calls.append(("list_all", query)); return list(self.rows.values())
    def list(self, page, page_size, query):
        self.calls.append(("list", page, page_size, query)); return {"rows": list(self.rows.values()), "count": 1}
    def get(self, identifier):
        self.calls.append(("get", identifier)); return self.rows.get(identifier)
    def create(self, payload):
        self.calls.append(("create", payload)); return 2
    def create_public(self, payload):
        self.calls.append(("create_public", payload))
        if self.failure:
            raise self.failure
        return 3
    def update(self, identifier, payload):
        self.calls.append(("update", identifier, payload))
    def pending(self):
        self.calls.append(("pending",)); return list(self.rows.values())


class FakeRecognition:
    def recognize(self, identifier):
        return {"name": "张三", "id": identifier}
    def result(self, identifier):
        return {"name": "张三", "id": identifier}


class FakeLinks:
    def delete_resumes(self, ids, expected=None):
        self.deleted = (ids, expected); return len(ids)
    def import_candidate(self, identifier):
        return SimpleNamespace(candidate_id=9, already_imported=False)
    def resume_delete_preview(self, ids):
        return [{"entity": "resume_documents", "id": value, "name": "一.pdf"} for value in ids]


class FakeHandler:
    def __init__(self, bodies=()):
        self._bodies = list(bodies)
        self.responses = []
        self.server = SimpleNamespace(
            remote_services=SimpleNamespace(
                resumes=FakeResumes(), recognition=FakeRecognition(), resume_candidates=FakeLinks(),
            ),
            resume_schema={"title": "简历收集", "fields": [{"key": "name", "label": "名称"}]},
            server_port=8116,
        )
        self.headers = {"Host": "localhost:8116"}
    def body(self):
        return self._bodies.pop(0)
    def send(self, status, data, content_type="application/json; charset=utf-8", headers=None):
        self.responses.append((status, data, content_type, headers or {}))


class ResumeHttpAdapterTests(unittest.TestCase):
    def call(self, handler, method, identifier=None, query=None):
        from features.nocobase_sync.resume_http_adapter import handle_remote_resume_request
        self.assertTrue(handle_remote_resume_request(handler, method, identifier, query or {}))
        return handler.responses[-1]

    def test_crud_paging_pending_recognition_and_import_contracts(self):
        handler = FakeHandler([{"name": "新.pdf"}, {"name": "改.pdf"}])
        self.assertEqual(self.call(handler, "GET")[:2], (200, list(handler.server.remote_services.resumes.rows.values())))
        self.assertEqual(self.call(handler, "GET", query={"page": ["1"], "pageSize": ["20"]})[1]["count"], 1)
        self.assertEqual(self.call(handler, "POST")[:2], (201, {"id": 2}))
        self.assertEqual(self.call(handler, "PUT", "1")[:2], (200, {"ok": True}))
        self.assertEqual(self.call(handler, "GET", "pending")[1][0]["status"], "待识别")
        self.assertEqual(self.call(handler, "POST", "1/recognize")[1]["result"]["name"], "张三")
        self.assertEqual(self.call(handler, "GET", "1/recognition-result")[1]["result"]["name"], "张三")
        self.assertEqual(self.call(handler, "POST", "1/candidate")[:2], (201, {"id": 9, "already_imported": False}))

    def test_delete_uses_server_side_preview_when_client_sends_no_confirmation(self):
        handler = FakeHandler([{"ids": [1]}, {"ids": [1]}])
        preview = self.call(handler, "POST", "delete-preview")[1]
        self.assertEqual(preview["count"], 1)
        self.assertEqual(self.call(handler, "POST", "batch-delete")[:2], (200, {"count": 1}))
        self.assertEqual(handler.server.remote_services.resume_candidates.deleted, ([1], None))

    def test_public_submission_uses_remote_service_and_ignores_forged_system_fields(self):
        from features.nocobase_sync.resume_http_adapter import handle_public_remote_resume_request
        handler = FakeHandler([{"status": "已入库", "linked_candidate": 8, "_resume_upload": {"name": "x.pdf"}}])
        self.assertTrue(handle_public_remote_resume_request(handler, "POST", "social"))
        self.assertEqual(handler.responses[-1][:2], (201, {"ok": True}))
        call = handler.server.remote_services.resumes.calls[-1]
        self.assertEqual(call[0], "create_public")
        self.assertEqual(call[1]["recruitment_type"], "社会招聘")

    def test_public_remote_failure_is_sanitized(self):
        from features.nocobase_sync.client import NocoBaseError
        from features.nocobase_sync.resume_http_adapter import handle_public_remote_resume_request
        handler = FakeHandler([{"_resume_upload": {"name": "x.pdf"}}])
        handler.server.remote_services.resumes.failure = NocoBaseError("network", None, "private")
        self.assertTrue(handle_public_remote_resume_request(handler, "POST", "campus"))
        self.assertEqual(handler.responses[-1][0], 503)
        rendered = json.dumps(handler.responses[-1][1], ensure_ascii=False)
        self.assertNotIn("private", rendered)
        self.assertIn("诊断编号", rendered)


if __name__ == "__main__":
    unittest.main()
