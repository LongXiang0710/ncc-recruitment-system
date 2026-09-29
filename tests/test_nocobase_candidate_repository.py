"""Tests for the NocoBase-backed talent-pool repository."""

import unittest

from features.nocobase_sync.candidate_repository import CandidateRepository
from features.nocobase_sync.client import NocoBaseError, NocoBaseResponse


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, action, **kwargs):
        self.calls.append((action, kwargs))
        return self.responses.pop(0)

    def request_envelope(self, action, **kwargs):
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

    def test_list_page_preserves_valid_total_count(self):
        client = FakeClient([NocoBaseResponse([{"id": 1, "name": "张三"}], {"count": 23})])
        result = CandidateRepository(client).list_page(page=2, page_size=10, query="张")
        self.assertEqual(result, {"rows": [{"id": 1, "name": "张三"}], "count": 23})
        self.assertEqual(client.calls[0][0], "campus_talent_pool:list")
        self.assertEqual(client.calls[0][1]["params"]["filter"], {
            "$or": [{"Number": {"$includes": "张"}}, {"name": {"$includes": "张"}}]
        })

    def test_list_page_rejects_missing_or_invalid_count(self):
        for meta in (None, {}, {"count": True}, {"count": -1}):
            with self.subTest(meta=meta), self.assertRaises(NocoBaseError) as raised:
                CandidateRepository(FakeClient([NocoBaseResponse([], meta)])).list_page()
            self.assertEqual(raised.exception.kind, "protocol")

    def test_find_by_phone_uses_exact_filter_and_rejects_multiple_matches(self):
        client = FakeClient([[{"id": 2, "phone": "13900000000", "name": "李四"}], []])
        repository = CandidateRepository(client)
        self.assertEqual(repository.find_by_phone("13900000000"), {
            "id": 2, "phone": "13900000000", "name": "李四",
        })
        self.assertIsNone(repository.find_by_phone("13800000000"))
        self.assertEqual(client.calls[0], ("campus_talent_pool:list", {
            "params": {"pageSize": 2, "filter": {"phone": {"$eq": "13900000000"}}},
        }))
        duplicate = CandidateRepository(FakeClient([[
            {"id": 1, "phone": "13900000000"}, {"id": 2, "phone": "13900000000"},
        ]]))
        with self.assertRaises(NocoBaseError):
            duplicate.find_by_phone("13900000000")


if __name__ == "__main__":
    unittest.main()
