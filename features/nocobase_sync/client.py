"""Small, secret-safe HTTP JSON client for NocoBase collection actions."""

from __future__ import annotations

import json
import socket
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import NocoBaseConfig


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

    def request(self, action: str, *, method: str = "GET", params: dict | None = None,
                body: dict | None = None):
        endpoint = action.lstrip("/")
        if not self.config.enabled:
            raise NocoBaseError("disabled", None, endpoint)
        query = {}
        for key, value in (params or {}).items():
            if value in (None, "") or value == {}:
                continue
            query[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if isinstance(value, (dict, list)) else value
        url = f"{self._api_root()}/{endpoint}"
        if query:
            url += "?" + urlencode(query)
        data = None if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(url, data=data, method=method.upper(), headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
            "X-Locale": "zh-CN",
        })
        try:
            with self.opener(request, self.timeout) as response:
                raw = response.read()
        except HTTPError as error:
            kind = "authentication" if error.code == 401 else "permission" if error.code == 403 else "validation" if error.code in (400, 409, 422) else "remote"
            error.close()
            raise NocoBaseError(kind, error.code, endpoint) from None
        except (URLError, TimeoutError, socket.timeout, OSError):
            raise NocoBaseError("network", None, endpoint) from None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise NocoBaseError("protocol", None, endpoint) from None
        if not isinstance(payload, dict) or "data" not in payload:
            raise NocoBaseError("protocol", None, endpoint)
        return payload["data"]
