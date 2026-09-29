"""Tests for NocoBase talent-pool one-to-many relation persistence."""

import unittest
from types import MappingProxyType

from features.nocobase_sync.client import NocoBaseError
from features.nocobase_sync.preflight import RelationFieldMap


FIELD_MAP = RelationFieldMap(
    education=MappingProxyType({
        "education": "degree", "school_name": "school", "major": "major_remote",
        "enrollment": "started", "graduation": "finished",
    }),
    work=MappingProxyType({
        "organization": "company", "position": "job", "start_date": "started",
        "end_date": "finished", "description": "details",
    }),
    project=MappingProxyType({
        "project_name": "project", "role": "role_remote", "start_date": "started",
        "end_date": "finished", "description": "details",
    }),
)


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, action, **kwargs):
        self.calls.append((action, kwargs))
        if not self.responses:
            raise AssertionError(f"unexpected call: {action}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class RelationRepositoryTests(unittest.TestCase):
    def repository(self, responses):
        from features.nocobase_sync.relation_repository import RelationRepository
        client = FakeClient(responses)
        return RelationRepository(client, FIELD_MAP), client

    def test_list_maps_remote_fields_dates_and_preserves_api_order(self):
        repository, client = self.repository([[
            {"id": 9, "company": "乙公司", "job": "工程师", "started": "2022-03-01", "finished": None, "details": "二"},
            {"id": 7, "company": "甲公司", "job": "助理", "started": "2020-01-15T00:00:00Z", "finished": "2021-12-01", "details": "一"},
        ]])
        self.assertEqual(repository.list(3, "work"), [
            {"organization": "乙公司", "position": "工程师", "start_date": "2022-03", "end_date": "", "description": "二"},
            {"organization": "甲公司", "position": "助理", "start_date": "2020-01", "end_date": "2021-12", "description": "一"},
        ])
        self.assertEqual(client.calls, [
            ("campus_talent_pool/3/Work_experience:list", {"params": {"pageSize": 10}}),
        ])

    def test_sync_updates_by_position_creates_extra_and_deletes_surplus(self):
        existing = [{"id": 11, "company": "旧一"}, {"id": 12, "company": "旧二"}]
        rows = [
            {"organization": "新一", "position": "岗位", "start_date": "2024-02", "end_date": "", "description": "说明"},
            {"organization": "新二", "position": "", "start_date": "", "end_date": "", "description": ""},
            {"organization": "新增", "position": "", "start_date": "2025-01", "end_date": "2025-06", "description": ""},
        ]
        repository, client = self.repository([existing, {}, {}, {"id": 13}])
        repository.sync(5, "work", rows)
        self.assertEqual(client.calls, [
            ("campus_talent_pool/5/Work_experience:list", {"params": {"pageSize": 10}}),
            ("campus_talent_pool/5/Work_experience:update", {
                "method": "POST", "params": {"filterByTk": 11},
                "body": {"company": "新一", "job": "岗位", "started": "2024-02-01", "finished": None, "details": "说明"},
            }),
            ("campus_talent_pool/5/Work_experience:update", {
                "method": "POST", "params": {"filterByTk": 12},
                "body": {"company": "新二", "job": "", "started": None, "finished": None, "details": ""},
            }),
            ("campus_talent_pool/5/Work_experience:create", {
                "method": "POST",
                "body": {"company": "新增", "job": "", "started": "2025-01-01", "finished": "2025-06-01", "details": ""},
            }),
        ])

        repository2, client2 = self.repository([existing, {}, 1])
        repository2.sync(5, "work", rows[:1])
        self.assertEqual(client2.calls[-1], (
            "campus_talent_pool/5/Work_experience:destroy",
            {"method": "POST", "params": {"filterByTk": 12}},
        ))

    def test_sync_empty_projects_clears_existing_records(self):
        repository, client = self.repository([[{"id": 21}, {"id": 22}], 1, 1])
        repository.sync(8, "project", [])
        self.assertEqual([call[0] for call in client.calls], [
            "campus_talent_pool/8/Project_Experience:list",
            "campus_talent_pool/8/Project_Experience:destroy",
            "campus_talent_pool/8/Project_Experience:destroy",
        ])

    def test_snapshot_and_restore_cover_all_relations(self):
        education = [{"id": 1, "degree": "本科", "school": "大学", "major_remote": "工程", "started": "2018-09-01", "finished": "2022-06-01"}]
        repository, client = self.repository([education, [], []])
        snapshot = repository.snapshot(4)
        self.assertEqual(snapshot["education"][0]["school_name"], "大学")
        self.assertEqual(snapshot["work"], [])
        self.assertEqual(snapshot["project"], [])
        self.assertEqual(len(client.calls), 3)

        restore, restore_client = self.repository([[], {"id": 31}, [], []])
        restore.restore(4, snapshot)
        self.assertEqual([call[0] for call in restore_client.calls], [
            "campus_talent_pool/4/Education_Background:list",
            "campus_talent_pool/4/Education_Background:create",
            "campus_talent_pool/4/Work_experience:list",
            "campus_talent_pool/4/Project_Experience:list",
        ])

    def test_rejects_invalid_relation_candidate_rows_and_more_than_ten(self):
        repository, client = self.repository([])
        invalid = (
            (0, "work", []), (1, "unknown", []), (1, "work", {}),
            (1, "work", [{}] * 11), (1, "work", ["bad"]),
        )
        for candidate_id, relation, rows in invalid:
            with self.subTest(candidate_id=candidate_id, relation=relation, rows=rows), self.assertRaises(ValueError):
                repository.sync(candidate_id, relation, rows)
        self.assertEqual(client.calls, [])

    def test_rejects_invalid_list_and_create_response_shapes(self):
        for response in ({}, [{"company": "missing id"}], [{"id": True}]):
            repository, _client = self.repository([response])
            with self.subTest(response=response), self.assertRaises(NocoBaseError) as raised:
                repository.list(1, "work")
            self.assertEqual(raised.exception.kind, "protocol")

        repository, _client = self.repository([[], {"name": "missing id"}])
        with self.assertRaises(NocoBaseError) as raised:
            repository.sync(1, "education", [{
                "education": "本科", "school_name": "大学", "major": "工程",
                "enrollment": "2018-09", "graduation": "2022-06",
            }])
        self.assertEqual(raised.exception.kind, "protocol")


if __name__ == "__main__":
    unittest.main()
