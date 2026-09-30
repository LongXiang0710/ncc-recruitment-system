"""Aggregate resume operations backed solely by NocoBase repositories."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from features.candidates.service import normalize_recruitment

from .client import NocoBaseError
from .resume_attachment_repository import ResumeAttachmentRepository


class RemoteResumeConsistencyError(RuntimeError):
    """Signals failed compensation without exposing resume content."""

    def __init__(self):
        self.diagnostic_id = uuid.uuid4().hex[:12]
        super().__init__(f"远端简历数据恢复不完整，请管理员核对（诊断编号：{self.diagnostic_id}）")


class RemoteResumeService:
    SYSTEM_FIELDS = {
        "id", "archive_no", "source_id", "file_hash", "status", "recognition_result",
        "linked_candidate", "created_at", "updated_at", "created_by", "resume",
    }

    def __init__(self, resumes, attachments, schema: dict, *, now=None, source_factory=None):
        self.resumes = resumes
        self.attachments = attachments
        self.schema = schema
        self.now = now or datetime.now
        self.source_factory = source_factory or (lambda: uuid.uuid4().hex)

    def _aggregate(self, row: dict) -> dict:
        result = dict(row)
        attachments = self.attachments.list(result["id"])
        attachment = attachments[0] if attachments else None
        result["resume"] = str(attachment["id"]) if attachment else ""
        result["resume_name"] = str(
            attachment.get("filename") or attachment.get("title") or attachment.get("name") or ""
        ) if attachment else ""
        result["created_date"] = str(result.get("created_at") or "").replace("T", " ")
        return result

    def list(self, page: int, page_size: int, query: str) -> dict:
        result = self.resumes.list_page(page, page_size, query)
        return {"rows": [self._aggregate(row) for row in result["rows"]], "count": result["count"]}

    def list_all(self, query: str = "") -> list[dict]:
        rows, page = [], 1
        while True:
            result = self.list(page, 100, query)
            rows.extend(result["rows"])
            if len(rows) >= result["count"]:
                return rows
            if not result["rows"]:
                raise NocoBaseError("protocol", None, "Resume_Collection:list")
            page += 1

    def get(self, identifier: int) -> dict | None:
        row = self.resumes.get(identifier)
        return self._aggregate(row) if row is not None else None

    def pending(self) -> list[dict]:
        return [row for row in self.list_all() if row.get("status") == "待识别"]

    def read_attachment(self, identifier: int) -> tuple[bytes, str, str]:
        return self.attachments.read(identifier)

    def _fields(self) -> dict[str, dict]:
        return {field["key"]: field for field in self.schema.get("fields", [])}

    def _validate_user_values(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("提交内容必须为对象")
        normalized = normalize_recruitment(payload)
        allowed = {
            "name", "position", "position_detail", "recruitment_type",
            "channel", "channel_detail",
        }
        fields = self._fields()
        result = {}
        for key in allowed:
            field = fields.get(key, {})
            value = str(normalized.get(key) or "").strip()
            if len(value) > field.get("maxLength", 300):
                raise ValueError(str(field.get("label") or key) + "内容过长")
            if value and field.get("options") and value not in field["options"]:
                raise ValueError(str(field.get("label") or key) + "选项无效")
            result[key] = value
        if result["position"] == "其它" and not result["position_detail"]:
            raise ValueError("请填写其它岗位名称")
        if result["position"] != "其它":
            result["position_detail"] = ""
        return result

    def _new_archive_no(self, recruitment_type: str) -> str:
        prefix = ("02" if recruitment_type == "校园招聘" else "01") + self.now().strftime("%Y%m%d")
        for suffix in range(1, 1000):
            candidate = f"{prefix}{suffix:03d}"
            if self.resumes.find_by_stable_key("archive_no", candidate) is None:
                return candidate
        raise ValueError("当日档案数量已超过999条")

    @staticmethod
    def _upload(payload: dict) -> tuple[dict, str, str]:
        upload = payload.get("_resume_upload")
        filename, _mime, content = ResumeAttachmentRepository._decode_upload(upload)
        return upload, filename, hashlib.sha256(content).hexdigest()

    def _cleanup_created(self, identifier: int) -> None:
        failed = False
        try:
            attachments = self.attachments.list(identifier)
        except Exception:
            attachments = []
            failed = True
        try:
            deleted = self.resumes.delete(identifier)
        except Exception as error:
            raise RemoteResumeConsistencyError() from error
        if not deleted:
            raise RemoteResumeConsistencyError()
        for attachment in attachments:
            try:
                self.attachments.delete_if_unreferenced(attachment["id"])
            except Exception:
                failed = True
        if failed:
            raise RemoteResumeConsistencyError()

    def _create(self, payload: dict, creator: str) -> int:
        upload, filename, file_hash = self._upload(payload)
        if self.resumes.find_by_stable_key("file_hash", file_hash) is not None:
            raise ValueError("同一份简历已存在，请使用已有记录")
        values = self._validate_user_values(payload)
        source_id = str(self.source_factory())
        if not source_id or self.resumes.find_by_stable_key("source_id", source_id) is not None:
            raise ValueError("简历来源编号冲突，请重试")
        values.update(
            name=filename,
            status="待识别",
            archive_no=self._new_archive_no(values["recruitment_type"]),
            source_id=source_id,
            file_hash=file_hash,
            created_by=creator,
            created_at=self.now().isoformat(timespec="seconds"),
        )
        try:
            identifier = self.resumes.create(values)
        except NocoBaseError as error:
            if error.kind in ("network", "remote"):
                found = self.resumes.find_by_stable_key("source_id", source_id)
                if found is not None and type(found.get("id")) is int:
                    self._cleanup_created(found["id"])
            raise
        try:
            self.attachments.replace(identifier, upload)
        except Exception:
            self._cleanup_created(identifier)
            raise
        return identifier

    def create(self, payload: dict) -> int:
        creator = str(payload.get("created_by") or "管理员").strip() if isinstance(payload, dict) else "管理员"
        return self._create(payload, creator or "管理员")

    def create_public(self, payload: dict) -> int:
        return self._create(payload, "公开投递")

    def update(self, identifier: int, payload: dict) -> None:
        current = self.resumes.get(identifier)
        if current is None:
            raise ValueError("简历记录已不存在，请刷新后重试")
        attachment_snapshot = self.attachments.list(identifier)
        upload = payload.get("_resume_upload") if isinstance(payload, dict) else None
        remove = payload.get("_remove_resume") is True if isinstance(payload, dict) else False
        if remove:
            raise ValueError("简历附件不能为空")
        merged = dict(current)
        merged.update({key: value for key, value in payload.items() if key not in self.SYSTEM_FIELDS})
        values = self._validate_user_values(merged)
        if upload is not None:
            _upload, filename, file_hash = self._upload(payload)
            duplicate = self.resumes.find_by_stable_key("file_hash", file_hash)
            if duplicate is not None and duplicate.get("id") != identifier:
                raise ValueError("同一份简历已存在，请使用已有记录")
            if current.get("status") == "已入库":
                raise ValueError("已入库简历不能替换附件，请新增简历")
            values.update(name=filename, file_hash=file_hash, status="待识别")
        restore_main = {key: current.get(key, "") for key in (
            "name", "position", "position_detail", "recruitment_type", "channel",
            "channel_detail", "status", "file_hash", "recognition_result", "linked_candidate",
        )}
        try:
            self.resumes.update(identifier, values)
            if upload is not None:
                self.attachments.replace(identifier, upload)
        except Exception as original_error:
            failed = False
            for restore in (
                lambda: self.resumes.update(identifier, restore_main),
                lambda: self.attachments.restore(identifier, attachment_snapshot),
            ):
                try:
                    restore()
                except Exception:
                    failed = True
            if failed:
                raise RemoteResumeConsistencyError() from original_error
            raise

    def delete_preview(self, ids: list[int]) -> dict:
        if not isinstance(ids, list) or not ids:
            raise ValueError("请选择有效记录")
        details = []
        for identifier in dict.fromkeys(ids):
            row = self.resumes.get(identifier)
            if row is None:
                raise ValueError("记录已不存在，请刷新后重试")
            details.append({"entity": "resume_documents", "id": identifier,
                            "name": row.get("name") or str(identifier)})
        return {"details": details}
