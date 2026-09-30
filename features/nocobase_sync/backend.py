"""Fail-safe selection of the unified recruitment data backend."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Callable, Literal

from .config import load


BACKEND_FILENAME = "recruitment-backend.json"
BACKEND_VERSION = 1
BackendName = Literal["sqlite", "nocobase"]


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / BACKEND_FILENAME


def read_backend(data_dir: Path) -> BackendName:
    """Return sqlite unless the selector is an exact, valid NocoBase opt-in."""
    try:
        payload = json.loads(_path(data_dir).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "sqlite"
    if payload == {"version": BACKEND_VERSION, "backend": "nocobase"}:
        return "nocobase"
    return "sqlite"


def write_backend(data_dir: Path, value: BackendName) -> None:
    if value not in ("sqlite", "nocobase"):
        raise ValueError("人才库数据源必须是 sqlite 或 nocobase。")
    destination = _path(data_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=".recruitment-backend-", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump({"version": BACKEND_VERSION, "backend": value}, temporary,
                      ensure_ascii=False, separators=(",", ":"))
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def _require_config(data_dir: Path):
    try:
        configuration = load(data_dir)
    except Exception as error:
        raise ValueError("NocoBase 配置无效，请先重新配置。") from error
    if not configuration.enabled:
        raise ValueError("NocoBase API 尚未启用。")
    return configuration


def _require_preflight(preflight: Callable[[], object]) -> object:
    report = preflight()
    if getattr(report, "ok", False) is not True:
        raise ValueError("NocoBase 只读预检未通过，简历收集和人才库未启用。")
    return report


def enable_nocobase(data_dir: Path, preflight: Callable[[], object]) -> None:
    _require_config(data_dir)
    _require_preflight(preflight)
    write_backend(data_dir, "nocobase")


def select_candidate_backend(
    data_dir: Path, *, preflight: Callable[[], object] | None = None,
) -> BackendName:
    selected = read_backend(data_dir)
    if selected == "sqlite":
        return selected
    _require_config(data_dir)
    if preflight is not None:
        _require_preflight(preflight)
    return "nocobase"
