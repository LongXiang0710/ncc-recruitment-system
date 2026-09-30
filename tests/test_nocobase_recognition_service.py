"""Recognition state-machine tests for NocoBase-backed resumes."""

import json
import threading
import unittest


class FakeRemoteResumes:
    SNAPSHOT_FIELDS = (
        "updated_at", "status", "resume", "source_id", "file_hash",
        "recruitment_type", "channel", "channel_detail", "position", "position_detail",
    )

    def __init__(self, status="待识别"):
        self.row = {
            "id": 7, "updated_at": "v1", "status": status, "resume": "81",
            "source_id": "SRC-7", "file_hash": "hash-7", "name": "候选人.pdf",
            "recruitment_type": "社会招聘", "channel": "智联招聘",
            "channel_detail": "", "position": "机械工程师", "position_detail": "",
            "recognition_result": json.dumps({"name": "上次结果"}, ensure_ascii=False),
        }
        self.reads = []
        self.updates = []

    def get(self, identifier):
        return dict(self.row) if identifier == self.row["id"] else None

    def read_attachment(self, identifier):
        self.reads.append(identifier)
        return b"%PDF-1.4\nresume", "application/pdf", "候选人.pdf"

    def recognition_snapshot(self, row):
        return {key: row.get(key) for key in self.SNAPSHOT_FIELDS}

    def update_recognition(self, identifier, snapshot, *, status, result=None):
        if identifier != self.row["id"] or self.recognition_snapshot(self.row) != snapshot:
            return False
        values = {"status": status}
        if result is not None:
            values["recognition_result"] = result
        self.row.update(values)
        self.updates.append(values)
        return True


class RecognitionServiceTests(unittest.TestCase):
    @staticmethod
    def service(remote, recognizer, lock=None):
        from features.nocobase_sync.recognition_service import RecognitionService
        return RecognitionService(remote, recognizer, lock=lock)

    def test_pending_and_failed_resume_are_recognized_and_saved_as_utf8_json(self):
        for status in ("待识别", "失败"):
            with self.subTest(status=status):
                remote = FakeRemoteResumes(status)
                calls = []

                def recognize(content, source_id, metadata, filename):
                    calls.append((content, source_id, metadata["id"], filename))
                    return {"candidate": {"basic": {"name": "张三", "phone": "13900000000"}}}

                result = self.service(remote, recognize).recognize(7)

                self.assertEqual(result["name"], "张三")
                self.assertEqual(remote.reads, [7])
                self.assertEqual(calls[0][1:], ("SRC-7", 7, "候选人.pdf"))
                self.assertEqual(remote.row["status"], "已识别")
                self.assertIn("张三", remote.row["recognition_result"])
                self.assertNotIn("\\u5f20", remote.row["recognition_result"])

    def test_busy_missing_and_invalid_status_are_rejected_before_dify(self):
        calls = []
        lock = threading.Lock()
        lock.acquire()
        try:
            with self.assertRaisesRegex(ValueError, "正在识别"):
                self.service(FakeRemoteResumes(), lambda *args: calls.append(args), lock).recognize(7)
        finally:
            lock.release()
        self.assertEqual(calls, [])

        remote = FakeRemoteResumes("已识别")
        with self.assertRaisesRegex(ValueError, "待识别或失败"):
            self.service(remote, lambda *args: calls.append(args)).recognize(7)
        with self.assertRaisesRegex(ValueError, "不存在"):
            self.service(remote, lambda *args: calls.append(args)).recognize(99)
        self.assertEqual(calls, [])

    def test_dify_or_mapping_failure_sets_failed_but_preserves_last_valid_result(self):
        for recognizer in (
            lambda *args: (_ for _ in ()).throw(ValueError("Dify失败")),
            lambda *args: [],
        ):
            with self.subTest(recognizer=recognizer):
                remote = FakeRemoteResumes()
                previous = remote.row["recognition_result"]
                with self.assertRaises(ValueError):
                    self.service(remote, recognizer).recognize(7)
                self.assertEqual(remote.row["status"], "失败")
                self.assertEqual(remote.row["recognition_result"], previous)
                self.assertEqual(remote.updates, [{"status": "失败"}])

    def test_concurrent_edit_prevents_success_or_failure_overwrite(self):
        for succeeds in (True, False):
            with self.subTest(succeeds=succeeds):
                remote = FakeRemoteResumes()

                def recognize(*args):
                    remote.row["updated_at"] = "v2"
                    if succeeds:
                        return {"name": "并发结果", "phone": "13900000001"}
                    raise ValueError("识别失败")

                with self.assertRaisesRegex(ValueError, "已被修改"):
                    self.service(remote, recognize).recognize(7)
                self.assertEqual(remote.row["status"], "待识别")
                self.assertEqual(remote.updates, [])

    def test_result_parses_saved_object_and_rejects_malformed_json(self):
        remote = FakeRemoteResumes("已识别")
        service = self.service(remote, lambda *args: None)
        self.assertEqual(service.result(7), {"name": "上次结果"})
        remote.row["recognition_result"] = "not-json"
        with self.assertRaisesRegex(ValueError, "损坏"):
            service.result(7)
        remote.row["recognition_result"] = ""
        self.assertIsNone(service.result(7))


if __name__ == "__main__":
    unittest.main()
