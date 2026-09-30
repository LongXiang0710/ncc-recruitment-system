"""Aggregate behavior tests for the remote NocoBase candidate service."""

import copy
import base64
import json
import unittest
from pathlib import Path

from features.nocobase_sync.client import NocoBaseError


SCHEMA = json.loads((Path(__file__).parents[1] / "features" / "candidates" / "schema.json").read_text(encoding="utf-8"))


def candidate(phone="13900000001", recruitment_type="社会招聘"):
    return {
        "name": "张三", "phone": phone, "email": "zhang@example.com",
        "recruitment_type": recruitment_type, "channel": "智联招聘",
        "position": "机械工程师", "age": "26", "birthdate": "2000-03",
        "education_experiences": [{
            "education": "本科", "school_name": "常州大学", "major": "机械工程",
            "enrollment": "2018-09", "graduation": "2022-06",
        }],
        "work_experiences": [{
            "organization": "甲公司", "position": "工程师", "start_date": "2022-07",
            "end_date": "", "description": "设备管理",
        }],
        "project_experiences": [{
            "project_name": "项目甲", "role": "成员", "start_date": "2023-01",
            "end_date": "2023-06", "description": "实施",
        }],
    }


class FakeCandidates:
    def __init__(self):
        self.records = {}
        self.calls = []
        self.next_id = 1
        self.fail_create = None
        self.ambiguous_create = False
        self.fail_update = None
        self.fail_delete = None

    def list_page(self, page=1, page_size=20, query=""):
        self.calls.append(("list_page", page, page_size, query))
        rows = [copy.deepcopy(row) for row in self.records.values()]
        return {"rows": rows, "count": len(rows)}

    def get(self, identifier):
        self.calls.append(("get", identifier))
        row = self.records.get(identifier)
        return copy.deepcopy(row) if row else None

    def find_by_phone(self, phone):
        self.calls.append(("find_by_phone", phone))
        return next((copy.deepcopy(row) for row in self.records.values() if row.get("phone") == phone), None)

    def create(self, values):
        self.calls.append(("create", copy.deepcopy(values)))
        if self.ambiguous_create:
            identifier = self.next_id
            self.next_id += 1
            self.records[identifier] = dict(values, id=identifier)
            raise NocoBaseError("network", None, "create")
        if self.fail_create:
            raise self.fail_create
        identifier = self.next_id
        self.next_id += 1
        self.records[identifier] = dict(values, id=identifier)
        return identifier

    def update(self, identifier, values):
        self.calls.append(("update", identifier, copy.deepcopy(values)))
        if self.fail_update:
            failure, self.fail_update = self.fail_update, None
            raise failure
        self.records[identifier].update(values)

    def delete(self, identifier):
        self.calls.append(("delete", identifier))
        if self.fail_delete:
            raise self.fail_delete
        return self.records.pop(identifier, None) is not None


class FakeRelations:
    def __init__(self):
        self.rows = {}
        self.calls = []
        self.fail_relation = None
        self.fail_restore = False

    def list(self, identifier, relation):
        self.calls.append(("list", identifier, relation))
        return copy.deepcopy(self.rows.get(identifier, {}).get(relation, []))

    def sync(self, identifier, relation, rows):
        self.calls.append(("sync", identifier, relation, copy.deepcopy(rows)))
        if self.fail_relation == relation:
            self.fail_relation = None
            raise NocoBaseError("remote", 500, relation)
        self.rows.setdefault(identifier, {})[relation] = copy.deepcopy(rows)

    def snapshot(self, identifier):
        self.calls.append(("snapshot", identifier))
        current = self.rows.get(identifier, {})
        return {name: copy.deepcopy(current.get(name, [])) for name in ("education", "work", "project")}

    def restore(self, identifier, snapshot):
        self.calls.append(("restore", identifier, copy.deepcopy(snapshot)))
        if self.fail_restore:
            raise NocoBaseError("remote", 500, "restore")
        self.rows[identifier] = copy.deepcopy(snapshot)


class FakeAttachments:
    def __init__(self):
        self.rows = {}
        self.calls = []

    def list(self, identifier):
        self.calls.append(("list", identifier))
        return copy.deepcopy(self.rows.get(identifier, []))

    def replace(self, identifier, upload=None, remove=False):
        self.calls.append(("replace", identifier, copy.deepcopy(upload), remove))
        if remove:
            self.rows[identifier] = []
        elif upload:
            self.rows[identifier] = [{"id": 90, "filename": upload["name"]}]
        return copy.deepcopy(self.rows.get(identifier, []))

    def restore(self, identifier, snapshot):
        self.calls.append(("restore", identifier, copy.deepcopy(snapshot)))
        self.rows[identifier] = copy.deepcopy(snapshot)

    def delete_if_unreferenced(self, attachment_id):
        self.calls.append(("delete_if_unreferenced", attachment_id))
        return True


class RemoteCandidateServiceTests(unittest.TestCase):
    def service(self):
        from features.nocobase_sync.remote_candidate_service import RemoteCandidateService
        candidates, relations, attachments = FakeCandidates(), FakeRelations(), FakeAttachments()
        return RemoteCandidateService(candidates, relations, attachments, SCHEMA), candidates, relations, attachments

    def seed(self, candidates, relations, attachments, identifier=1, kind="社会招聘"):
        candidates.records[identifier] = {
            "id": identifier, "name": "张三", "phone": "13900000001",
            "recruitment_type": kind, "age": "26",
        }
        candidates.next_id = max(candidates.next_id, identifier + 1)
        relations.rows[identifier] = {
            "education": candidate()["education_experiences"],
            "work": candidate()["work_experiences"],
            "project": candidate()["project_experiences"] if kind == "社会招聘" else [],
        }
        attachments.rows[identifier] = [{"id": 70, "filename": "原简历.pdf"}]

    def test_list_and_get_aggregate_relations_attachment_and_total_count(self):
        service, candidates, relations, attachments = self.service()
        self.seed(candidates, relations, attachments)
        result = service.list(page=1, page_size=20, query="张")
        self.assertEqual(result["count"], 1)
        row = result["rows"][0]
        self.assertEqual(row["school_name"], "常州大学")
        self.assertEqual(row["education_experiences"][0]["major"], "机械工程")
        self.assertEqual(row["resume"], "70")
        self.assertEqual(row["resume_name"], "原简历.pdf")
        self.assertEqual(service.get(1)["project_experiences"][0]["project_name"], "项目甲")
        self.assertIsNone(service.get(99))

    def test_validation_and_phone_duplicate_fail_before_any_mutation(self):
        service, candidates, relations, attachments = self.service()
        self.seed(candidates, relations, attachments)
        baseline = len(candidates.calls)
        with self.assertRaises(ValueError):
            service.create(candidate(phone="13900000001"))
        self.assertFalse(any(call[0] == "create" for call in candidates.calls[baseline:]))
        with self.assertRaises(ValueError):
            service.create(dict(candidate(phone="13900000002"), email="bad-email"))
        self.assertFalse(any(call[0] == "create" for call in candidates.calls[baseline:]))
        self.assertEqual(relations.calls, [])
        self.assertEqual(attachments.calls, [])

    def test_campus_create_writes_no_projects_and_social_create_writes_all_relations(self):
        service, candidates, relations, attachments = self.service()
        campus = candidate(phone="13900000002", recruitment_type="校园招聘")
        campus["channel"] = "校园平台"
        campus_id = service.create(campus)
        self.assertEqual(relations.rows[campus_id]["project"], [])
        social_payload = candidate(phone="13900000003")
        social_payload["_resume_upload"] = {
            "name": "简历.pdf",
            "content": base64.b64encode(b"%PDF-1.4\nresume").decode("ascii"),
        }
        social_id = service.create(social_payload)
        self.assertEqual(relations.rows[social_id]["work"][0]["organization"], "甲公司")
        self.assertEqual(relations.rows[social_id]["project"][0]["project_name"], "项目甲")
        self.assertEqual(attachments.calls[-1][0], "replace")

    def test_parent_create_is_compensated_when_relation_fails(self):
        service, candidates, relations, _attachments = self.service()
        relations.fail_relation = "work"
        with self.assertRaises(NocoBaseError):
            service.create(candidate())
        self.assertEqual(candidates.records, {})
        self.assertIn(("delete", 1), candidates.calls)

    def test_unknown_create_result_is_queried_by_phone_and_compensated(self):
        service, candidates, _relations, _attachments = self.service()
        candidates.ambiguous_create = True
        with self.assertRaises(NocoBaseError):
            service.create(candidate())
        self.assertEqual(candidates.records, {})
        self.assertIn(("find_by_phone", "13900000001"), candidates.calls)
        self.assertIn(("delete", 1), candidates.calls)

    def test_create_many_validates_all_then_compensates_prior_creates(self):
        service, candidates, relations, _attachments = self.service()
        invalid = [candidate("13900000002"), dict(candidate("13900000003"), email="bad")]
        with self.assertRaises(ValueError):
            service.create_many(invalid)
        self.assertFalse(any(call[0] == "create" for call in candidates.calls))

        original_sync = relations.sync
        create_count = {"value": 0}
        def fail_second(identifier, relation, rows):
            if relation == "work":
                create_count["value"] += 1
                if create_count["value"] == 2:
                    raise NocoBaseError("remote", 500, "work")
            return original_sync(identifier, relation, rows)
        relations.sync = fail_second
        with self.assertRaises(NocoBaseError):
            service.create_many([candidate("13900000002"), candidate("13900000003")])
        self.assertEqual(candidates.records, {})

    def test_update_failure_restores_main_relations_and_attachment_snapshot(self):
        service, candidates, relations, attachments = self.service()
        self.seed(candidates, relations, attachments)
        before_main = copy.deepcopy(candidates.records[1])
        before_relations = copy.deepcopy(relations.rows[1])
        relations.fail_relation = "project"
        payload = candidate()
        payload["name"] = "已修改"
        with self.assertRaises(NocoBaseError):
            service.update(1, payload)
        for key, value in before_main.items():
            self.assertEqual(candidates.records[1][key], value)
        self.assertEqual(relations.rows[1], before_relations)
        self.assertEqual(attachments.rows[1][0]["id"], 70)

    def test_restore_failure_raises_safe_consistency_error(self):
        from features.nocobase_sync.remote_candidate_service import RemoteCandidateConsistencyError

        service, candidates, relations, attachments = self.service()
        self.seed(candidates, relations, attachments)
        relations.fail_relation = "project"
        relations.fail_restore = True
        with self.assertRaises(RemoteCandidateConsistencyError) as raised:
            service.update(1, dict(candidate(), name="已修改"))
        self.assertTrue(raised.exception.diagnostic_id)
        self.assertNotIn("张三", str(raised.exception))
        self.assertNotIn("13900000001", str(raised.exception))

    def test_delete_preview_rejects_stale_confirmation(self):
        service, candidates, relations, attachments = self.service()
        self.seed(candidates, relations, attachments)
        preview = service.delete_preview([1])
        self.assertEqual(preview["details"][0]["name"], "张三")
        with self.assertRaises(ValueError):
            service.delete([1], [{"entity": "candidates", "id": 1, "name": "旧姓名"}])
        self.assertIn(1, candidates.records)
        self.assertEqual(service.delete([1], preview["details"]), 1)
        self.assertNotIn(1, candidates.records)

    def test_find_by_phone_and_create_from_resume_reuse_the_existing_attachment(self):
        service, candidates, relations, attachments = self.service()
        self.assertIsNone(service.find_by_phone("13900000009"))
        identifier = service.create_from_resume(
            candidate("13900000009"), [{"id": 81, "filename": "来源.pdf"}],
        )
        self.assertEqual(service.find_by_phone("13900000009")["id"], identifier)
        self.assertEqual(attachments.rows[identifier][0]["id"], 81)
        service.rollback_created(identifier)
        self.assertNotIn(identifier, candidates.records)


if __name__ == "__main__":
    unittest.main()
