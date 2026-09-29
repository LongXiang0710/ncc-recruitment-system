"""Tests for the NocoBase-backed talent-pool repository."""

import unittest

from features.nocobase_sync.candidate_repository import CandidateRepository
from features.nocobase_sync.client import NocoBaseError


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, action, **kwargs):
        self.calls.append((action, kwargs))
        return self.responses.pop(0)


class CandidateRepositoryTests(unittest.TestCase):
    def test_list_maps_records_and_uses_pagination_without_empty_filter(self):
        client = FakeClient([[{"id": 1, "Number": "A1", "name": "张三"}]])
        rows = CandidateRepository(client).list(page=2, page_size=50)
        self.assertEqual(rows, [{"id": 1, "archive_no": "A1", "name": "张三"}])
        self.assertEqual(client.calls, [("campus_talent_pool:list", {
            "params": {"page": 2, "pageSize": 50, "sort": "-createdAt"}
        })])

    def test_search_builds_archive_or_name_filter(self):
        client = FakeClient([[]])
        CandidateRepository(client).list(query="  A-001  ")
        self.assertEqual(client.calls[0][1]["params"]["filter"], {
            "$or": [{"Number": {"$includes": "A-001"}}, {"name": {"$includes": "A-001"}}]
        })

    def test_get_maps_record_and_preserves_missing_record(self):
        client = FakeClient([{"id": 2, "name": "李四"}, None])
        repository = CandidateRepository(client)
        self.assertEqual(repository.get(2), {"id": 2, "name": "李四"})
        self.assertIsNone(repository.get(3))
        self.assertEqual(client.calls[0], ("campus_talent_pool:get", {"params": {"filterByTk": 2}}))

    def test_create_maps_body_and_returns_remote_id(self):
        client = FakeClient([{"id": 9, "name": "王五"}])
        identifier = CandidateRepository(client).create({"name": "王五", "archive_no": "A9", "notes": "drop"})
        self.assertEqual(identifier, 9)
        self.assertEqual(client.calls, [("campus_talent_pool:create", {
            "method": "POST", "body": {"name": "王五", "Number": "A9"}
        })])

    def test_create_rejects_response_without_integer_id(self):
        with self.assertRaises(NocoBaseError) as raised:
            CandidateRepository(FakeClient([{"name": "bad"}])).create({"name": "bad"})
        self.assertEqual(raised.exception.kind, "protocol")

    def test_update_and_delete_use_only_filter_by_primary_key(self):
        client = FakeClient([[{"id": 7}], 1, 0])
        repository = CandidateRepository(client)
        repository.update(7, {"name": "已修改", "unknown": "drop"})
        self.assertTrue(repository.delete(7))
        self.assertFalse(repository.delete(8))
        self.assertEqual(client.calls, [
            ("campus_talent_pool:update", {"method": "POST", "params": {"filterByTk": 7},
                                            "body": {"name": "已修改"}}),
            ("campus_talent_pool:destroy", {"method": "POST", "params": {"filterByTk": 7}}),
            ("campus_talent_pool:destroy", {"method": "POST", "params": {"filterByTk": 8}}),
        ])


if __name__ == "__main__":
    unittest.main()
