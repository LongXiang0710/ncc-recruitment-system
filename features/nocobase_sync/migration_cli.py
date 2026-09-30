"""Operator commands for checking and applying the guarded migration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .configure import default_data_dir
from .migration_apply import apply_migration, select_latest_eligible_report
from .migration_reports import check_migration, save_report


def main(argv=(), *, services_factory=None) -> int:
    arguments = list(argv)
    if not arguments or arguments[0] not in ("check", "apply"):
        print("用法：migration_cli.py [check|apply] SQLite文件")
        return 2
    if len(arguments) != 2:
        print("请指定复制后的SQLite数据库文件")
        return 2
    data_dir, sqlite_path = default_data_dir(), Path(arguments[1])
    try:
        if services_factory is None:
            from .http_adapter import build_migration_services
            services = build_migration_services(data_dir)
        else:
            services = services_factory(data_dir)
        if arguments[0] == "check":
            report = check_migration(sqlite_path, services)
            path = save_report(data_dir, report)
            print(("检查通过：" if report.eligible else "检查未通过：") + str(path))
            return 0 if report.eligible else 1
        report = select_latest_eligible_report(data_dir)
        journal = data_dir / "migration-reports" / "nocobase-migration-journal.json"
        result = apply_migration(sqlite_path, services, report, journal)
        print(f"迁移完成：人才{len(result.candidate_ids)}条，简历{len(result.resume_ids)}条。尚未启用NocoBase数据源。")
        return 0
    except Exception as error:
        diagnostic = getattr(error, "diagnostic_id", None)
        print("操作未完成" + (f"（诊断编号：{diagnostic}）" if diagnostic else "，请检查报告后重试"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
