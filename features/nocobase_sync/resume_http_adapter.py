"""HTTP boundary for NocoBase-backed resume collection operations."""

from __future__ import annotations

import base64
import csv
import io
import time
from urllib.parse import quote

import qrcode
import qrcode.image.svg

from excel_io import workbook_bytes

from . import diagnostics
from .client import NocoBaseError
from .remote_candidate_service import RemoteCandidateConsistencyError
from .remote_resume_service import RemoteResumeConsistencyError
from .resume_candidate_service import ResumeCandidateConsistencyError


def _query(query: dict, key: str, default: str = "") -> str:
    value = query.get(key, [default])
    return str(value[0] if isinstance(value, list) and value else value or default)


def _ids(value) -> list[int]:
    if not isinstance(value, list) or not 1 <= len(value) <= 1000 or any(
        type(identifier) is not int or identifier <= 0 for identifier in value
    ):
        raise ValueError("请选择1至1000条有效记录")
    return list(dict.fromkeys(value))


def _rows(service, ids):
    result = []
    for identifier in _ids(ids):
        row = service.get(identifier)
        if row is None:
            raise ValueError("记录已不存在，请刷新列表")
        result.append(row)
    return result


def _export(handler, rows, *, excel: bool):
    spec = handler.server.resume_schema
    if excel:
        host = handler.headers.get("Host", "")
        return handler.send(
            200, workbook_bytes(spec, rows, attachment_base_url="http://" + host if host else ""),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(spec['title'])}.xlsx"},
        )
    fields = [field for field in spec["fields"] if field.get("export", True) and not field.get("hidden")]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["编号", *[field["label"] for field in fields], "创建时间"])
    for row in rows:
        writer.writerow([row["id"], *[row.get(field["key"], "") for field in fields], row.get("created_at", "")])
    return handler.send(
        200, ("\ufeff" + output.getvalue()).encode("utf-8"), "text/csv; charset=utf-8",
        {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(spec['title'])}.csv"},
    )


def _handle(handler, method: str, identifier: str | None, query: dict):
    services = handler.server.remote_services
    resumes = services.resumes
    links = services.resume_candidates
    recognition = services.recognition
    if method == "GET" and identifier is None:
        text = _query(query, "q").strip()
        if "page" in query or "pageSize" in query:
            return handler.send(200, resumes.list(
                int(_query(query, "page", "1")), int(_query(query, "pageSize", "20")), text,
            ))
        return handler.send(200, resumes.list_all(text))
    if method == "GET" and identifier == "pending":
        return handler.send(200, resumes.pending())
    if method == "GET" and identifier and identifier.isdigit():
        row = resumes.get(int(identifier))
        return handler.send(200, row) if row else handler.send(404, {"error": "记录不存在"})
    if method == "POST" and identifier is None:
        return handler.send(201, {"id": resumes.create(handler.body())})
    if method == "POST" and identifier == "batch-import":
        payload = handler.body()
        items = payload.get("items") if isinstance(payload, dict) else None
        identifiers = resumes.create_many(items)
        return handler.send(201, {"count": len(identifiers), "ids": identifiers})
    if method == "PUT" and identifier and identifier.isdigit():
        resumes.update(int(identifier), handler.body())
        return handler.send(200, {"ok": True})
    if method == "DELETE" and identifier and identifier.isdigit():
        links.delete_resumes([int(identifier)])
        return handler.send(200, {"ok": True})
    if method == "POST" and identifier == "delete-preview":
        details = links.resume_delete_preview(handler.body().get("ids"))
        return handler.send(200, {"items": details, "count": len(details)})
    if method == "POST" and identifier == "batch-delete":
        payload = handler.body()
        return handler.send(200, {"count": links.delete_resumes(
            payload.get("ids"), payload.get("expected"),
        )})
    if identifier and "/" in identifier:
        number, action = identifier.split("/", 1)
        if number.isdigit() and method == "POST" and action == "recognize":
            return handler.send(200, {"result": recognition.recognize(int(number))})
        if number.isdigit() and method == "GET" and action == "recognition-result":
            return handler.send(200, {"result": recognition.result(int(number))})
        if number.isdigit() and method == "POST" and action == "candidate":
            result = links.import_candidate(int(number))
            return handler.send(201, {"id": result.candidate_id,
                                      "already_imported": result.already_imported})
    if method == "POST" and identifier == "export.xlsx":
        return _export(handler, _rows(resumes, handler.body().get("ids")), excel=True)
    if method == "GET" and identifier in ("export", "export.xlsx"):
        return _export(handler, resumes.list_all(_query(query, "q").strip()),
                       excel=identifier.endswith(".xlsx"))
    if method == "POST" and identifier == "qr-print":
        items = []
        host = handler.headers.get("Host", "localhost:8116")
        for row in _rows(resumes, handler.body().get("ids")):
            url = f"http://{host}/?module=resume_documents&record={row['id']}"
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                               box_size=6, border=4)
            qr.add_data(url); qr.make(fit=True)
            svg = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).to_string()
            items.append({"id": row["id"], "title": row.get("name") or str(row["id"]),
                          "url": url, "image": "data:image/svg+xml;base64," +
                          base64.b64encode(svg).decode("ascii")})
        return handler.send(200, {"title": handler.server.resume_schema["title"], "items": items})
    return handler.send(405, {"error": "不支持此操作"})


def handle_remote_resume_request(handler, method: str, identifier: str | None,
                                 query: dict) -> bool:
    if getattr(handler.server, "remote_services", None) is None:
        return False
    started = time.monotonic()
    try:
        _handle(handler, method, identifier, query)
    except NocoBaseError as error:
        status = 503 if error.kind in ("network", "remote", "disabled") else 502
        diagnostic_id = diagnostics.record("resume-api", status=error.status,
                                           elapsed=time.monotonic() - started,
                                           diagnostic_id=error.diagnostic_id)
        handler.send(status, {"error": f"NocoBase 简历库暂时不可用（诊断编号：{diagnostic_id}）"})
    except (RemoteResumeConsistencyError, RemoteCandidateConsistencyError,
            ResumeCandidateConsistencyError) as error:
        diagnostics.record("resume-compensation", status=None,
                           elapsed=time.monotonic() - started,
                           diagnostic_id=error.diagnostic_id)
        handler.send(409, {"error": str(error)})
    return True


def handle_public_remote_resume_request(handler, method: str, kind: str) -> bool:
    if getattr(handler.server, "remote_services", None) is None:
        return False
    if method != "POST" or kind not in ("campus", "social"):
        handler.send(405, {"error": "不支持此操作"})
        return True
    started = time.monotonic()
    try:
        submitted = handler.body()
        if not isinstance(submitted, dict):
            raise ValueError("提交内容必须为对象")
        def public_payload(item):
            if not isinstance(item, dict):
                raise ValueError("简历批量提交内容无效")
            return {
                "recruitment_type": "校园招聘" if kind == "campus" else "社会招聘",
                "channel": item.get("channel") or ("校园线下" if kind == "campus" else ""),
                "channel_detail": item.get("channel_detail") or "",
                "position": item.get("position") or "",
                "position_detail": item.get("position_detail") or "",
                "_resume_upload": item.get("_resume_upload"),
            }
        if "items" in submitted:
            items = submitted.get("items")
            if not isinstance(items, list):
                raise ValueError("简历批量提交内容无效")
            identifiers = handler.server.remote_services.resumes.create_many(
                [public_payload(item) for item in items], public=True,
            )
            handler.send(201, {"ok": True, "count": len(identifiers)})
        else:
            handler.server.remote_services.resumes.create_public(public_payload(submitted))
            handler.send(201, {"ok": True})
    except NocoBaseError as error:
        status = 503 if error.kind in ("network", "remote", "disabled") else 502
        diagnostic_id = diagnostics.record("public-resume-api", status=error.status,
                                           elapsed=time.monotonic() - started,
                                           diagnostic_id=error.diagnostic_id)
        handler.send(status, {"error": f"简历提交服务暂时不可用（诊断编号：{diagnostic_id}）"})
    return True
