"""Persistent configuration for the one-way NocoBase synchronization."""

from __future__ import annotations

import base64
import binascii
import ctypes
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit, urlunsplit


CONFIG_FILENAME = "nocobase-config.json"
CONFIG_VERSION = 2
_RECONFIGURE_MESSAGE = "无法解密 NocoBase API Key，请在当前 Windows 帐户下重新配置。"


@dataclass(frozen=True)
class NocoBaseConfig:
    """Validated connection values held only in process memory."""

    url: str
    api_key: str
    enabled: bool = True


class _DPAPIUnavailable(RuntimeError):
    """Raised when Windows DPAPI cannot be used on this computer."""


def normalize_url(value: str) -> str:
    """Return a canonical HTTP(S) URL without surrounding or trailing slashes."""
    if not isinstance(value, str):
        raise ValueError("NocoBase 地址必须是 HTTP 或 HTTPS 网址。")
    normalized = value.strip()
    if not normalized or any(character.isspace() or ord(character) < 32 for character in normalized):
        raise ValueError("NocoBase 地址必须是带主机名的 HTTP 或 HTTPS 网址。")
    try:
        parsed = urlsplit(normalized)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise ValueError("NocoBase 地址必须是带有效主机和端口的 HTTP 或 HTTPS 网址。") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is not None and not 1 <= port <= 65535
    ):
        raise ValueError("NocoBase 地址必须是带主机名的 HTTP 或 HTTPS 网址。")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _require_nonblank(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}不能为空。")
    return value


def _windows_crypto():
    if os.name != "nt":
        raise _DPAPIUnavailable("当前平台不支持 Windows DPAPI，请在 Windows 上配置 NocoBase。")
    try:
        return ctypes.WinDLL("Crypt32.dll", use_last_error=True), ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    except (AttributeError, OSError) as error:
        raise _DPAPIUnavailable("Windows DPAPI 不可用，请检查当前 Windows 配置。") from error


def _crypt(data: bytes, function_name: str) -> bytes:
    """Invoke a DPAPI routine and free its output DATA_BLOB with LocalFree."""
    if not isinstance(data, bytes):
        raise TypeError("DPAPI 输入必须是 bytes。")
    crypt32, kernel32 = _windows_crypto()

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]

    input_buffer = ctypes.create_string_buffer(data)
    input_blob = DATA_BLOB(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_char)))
    output_blob = DATA_BLOB()
    crypt_function = getattr(crypt32, function_name)
    description_argument = ctypes.c_wchar_p if function_name == "CryptProtectData" else ctypes.POINTER(ctypes.c_wchar_p)
    crypt_function.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        description_argument,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt_function.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    try:
        if not crypt_function(ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)):
            error_code = ctypes.get_last_error()
            raise _DPAPIUnavailable(
                f"Windows DPAPI 无法使用（错误 {error_code}），请在已加载用户配置文件的 Windows 帐户下重新配置。"
            )
        return bytes(output_blob.pbData[:int(output_blob.cbData)])
    finally:
        if output_blob.pbData:
            kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))


def _protect_password(value: bytes) -> bytes:
    return _crypt(value, "CryptProtectData")


def _unprotect_password(value: bytes) -> bytes:
    return _crypt(value, "CryptUnprotectData")


def _require_bytes(value: object, operation: str) -> bytes:
    if not isinstance(value, bytes):
        raise TypeError(f"{operation} 必须返回 bytes。")
    return value


def _config_path(data_dir: Path) -> Path:
    return Path(data_dir) / CONFIG_FILENAME


def save(
    data_dir: Path,
    url: str,
    api_key: str,
    enabled: bool = True,
    protect: Callable[[bytes], bytes] | None = None,
) -> None:
    """Validate, encrypt and atomically persist the NocoBase API settings."""
    normalized_url = normalize_url(url)
    api_key = _require_nonblank(api_key, "API Key")
    if type(enabled) is not bool:
        raise TypeError("启用开关必须是布尔值。")
    protector = protect if protect is not None else _protect_password
    ciphertext = _require_bytes(protector(api_key.encode("utf-8")), "API Key 保护函数")
    if not ciphertext:
        raise ValueError("API Key 保护函数返回了空密文，配置未保存。")
    payload = {
        "version": CONFIG_VERSION,
        "url": normalized_url,
        "api_key": base64.b64encode(ciphertext).decode("ascii"),
        "enabled": enabled,
    }

    destination = _config_path(data_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, prefix=".nocobase-config-", suffix=".tmp", delete=False
        ) as temporary:
            temporary_name = temporary.name
            json.dump(payload, temporary, ensure_ascii=False, separators=(",", ":"))
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def _read_payload(path: Path) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as source:
            payload = json.load(source)
    except (FileNotFoundError, OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("NocoBase 配置文件不存在或已损坏，请重新配置。") from error
    if isinstance(payload, dict) and set(payload) == {"version", "url", "username", "password"}:
        raise ValueError("NocoBase 旧账号密码配置已失效，请使用 API Key 重新配置。")
    if not isinstance(payload, dict) or set(payload) != {"version", "url", "api_key", "enabled"}:
        raise ValueError("NocoBase API Key 配置文件格式无效，请重新配置。")
    if (
        type(payload["version"]) is not int
        or payload["version"] != CONFIG_VERSION
        or not all(isinstance(payload[key], str) for key in ("url", "api_key"))
        or type(payload["enabled"]) is not bool
    ):
        raise ValueError("NocoBase 配置文件版本或字段无效，请重新配置。")
    return payload


def load(data_dir: Path, unprotect: Callable[[bytes], bytes] | None = None) -> NocoBaseConfig:
    """Load and decrypt a configuration, rejecting malformed or wrong-account data."""
    payload = _read_payload(_config_path(data_dir))
    try:
        ciphertext = base64.b64decode(payload["api_key"], validate=True)
    except (ValueError, binascii.Error, UnicodeEncodeError) as error:
        raise ValueError("NocoBase 配置文件中的密码密文无效，请重新配置。") from error
    if not ciphertext:
        raise ValueError("NocoBase 配置文件中的密码密文无效，请重新配置。")

    try:
        normalized_url = normalize_url(payload["url"])
    except ValueError as error:
        raise ValueError("NocoBase 配置文件字段无效，请重新配置。") from error

    unprotector = unprotect if unprotect is not None else _unprotect_password
    try:
        decrypted = unprotector(ciphertext)
    except _DPAPIUnavailable:
        raise
    except Exception as error:
        raise ValueError(_RECONFIGURE_MESSAGE) from error
    decrypted = _require_bytes(decrypted, "密码解密函数")
    try:
        api_key = decrypted.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(_RECONFIGURE_MESSAGE) from error
    if not api_key.strip():
        raise ValueError(_RECONFIGURE_MESSAGE)
    return NocoBaseConfig(normalized_url, api_key, payload["enabled"])


def configured(data_dir: Path, unprotect: Callable[[bytes], bytes] | None = None) -> bool:
    """Report whether a usable configuration is available without leaking its contents."""
    try:
        value = load(data_dir, unprotect=unprotect)
    except Exception:
        return False
    return bool(value.enabled and value.url.strip() and value.api_key.strip())
