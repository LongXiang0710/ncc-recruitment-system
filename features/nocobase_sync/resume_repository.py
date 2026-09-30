"""Repository for the NocoBase Resume_Collection main collection."""

from __future__ import annotations

from .client import NocoBaseClient, NocoBaseError
from .resume_mapping import from_nocobase_resume, to_nocobase_resume


class ResumeRepository:
    COLLECTION = "Resume_Collection"
    STABLE_FIELDS = {
        "archive_no": "Number",
        "source_id": "source_id",
        "file_hash": "file_hash",
        "linked_candidate": "linked_candidate",
    }

    def __init__(self, client: NocoBaseClient):
        self.client = client

    @staticmethod
    def _identifier(value: int) -> int:
        if type(value) is not int or value <= 0:
            raise ValueError("简历记录编号无效")
        return value

    @staticmethod
    def _list_params(page: int, page_size: int, query: str) -> dict:
        if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError("页码或每页条数无效")
        params = {"page": page, "pageSize": page_size, "sort": "-createdAt"}
        query = str(query or "").strip()
        if query:
            params["filter"] = {"$or": [
                {"Number": {"$includes": query}},
                {"name": {"$includes": query}},
            ]}
        return params

    @classmethod
    def _rows(cls, data: object, endpoint: str) -> list[dict]:
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise NocoBaseError("protocol", None, endpoint)
        return [from_nocobase_resume(row) for row in data]

    def list_page(self, page: int = 1, page_size: int = 20, query: str = "") -> dict:
        endpoint = f"{self.COLLECTION}:list"
        response = self.client.request_envelope(
            endpoint, params=self._list_params(page, page_size, query),
        )
        count = response.meta.get("count") if isinstance(response.meta, dict) else None
        if type(count) is not int or count < 0:
            raise NocoBaseError("protocol", None, endpoint)
        return {"rows": self._rows(response.data, endpoint), "count": count}

    def list(self, page: int = 1, page_size: int = 20, query: str = "") -> list[dict]:
        endpoint = f"{self.COLLECTION}:list"
        data = self.client.request(endpoint, params=self._list_params(page, page_size, query))
        return self._rows(data, endpoint)

    def get(self, identifier: int) -> dict | None:
        endpoint = f"{self.COLLECTION}:get"
        data = self.client.request(endpoint, params={"filterByTk": self._identifier(identifier)})
        if data is None:
            return None
        if not isinstance(data, dict):
            raise NocoBaseError("protocol", None, endpoint)
        return from_nocobase_resume(data)

    def create(self, values: dict) -> int:
        endpoint = f"{self.COLLECTION}:create"
        data = self.client.request(endpoint, method="POST", body=to_nocobase_resume(values))
        if not isinstance(data, dict) or type(data.get("id")) is not int:
            raise NocoBaseError("protocol", None, endpoint)
        return data["id"]

    def update(self, identifier: int, values: dict) -> None:
        self.client.request(
            f"{self.COLLECTION}:update", method="POST",
            params={"filterByTk": self._identifier(identifier)},
            body=to_nocobase_resume(values),
        )

    def delete(self, identifier: int) -> bool:
        data = self.client.request(
            f"{self.COLLECTION}:destroy", method="POST",
            params={"filterByTk": self._identifier(identifier)},
        )
        return type(data) is int and data > 0

    def find_by_stable_key(self, field: str, value) -> dict | None:
        remote = self.STABLE_FIELDS.get(field)
        if remote is None:
            raise ValueError("不支持的简历稳定键")
        if field == "linked_candidate":
            value = self._identifier(value)
            filter_value = {remote: {"id": {"$eq": value}}}
        else:
            value = str(value or "").strip()
            if not value:
                return None
            filter_value = {remote: {"$eq": value}}
        endpoint = f"{self.COLLECTION}:list"
        data = self.client.request(endpoint, params={"pageSize": 2, "filter": filter_value})
        rows = self._rows(data, endpoint)
        if len(rows) > 1:
            raise NocoBaseError("protocol", None, endpoint)
        return rows[0] if rows else None

    def find_by_linked_candidate(self, candidate_id: int) -> list[dict]:
        candidate_id = self._identifier(candidate_id)
        endpoint = f"{self.COLLECTION}:list"
        data = self.client.request(endpoint, params={
            "pageSize": 100,
            "filter": {"linked_candidate": {"id": {"$eq": candidate_id}}},
        })
        return self._rows(data, endpoint)
