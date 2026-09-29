"""Repository for NocoBase talent-pool education, work and project rows."""

from __future__ import annotations

import re

from .client import NocoBaseClient, NocoBaseError
from .preflight import RelationFieldMap


RELATIONS = {
    "education": "Education_Background",
    "work": "Work_experience",
    "project": "Project_Experience",
}
DATE_KEYS = {
    "education": {"enrollment", "graduation"},
    "work": {"start_date", "end_date"},
    "project": {"start_date", "end_date"},
}


class RelationRepository:
    COLLECTION = "campus_talent_pool"

    def __init__(self, client: NocoBaseClient, fields: RelationFieldMap):
        self.client = client
        self.fields = {
            "education": fields.education,
            "work": fields.work,
            "project": fields.project,
        }

    @staticmethod
    def _candidate_id(value: int) -> int:
        if type(value) is not int or value <= 0:
            raise ValueError("人才记录编号无效")
        return value

    @staticmethod
    def _relation(value: str) -> str:
        if value not in RELATIONS:
            raise ValueError("人才经历类型无效")
        return value

    def _action(self, candidate_id: int, relation: str, action: str) -> str:
        return f"{self.COLLECTION}/{candidate_id}/{RELATIONS[relation]}:{action}"

    def _raw_list(self, candidate_id: int, relation: str) -> list[dict]:
        data = self.client.request(
            self._action(candidate_id, relation, "list"),
            params={"pageSize": 10},
        )
        if not isinstance(data, list) or any(
            not isinstance(row, dict) or type(row.get("id")) is not int for row in data
        ):
            raise NocoBaseError("protocol", None, self._action(candidate_id, relation, "list"))
        return data

    @staticmethod
    def _from_date(value: object) -> str:
        if value in (None, ""):
            return ""
        text = str(value)
        match = re.match(r"^(\d{4})-(\d{2})", text)
        return f"{match.group(1)}-{match.group(2)}" if match else text

    @staticmethod
    def _to_date(value: object) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if re.fullmatch(r"\d{4}-\d{2}", text):
            return text + "-01"
        return text

    def _from_remote(self, relation: str, row: dict) -> dict:
        result = {}
        for local_key, remote_key in self.fields[relation].items():
            value = row.get(remote_key)
            result[local_key] = self._from_date(value) if local_key in DATE_KEYS[relation] else str(value or "")
        return result

    def _to_remote(self, relation: str, row: dict) -> dict:
        result = {}
        for local_key, remote_key in self.fields[relation].items():
            value = row.get(local_key, "")
            result[remote_key] = self._to_date(value) if local_key in DATE_KEYS[relation] else str(value or "")
        return result

    @staticmethod
    def _rows(value: object) -> list[dict]:
        if not isinstance(value, list) or len(value) > 10:
            raise ValueError("人才经历必须是最多 10 条的列表")
        if any(not isinstance(row, dict) for row in value):
            raise ValueError("人才经历格式无效")
        return value

    def list(self, candidate_id: int, relation: str) -> list[dict]:
        candidate_id = self._candidate_id(candidate_id)
        relation = self._relation(relation)
        return [self._from_remote(relation, row) for row in self._raw_list(candidate_id, relation)]

    def sync(self, candidate_id: int, relation: str, rows: list[dict]) -> None:
        candidate_id = self._candidate_id(candidate_id)
        relation = self._relation(relation)
        rows = self._rows(rows)
        existing = self._raw_list(candidate_id, relation)
        shared = min(len(existing), len(rows))

        for index in range(shared):
            self.client.request(
                self._action(candidate_id, relation, "update"),
                method="POST",
                params={"filterByTk": existing[index]["id"]},
                body=self._to_remote(relation, rows[index]),
            )
        for row in rows[shared:]:
            data = self.client.request(
                self._action(candidate_id, relation, "create"),
                method="POST",
                body=self._to_remote(relation, row),
            )
            if not isinstance(data, dict) or type(data.get("id")) is not int:
                raise NocoBaseError("protocol", None, self._action(candidate_id, relation, "create"))
        for row in existing[shared:]:
            self.client.request(
                self._action(candidate_id, relation, "destroy"),
                method="POST",
                params={"filterByTk": row["id"]},
            )

    def snapshot(self, candidate_id: int) -> dict[str, list[dict]]:
        candidate_id = self._candidate_id(candidate_id)
        return {relation: self.list(candidate_id, relation) for relation in RELATIONS}

    def restore(self, candidate_id: int, snapshot: dict[str, list[dict]]) -> None:
        candidate_id = self._candidate_id(candidate_id)
        if not isinstance(snapshot, dict) or set(snapshot) != set(RELATIONS):
            raise ValueError("人才经历快照无效")
        for relation in RELATIONS:
            self.sync(candidate_id, relation, snapshot[relation])
