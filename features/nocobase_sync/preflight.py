"""Strict, read-only discovery of the NocoBase talent-pool schema."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .candidate_mapping import LOCAL_TO_REMOTE
from .client import NocoBaseClient, NocoBaseError


ENDPOINT = "swagger:get"
NAMESPACE = "collections/campus_talent_pool"
RESUME_NAMESPACE = "collections/Resume_Collection"

RELATIONS = {
    "Education_Background": "hasMany",
    "Work_experience": "hasMany",
    "Project_Experience": "hasMany",
    "biographical_notes": "belongsToMany",
}

FIELD_TITLES = {
    "Education_Background": {
        "education": "学历",
        "school_name": "毕业院校",
        "major": "专业",
        "enrollment": "入学时间",
        "graduation": "毕业日期",
    },
    "Work_experience": {
        "organization": "工作单位",
        "position": "岗位",
        "start_date": "开始时间",
        "end_date": "结束时间",
        "description": "工作描述",
    },
    "Project_Experience": {
        "project_name": "项目名称",
        "role": "担任角色",
        "start_date": "开始时间",
        "end_date": "结束时间",
        "description": "项目描述",
    },
}

DATE_FIELDS = {
    ("Education_Background", "enrollment"),
    ("Education_Background", "graduation"),
    ("Work_experience", "start_date"),
    ("Work_experience", "end_date"),
    ("Project_Experience", "start_date"),
    ("Project_Experience", "end_date"),
}
ALLOWED_DATE_FORMATS = {None, "date", "date-time", "month", "year-month"}

RESUME_FIELDS = MappingProxyType({
    "archive_no": "Number",
    "status": "Processing_Status",
    "name": "name",
    "recruitment_type": "Job_Type",
    "campus_channel": "Campus_recruitment_channels",
    "social_channel": "External_hiring_channels",
    "channel_detail": "Details",
    "position": "Job",
    "position_detail": "Other_job_titles",
    "created_by": "Creator",
    "created_at": "time",
    "source_id": "source_id",
    "file_hash": "file_hash",
    "recognition_result": "recognition_result",
    "linked_candidate": "linked_candidate",
})


@dataclass(frozen=True)
class RelationFieldMap:
    education: Mapping[str, str]
    work: Mapping[str, str]
    project: Mapping[str, str]


@dataclass(frozen=True)
class PreflightReport:
    ok: bool
    checks: tuple[str, ...]
    relation_fields: RelationFieldMap
    resume_fields: Mapping[str, str]


def _protocol() -> NocoBaseError:
    return NocoBaseError("protocol", None, ENDPOINT)


def _operation(paths: dict, path: str, method: str) -> dict:
    item = paths.get(path)
    if not isinstance(item, dict) or not isinstance(item.get(method), dict):
        raise _protocol()
    return item


def _schema(schemas: dict, name: str) -> dict:
    matches = [value for key, value in schemas.items()
               if key == name or key.endswith("." + name)]
    if len(matches) != 1 or not isinstance(matches[0], dict):
        raise _protocol()
    schema = matches[0]
    if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
        raise _protocol()
    return schema


def _validate_main_schema(schema: dict) -> None:
    properties = schema["properties"]
    if not isinstance(properties.get("id"), dict) or properties["id"].get("type") != "integer":
        raise _protocol()


def _validate_resume_schema(schema: dict) -> Mapping[str, str]:
    properties = schema["properties"]
    if not isinstance(properties.get("id"), dict) or properties["id"].get("type") != "integer":
        raise _protocol()
    required = {
        "Number", "Processing_Status", "name", "Job_Type",
        "Campus_recruitment_channels", "External_hiring_channels", "Details",
        "Job", "Other_job_titles", "Creator", "time", "source_id",
    }
    if any(not isinstance(properties.get(key), dict) or properties[key].get("type") != "string"
           for key in required):
        raise _protocol()
    linked = properties.get("linked_candidate")
    if linked is not None and (not isinstance(linked, dict)
            or linked.get("x-association-type") != "belongsTo"
            or linked.get("x-target") != "campus_talent_pool"):
        raise _protocol()
    resolved = {}
    for local, remote in RESUME_FIELDS.items():
        definition = properties.get(remote)
        if not isinstance(definition, dict):
            continue
        if local != "linked_candidate" and definition.get("type") != "string":
            raise _protocol()
        resolved[local] = remote
    return MappingProxyType(resolved)


def _document(client: NocoBaseClient, namespace: str) -> tuple[dict, dict]:
    document = client.request(ENDPOINT, params={"ns": namespace})
    if not isinstance(document, dict):
        raise _protocol()
    paths = document.get("paths")
    components = document.get("components")
    schemas = components.get("schemas") if isinstance(components, dict) else None
    if not isinstance(paths, dict) or not isinstance(schemas, dict) or not schemas:
        raise _protocol()
    return paths, schemas
    required = set(LOCAL_TO_REMOTE.values()) | {"channel", "Social_recruitment_channels"}
    if any(not isinstance(properties.get(key), dict) or properties[key].get("type") != "string"
           for key in required):
        raise _protocol()


def _resolve_fields(relation: str, schema: dict) -> Mapping[str, str]:
    properties = schema["properties"]
    by_title: dict[str, list[tuple[str, dict]]] = {}
    for remote_key, definition in properties.items():
        if isinstance(definition, dict) and isinstance(definition.get("title"), str):
            by_title.setdefault(definition["title"], []).append((remote_key, definition))

    resolved = {}
    for local_key, title in FIELD_TITLES[relation].items():
        matches = by_title.get(title, [])
        if len(matches) != 1:
            raise _protocol()
        remote_key, definition = matches[0]
        if definition.get("type") != "string":
            raise _protocol()
        if (relation, local_key) in DATE_FIELDS and definition.get("format") not in ALLOWED_DATE_FORMATS:
            raise _protocol()
        resolved[local_key] = remote_key
    return MappingProxyType(resolved)


def run_preflight(client: NocoBaseClient) -> PreflightReport:
    """Read and validate Swagger metadata without issuing any mutation request."""
    paths, schemas = _document(client, NAMESPACE)

    for action in ("list", "get", "create", "update", "destroy"):
        method = "get" if action in ("list", "get") else "post"
        _operation(paths, f"/campus_talent_pool:{action}", method)

    relation_schemas = {}
    for relation, expected_type in RELATIONS.items():
        relation_schema = _schema(schemas, f"campus_talent_pool.{relation}")
        if relation_schema.get("x-association-type") not in (None, expected_type):
            raise _protocol()
        relation_schemas[relation] = relation_schema
        for action in ("list", "get", "create", "update", "destroy", "set", "remove", "toggle"):
            method = "get" if action in ("list", "get") else "post"
            item = _operation(
                paths,
                f"/campus_talent_pool/{{collectionIndex}}/{relation}:{action}",
                method,
            )
            association_type = item.get("x-association-type")
            if association_type is not None and association_type != expected_type:
                raise _protocol()

    _validate_main_schema(_schema(schemas, "campus_talent_pool"))
    relation_fields = RelationFieldMap(
        education=_resolve_fields("Education_Background", relation_schemas["Education_Background"]),
        work=_resolve_fields("Work_experience", relation_schemas["Work_experience"]),
        project=_resolve_fields("Project_Experience", relation_schemas["Project_Experience"]),
    )
    resume_paths, resume_schemas = _document(client, RESUME_NAMESPACE)
    for action in ("list", "get", "create", "update", "updateOrCreate", "destroy"):
        method = "get" if action in ("list", "get") else "post"
        _operation(resume_paths, f"/Resume_Collection:{action}", method)
    resume_relation = _schema(resume_schemas, "Resume_Collection.Resume")
    if resume_relation.get("x-association-type") not in (None, "belongsToMany"):
        raise _protocol()
    for action in ("list", "get", "create", "update", "destroy", "set", "remove", "toggle"):
        method = "get" if action in ("list", "get") else "post"
        item = _operation(
            resume_paths,
            f"/Resume_Collection/{{collectionIndex}}/Resume:{action}",
            method,
        )
        if item.get("x-association-type") not in (None, "belongsToMany"):
            raise _protocol()
    resume_fields = _validate_resume_schema(_schema(resume_schemas, "Resume_Collection"))

    return PreflightReport(
        ok=True,
        checks=("candidate-collection", "candidate-crud", "candidate-relations",
                "candidate-fields", "resume-collection", "resume-crud",
                "resume-relation", "resume-fields"),
        relation_fields=relation_fields,
        resume_fields=resume_fields,
    )
