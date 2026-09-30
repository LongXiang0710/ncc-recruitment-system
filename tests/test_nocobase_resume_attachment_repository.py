"""Tests for Resume_Collection attachment relation handling."""

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
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def upload(self, action, **kwargs):
        self.calls.append(("upload", action, kwargs))
        return self.upload_response

    def download(self, url, **kwargs):
        self.calls.append(("download", url, kwargs))
        return self.download_response


def pdf_upload(name="简历.pdf", content=b"%PDF-1.4\nresume"):
    return {"name": name, "content": base64.b64encode(content).decode("ascii")}


class ResumeAttachmentRepositoryTests(unittest.TestCase):
    def repository(self, client):
        from features.nocobase_sync.resume_attachment_repository import ResumeAttachmentRepository
        return ResumeAttachmentRepository(client)

    def test_replace_uses_resume_relation_and_deletes_only_unreferenced_old_file(self):
        client = FakeClient(
            responses=[[{"id": 4}], {}, [], [], 1],
            upload_response={"id": 9, "filename": "新简历.pdf", "url": "/uploads/9.pdf"},
        )
        result = self.repository(client).replace(2, pdf_upload("新简历.pdf"))
        self.assertEqual(result[0]["id"], 9)
        self.assertEqual(client.calls[1], (
            "upload", "attachments:create", {
                "filename": "新简历.pdf", "mime_type": "application/pdf",
                "content": b"%PDF-1.4\nresume",
                "params": {"attachmentField": "Resume_Collection.Resume"},
            },
        ))
        self.assertEqual(client.calls[2], (
            "request", "Resume_Collection/2/Resume:set",
            {"method": "POST", "body": {"values": [9]}},
        ))
        self.assertEqual([call[1] for call in client.calls[3:]], [
            "Resume_Collection:list", "campus_talent_pool:list", "attachments:destroy",
        ])

    def test_read_is_bounded_and_sanitizes_filename(self):
        client = FakeClient(
            responses=[{"id": 7, "filename": '简历"\r\n注入.pdf', "url": "https://cdn.test/7.pdf"}],
            download_response=(b"%PDF", "application/pdf"),
        )
        content, mime, name = self.repository(client).read(7)
        self.assertEqual((content, mime, name), (b"%PDF", "application/pdf", "简历___注入.pdf"))
        self.assertEqual(client.calls[-1], (
            "download", "https://cdn.test/7.pdf", {"maximum_bytes": 50 * 1024 * 1024},
        ))

    def test_restore_remove_and_association_failure_compensate(self):
        restore_client = FakeClient(responses=[{}])
        self.repository(restore_client).restore(3, [{"id": 8}, {"id": 9}])
        self.assertEqual(restore_client.calls[0][1], "Resume_Collection/3/Resume:set")

        shared_remove = FakeClient(responses=[[{"id": 4}], {}, [{"id": 1}], []])
        self.assertEqual(self.repository(shared_remove).replace(3, remove=True), [])
        self.assertFalse(any(call[1] == "attachments:destroy" for call in shared_remove.calls))

        failure = NocoBaseError("remote", 500, "set")
        failed = FakeClient(responses=[[], failure, 1], upload_response={"id": 10})
        with self.assertRaises(NocoBaseError):
            self.repository(failed).replace(3, pdf_upload())
        self.assertEqual(failed.calls[-1][1], "attachments:destroy")

    def test_invalid_uploads_are_rejected_before_remote_calls(self):
        client = FakeClient()
        repository = self.repository(client)
        for upload in (
            {"name": "x.pdf", "content": "%%%"},
            pdf_upload("x.exe"),
            pdf_upload("x.pdf", b"not-pdf"),
        ):
            with self.subTest(upload=upload), self.assertRaises(ValueError):
                repository.replace(1, upload)
        with mock.patch("features.nocobase_sync.resume_attachment_repository.MAX_FILE_SIZE", 3):
            with self.assertRaises(ValueError):
                repository.replace(1, pdf_upload(content=b"%PDF"))
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
