"""Small, secret-safe HTTP JSON client for NocoBase collection actions."""

from __future__ import annotations

import json
import socket
import uuid
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .config import NocoBaseConfig


@dataclass(frozen=True)
class NocoBaseResponse:
    data: object
    meta: dict | None = None


class NocoBaseError(RuntimeError):
    """A sanitized error safe to show or log without credentials or record data."""

    def __init__(self, kind: str, status: int | None, endpoint: str, diagnostic_id: str | None = None):
        self.kind = kind
        self.status = status
        self.endpoint = endpoint
        self.diagnostic_id = diagnostic_id or uuid.uuid4().hex[:12]
        labels = {
            "disabled": "NocoBase API 尚未启用",
            "authentication": "NocoBase API Key 无效或已过期",
            "permission": "NocoBase API 权限不足",
            "validation": "NocoBase 拒绝了请求参数",
            "network": "NocoBase 连接失败或超时",
            "remote": "NocoBase 服务暂时异常",
            "protocol": "NocoBase 返回了无效数据",
        }
        super().__init__(f"{labels.get(kind, 'NocoBase API 请求失败')}（诊断编号：{self.diagnostic_id}）")


class NocoBaseClient:
    def __init__(self, config: NocoBaseConfig, *, opener=urlopen, timeout: int = 30):
        self.config = config
        self.opener = opener
        self.timeout = timeout

    def _api_root(self) -> str:
        root = self.config.url.rstrip("/")
        return root if root.endswith("/api") else root + "/api"

    def _query_url(self, action: str, params: dict | None = None) -> tuple[str, str]:
        endpoint = action.lstrip("/")
        query = {}
        for key, value in (params or {}).items():
            if value in (None, "") or value == {}:
                continue
            query[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if isinstance(value, (dict, list)) else value
        url = f"{self._api_root()}/{endpoint}"
        if query:
            url += "?" + urlencode(query)
        return endpoint, url

    @staticmethod
    def _error_kind(status: int) -> str:
        return "authentication" if status == 401 else "permission" if status == 403 else "validation" if status in (400, 409, 422) else "remote"

    @staticmethod
    def _origin(parsed) -> tuple[str, str | None, int | None]:
        scheme = parsed.scheme.lower()
        port = parsed.port
        if port is None:
            port = 443 if scheme == "https" else 80 if scheme == "http" else None
        return scheme, parsed.hostname, port

    def _open(self, request: Request, endpoint: str):
        try:
            return self.opener(request, self.timeout)
        except HTTPError as error:
            status = error.code
            error.close()
            raise NocoBaseError(self._error_kind(status), status, endpoint) from None
        except (URLError, TimeoutError, socket.timeout, OSError):
            raise NocoBaseError("network", None, endpoint) from None

    @staticmethod
    def _json_payload(raw: bytes, endpoint: str) -> dict:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise NocoBaseError("protocol", None, endpoint) from None
        if not isinstance(payload, dict) or "data" not in payload:
            raise NocoBaseError("protocol", None, endpoint)
        return payload

    def request(self, action: str, *, method: str = "GET", params: dict | None = None,
                body: dict | None = None):
        return self.request_envelope(action, method=method, params=params, body=body).data

    def request_envelope(self, action: str, *, method: str = "GET", params: dict | None = None,
                         body: dict | None = None) -> NocoBaseResponse:
        endpoint, url = self._query_url(action, params)
        if not self.config.enabled:
            raise NocoBaseError("disabled", None, endpoint)
        data = None if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(url, data=data, method=method.upper(), headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
            "X-Locale": "zh-CN",
        })
        try:
            with self._open(request, endpoint) as response:
                raw = response.read()
        except NocoBaseError:
            raise
        payload = self._json_payload(raw, endpoint)
        meta = payload.get("meta")
        if meta is not None and not isinstance(meta, dict):
            raise NocoBaseError("protocol", None, endpoint)
        return NocoBaseResponse(payload["data"], meta)

    def upload(self, action: str, *, filename: str, mime_type: str, content: bytes,
               params: dict | None = None) -> dict:
        endpoint, url = self._query_url(action, params)
        if not self.config.enabled:
            raise NocoBaseError("disabled", None, endpoint)
        if not isinstance(content, bytes):
            raise TypeError("附件内容必须是 bytes。")
        safe_name = str(filename or "file").replace("\\", "/").rsplit("/", 1)[-1]
        safe_name = "".join("_" if character in '\"\r\n' or ord(character) < 32 else character
                            for character in safe_name) or "file"
        boundary = "----NocoBase" + uuid.uuid4().hex
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{safe_name}\"\r\n"
            f"Content-Type: {mime_type or 'application/octet-stream'}\r\n\r\n"
        ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("ascii")
        request = Request(url, data=body, method="POST", headers={
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {self.config.api_key}",
            "X-Locale": "zh-CN",
        })
        with self._open(request, endpoint) as response:
            payload = self._json_payload(response.read(), endpoint)
        data = payload["data"]
        if not isinstance(data, dict) or type(data.get("id")) is not int:
            raise NocoBaseError("protocol", None, endpoint)
        return data

    def download(self, url: str) -> tuple[bytes, str]:
        if not self.config.enabled:
            raise NocoBaseError("disabled", None, "attachment:download")
        try:
            parsed = urlsplit(str(url))
            configured = urlsplit(self.config.url)
            origin = self._origin(parsed)
            configured_origin = self._origin(configured)
        except ValueError as error:
            raise ValueError("附件地址无效。") from error
        if (parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username is not None
                or parsed.password is not None or parsed.fragment):
            raise ValueError("附件地址必须是有效的 HTTP 或 HTTPS 网址。")
        headers = {"Accept": "*/*"}
        if origin == configured_origin:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = Request(url, method="GET", headers=headers)
        with self._open(request, "attachment:download") as response:
            content = response.read()
            content_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].strip()
        return content, content_type or "application/octet-stream"
