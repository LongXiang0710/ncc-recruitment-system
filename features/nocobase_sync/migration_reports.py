"""Create and persist redacted migration eligibility reports."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from .migration_inventory import build_inventory
from .migration_models import MigrationReport


def load_report(path: Path) -> MigrationReport:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("迁移检查报告无法读取") from error
    return MigrationReport.from_redacted(payload)


def check_migration(sqlite_path: Path, services, *, now=None) -> MigrationReport:
    generated = (now or datetime.now)()
    inventory = build_inventory(sqlite_path, services)
    return MigrationReport(
        generated_at=generated,
        expires_at=generated + timedelta(hours=24),
        eligible=inventory.preflight_ok and not inventory.issues,
        counts=dict(inventory.counts),
        digests=dict(inventory.digests),
        issues=tuple(inventory.issues),
    )


def save_report(data_dir: Path, report: MigrationReport) -> Path:
    directory = Path(data_dir) / "migration-reports"
    directory.mkdir(parents=True, exist_ok=True)
    name = "nocobase-check-" + report.generated_at.strftime("%Y%m%d-%H%M%S") + ".json"
    destination = directory / name
    payload = json.dumps(report.redacted(), ensure_ascii=False, indent=2, sort_keys=True)
    handle, temporary = tempfile.mkstemp(prefix=name + ".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    text_path = destination.with_suffix(".txt")
    lines = [
        "NocoBase 迁移只读检查报告",
        "生成时间：" + report.generated_at.isoformat(),
        "有效期至：" + report.expires_at.isoformat(),
        "结论：" + ("允许迁移" if report.eligible else "不允许迁移"),
        "问题数量：" + str(len(report.issues)),
    ]
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
