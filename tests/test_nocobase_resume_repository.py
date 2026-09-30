"""Repository tests for Resume_Collection without network access."""

import unittest

from features.nocobase_sync.client import NocoBaseError, NocoBaseResponse


class FakeClient:
    def __init__(self):
        self.calls = []
        self.data = []
        self.meta = {"count": 0}

    def request(self, action, **kwargs):
        self.calls.append((action, kwargs))
        return self.data

    def request_envelope(self, action, **kwargs):
        self.calls.append((action, kwargs))
        return NocoBaseResponse(self.data, self.meta)


class ResumeRepositoryTests(unittest.TestCase):
    def test_page_search_uses_archive_and_name_and_validates_count(self):
        from features.nocobase_sync.resume_repository import ResumeRepository

        client = FakeClient()
        client.data = [{"id": 1, "Number": "A-1", "Processing_Status": "待识别", "name": "甲"}]
        client.meta = {"count": 1}
        result = ResumeRepository(client).list_page(2, 20, " 甲 ")

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["rows"][0]["archive_no"], "A-1")
        self.assertEqual(client.calls[0], ("Resume_Collection:list", {"params": {
            "page": 2, "pageSize": 20, "sort": "-createdAt", "filter": {"$or": [
                {"Number": {"$includes": "甲"}}, {"name": {"$includes": "甲"}},
            ]},
        }}))

    def test_stable_key_lookup_rejects_duplicates_and_unknown_fields(self):
        from features.nocobase_sync.resume_repository import ResumeRepository

        client = FakeClient()
        repository = ResumeRepository(client)
        client.data = [
            {"id": 1, "Number": "A", "Processing_Status": "待识别", "name": "一"},
            {"id": 2, "Number": "A", "Processing_Status": "待识别", "name": "二"},
        ]
        with self.assertRaises(NocoBaseError) as raised:
            repository.find_by_stable_key("archive_no", "A")
        self.assertEqual(raised.exception.kind, "protocol")
        with self.assertRaises(ValueError):
            repository.find_by_stable_key("name", "一")

    def test_linked_candidate_filter_and_crud_contract(self):
        from features.nocobase_sync.resume_repository import ResumeRepository

        client = FakeClient()
        repository = ResumeRepository(client)
        client.data = [{"id": 5, "Number": "A-5", "Processing_Status": "已入库", "name": "五",
                        "linked_candidate": {"id": 33}}]
        self.assertEqual(repository.find_by_linked_candidate(33)[0]["id"], 5)
        self.assertEqual(client.calls[-1], ("Resume_Collection:list", {"params": {
            "pageSize": 100, "filter": {"linked_candidate": {"id": {"$eq": 33}}},
        }}))

        client.data = {"id": 8}
        self.assertEqual(repository.create({"name": "八", "status": "待识别"}), 8)
        repository.update(8, {"status": "失败"})
        client.data = 1
        self.assertTrue(repository.delete(8))
        self.assertEqual([call[0] for call in client.calls[-3:]], [
            "Resume_Collection:create", "Resume_Collection:update", "Resume_Collection:destroy",
        ])


if __name__ == "__main__":
    unittest.main()
