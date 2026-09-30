"""Dify recognition state machine for NocoBase-backed resumes."""

from __future__ import annotations

import json
import threading

from features.resume_documents.dify_mapping import to_candidate_payload


class RecognitionService:
    """Recognize one resume without overwriting concurrent remote edits."""

    def __init__(self, resumes, recognizer, *, mapper=to_candidate_payload, lock=None):
        self.resumes = resumes
        self.recognizer = recognizer
        self.mapper = mapper
        self.lock = lock or threading.Lock()

    def recognize(self, resume_id: int) -> dict:
        if not self.lock.acquire(blocking=False):
            raise ValueError("已有简历正在识别，请稍后重试")
        try:
            source = self.resumes.get(resume_id)
            if source is None:
                raise ValueError("简历不存在或已删除")
            if source.get("status") not in ("待识别", "失败"):
                raise ValueError("仅处理待识别或失败简历")
            snapshot = self.resumes.recognition_snapshot(source)
            content, _mime_type, filename = self.resumes.read_attachment(resume_id)
            try:
                raw_result = self.recognizer(
                    content, str(source.get("source_id") or ""), dict(source), filename,
                )
                result = self.mapper(raw_result, source)
                encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
                if not isinstance(result, dict) or not result:
                    raise ValueError("工作流未返回可用的人才字段，请检查 Dify 输出")
            except Exception as error:
                if not self.resumes.update_recognition(
                    resume_id, snapshot, status="失败",
                ):
                    raise ValueError("简历已被修改，请刷新后检查") from error
                raise
            if not self.resumes.update_recognition(
                resume_id, snapshot, status="已识别", result=encoded,
            ):
                raise ValueError("简历已被修改，请刷新后检查")
            return result
        finally:
            self.lock.release()

    def result(self, resume_id: int) -> dict | None:
        source = self.resumes.get(resume_id)
        if source is None:
            raise ValueError("简历不存在或已删除")
        encoded = source.get("recognition_result")
        if not encoded:
            return None
        if isinstance(encoded, dict):
            return encoded
        try:
            result = json.loads(encoded)
        except (TypeError, json.JSONDecodeError):
            raise ValueError("简历识别结果已损坏，请重新识别") from None
        if not isinstance(result, dict):
            raise ValueError("简历识别结果已损坏，请重新识别")
        return result
