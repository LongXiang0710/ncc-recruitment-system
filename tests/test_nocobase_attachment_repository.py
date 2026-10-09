"""Tests for NocoBase candidate resume attachment handling."""

import base64
import unittest
from unittest import mock

from features.nocobase_sync.client import NocoBaseError


class FakeClient:
    def __init__(self, responses=(), upload_response=None, download_response=None):
        self.responses = list(responses)
        self.upload_response = upload_response
        self.download_response = download_response
        self.calls = []

    def request(self, action, **kwargs):
        self.calls.append(("request", action, kwargs))
        if not self.responses:
            raise AssertionError(f"unexpected request: {action}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def upload(self, action, **kwargs):
        self.calls.append(("upload", action, kwargs))
        if isinstance(self.upload_response, Exception):
            raise self.upload_response
        return self.upload_response

    def download(self, url):
        self.calls.append(("download", url, {}))
        if isinstance(self.download_response, Exception):
            raise self.download_response
        return self.download_response


class AttachmentRepositoryTests(unittest.TestCase):
    def repository(self, client):
        from features.nocobase_sync.attachment_repository import AttachmentRepository
        return AttachmentRepository(client)

    @staticmethod
    def pdf_upload(name="简历.pdf", content=b"%PDF-1.4\nresume"):
        return {"name": name, "content": base64.b64encode(content).decode("ascii")}

    def test_list_and_read_validate_shapes_and_proxy_binary_content(self):
        client = FakeClient(
            responses=[
                [{"id": 7, "filename": "简历.pdf", "url": "https://cdn.test/7.pdf"}],
                {"id": 7, "filename": "简历.pdf", "url": "https://cdn.test/7.pdf"},
            ],
            download_response=(b"%PDF-data", "application/pdf"),
        )
        repository = self.repository(client)
        self.assertEqual(repository.list(3)[0]["id"], 7)
        self.assertEqual(repository.read(7), (b"%PDF-data", "application/pdf", "简历.pdf"))
        self.assertEqual(client.calls, [
            ("request", "campus_talent_pool/3/biographical_notes:list", {"params": {"pageSize": 100}}),
            ("request", "attachments:get", {"params": {"filterByTk": 7}}),
            ("download", "https://cdn.test/7.pdf", {}),
        ])

    def test_replace_uploads_then_sets_relation_and_removes_unreferenced_old_file(self):
        client = FakeClient(
            responses=[
                [{"id": 4, "filename": "旧.pdf"}],
                {},
                [],
                [],
                1,
            ],
            upload_response={"id": 9, "filename": "新简历.pdf", "url": "/uploads/9.pdf"},
        )
        result = self.repository(client).replace(2, self.pdf_upload("新简历.pdf"))
        self.assertEqual(result, [{"id": 9, "filename": "新简历.pdf", "url": "/uploads/9.pdf"}])
        self.assertEqual(client.calls[1], (
            "upload", "attachments:create", {
                "filename": "新简历.pdf", "mime_type": "application/pdf",
                "content": b"%PDF-1.4\nresume",
                "params": {"attachmentField": "campus_talent_pool.biographical_notes"},
            },
        ))
        self.assertEqual(client.calls[2], (
            "request", "campus_talent_pool/2/biographical_notes:set",
            {"method": "POST", "params": {"filterByTks": [9]}},
        ))
        self.assertEqual(client.calls[3], (
            "request", "campus_talent_pool:list", {
                "params": {"pageSize": 1, "filter": {"biographical_notes": {"id": 4}}},
            },
        ))
        self.assertEqual(client.calls[4], (
            "request", "Resume_Collection:list", {
                "params": {"pageSize": 1, "filter": {"Resume": {"id": 4}}},
            },
        ))
        self.assertEqual(client.calls[5], (
            "request", "attachments:destroy", {"method": "POST", "params": {"filterByTk": 4}},
        ))

    def test_no_change_makes_no_mutation_and_explicit_remove_detaches(self):
        existing = [{"id": 4, "filename": "旧.pdf"}]
        client = FakeClient(responses=[existing])
        self.assertEqual(self.repository(client).replace(2), existing)
        self.assertEqual(len(client.calls), 1)

        remove_client = FakeClient(responses=[existing, {}, [{"id": 99}]])
        self.assertEqual(self.repository(remove_client).replace(2, remove=True), [])
        self.assertEqual(remove_client.calls[1], (
            "request", "campus_talent_pool/2/biographical_notes:set",
            {"method": "POST", "params": {"filterByTks": []}},
        ))
        self.assertFalse(any(call[1] == "attachments:destroy" for call in remove_client.calls))

    def test_association_failure_attempts_cleanup_of_only_new_upload(self):
        failure = NocoBaseError("remote", 500, "set")
        client = FakeClient(
            responses=[[], failure, 1],
            upload_response={"id": 9, "filename": "新简历.pdf"},
        )
        with self.assertRaises(NocoBaseError) as raised:
            self.repository(client).replace(2, self.pdf_upload())
        self.assertIs(raised.exception, failure)
        self.assertEqual(client.calls[-1], (
            "request", "attachments:destroy", {"method": "POST", "params": {"filterByTk": 9}},
        ))

    def test_invalid_base64_content_extension_and_size_are_rejected_before_calls(self):
        client = FakeClient()
        repository = self.repository(client)
        invalid = (
            {"name": "简历.pdf", "content": "%%%"},
            self.pdf_upload("简历.exe"),
            self.pdf_upload("简历.pdf", b"not-a-pdf"),
        )
        for upload in invalid:
            with self.subTest(upload=upload), self.assertRaises(ValueError):
                repository.replace(1, upload)
        with mock.patch("features.nocobase_sync.attachment_repository.MAX_FILE_SIZE", 3):
            with self.assertRaises(ValueError):
                repository.replace(1, self.pdf_upload(content=b"%PDF"))
        self.assertEqual(client.calls, [])

    def test_shared_attachment_is_retained_and_unreferenced_is_deleted(self):
        shared = FakeClient(responses=[[{"id": 5}]])
        self.assertFalse(self.repository(shared).delete_if_unreferenced(5))
        self.assertEqual(len(shared.calls), 1)

        resume_shared = FakeClient(responses=[[], [{"id": 8}]])
        self.assertFalse(self.repository(resume_shared).delete_if_unreferenced(5))
        self.assertEqual(resume_shared.calls[-1][1], "Resume_Collection:list")

        orphan = FakeClient(responses=[[], [], 1])
        self.assertTrue(self.repository(orphan).delete_if_unreferenced(5))
        self.assertEqual(orphan.calls[-1][1], "attachments:destroy")

    def test_restore_reassociates_snapshot_ids_without_upload_or_delete(self):
        client = FakeClient(responses=[{}])
        self.repository(client).restore(3, [{"id": 8}, {"id": 9}])
        self.assertEqual(client.calls, [(
            "request", "campus_talent_pool/3/biographical_notes:set",
            {"method": "POST", "params": {"filterByTks": [8, 9]}},
        )])

    def test_invalid_attachment_responses_are_protocol_errors(self):
        cases = (
            FakeClient(responses=[{}]),
            FakeClient(responses=[[{"filename": "missing id"}]]),
            FakeClient(responses=[{"id": 7, "filename": "x.pdf", "url": ""}]),
        )
        actions = (
            lambda repository: repository.list(1),
            lambda repository: repository.list(1),
            lambda repository: repository.read(7),
        )
        for client, action in zip(cases, actions):
            with self.assertRaises(NocoBaseError) as raised:
                action(self.repository(client))
            self.assertEqual(raised.exception.kind, "protocol")

        missing_id = FakeClient(responses=[[]], upload_response={"filename": "x.pdf"})
        with self.assertRaises(NocoBaseError):
            self.repository(missing_id).replace(1, self.pdf_upload())


if __name__ == "__main__":
    unittest.main()
