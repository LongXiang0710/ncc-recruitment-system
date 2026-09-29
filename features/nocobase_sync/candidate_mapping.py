"""Explicit field mapping for the NocoBase recruitment talent pool."""

LOCAL_TO_REMOTE = {
    "archive_no": "Number",
    "name": "name",
    "gender": "gender",
    "birthdate": "birthday",
    "age": "age",
    "phone": "phone",
    "email": "email",
    "political_status": "political_status",
    "hometown": "area",
    "recruitment_type": "Type",
    "channel_detail": "detailed",
    "position": "post",
    "position_detail": "Other_job_titles",
}
REMOTE_TO_LOCAL = {remote: local for local, remote in LOCAL_TO_REMOTE.items()}


def to_nocobase(local: dict) -> dict:
    """Return only confirmed writable fields, preserving explicit empty values."""
    result = {remote: local[local_key] for local_key, remote in LOCAL_TO_REMOTE.items() if local_key in local}
    if "channel" in local:
        key = "Social_recruitment_channels" if local.get("recruitment_type") == "社会招聘" else "channel"
        result[key] = local["channel"]
    return result


def from_nocobase(remote: dict) -> dict:
    """Translate a NocoBase record without exposing unknown or ownership fields."""
    result = {local: remote[remote_key] for remote_key, local in REMOTE_TO_LOCAL.items() if remote_key in remote}
    recruitment_type = remote.get("Type")
    channel_key = "Social_recruitment_channels" if recruitment_type == "社会招聘" else "channel"
    if channel_key in remote:
        result["channel"] = remote[channel_key]
    for remote_key, local_key in (("id", "id"), ("createdAt", "created_at"), ("updatedAt", "updated_at")):
        if remote_key in remote:
            result[local_key] = remote[remote_key]
    return result
