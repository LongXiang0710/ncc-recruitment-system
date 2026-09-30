"""Aggregate behavior tests for NocoBase-backed resume collection."""

import base64
import unittest
from datetime import datetime

from features.nocobase_sync.client import NocoBaseError


SCHEMA = {"fields": [
    {"key": "archive_no", "label": "档案编号", "readonly": True},
    {"key": "source_id", "label": "source_id", "readonly": True},
    {"key": "status", "label": "处理状态", "options": ["待识别", "已识别", "已入库", "失败"]},
    {"key": "name", "label": "简历名称", "required": True},
    {"key": "position", "label": "应聘岗位", "options": ["机械工程师", "电气工程师", "其它"]},
    {"key": "position_detail", "label": "其它岗位名称"},
    {"key": "recruitment_type", "label": "招聘类型", "options": ["校园招聘", "社会招聘"]},
    {"key": "channel", "label": "招聘渠道", "options": ["校园线下", "校园平台", "智联招聘", "boss直聘", "其他"]},
    {"key": "channel_detail", "label": "其他渠道详情"},
    {"key": "resume", "label": "简历附件", "type": "attachment"},
    {"key": "created_by", "label": "创建人", "readonly": True},
]}


def upload(content=b"%PDF-1.4\nresume", name="测试.pdf"):
    return {"name": name, "content": base64.b64encode(content).decode("ascii")}


class FakeResumes:
    def __init__(self):
        self.rows = {}
        self.calls = []
        self.next_id = 1
        self.create_error = None

    def list_page(self, page, page_size, query):
        return {"rows": list(self.rows.values()), "count": len(self.rows)}
    def list(self, page=1, page_size=20, query=""):
        return list(self.rows.values())
    def get(self, identifier):
        row = self.rows.get(identifier)
        return dict(row) if row else None
    def create(self, values):
        self.calls.append(("create", dict(values)))
        identifier = self.next_id; self.next_id += 1
        self.rows[identifier] = {"id": identifier, "updated_at": "v1", **values}
        if self.create_error:
            raise self.create_error
        return identifier
    def update(self, identifier, values):
        self.calls.append(("update", identifier, dict(values)))
        self.rows[identifier].update(values)
    def delete(self, identifier):
        self.calls.append(("delete", identifier))
        return self.rows.pop(identifier, None) is not None
    def find_by_stable_key(self, field, value):
        matches = [row for row in self.rows.values() if row.get(field) == value]
        return dict(matches[0]) if matches else None


class FakeAttachments:
    def __init__(self):
        self.by_resume = {}
        self.calls = []
        self.fail_replace = None
    def list(self, identifier):
        return [dict(row) for row in self.by_resume.get(identifier, [])]
    def replace(self, identifier, value=None, remove=False):
        self.calls.append(("replace", identifier, value, remove))
        if self.fail_replace:
            raise self.fail_replace
        result = [] if remove else [{"id": 100 + identifier, "filename": value["name"]}]
        self.by_resume[identifier] = result
        return result
    def restore(self, identifier, snapshot):
        self.calls.append(("restore", identifier, snapshot))
        self.by_resume[identifier] = list(snapshot)
    def read(self, identifier):
        return b"%PDF", "application/pdf", "测试.pdf"
    def delete_if_unreferenced(self, identifier):
        self.calls.append(("delete_if_unreferenced", identifier)); return True


class RemoteResumeServiceTests(unittest.TestCase):
    def service(self, resumes=None, attachments=None):
        from features.nocobase_sync.remote_resume_service import RemoteResumeService
        return RemoteResumeService(
            resumes or FakeResumes(), attachments or FakeAttachments(), SCHEMA,
            now=lambda: datetime(2026, 9, 30, 8, 30), source_factory=lambda: "SRC-TOKEN",
        )

    def test_create_validates_then_generates_keys_hash_and_attachment(self):
        resumes, attachments = FakeResumes(), FakeAttachments()
        service = self.service(resumes, attachments)
        identifier = service.create({
            "name": "伪造名称", "status": "已入库", "archive_no": "FORGED",
            "source_id": "FORGED", "recognition_result": "secret", "linked_candidate": 99,
            "recruitment_type": "社会招聘", "channel": "智联招聘",
            "position": "机械工程师", "_resume_upload": upload(name="真实.pdf"),
        })
        row = resumes.rows[identifier]
        self.assertEqual(row["archive_no"], "0120260930001")
        self.assertEqual(row["source_id"], "SRC-TOKEN")
        self.assertEqual(row["status"], "待识别")
        self.assertEqual(row["name"], "真实.pdf")
        self.assertEqual(len(row["file_hash"]), 64)
        self.assertNotIn("recognition_result", row)
        self.assertNotIn("linked_candidate", row)
        self.assertEqual(attachments.calls[0][0:2], ("replace", identifier))

    def test_duplicate_hash_and_invalid_public_fields_never_create(self):
        resumes = FakeResumes()
        service = self.service(resumes, FakeAttachments())
        service.create({"recruitment_type": "校园招聘", "channel": "校园平台",
                        "_resume_upload": upload()})
        with self.assertRaisesRegex(ValueError, "已存在"):
            service.create({"recruitment_type": "校园招聘", "channel": "校园平台",
                            "_resume_upload": upload()})
        self.assertEqual(len([call for call in resumes.calls if call[0] == "create"]), 1)

        public = FakeResumes()
        created = self.service(public, FakeAttachments()).create_public({
            "created_by": "伪造管理员", "status": "已入库", "linked_candidate": 99,
            "recruitment_type": "校园招聘", "channel": "校园线下",
            "_resume_upload": upload(name="公开.pdf"),
        })
        self.assertEqual(public.rows[created]["created_by"], "公开投递")
        self.assertEqual(public.rows[created]["status"], "待识别")

    def test_attachment_failure_deletes_created_main_record(self):
        resumes, attachments = FakeResumes(), FakeAttachments()
        attachments.fail_replace = NocoBaseError("remote", 500, "upload")
        with self.assertRaises(NocoBaseError):
            self.service(resumes, attachments).create({
                "recruitment_type": "校园招聘", "channel": "校园平台",
                "_resume_upload": upload(),
            })
        self.assertEqual(resumes.rows, {})
        self.assertEqual(resumes.calls[-1], ("delete", 1))

    def test_ambiguous_create_uses_source_key_and_cleans_up_without_second_create(self):
        resumes = FakeResumes()
        resumes.create_error = NocoBaseError("network", None, "Resume_Collection:create")
        with self.assertRaises(NocoBaseError):
            self.service(resumes, FakeAttachments()).create({
                "recruitment_type": "校园招聘", "channel": "校园平台",
                "_resume_upload": upload(),
            })
        self.assertEqual([call[0] for call in resumes.calls], ["create", "delete"])
        self.assertEqual(resumes.rows, {})

    def test_update_restores_main_and_attachment_snapshot_after_failure(self):
        resumes, attachments = FakeResumes(), FakeAttachments()
        resumes.rows[1] = {
            "id": 1, "name": "旧.pdf", "status": "待识别", "archive_no": "A1",
            "source_id": "S1", "file_hash": "old", "recruitment_type": "校园招聘",
            "channel": "校园平台", "position": "机械工程师", "created_by": "管理员",
        }
        attachments.by_resume[1] = [{"id": 8, "filename": "旧.pdf"}]
        attachments.fail_replace = NocoBaseError("remote", 500, "set")
        with self.assertRaises(NocoBaseError):
            self.service(resumes, attachments).update(1, {"_resume_upload": upload(name="新.pdf")})
        self.assertEqual(resumes.rows[1]["name"], "旧.pdf")
        self.assertIn(("restore", 1, [{"id": 8, "filename": "旧.pdf"}]), attachments.calls)

    def test_read_attachment_resolves_the_resume_relation_before_download(self):
        resumes, attachments = FakeResumes(), FakeAttachments()
        resumes.rows[7] = {"id": 7, "status": "待识别"}
        attachments.by_resume[7] = [{"id": 81, "filename": "候选人.pdf"}]
        reads = []

        def read_attachment(identifier):
            reads.append(identifier)
            return b"%PDF", "application/pdf", "候选人.pdf"

        attachments.read = read_attachment
        result = self.service(resumes, attachments).read_attachment(7)
        self.assertEqual(result[2], "候选人.pdf")
        self.assertEqual(reads, [81])

    def test_batch_create_validates_every_file_then_compensates_partial_failure(self):
        from features.nocobase_sync.remote_resume_service import RemoteResumeService

        resumes = FakeResumes()
        attachments = FakeAttachments()
        sources = iter(("SRC-1", "SRC-2", "SRC-3"))
        service = RemoteResumeService(
            resumes, attachments, SCHEMA,
            now=lambda: datetime(2026, 9, 30, 8, 30), source_factory=lambda: next(sources),
        )
        duplicate = {"recruitment_type": "校园招聘", "channel": "校园平台",
                     "_resume_upload": upload(name="一.pdf")}
        with self.assertRaisesRegex(ValueError, "重复"):
            service.create_many([duplicate, {**duplicate, "_resume_upload": upload(name="二.pdf")}])
        self.assertEqual(resumes.rows, {})

        original_replace = attachments.replace
        def fail_second(identifier, value=None, remove=False):
            if identifier == 2:
                raise NocoBaseError("remote", 500, "batch upload")
            return original_replace(identifier, value, remove)
        attachments.replace = fail_second
        with self.assertRaises(NocoBaseError):
            service.create_many([
                {"recruitment_type": "校园招聘", "channel": "校园平台",
                 "_resume_upload": upload(content=b"%PDF-1.4\none", name="一.pdf")},
                {"recruitment_type": "校园招聘", "channel": "校园平台",
                 "_resume_upload": upload(content=b"%PDF-1.4\ntwo", name="二.pdf")},
            ])
        self.assertEqual(resumes.rows, {})


if __name__ == "__main__":
    unittest.main()
