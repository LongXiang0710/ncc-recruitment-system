"""HTTP boundary for the explicitly selected NocoBase candidate backend."""

from __future__ import annotations

import base64
import csv
import io
import json
import secrets
import time
from pathlib import Path
from urllib.parse import quote

import qrcode
import qrcode.image.svg

from excel_io import workbook_bytes

from . import diagnostics
from .attachment_repository import AttachmentRepository
from .backend import read_backend, select_candidate_backend
from .candidate_repository import CandidateRepository
from .client import NocoBaseClient, NocoBaseError
from .config import load
from .preflight import run_preflight
from .relation_repository import RelationRepository
from .remote_candidate_service import RemoteCandidateConsistencyError, RemoteCandidateService


def build_candidate_service(data_dir: Path) -> RemoteCandidateService | None:
    """Build exactly one backend at startup; sqlite mode performs no API work."""
    data_dir = Path(data_dir)
    if read_backend(data_dir) != "nocobase":
        return None
    client = NocoBaseClient(load(data_dir))
    report = run_preflight(client)
    select_candidate_backend(data_dir, preflight=lambda: report)
    schema_path = Path(__file__).parents[1] / "candidates" / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return RemoteCandidateService(
        CandidateRepository(client),
        RelationRepository(client, report.relation_fields),
        AttachmentRepository(client),
        schema,
    )


def _query_value(query: dict, key: str, default: str = "") -> str:
    value = query.get(key, [default])
    return str(value[0] if isinstance(value, list) and value else value or default)


def _ids(value: object, maximum: int = 1000) -> list[int]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum or any(
        type(identifier) is not int or identifier <= 0 for identifier in value
    ):
        raise ValueError(f"请选择1至{maximum}条有效记录")
    return list(dict.fromkeys(value))


def _rows_for_ids(service, ids: list[int]) -> list[dict]:
    rows = []
    for identifier in _ids(ids):
        row = service.get(identifier)
        if row is None:
            raise ValueError(f"记录{identifier}已不存在，请刷新列表")
        rows.append(row)
    return rows


def _send_export(handler, rows: list[dict], *, excel: bool):
    spec = handler.server.candidate_schema
    if excel:
        host = handler.headers.get("Host", "")
        base = ("http://" + host) if host else ""
        return handler.send(
            200, workbook_bytes(spec, rows, attachment_base_url=base),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(spec['title'])}.xlsx"},
        )
    output = io.StringIO()
    fields = [field for field in spec["fields"] if field.get("export", True) and not field.get("hidden")]
    writer = csv.writer(output)
    writer.writerow(["编号", *[field["label"] for field in fields], "创建时间"])
    for row in rows:
        values = [row["id"], *[row.get(field["key"] + "_label" if field.get("ref") else field["key"], "") for field in fields], row.get("created_at", "")]
        writer.writerow(["'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value for value in values])
    return handler.send(
        200, ("\ufeff" + output.getvalue()).encode("utf-8"), "text/csv; charset=utf-8",
        {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(spec['title'])}.csv"},
    )


def _import_preview(handler, service):
    preview = handler.server.candidate_import_preparer(handler.body())
    errors = list(preview.get("errors", []))
    valid_rows = []
    phones = set()
    for row in preview.get("rows", []):
        try:
            normalized = service.validate(row["values"])
            phone = normalized["main"]["phone"]
            if phone in phones:
                raise ValueError("批量导入中存在重复联系方式")
            phones.add(phone)
            valid_rows.append(row)
        except ValueError as error:
            errors.append({"line": row["line"], "error": str(error)})
    token = None
    store = handler.server.candidate_imports
    now = time.time()
    for key in list(store):
        if store[key]["expires"] < now:
            store.pop(key, None)
    if not errors:
        if len(store) >= 100:
            raise ValueError("当前待导入任务过多，请稍后重试")
        token = secrets.token_urlsafe(24)
        store[token] = {
            "session": handler.session(), "expires": now + 900,
            "rows": [row["values"] for row in valid_rows],
        }
    response = {**preview, "errors": errors, "rows": valid_rows[:20],
                "total": len(preview.get("rows", [])) + len(preview.get("errors", [])), "token": token}
    return handler.send(200, response)


def _handle(handler, method: str, identifier: str | None, query: dict):
    service = handler.server.candidate_service
    if identifier and identifier.startswith("attachment:"):
        if method != "GET" or not identifier.removeprefix("attachment:").isdigit():
            return handler.send(405, {"error": "不支持此操作"})
        content, mime_type, filename = service.read_attachment(int(identifier.split(":", 1)[1]))
        return handler.send(200, content, mime_type, {
            "Content-Disposition": "inline; filename*=UTF-8''" + quote(filename),
        })

    if method == "GET" and identifier is None:
        query_text = _query_value(query, "q").strip()
        if "page" in query or "pageSize" in query:
            result = service.list(
                page=int(_query_value(query, "page", "1")),
                page_size=int(_query_value(query, "pageSize", "20")),
                query=query_text,
            )
            return handler.send(200, result)
        return handler.send(200, service.list_all(query_text))
    if method == "GET" and identifier and identifier.isdigit():
        row = service.get(int(identifier))
        return handler.send(200, row) if row else handler.send(404, {"error": "记录不存在"})
    if method == "POST" and identifier is None:
        return handler.send(201, {"id": service.create(handler.body())})
    if method == "PUT" and identifier and identifier.isdigit():
        service.update(int(identifier), handler.body())
        return handler.send(200, {"ok": True})
    if method == "DELETE" and identifier and identifier.isdigit():
        preview = service.delete_preview([int(identifier)])["details"]
        service.delete([int(identifier)], preview)
        return handler.send(200, {"ok": True})
    if method == "POST" and identifier == "delete-preview":
        details = service.delete_preview(handler.body().get("ids"))["details"]
        return handler.send(200, {"items": details, "count": len(details)})
    if method == "POST" and identifier == "batch-delete":
        payload = handler.body()
        count = service.delete(payload.get("ids"), payload.get("expected") or service.delete_preview(payload.get("ids"))["details"])
        return handler.send(200, {"count": count})
    if method == "POST" and identifier == "import-preview":
        return _import_preview(handler, service)
    if method == "POST" and identifier == "import-commit":
        token = str(handler.body().get("token") or "")
        store = handler.server.candidate_imports
        job = store.get(token)
        if not job or job["session"] != handler.session() or job["expires"] < time.time():
            raise ValueError("预览已过期或已提交，请重新识别文件")
        store.pop(token, None)
        identifiers = service.create_many(job["rows"])
        return handler.send(201, {"count": len(identifiers), "ids": identifiers})
    if method == "POST" and identifier == "export.xlsx":
        return _send_export(handler, _rows_for_ids(service, handler.body().get("ids")), excel=True)
    if method == "GET" and identifier in ("export", "export.xlsx"):
        return _send_export(handler, service.list_all(_query_value(query, "q").strip()), excel=identifier.endswith(".xlsx"))
    if method == "GET" and identifier == "template.xlsx":
        return handler.send(200, workbook_bytes(handler.server.candidate_schema, [], template=True),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if method == "POST" and identifier == "qr-print":
        ids = _ids(handler.body().get("ids"), maximum=100)
        items = []
        host = handler.headers.get("Host", "localhost:8116")
        for row in _rows_for_ids(service, ids):
            url = f"http://{host}/?module=candidates&record={row['id']}"
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=4)
            qr.add_data(url); qr.make(fit=True)
            svg = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).to_string()
            items.append({"id": row["id"], "title": row.get("name") or str(row["id"]), "url": url,
                          "image": "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")})
        return handler.send(200, {"title": handler.server.candidate_schema["title"], "items": items})
    return handler.send(405, {"error": "不支持此操作"})


def handle_remote_candidate_request(handler, method: str, identifier: str | None,
                                    query: dict) -> bool:
    """Handle a candidate request without falling through to SQLite."""
    if getattr(handler.server, "candidate_service", None) is None:
        return False
    started = time.monotonic()
    try:
        _handle(handler, method, identifier, query)
    except NocoBaseError as error:
        status = 400 if error.kind == "validation" else 503 if error.kind in ("network", "remote", "disabled") else 502
        diagnostic_id = diagnostics.record(
            "candidate-api", status=error.status, elapsed=time.monotonic() - started,
            diagnostic_id=error.diagnostic_id,
        )
        handler.send(status, {"error": f"NocoBase 人才库暂时不可用（诊断编号：{diagnostic_id}）"})
    except RemoteCandidateConsistencyError as error:
        diagnostics.record("candidate-compensation", status=None, elapsed=time.monotonic() - started,
                           diagnostic_id=error.diagnostic_id)
        handler.send(409, {"error": str(error)})
    return True
