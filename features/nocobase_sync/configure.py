"""Interactive, local-only configuration command for NocoBase synchronization."""

from __future__ import annotations

import getpass
import os
from importlib import import_module
from pathlib import Path

from .config import load, save


def default_data_dir() -> Path:
    """Locate the application data directory without writing any credentials here."""
    configured_path = os.environ.get("RECRUIT_DATA_DIR")
    if configured_path:
        return Path(configured_path)
    return Path(__file__).resolve().parents[2] / "data"


def main() -> int:
    """Prompt for local credentials and optionally perform a read-only login check."""
    url = input("NocoBase 地址: ")
    username = input("NocoBase 用户名: ")
    password = getpass.getpass("NocoBase 密码: ")
    try:
        save(default_data_dir(), url, username, password)
    except (RuntimeError, ValueError, TypeError) as error:
        print(f"配置未保存：{error}")
        return 1

    print("配置已保存。")
    if input("是否测试连接？[y/N]: ").strip().lower() not in {"y", "yes"}:
        return 0

    try:
        test_login = import_module("features.nocobase_sync.browser").test_login
    except (ImportError, AttributeError):
        print("配置已保存，连接测试将在浏览器模块完成后可用")
        return 0

    try:
        test_login(load(default_data_dir()))
    except Exception:
        print("连接测试失败，请检查 NocoBase 地址、账号和网络后重试。")
        return 1
    print("连接测试成功。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
