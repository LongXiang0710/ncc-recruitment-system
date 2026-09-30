"""Behavior tests for the local/NocoBase resume field contract."""

import unittest


class ResumeMappingTests(unittest.TestCase):
    def test_social_resume_maps_channel_and_never_writes_remote_status(self):
        from features.nocobase_sync.resume_mapping import to_nocobase_resume

        result = to_nocobase_resume({
            "archive_no": "A-1", "status": "待识别", "name": "测试简历",
            "recruitment_type": "社会招聘", "channel": "智联招聘",
            "channel_detail": "自定义", "position": "机械工程师",
            "position_detail": "", "created_by": "管理员", "created_at": "2026-09-30T08:00:00",
            "source_id": "SRC-1", "file_hash": "abc", "recognition_result": "{}",
            "linked_candidate": 9,
        })

        self.assertEqual(result, {
            "Number": "A-1", "Processing_Status": "待识别", "name": "测试简历",
            "Job_Type": "社会招聘", "Campus_recruitment_channels": "",
            "External_hiring_channels": "智联招聘", "Details": "自定义",
            "Job": "机械工程师", "Other_job_titles": "", "Creator": "管理员",
            "time": "2026-09-30T08:00:00", "source_id": "SRC-1", "file_hash": "abc",
            "recognition_result": "{}", "linked_candidate": 9,
        })
        self.assertNotIn("status", result)

    def test_campus_remote_row_maps_channel_relation_and_timestamps(self):
        from features.nocobase_sync.resume_mapping import from_nocobase_resume

        result = from_nocobase_resume({
            "id": 7, "Number": "A-7", "Processing_Status": "已识别", "status": "NEW",
            "name": "校园简历", "Job_Type": "校园招聘",
            "Campus_recruitment_channels": "校园平台", "External_hiring_channels": "智联招聘",
            "Details": "", "Job": "电气工程师", "Other_job_titles": "",
            "Creator": "公开投递", "time": "2026-09-30T08:00:00.000Z",
            "source_id": "SRC-7", "file_hash": "hash7", "recognition_result": "{\"name\":\"x\"}",
            "linked_candidate": {"id": 19}, "createdAt": "2026-09-30T07:59:00.000Z",
            "updatedAt": "2026-09-30T08:01:00.000Z",
        })

        self.assertEqual(result["channel"], "校园平台")
        self.assertEqual(result["linked_candidate"], 19)
        self.assertEqual(result["created_at"], "2026-09-30T07:59:00.000Z")
        self.assertEqual(result["updated_at"], "2026-09-30T08:01:00.000Z")
        self.assertEqual(result["status"], "已识别")


if __name__ == "__main__":
    unittest.main()
