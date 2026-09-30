"""Build a canonical, read-only inventory of SQLite and NocoBase recruitment data."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from .migration_models import MigrationInventory, MigrationIssue


SOURCE_TABLES = (
    "candidates", "resume_documents", "candidate_educations",
    "candidate_work_experiences", "candidate_project_experiences",
    "resume_imports", "applications", "interviews", "employees",
)
REFERENCE_TABLES = ("resume_imports", "applications", "interviews", "employees")
STABLE_KEYS = {
    "candidates": ("archive_no", "phone"),
    "resume_documents": ("archive_no", "source_id", "file_hash"),
}


def canonical_digest(value) -> str:
    def normalize(item):
        if isinstance(item, bytes):
            return {"sha256": hashlib.sha256(item).hexdigest(), "size": len(item)}
        if isinstance(item, dict):
            return {str(key): normalize(item[key]) for key in sorted(item)}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        return item
    encoded = json.dumps(normalize(value), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _table_exists(connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,),
    ).fetchone() is not None


def _rows(connection, table: str) -> list[dict]:
    if not _table_exists(connection, table):
        return []
    order = " ORDER BY id" if "id" in {
        row["name"] for row in connection.execute(f'PRAGMA table_info("{table}")')
    } else " ORDER BY rowid"
    return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"{order}')]


def _duplicates(rows: list[dict], fields: tuple[str, ...], entity: str,
                issues: list[MigrationIssue], prefix: str) -> None:
    for field in fields:
        seen = {}
        for row in rows:
            value = str(row.get(field) or "").strip()
            if not value:
                continue
            if value in seen:
                for duplicate in (seen[value], row):
                    issue = MigrationIssue(
                        f"{prefix}_duplicate_{field}", entity,
                        duplicate.get("id") if prefix == "local" else None,
                        str(duplicate.get("archive_no") or ""),
                    )
                    if issue not in issues:
                        issues.append(issue)
            else:
                seen[value] = row


def _cross_conflicts(local: list[dict], remote: list[dict], fields: tuple[str, ...],
                     entity: str, issues: list[MigrationIssue]) -> None:
    indexes = {field: {str(row.get(field) or "").strip() for row in remote
                       if str(row.get(field) or "").strip()} for field in fields}
    for row in local:
        for field in fields:
            value = str(row.get(field) or "").strip()
            if value and value in indexes[field]:
                issues.append(MigrationIssue(
                    f"target_conflict_{field}", entity, row.get("id"),
                    str(row.get("archive_no") or ""),
                ))


def build_inventory(sqlite_path: Path, services) -> MigrationInventory:
    """Read both stores without issuing a mutation to either one."""
    path = Path(sqlite_path).resolve()
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        missing_tables = [table for table in (*SOURCE_TABLES, "attachments")
                          if not _table_exists(connection, table)]
        source = {table: _rows(connection, table) for table in SOURCE_TABLES}
        attachments = {str(row["id"]): dict(row) for row in _rows(connection, "attachments")}
    finally:
        connection.close()

    issues = [MigrationIssue("missing_table", table) for table in missing_tables]
    attachment_inventory = []
    for entity in ("candidates", "resume_documents"):
        for row in source[entity]:
            attachment_id = str(row.get("resume") or "")
            if not attachment_id:
                if entity == "resume_documents":
                    issues.append(MigrationIssue("missing_attachment", entity, row.get("id"),
                                                 str(row.get("archive_no") or "")))
                continue
            attachment = attachments.get(attachment_id)
            if attachment is None:
                issues.append(MigrationIssue("missing_attachment", entity, row.get("id"),
                                             str(row.get("archive_no") or "")))
                continue
            content = bytes(attachment.get("content") or b"")
            digest = hashlib.sha256(content).hexdigest()
            attachment_inventory.append({
                "entity": entity, "local_id": row.get("id"), "attachment_id": attachment_id,
                "name": attachment.get("name") or "", "content": content, "sha256": digest,
            })
            expected = str(row.get("file_hash") or "") if entity == "resume_documents" else ""
            if expected and expected != digest:
                issues.append(MigrationIssue("attachment_hash_mismatch", entity, row.get("id"),
                                             str(row.get("archive_no") or "")))
    source["attachments"] = attachment_inventory

    candidate_ids = {row.get("id") for row in source["candidates"]}
    resume_keys = {str(row.get("source_id") or "") for row in source["resume_documents"]}
    for row in source["candidates"]:
        if not str(row.get("name") or "").strip() or not str(row.get("phone") or "").strip():
            issues.append(MigrationIssue("invalid_source_row", "candidates", row.get("id"),
                                         str(row.get("archive_no") or "")))
    for row in source["resume_documents"]:
        if any(not str(row.get(key) or "").strip() for key in ("archive_no", "source_id", "file_hash")):
            issues.append(MigrationIssue("invalid_source_row", "resume_documents", row.get("id"),
                                         str(row.get("archive_no") or "")))
    for table in ("applications", "interviews", "employees"):
        for row in source[table]:
            if row.get("candidate_id") is not None and row.get("candidate_id") not in candidate_ids:
                issues.append(MigrationIssue("invalid_reference", table, row.get("id")))
    for row in source["resume_imports"]:
        if row.get("candidate_id") not in candidate_ids or str(row.get("source_id") or "") not in resume_keys:
            issues.append(MigrationIssue("invalid_reference", "resume_imports"))

    target = {
        "candidates": services.candidates.list_all(""),
        "resume_documents": services.resumes.list_all(""),
    }
    target_attachments = []
    for row in target["candidates"]:
        attachment_id = row.get("resume")
        if attachment_id:
            content, _mime, filename = services.candidates.read_attachment(int(attachment_id))
            target_attachments.append({"entity": "candidates", "remote_id": row.get("id"),
                                       "name": filename, "sha256": hashlib.sha256(content).hexdigest()})
    for row in target["resume_documents"]:
        if row.get("resume"):
            content, _mime, filename = services.resumes.read_attachment(int(row["id"]))
            target_attachments.append({"entity": "resume_documents", "remote_id": row.get("id"),
                                       "name": filename, "sha256": hashlib.sha256(content).hexdigest()})
    for entity, fields in STABLE_KEYS.items():
        _duplicates(source[entity], fields, entity, issues, "local")
        _duplicates(target[entity], fields, entity, issues, "remote")
        _cross_conflicts(source[entity], target[entity], fields, entity, issues)

    preflight = getattr(services, "preflight", None)
    preflight_ok = bool(getattr(preflight, "ok", True))
    if not preflight_ok:
        issues.append(MigrationIssue("preflight_failed", "nocobase"))
    counts = {f"local_{table}": len(rows) for table, rows in source.items()}
    counts.update({f"remote_{table}": len(rows) for table, rows in target.items()})
    counts["remote_attachments"] = len(target_attachments)
    digests = {
        "source_rows": canonical_digest({key: value for key, value in source.items()
                                          if key not in ("attachments", *REFERENCE_TABLES)}),
        "attachments": canonical_digest(attachment_inventory),
        "references": canonical_digest({key: source[key] for key in REFERENCE_TABLES}),
        "target": canonical_digest({**target, "attachments": target_attachments}),
    }
    return MigrationInventory(source, target, counts, digests, issues, preflight_ok)
