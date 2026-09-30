"""Translate resume records between local UI names and NocoBase fields."""

from __future__ import annotations


DIRECT_FIELDS = {
    "archive_no": "Number",
    "status": "Processing_Status",
    "name": "name",
    "recruitment_type": "Job_Type",
    "channel_detail": "Details",
    "position": "Job",
    "position_detail": "Other_job_titles",
    "created_by": "Creator",
    "created_at": "time",
    "source_id": "source_id",
    "file_hash": "file_hash",
    "recognition_result": "recognition_result",
    "linked_candidate": "linked_candidate",
}


def _candidate_id(value):
    if isinstance(value, dict):
        return value.get("id")
    return value


def to_nocobase_resume(values: dict, fields=None) -> dict:
    if not isinstance(values, dict):
        raise TypeError("简历数据必须是对象。")
    direct = fields or DIRECT_FIELDS
    result = {
        remote: values[local]
        for local, remote in direct.items()
        if local in values
    }
    if "channel" in values or "recruitment_type" in values:
        channel = values.get("channel", "")
        if values.get("recruitment_type") == "社会招聘":
            result["Campus_recruitment_channels"] = ""
            result["External_hiring_channels"] = channel
        else:
            result["Campus_recruitment_channels"] = channel
            result["External_hiring_channels"] = ""
    return result


def from_nocobase_resume(row: dict, fields=None) -> dict:
    if not isinstance(row, dict):
        raise TypeError("NocoBase 简历记录必须是对象。")
    direct = fields or DIRECT_FIELDS
    result = {
        local: row.get(remote, "")
        for local, remote in direct.items()
    }
    result["id"] = row.get("id")
    result["linked_candidate"] = _candidate_id(row.get("linked_candidate"))
    result["channel"] = (
        row.get("External_hiring_channels", "")
        if result.get("recruitment_type") == "社会招聘"
        else row.get("Campus_recruitment_channels", "")
    )
    result["created_at"] = row.get("createdAt") or row.get("time") or ""
    result["updated_at"] = row.get("updatedAt") or ""
    return result
