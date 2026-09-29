"""Interactive, local-only configuration command for the NocoBase API."""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

from .backend import enable_nocobase, read_backend, write_backend
from .client import NocoBaseClient
from .config import load, save


def default_data_dir() -> Path:
    """Locate the application data directory without writing any credentials here."""
    configured_path = os.environ.get("RECRUIT_DATA_DIR")
    if configured_path:
        return Path(configured_path)
    return Path(__file__).resolve().parents[2] / "data"


def _configure() -> int:
    url = input("NocoBase 地址: ")
    api_key = getpass.getpass("NocoBase API Key（输入不显示）: ")
    try:
        save(default_data_dir(), url, api_key)
    except (RuntimeError, ValueError, TypeError) as error:
        print(f"配置未保存：{error}")
        return 1

    print("配置已保存。API Key 已用 Windows DPAPI 加密。")
    return 0


def _preflight(data_dir: Path):
    from .preflight import run_preflight
    return run_preflight(NocoBaseClient(load(data_dir)))


def main(argv=()) -> int:
    """Configure, check, enable or disable the NocoBase candidate backend."""
    arguments = list(argv)
    command = arguments[0].lower() if arguments else "configure"
    data_dir = default_data_dir()
    if command == "configure":
        return _configure()
    if command == "disable":
        write_backend(data_dir, "sqlite")
        print("人才库将在下次启动时使用 SQLite；现有数据和 NocoBase 配置均未删除。")
        return 0
    if command == "status":
        print("当前人才库数据源：" + read_backend(data_dir))
        return 0
    if command not in ("check", "enable"):
        print("用法：configure.py [configure|check|enable|disable|status]")
        return 2
    try:
        if command == "enable":
            enable_nocobase(data_dir, lambda: _preflight(data_dir))
            print("只读预检通过，人才库将在下次启动时使用 NocoBase。")
        else:
            report = _preflight(data_dir)
            if not report.ok:
                raise ValueError("NocoBase 只读预检未通过。")
            for check in report.checks:
                print("通过：" + check)
    except (RuntimeError, ValueError, TypeError) as error:
        print(f"操作未完成：{error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
