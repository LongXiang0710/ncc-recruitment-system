"""Tests for the explicit talent-pool field boundary."""

import unittest

from features.nocobase_sync.candidate_mapping import from_nocobase, to_nocobase


class CandidateMappingTests(unittest.TestCase):
    def test_campus_candidate_maps_only_confirmed_fields(self):
        local = {
            "archive_no": "0220260929001", "name": "测试人才", "gender": "女",
            "birthdate": "2000-07", "age": "26", "phone": "19000000002",
            "email": "test@example.com", "political_status": "群众", "hometown": "江苏南京",
            "recruitment_type": "校园招聘", "channel": "校园线下", "channel_detail": "",
            "position": "机械工程师", "position_detail": "", "notes": "must-not-upload",
            "status": "待筛选",
            "created_at": "2026-09-29T10:00:00", "id": 99,
        }
        self.assertEqual(to_nocobase(local), {
            "Number": "0220260929001", "name": "测试人才", "gender": "女",
            "birthday": "2000-07", "age": "26", "phone": "19000000002",
            "email": "test@example.com", "political_status": "群众", "area": "江苏南京",
            "Type": "校园招聘", "channel": "校园线下", "detailed": "",
            "post": "机械工程师", "Other_job_titles": "",
            "status": "待筛选",
        })

    def test_social_channel_uses_social_field_and_round_trips(self):
        remote = to_nocobase({"recruitment_type": "社会招聘", "channel": "boss直聘", "name": "张三"})
        self.assertEqual(remote, {"Type": "社会招聘", "Social_recruitment_channels": "boss直聘", "name": "张三"})
        self.assertEqual(from_nocobase({**remote, "id": 7, "createdAt": "2026-09-29T01:02:03Z"}), {
            "recruitment_type": "社会招聘", "channel": "boss直聘", "name": "张三",
            "id": 7, "created_at": "2026-09-29T01:02:03Z",
        })

    def test_reverse_mapping_ignores_unknown_and_sensitive_system_fields(self):
        result = from_nocobase({"id": 8, "Number": "A1", "name": "李四", "updatedAt": "now",
                                "createdById": 26, "updatedById": 26, "unknown": "drop"})
        self.assertEqual(result, {"id": 8, "archive_no": "A1", "name": "李四", "updated_at": "now"})


if __name__ == "__main__":
    unittest.main()
