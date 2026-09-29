"""Candidate validation independent of SQLite and the HTTP server module."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Callable

from features.candidates import experiences, positions, project_experiences, service as candidate_service

from .attachment_repository import AttachmentRepository


EDUCATION_FIELDS = ("education", "school_name", "major", "enrollment", "graduation")
EDUCATION_RANK = {"专科": 1, "本科": 2, "硕士": 3, "博士": 4}
PHONE_PATTERN = re.compile(r"(?:\+?86[- ]?)?(?:1[3-9]\d{9}|0\d{2,3}[- ]?\d{7,8}(?:-\d{1,6})?)")
EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
MONTH_PATTERN = re.compile(r"(\d{4})[-/年](\d{1,2})(?:月|[-/]\d{1,2})?")


def _month(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = MONTH_PATTERN.fullmatch(text)
    if not match or int(match.group(1)) < 1 or not 1 <= int(match.group(2)) <= 12:
        raise ValueError(f"{label}须为有效年月，如2026-07")
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"


def _education_rows(payload: dict) -> list[dict]:
    source = payload.get("education_experiences")
    if source is None:
        source = [{key: payload.get(key, "") for key in EDUCATION_FIELDS}]
    if not isinstance(source, list) or not 1 <= len(source) <= 10:
        raise ValueError("请填写1至10条教育经历")
    rows = []
    for index, row in enumerate(source, 1):
        if not isinstance(row, dict) or any(isinstance(row.get(key), (dict, list, bool)) for key in EDUCATION_FIELDS):
            raise ValueError(f"第{index}条教育经历格式不正确")
        values = {key: str(row.get(key) or "").strip() for key in EDUCATION_FIELDS}
        if values["education"] == "大专":
            values["education"] = "专科"
        if values["education"] not in EDUCATION_RANK:
            raise ValueError(f"请选择第{index}条教育经历的学历")
        for key, label in (("school_name", "毕业院校"), ("major", "专业")):
            if not values[key]:
                raise ValueError(f"请填写第{index}条教育经历的{label}")
        if any(len(value) > 300 for value in values.values()):
            raise ValueError(f"第{index}条教育经历内容过长")
        values["enrollment"] = _month(values["enrollment"], f"第{index}条教育经历的入学时间")
        values["graduation"] = _month(values["graduation"], f"第{index}条教育经历的毕业时间")
        if values["enrollment"] and values["graduation"] and values["enrollment"] > values["graduation"]:
            raise ValueError(f"第{index}条教育经历的入学时间不能晚于毕业时间")
        rows.append(values)
    return rows


def _main_values(payload: dict, schema: dict) -> dict:
    normalized = positions.normalize_payload(candidate_service.normalize_recruitment(payload))
    normalized.setdefault("status", "待筛选")
    normalized["political_status"] = candidate_service.normalize_political_status(
        normalized.get("political_status")
    )
    if normalized.get("recruitment_type") not in ("校园招聘", "社会招聘"):
        raise ValueError("请选择招聘类型")
    result = {}
    for field in schema.get("fields", []):
        key = field.get("key")
        if not key or field.get("virtual") or field.get("type") in ("attachment",) or field.get("ref"):
            continue
        value = normalized.get(key, "")
        if isinstance(value, (dict, list, bool)):
            raise ValueError(str(field.get("label") or key) + "格式不正确")
        value = str(value or "").strip()
        if field.get("required") and key not in EDUCATION_FIELDS and not value:
            raise ValueError("请填写" + str(field.get("label") or key))
        if len(value) > field.get("maxLength", 5000 if field.get("type") == "textarea" else 300):
            raise ValueError(str(field.get("label") or key) + "内容过长")
        if value and field.get("options") and value not in field["options"]:
            raise ValueError(str(field.get("label") or key) + "选项无效")
        if field.get("type") == "month":
            value = _month(value, str(field.get("label") or key))
            if key == "birthdate" and value > datetime.now().strftime("%Y-%m"):
                raise ValueError("出生日期不能晚于本月")
        if value and key == "phone" and not PHONE_PATTERN.fullmatch(value):
            raise ValueError("请填写有效手机号或带区号的固定电话")
        if value and field.get("type") == "email" and not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("邮箱格式不正确")
        if value and field.get("type") == "number":
            try:
                number = float(value)
            except ValueError:
                raise ValueError("年龄应在1至100之间") from None
            if not 1 <= number <= 100 or not number.is_integer():
                raise ValueError("年龄应在1至100之间")
            value = str(int(number))
        result[key] = value
    return result


def validate_remote_candidate(
    payload: dict, schema: dict, *, phone_exists: Callable[[str], bool],
) -> dict:
    """Normalize every aggregate component before any remote mutation occurs."""
    if not isinstance(payload, dict):
        raise ValueError("提交内容必须为对象")
    main = _main_values(payload, schema)
    phone = main.get("phone", "")
    if phone_exists(phone):
        raise ValueError("相同联系方式的人才已存在")
    education = _education_rows(payload)
    _key, work = experiences.payload_values(payload)
    work = work or []
    project = project_experiences.payload_values(payload, main["recruitment_type"])
    project = project or []
    highest = min(enumerate(education), key=lambda item: (-EDUCATION_RANK[item[1]["education"]], item[0]))[1]
    main.update({key: highest[key] for key in ("education", "school_name", "major")})
    main["graduation"] = highest["graduation"] if main["recruitment_type"] == "校园招聘" else ""

    upload = payload.get("_resume_upload")
    remove_resume = payload.get("_remove_resume", False)
    if type(remove_resume) is not bool:
        raise ValueError("移除附件标记无效")
    if upload is not None:
        AttachmentRepository._decode_upload(upload)
    if upload is not None and remove_resume:
        raise ValueError("不能同时上传和移除简历附件")
    return {
        "main": main,
        "education": education,
        "work": work,
        "project": project,
        "upload": upload,
        "remove_resume": remove_resume,
    }
