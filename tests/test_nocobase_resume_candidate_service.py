"""Cross-aggregate import and delete rules for remote resumes and candidates."""

import copy
import json
import unittest


class FakeResumeRepository:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def find_by_stable_key(self, field, value):
        matches = [row for row in self.rows.values() if row.get(field) == value]
        return copy.deepcopy(matches[-1]) if matches else None

    def find_by_linked_candidate(self, candidate_id):
        return [copy.deepcopy(row) for row in self.rows.values()
                if row.get("linked_candidate") == candidate_id]

    def update(self, identifier, values):
        self.calls.append(("update", identifier, copy.deepcopy(values)))
        self.rows[identifier].update(values)

    def delete(self, identifier):
        self.calls.append(("delete", identifier))
        return self.rows.pop(identifier, None) is not None


class FakeResumeAttachments:
    def __init__(self):
        self.rows = {1: [{"id": 81, "filename": "一.pdf"}], 2: [{"id": 82, "filename": "二.pdf"}]}
        self.calls = []

    def list(self, identifier):
        return copy.deepcopy(self.rows.get(identifier, []))

    def delete_if_unreferenced(self, identifier):
        self.calls.append(("cleanup", identifier))
        return True


class FakeResumes:
    SNAPSHOT_FIELDS = ("updated_at", "status", "resume", "source_id", "file_hash",
                       "archive_no", "linked_candidate")

    def __init__(self, rows):
        self.resumes = FakeResumeRepository(rows)
        self.attachments = FakeResumeAttachments()
        self.fail_link = False
        self.fail_restore = False

    def get(self, identifier):
        row = self.resumes.rows.get(identifier)
        if row is None:
            return None
        result = copy.deepcopy(row)
        files = self.attachments.list(identifier)
        result["resume"] = str(files[0]["id"]) if files else ""
        return result

    def recognition_snapshot(self, row):
        return {key: row.get(key) for key in self.SNAPSHOT_FIELDS}

    def link_candidate(self, identifier, snapshot, candidate_id):
        if self.fail_link:
            raise RuntimeError("link failed")
        current = self.get(identifier)
        if self.recognition_snapshot(current) != snapshot:
            return False
        self.resumes.update(identifier, {"linked_candidate": candidate_id, "status": "已入库"})
        return True

    def restore_link(self, identifier, snapshot):
        if self.fail_restore:
            raise RuntimeError("restore failed")
        self.resumes.update(identifier, {
            "linked_candidate": snapshot.get("linked_candidate"), "status": snapshot.get("status"),
        })

    def delete_preview(self, ids):
        return {"details": [{"entity": "resume_documents", "id": identifier,
                             "name": self.resumes.rows[identifier]["name"]} for identifier in ids]}

    def delete_one(self, identifier):
        attachments = self.attachments.list(identifier)
        if not self.resumes.delete(identifier):
            return False
        for attachment in attachments:
            self.attachments.delete_if_unreferenced(attachment["id"])
        return True


class FakeRecognition:
    def result(self, identifier):
        row = self.rows.get(identifier)
        return copy.deepcopy(row) if row else None

    def __init__(self, rows):
        self.rows = rows


class FakeCandidates:
    def __init__(self):
        self.rows = {}
        self.calls = []
        self.next_id = 10
        self.rollback_fails = False
        self.delete_fails = False

    def find_by_phone(self, phone):
        return next((copy.deepcopy(row) for row in self.rows.values()
                     if row.get("phone") == phone), None)

    def create_from_resume(self, payload, attachment_snapshot):
        identifier = self.next_id
        self.next_id += 1
        self.rows[identifier] = {"id": identifier, **copy.deepcopy(payload),
                                 "attachments": copy.deepcopy(attachment_snapshot)}
        self.calls.append(("create", identifier))
        return identifier

    def rollback_created(self, identifier):
        self.calls.append(("rollback", identifier))
        if self.rollback_fails:
            raise RuntimeError("rollback failed")
        self.rows.pop(identifier, None)

    def get(self, identifier):
        return copy.deepcopy(self.rows.get(identifier))

    def delete_preview(self, ids):
        return {"details": [{"entity": "candidates", "id": identifier,
                             "name": self.rows[identifier]["name"]} for identifier in ids]}

    def delete(self, ids, expected):
        self.calls.append(("delete", list(ids)))
        if self.delete_fails:
            raise RuntimeError("delete failed")
        for identifier in ids:
            self.rows.pop(identifier, None)
        return len(ids)


def resume(identifier=1, linked=None):
    return {
        "id": identifier, "name": f"简历{identifier}",
        "status": "已入库" if linked else "已识别",
        "updated_at": "v1", "source_id": f"SRC-{identifier}",
        "file_hash": f"HASH-{identifier}", "archive_no": f"NO-{identifier}",
        "linked_candidate": linked, "recruitment_type": "社会招聘",
    }


def recognized(phone="13900000001"):
    return {
        "name": "张三", "phone": phone, "email": "zhang@example.com",
        "recruitment_type": "社会招聘", "channel": "智联招聘",
        "position": "机械工程师", "education_experiences": [{
            "education": "本科", "school_name": "常州大学", "major": "机械工程",
            "enrollment": "2018-09", "graduation": "2022-06",
        }],
    }


class ResumeCandidateServiceTests(unittest.TestCase):
    @staticmethod
    def build(rows=None, results=None):
        from features.nocobase_sync.resume_candidate_service import ResumeCandidateService
        resumes = FakeResumes(rows or {1: resume()})
        candidates = FakeCandidates()
        recognition = FakeRecognition(results or {1: recognized()})
        return ResumeCandidateService(resumes, recognition, candidates), resumes, candidates

    def test_import_creates_candidate_with_same_attachment_then_links_idempotently(self):
        service, resumes, candidates = self.build()
        result = service.import_candidate(1)
        self.assertEqual((result.candidate_id, result.already_imported), (10, False))
        self.assertEqual(candidates.rows[10]["archive_no"], "NO-1")
        self.assertEqual(candidates.rows[10]["attachments"][0]["id"], 81)
        self.assertEqual(resumes.resumes.rows[1]["linked_candidate"], 10)
        self.assertEqual(resumes.resumes.rows[1]["status"], "已入库")
        again = service.import_candidate(1)
        self.assertEqual((again.candidate_id, again.already_imported), (10, True))
        self.assertEqual([call[0] for call in candidates.calls].count("create"), 1)

    def test_import_rechecks_stable_keys_and_rolls_back_candidate_when_link_fails(self):
        service, resumes, candidates = self.build()
        resumes.fail_link = True
        with self.assertRaisesRegex(RuntimeError, "link failed"):
            service.import_candidate(1)
        self.assertEqual(candidates.rows, {})
        self.assertIn(("rollback", 10), candidates.calls)

        service, resumes, candidates = self.build()
        resumes.resumes.rows[3] = {**resume(3), "archive_no": "NO-1"}
        with self.assertRaisesRegex(ValueError, "档案编号"):
            service.import_candidate(1)
        self.assertEqual(candidates.calls, [])

    def test_failed_compensation_exposes_only_diagnostic_id(self):
        from features.nocobase_sync.resume_candidate_service import ResumeCandidateConsistencyError
        service, resumes, candidates = self.build()
        resumes.fail_link = True
        candidates.rollback_fails = True
        with self.assertRaises(ResumeCandidateConsistencyError) as raised:
            service.import_candidate(1)
        self.assertTrue(raised.exception.diagnostic_id)
        self.assertNotIn("张三", str(raised.exception))
        self.assertNotIn("13900000001", str(raised.exception))

    def test_resume_delete_blocks_shared_candidate_before_mutation(self):
        rows = {1: resume(1, 10), 2: resume(2, 10)}
        service, resumes, candidates = self.build(rows, {1: recognized(), 2: recognized()})
        candidates.rows[10] = {"id": 10, "name": "张三", "phone": "13900000001"}
        with self.assertRaisesRegex(ValueError, "多份简历"):
            service.delete_resumes([1])
        self.assertEqual(candidates.calls, [])
        self.assertEqual(resumes.resumes.calls, [])

    def test_resume_cascade_and_direct_candidate_delete_follow_opposite_link_rules(self):
        service, resumes, candidates = self.build({1: resume(1, 10)}, {1: recognized()})
        candidates.rows[10] = {"id": 10, "name": "张三", "phone": "13900000001"}
        self.assertEqual(service.delete_resumes([1]), 1)
        self.assertEqual(candidates.calls[0], ("delete", [10]))
        self.assertEqual(resumes.resumes.calls[-1], ("delete", 1))
        self.assertIn(("cleanup", 81), resumes.attachments.calls)

        service, resumes, candidates = self.build({1: resume(1, 10)}, {1: recognized()})
        candidates.rows[10] = {"id": 10, "name": "张三", "phone": "13900000001"}
        self.assertEqual(service.delete_candidates([10]), 1)
        self.assertIn(1, resumes.resumes.rows)
        self.assertIsNone(resumes.resumes.rows[1]["linked_candidate"])
        self.assertEqual(resumes.resumes.rows[1]["status"], "已识别")

    def test_candidate_delete_failure_restores_resume_links(self):
        service, resumes, candidates = self.build({1: resume(1, 10)}, {1: recognized()})
        candidates.rows[10] = {"id": 10, "name": "张三", "phone": "13900000001"}
        candidates.delete_fails = True
        with self.assertRaisesRegex(RuntimeError, "delete failed"):
            service.delete_candidates([10])
        self.assertEqual(resumes.resumes.rows[1]["linked_candidate"], 10)
        self.assertEqual(resumes.resumes.rows[1]["status"], "已入库")


if __name__ == "__main__":
    unittest.main()
