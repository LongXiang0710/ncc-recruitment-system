"""Aggregate candidate operations backed solely by NocoBase repositories."""

from __future__ import annotations

import uuid

from .candidate_mapping import LOCAL_TO_REMOTE
from .candidate_validation import EDUCATION_RANK, validate_remote_candidate
from .client import NocoBaseError


class RemoteCandidateConsistencyError(RuntimeError):
    """Signals a failed compensation without exposing candidate content."""

    def __init__(self):
        self.diagnostic_id = uuid.uuid4().hex[:12]
        super().__init__(f"远端人才数据恢复不完整，请管理员核对（诊断编号：{self.diagnostic_id}）")


class RemoteCandidateService:
    def __init__(self, candidates, relations, attachments, schema: dict):
        self.candidates = candidates
        self.relations = relations
        self.attachments = attachments
        self.schema = schema

    def _aggregate(self, main: dict) -> dict:
        result = dict(main)
        identifier = result["id"]
        education = self.relations.list(identifier, "education")
        work = self.relations.list(identifier, "work")
        project = self.relations.list(identifier, "project")
        attachments = self.attachments.list(identifier)
        result["education_experiences"] = education
        result["work_experiences"] = work
        result["project_experiences"] = project if result.get("recruitment_type") == "社会招聘" else []
        if education:
            highest = min(
                enumerate(education),
                key=lambda item: (-EDUCATION_RANK.get(item[1].get("education"), 0), item[0]),
            )[1]
            result.update({key: highest.get(key, "") for key in ("education", "school_name", "major")})
            result["graduation"] = highest.get("graduation", "") if result.get("recruitment_type") == "校园招聘" else ""
        else:
            result.update(education="", school_name="", major="", graduation="")
        attachment = attachments[0] if attachments else None
        result["resume"] = str(attachment["id"]) if attachment else ""
        result["resume_name"] = (
            str(attachment.get("filename") or attachment.get("title") or attachment.get("name") or "")
            if attachment else ""
        )
        result["created_date"] = str(result.get("created_at") or "").replace("T", " ")
        result["cohort"] = (
            result["graduation"][:4] + "届"
            if result.get("recruitment_type") == "校园招聘" and result.get("graduation") else ""
        )
        return result

    def list(self, page: int, page_size: int, query: str) -> dict:
        result = self.candidates.list_page(page=page, page_size=page_size, query=query)
        return {"rows": [self._aggregate(row) for row in result["rows"]], "count": result["count"]}

    def list_all(self, query: str = "") -> list[dict]:
        rows = []
        page = 1
        while True:
            result = self.list(page=page, page_size=100, query=query)
            rows.extend(result["rows"])
            if len(rows) >= result["count"]:
                return rows
            if not result["rows"]:
                raise NocoBaseError("protocol", None, "campus_talent_pool:list")
            page += 1

    def get(self, identifier: int) -> dict | None:
        row = self.candidates.get(identifier)
        return self._aggregate(row) if row is not None else None

    def _validate(self, payload: dict, allowed_id: int | None = None) -> dict:
        def phone_exists(phone: str) -> bool:
            existing = self.candidates.find_by_phone(phone)
            return existing is not None and existing.get("id") != allowed_id
        return validate_remote_candidate(payload, self.schema, phone_exists=phone_exists)

    def validate(self, payload: dict) -> dict:
        return self._validate(payload)

    def find_by_phone(self, phone: str) -> dict | None:
        return self.candidates.find_by_phone(phone)

    def read_attachment(self, identifier: int) -> tuple[bytes, str, str]:
        return self.attachments.read(identifier)

    def _cleanup_created(self, identifier: int) -> None:
        cleanup_failed = False
        try:
            attachments = self.attachments.list(identifier)
        except Exception:
            attachments = []
            cleanup_failed = True
        try:
            deleted = self.candidates.delete(identifier)
        except Exception as error:
            raise RemoteCandidateConsistencyError() from error
        if not deleted:
            raise RemoteCandidateConsistencyError()
        for attachment in attachments:
            try:
                self.attachments.delete_if_unreferenced(attachment["id"])
            except Exception:
                cleanup_failed = True
        if cleanup_failed:
            raise RemoteCandidateConsistencyError()

    def _create_validated(self, values: dict) -> int:
        try:
            identifier = self.candidates.create(values["main"])
        except NocoBaseError as error:
            if error.kind in ("network", "remote"):
                found = self.candidates.find_by_phone(values["main"]["phone"])
                if found is not None and type(found.get("id")) is int:
                    self._cleanup_created(found["id"])
            raise
        try:
            self.relations.sync(identifier, "education", values["education"])
            self.relations.sync(identifier, "work", values["work"])
            self.relations.sync(identifier, "project", values["project"])
            if values["upload"] is not None or values["remove_resume"]:
                self.attachments.replace(
                    identifier, values["upload"], remove=values["remove_resume"],
                )
        except Exception:
            self._cleanup_created(identifier)
            raise
        return identifier

    def create(self, payload: dict) -> int:
        return self._create_validated(self._validate(payload))

    def create_from_resume(self, payload: dict, attachment_snapshot: list[dict]) -> int:
        if not isinstance(attachment_snapshot, list) or any(
            not isinstance(row, dict) or type(row.get("id")) is not int
            for row in attachment_snapshot
        ):
            raise ValueError("简历附件快照无效")
        values = self._validate(payload)
        identifier = self._create_validated(values)
        try:
            self.attachments.restore(identifier, attachment_snapshot)
        except Exception:
            self._cleanup_created(identifier)
            raise
        return identifier

    def rollback_created(self, identifier: int) -> None:
        self._cleanup_created(identifier)

    def create_many(self, payloads: list[dict]) -> list[int]:
        if not isinstance(payloads, list) or not payloads:
            raise ValueError("批量导入内容不能为空")
        validated = []
        phones = set()
        for payload in payloads:
            values = self._validate(payload)
            phone = values["main"]["phone"]
            if phone in phones:
                raise ValueError("批量导入中存在重复联系方式")
            phones.add(phone)
            validated.append(values)
        created = []
        try:
            for values in validated:
                created.append(self._create_validated(values))
        except Exception:
            compensation_failed = False
            for identifier in reversed(created):
                try:
                    self._cleanup_created(identifier)
                except Exception:
                    compensation_failed = True
            if compensation_failed:
                raise RemoteCandidateConsistencyError() from None
            raise
        return created

    def update(self, identifier: int, payload: dict) -> None:
        current = self.candidates.get(identifier)
        if current is None:
            raise ValueError("人才记录已不存在，请刷新后重试")
        relation_snapshot = self.relations.snapshot(identifier)
        attachment_snapshot = self.attachments.list(identifier)
        merged = dict(current)
        merged.update(payload)
        merged.setdefault("education_experiences", relation_snapshot["education"])
        merged.setdefault("work_experiences", relation_snapshot["work"])
        merged.setdefault("project_experiences", relation_snapshot["project"])
        values = self._validate(merged, allowed_id=identifier)
        try:
            self.candidates.update(identifier, values["main"])
            self.relations.sync(identifier, "education", values["education"])
            self.relations.sync(identifier, "work", values["work"])
            self.relations.sync(identifier, "project", values["project"])
            if values["upload"] is not None or values["remove_resume"]:
                self.attachments.replace(
                    identifier, values["upload"], remove=values["remove_resume"],
                )
        except Exception as original_error:
            restore_failed = False
            restore_main = {key: current.get(key, "") for key in LOCAL_TO_REMOTE}
            for restore in (
                lambda: self.candidates.update(identifier, restore_main),
                lambda: self.relations.restore(identifier, relation_snapshot),
                lambda: self.attachments.restore(identifier, attachment_snapshot),
            ):
                try:
                    restore()
                except Exception:
                    restore_failed = True
            if restore_failed:
                raise RemoteCandidateConsistencyError() from original_error
            raise

    @staticmethod
    def _ids(ids: list[int]) -> list[int]:
        if not isinstance(ids, list) or not 1 <= len(ids) <= 1000 or any(
            type(identifier) is not int or identifier <= 0 for identifier in ids
        ):
            raise ValueError("请选择1至1000条有效记录")
        return list(dict.fromkeys(ids))

    def delete_preview(self, ids: list[int]) -> dict:
        details = []
        for identifier in self._ids(ids):
            row = self.candidates.get(identifier)
            if row is None:
                raise ValueError("记录已不存在，请刷新后重新删除")
            details.append({"entity": "candidates", "id": identifier, "name": row.get("name") or str(identifier)})
        return {"details": details}

    def delete(self, ids: list[int], expected: list[dict]) -> int:
        identifiers = self._ids(ids)
        current = self.delete_preview(identifiers)["details"]
        if expected != current:
            raise ValueError("记录已发生变化，请刷新后重新删除")
        deleted = 0
        for identifier in identifiers:
            attachments = self.attachments.list(identifier)
            if not self.candidates.delete(identifier):
                raise ValueError("记录已不存在，请刷新后重新删除")
            for attachment in attachments:
                self.attachments.delete_if_unreferenced(attachment["id"])
            deleted += 1
        return deleted
