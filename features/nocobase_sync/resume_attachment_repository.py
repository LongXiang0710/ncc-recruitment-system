"""Safe attachment operations for Resume_Collection.Resume."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from features.resume_documents import file_types

from .client import NocoBaseClient, NocoBaseError


MAX_FILE_SIZE = 50 * 1024 * 1024
ATTACHMENT_FIELD = "Resume_Collection.Resume"


class ResumeAttachmentRepository:
    def __init__(self, client: NocoBaseClient):
        self.client = client

    @staticmethod
    def _identifier(value: int, label: str = "附件") -> int:
        if type(value) is not int or value <= 0:
            raise ValueError(f"{label}编号无效")
        return value

    @staticmethod
    def _protocol(endpoint: str) -> NocoBaseError:
        return NocoBaseError("protocol", None, endpoint)

    def list(self, resume_id: int) -> list[dict]:
        resume_id = self._identifier(resume_id, "简历记录")
        endpoint = f"Resume_Collection/{resume_id}/Resume:list"
        data = self.client.request(endpoint, params={"pageSize": 100})
        if not isinstance(data, list) or any(
            not isinstance(row, dict) or type(row.get("id")) is not int for row in data
        ):
            raise self._protocol(endpoint)
        return data

    @staticmethod
    def _decode_upload(upload: dict) -> tuple[str, str, bytes]:
        if not isinstance(upload, dict):
            raise ValueError("简历附件格式无效")
        filename = Path(str(upload.get("name") or "").replace("\\", "/")).name
        encoded = upload.get("content")
        if not filename or not isinstance(encoded, str):
            raise ValueError("简历附件格式无效")
        extension = file_types.extension(filename)
        if extension not in file_types.ALL_EXTENSIONS:
            raise ValueError("简历附件类型不支持")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("简历附件内容无效") from None
        if not content or len(content) > MAX_FILE_SIZE:
            raise ValueError("简历附件须在50MB以内")
        if not file_types.valid_content(extension, content):
            raise ValueError("简历附件内容与文件类型不一致")
        return filename, file_types.mime_type(filename), content

    def _set(self, resume_id: int, values: list[int]) -> None:
        self.client.request(
            f"Resume_Collection/{resume_id}/Resume:set",
            method="POST", body={"values": values},
        )

    def replace(self, resume_id: int, upload: dict | None = None,
                remove: bool = False) -> list[dict]:
        resume_id = self._identifier(resume_id, "简历记录")
        if upload is not None and remove:
            raise ValueError("不能同时上传和移除简历附件")
        decoded = self._decode_upload(upload) if upload is not None else None
        existing = self.list(resume_id)
        if decoded is None and not remove:
            return existing
        if remove:
            self._set(resume_id, [])
            for attachment in existing:
                self.delete_if_unreferenced(attachment["id"])
            return []

        filename, mime_type, content = decoded
        created = self.client.upload(
            "attachments:create", filename=filename, mime_type=mime_type,
            content=content, params={"attachmentField": ATTACHMENT_FIELD},
        )
        if not isinstance(created, dict) or type(created.get("id")) is not int:
            raise self._protocol("attachments:create")
        try:
            self._set(resume_id, [created["id"]])
        except Exception:
            try:
                self.client.request("attachments:destroy", method="POST",
                                    params={"filterByTk": created["id"]})
            except Exception:
                pass
            raise
        for attachment in existing:
            if attachment["id"] != created["id"]:
                self.delete_if_unreferenced(attachment["id"])
        return [created]

    @staticmethod
    def _safe_filename(record: dict) -> str:
        value = record.get("filename") or record.get("title") or record.get("name")
        name = Path(str(value or "").replace("\\", "/")).name
        return "".join("_" if character in '\"\r\n' or ord(character) < 32 else character
                       for character in name)

    def read(self, attachment_id: int) -> tuple[bytes, str, str]:
        attachment_id = self._identifier(attachment_id)
        endpoint = "attachments:get"
        record = self.client.request(endpoint, params={"filterByTk": attachment_id})
        if not isinstance(record, dict) or record.get("id") != attachment_id:
            raise self._protocol(endpoint)
        filename = self._safe_filename(record)
        url = record.get("url")
        if not filename or not isinstance(url, str) or not url.strip():
            raise self._protocol(endpoint)
        url = url.strip()
        if not urlsplit(url).scheme:
            configured_url = getattr(getattr(self.client, "config", None), "url", "")
            if not configured_url or not url.startswith("/"):
                raise self._protocol(endpoint)
            url = urljoin(configured_url.rstrip("/") + "/", url)
        content, mime_type = self.client.download(url, maximum_bytes=MAX_FILE_SIZE)
        return content, mime_type, filename

    def restore(self, resume_id: int, snapshot: list[dict]) -> None:
        resume_id = self._identifier(resume_id, "简历记录")
        if not isinstance(snapshot, list) or any(
            not isinstance(row, dict) or type(row.get("id")) is not int for row in snapshot
        ):
            raise ValueError("简历附件快照无效")
        self._set(resume_id, [row["id"] for row in snapshot])

    def delete_if_unreferenced(self, attachment_id: int) -> bool:
        attachment_id = self._identifier(attachment_id)
        checks = (
            ("Resume_Collection:list", "Resume"),
            ("campus_talent_pool:list", "biographical_notes"),
        )
        for endpoint, relation in checks:
            references = self.client.request(endpoint, params={
                "pageSize": 1, "filter": {relation: {"id": {"$eq": attachment_id}}},
            })
            if not isinstance(references, list):
                raise self._protocol(endpoint)
            if references:
                return False
        deleted = self.client.request(
            "attachments:destroy", method="POST", params={"filterByTk": attachment_id},
        )
        return type(deleted) is int and deleted > 0
