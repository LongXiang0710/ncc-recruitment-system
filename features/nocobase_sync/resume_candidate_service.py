"""Coordinate candidate import and bidirectional remote deletion rules."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


class ResumeCandidateConsistencyError(RuntimeError):
    """Report incomplete cross-aggregate compensation without personal data."""

    def __init__(self):
        self.diagnostic_id = uuid.uuid4().hex[:12]
        super().__init__(
            f"远端简历与人才数据恢复不完整，请管理员核对（诊断编号：{self.diagnostic_id}）"
        )


@dataclass(frozen=True)
class ImportResult:
    candidate_id: int
    already_imported: bool


class ResumeCandidateService:
    def __init__(self, resumes, recognition, candidates):
        self.resumes = resumes
        self.recognition = recognition
        self.candidates = candidates

    @staticmethod
    def _ids(ids: list[int]) -> list[int]:
        if not isinstance(ids, list) or not 1 <= len(ids) <= 1000 or any(
            type(identifier) is not int or identifier <= 0 for identifier in ids
        ):
            raise ValueError("请选择1至1000条有效记录")
        return list(dict.fromkeys(ids))

    def _stable_resume(self, resume_id: int) -> tuple[dict, dict]:
        source = self.resumes.get(resume_id)
        if source is None:
            raise ValueError("简历不存在或已删除")
        if source.get("linked_candidate"):
            return source, self.resumes.recognition_snapshot(source)
        if source.get("status") != "已识别":
            raise ValueError("仅已识别简历可以录入人才库")
        for field, label in (
            ("archive_no", "档案编号"), ("source_id", "来源编号"),
            ("file_hash", "文件指纹"),
        ):
            value = source.get(field)
            found = self.resumes.resumes.find_by_stable_key(field, value)
            if found is None or found.get("id") != resume_id:
                raise ValueError(f"简历{label}冲突，请刷新后核对")
        return source, self.resumes.recognition_snapshot(source)

    def import_candidate(self, resume_id: int) -> ImportResult:
        source, snapshot = self._stable_resume(resume_id)
        linked = source.get("linked_candidate")
        if linked:
            if self.candidates.get(linked) is None:
                raise ValueError("简历关联的人才记录不存在，请管理员核对")
            return ImportResult(linked, True)
        result = self.recognition.result(resume_id)
        if not isinstance(result, dict) or not result:
            raise ValueError("简历没有可用的识别结果")
        phone = str(result.get("phone") or "").strip()
        if self.candidates.find_by_phone(phone) is not None:
            raise ValueError("相同联系方式的人才已存在")
        payload = dict(result)
        payload["archive_no"] = source.get("archive_no") or ""
        attachments = self.resumes.attachments.list(resume_id)
        current, current_snapshot = self._stable_resume(resume_id)
        if current_snapshot != snapshot:
            raise ValueError("简历已被修改，请刷新后检查")
        candidate_id = self.candidates.create_from_resume(payload, attachments)
        try:
            if not self.resumes.link_candidate(resume_id, snapshot, candidate_id):
                raise ValueError("简历已被修改，请刷新后检查")
        except Exception as original_error:
            try:
                self.candidates.rollback_created(candidate_id)
            except Exception:
                raise ResumeCandidateConsistencyError() from original_error
            raise
        return ImportResult(candidate_id, False)

    def _resume_delete_preview(self, ids: list[int]) -> list[dict]:
        details = list(self.resumes.delete_preview(ids)["details"])
        seen_candidates = set()
        seen_attachments = set()
        for resume_id in ids:
            source = self.resumes.get(resume_id)
            if source is None:
                raise ValueError("简历不存在或已删除")
            for attachment in self.resumes.attachments.list(resume_id):
                if attachment["id"] not in seen_attachments:
                    seen_attachments.add(attachment["id"])
                    details.append({"entity": "attachments", "id": attachment["id"],
                                    "name": attachment.get("filename") or str(attachment["id"])})
            candidate_id = source.get("linked_candidate")
            if not candidate_id or candidate_id in seen_candidates:
                continue
            linked = self.resumes.resumes.find_by_linked_candidate(candidate_id)
            if len(linked) != 1 or linked[0].get("id") != resume_id:
                raise ValueError("同一人才被多份简历关联，需人工核对后处理")
            candidate = self.candidates.get(candidate_id)
            if candidate is None:
                raise ValueError("简历关联的人才记录不存在，请管理员核对")
            seen_candidates.add(candidate_id)
            details.append({"entity": "candidates", "id": candidate_id,
                            "name": candidate.get("name") or str(candidate_id)})
            for key, entity in (("education_experiences", "education"),
                                ("work_experiences", "work"),
                                ("project_experiences", "project")):
                for row in candidate.get(key, []):
                    if type(row.get("id")) is int:
                        details.append({"entity": entity, "id": row["id"],
                                        "name": row.get("name") or str(row["id"])})
        return details

    def resume_delete_preview(self, ids: list[int]) -> list[dict]:
        return self._resume_delete_preview(self._ids(ids))

    def delete_resumes(self, ids: list[int], expected: list[dict] | None = None) -> int:
        identifiers = self._ids(ids)
        details = self._resume_delete_preview(identifiers)
        if expected is not None and expected != details:
            raise ValueError("记录已发生变化，请刷新后重新删除")
        sources = [self.resumes.get(identifier) for identifier in identifiers]
        deleted = 0
        for source in sources:
            candidate_id = source.get("linked_candidate")
            if candidate_id:
                preview = self.candidates.delete_preview([candidate_id])["details"]
                self.candidates.delete([candidate_id], preview)
            if not self.resumes.delete_one(source["id"]):
                if candidate_id:
                    raise ResumeCandidateConsistencyError()
                raise ValueError("记录已不存在，请刷新后重新删除")
            deleted += 1
        return deleted

    def _candidate_delete_preview(self, ids: list[int]) -> list[dict]:
        details = list(self.candidates.delete_preview(ids)["details"])
        for candidate_id in ids:
            for source in self.resumes.resumes.find_by_linked_candidate(candidate_id):
                details.append({"entity": "resume_documents", "id": source["id"],
                                "name": source.get("name") or str(source["id"])})
        return details

    def candidate_delete_preview(self, ids: list[int]) -> list[dict]:
        return self._candidate_delete_preview(self._ids(ids))

    def delete_candidates(self, ids: list[int], expected: list[dict] | None = None) -> int:
        identifiers = self._ids(ids)
        details = self._candidate_delete_preview(identifiers)
        if expected is not None and expected != details:
            raise ValueError("记录已发生变化，请刷新后重新删除")
        deleted = 0
        for candidate_id in identifiers:
            linked = self.resumes.resumes.find_by_linked_candidate(candidate_id)
            snapshots = [(row["id"], dict(row)) for row in linked]
            try:
                for resume_id, _snapshot in snapshots:
                    self.resumes.restore_link(resume_id, {
                        "linked_candidate": None, "status": "已识别",
                    })
                preview = self.candidates.delete_preview([candidate_id])["details"]
                self.candidates.delete([candidate_id], preview)
            except Exception as original_error:
                restore_failed = False
                for resume_id, snapshot in reversed(snapshots):
                    try:
                        self.resumes.restore_link(resume_id, snapshot)
                    except Exception:
                        restore_failed = True
                if restore_failed:
                    raise ResumeCandidateConsistencyError() from original_error
                raise
            deleted += 1
        return deleted
