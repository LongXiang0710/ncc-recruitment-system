"""Guarded, journaled migration from a copied SQLite database to NocoBase."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from .migration_inventory import build_inventory
from .migration_models import MigrationReport, MigrationResult
from .migration_reports import load_report


class MigrationConsistencyError(RuntimeError):
    def __init__(self):
        self.diagnostic_id = uuid.uuid4().hex[:12]
        super().__init__(f"迁移恢复不完整，请管理员核对（诊断编号：{self.diagnostic_id}）")


def select_latest_eligible_report(data_dir: Path, now=None) -> MigrationReport:
    current = (now or datetime.now)()
    directory = Path(data_dir) / "migration-reports"
    reports = []
    for path in directory.glob("nocobase-check-*.json"):
        try:
            report = load_report(path)
        except ValueError:
            continue
        if report.eligible and not report.issues and report.generated_at <= current < report.expires_at:
            reports.append(report)
    if not reports:
        raise ValueError("没有找到24小时内有效的迁移检查报告，请先重新检查")
    return max(reports, key=lambda item: item.generated_at)


def _atomic_json(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _upload(attachment: dict | None) -> dict | None:
    if attachment is None:
        return None
    return {
        "name": str(attachment.get("name") or "resume.pdf"),
        "content": base64.b64encode(bytes(attachment.get("content") or b"")).decode("ascii"),
    }


def _relation_rows(source: dict, table: str, candidate_id: int) -> list[dict]:
    return [
        {key: value for key, value in row.items() if key not in ("id", "candidate_id", "created_at", "updated_at")}
        for row in source.get(table, []) if row.get("candidate_id") == candidate_id
    ]


def _attachment_index(source: dict) -> dict[tuple[str, int], dict]:
    return {(row["entity"], row["local_id"]): row for row in source.get("attachments", [])}


def _journal_payload(created_candidates, created_resumes, candidate_ids, resume_ids, references, stage):
    return {
        "version": 1, "stage": stage,
        "created_candidates": list(created_candidates),
        "created_resumes": list(created_resumes),
        "candidate_id_map": {str(key): value for key, value in candidate_ids.items()},
        "resume_id_map": {str(key): value for key, value in resume_ids.items()},
        "reference_updates": list(references),
    }


def apply_migration(sqlite_path: Path, services, report: MigrationReport,
                    journal_path: Path, *, now=None) -> MigrationResult:
    """Apply the checked snapshot; never changes the backend selector."""
    current = (now or datetime.now)()
    if not report.eligible or report.issues or not (report.generated_at <= current < report.expires_at):
        raise ValueError("迁移检查报告无效或已过期")
    inventory = build_inventory(Path(sqlite_path), services)
    if inventory.issues or inventory.digests != report.digests:
        raise ValueError("源数据或NocoBase数据已变化，请重新执行迁移检查")

    source = inventory.source
    attachments = _attachment_index(source)
    candidate_ids, resume_ids = {}, {}
    created_candidates, created_resumes, references = [], [], []
    journal_path = Path(journal_path)
    connection = None

    def save(stage):
        _atomic_json(journal_path, _journal_payload(
            created_candidates, created_resumes, candidate_ids, resume_ids, references, stage,
        ))

    try:
        save("started")
        # 1. Candidate main records.
        for row in source["candidates"]:
            local_id = int(row["id"])
            remote_id = services.candidates.candidates.create(row)
            candidate_ids[local_id] = remote_id; created_candidates.append(remote_id); save("candidates")

        # 2. Candidate relations and attachments.
        for row in source["candidates"]:
            local_id, remote_id = int(row["id"]), candidate_ids[int(row["id"])]
            services.candidates.relations.sync(remote_id, "education", _relation_rows(source, "candidate_educations", local_id))
            services.candidates.relations.sync(remote_id, "work", _relation_rows(source, "candidate_work_experiences", local_id))
            services.candidates.relations.sync(remote_id, "project", _relation_rows(source, "candidate_project_experiences", local_id))
            upload = _upload(attachments.get(("candidates", local_id)))
            if upload: services.candidates.attachments.replace(remote_id, upload)
        save("candidate-details")

        # 3. Resume records, recognition payload when supported, and attachments.
        recognition = {row.get("source_id"): row for row in source.get("resume_recognition", [])}
        resume_fields = getattr(getattr(services, "preflight", None), "resume_fields", {})
        for row in source["resume_documents"]:
            local_id = int(row["id"]); values = dict(row)
            if "recognition_result" in resume_fields and row.get("source_id") in recognition:
                values["recognition_result"] = recognition[row["source_id"]].get("result") or recognition[row["source_id"]].get("recognition_result")
            remote_id = services.resumes.resumes.create(values)
            resume_ids[local_id] = remote_id; created_resumes.append(remote_id); save("resumes")
            upload = _upload(attachments.get(("resume_documents", local_id)))
            if upload: services.resumes.attachments.replace(remote_id, upload)

        # 4. Link imported resumes to migrated candidates when the remote schema supports it.
        resumes_by_source = {str(row.get("source_id") or ""): resume_ids[int(row["id"])] for row in source["resume_documents"]}
        for link in source["resume_imports"] if "linked_candidate" in resume_fields else ():
            remote_resume = resumes_by_source.get(str(link.get("source_id") or ""))
            remote_candidate = candidate_ids.get(link.get("candidate_id"))
            if remote_resume and remote_candidate:
                services.resumes.resumes.update(remote_resume, {"linked_candidate": remote_candidate, "status": "已入库"})
        save("resume-links")

        # 5. Change local business references in one transaction kept open until verification.
        connection = sqlite3.connect(Path(sqlite_path))
        connection.execute("BEGIN IMMEDIATE")
        for table in ("applications", "interviews", "employees"):
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            if "candidate_id" not in columns: continue
            for row in source[table]:
                old = row.get("candidate_id")
                if old in candidate_ids:
                    connection.execute(f'UPDATE "{table}" SET candidate_id=? WHERE id=?', (candidate_ids[old], row["id"]))
                    references.append({"table": table, "row_id": row["id"], "old_id": old, "new_id": candidate_ids[old]}); save("local-references")

        # 6. Re-read all created aggregates before committing local references.
        for remote_id in created_candidates:
            if services.candidates.get(remote_id) is None: raise RuntimeError("远端人才校验失败")
        for remote_id in created_resumes:
            if services.resumes.get(remote_id) is None: raise RuntimeError("远端简历校验失败")
        connection.commit(); connection.close(); connection = None
        save("complete")
        return MigrationResult(candidate_ids, resume_ids, len(references), str(journal_path))
    except Exception as original:
        if connection is not None:
            connection.rollback(); connection.close()
        cleanup_failed = False
        for identifier in reversed(created_resumes):
            try: services.resumes._cleanup_created(identifier)
            except Exception: cleanup_failed = True
        for identifier in reversed(created_candidates):
            try: services.candidates.rollback_created(identifier)
            except Exception: cleanup_failed = True
        save("cleanup-incomplete" if cleanup_failed else "rolled-back")
        if cleanup_failed: raise MigrationConsistencyError() from original
        raise
