"""Interactive, local-only configuration command for the NocoBase API."""

from __future__ import annotations

import getpass
import os
from pathlib import Path

from .config import load, save


def default_data_dir() -> Path:
    """Locate the application data directory without writing any credentials here."""
    configured_path = os.environ.get("RECRUIT_DATA_DIR")
    if configured_path:
        return Path(configured_path)
    return Path(__file__).resolve().parents[2] / "data"


def main() -> int:
    """Prompt for a local API endpoint and hidden API Key."""
    url = input("NocoBase 地址: ")
    api_key = getpass.getpass("NocoBase API Key（输入不显示）: ")
    try:
        save(default_data_dir(), url, api_key)
    except (RuntimeError, ValueError, TypeError) as error:
        print(f"配置未保存：{error}")
        return 1

    print("配置已保存。API Key 已用 Windows DPAPI 加密。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
