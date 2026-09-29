"""Repository for the NocoBase recruitment talent-pool main collection."""

from __future__ import annotations

from .candidate_mapping import from_nocobase, to_nocobase
from .client import NocoBaseClient, NocoBaseError


class CandidateRepository:
    COLLECTION = "campus_talent_pool"

    def __init__(self, client: NocoBaseClient):
        self.client = client

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
        return [from_nocobase(row) for row in data]

    def list(self, page: int = 1, page_size: int = 20, query: str = "") -> list[dict]:
        params = self._list_params(page, page_size, query)
        data = self.client.request(f"{self.COLLECTION}:list", params=params)
        return self._rows(data, f"{self.COLLECTION}:list")

    def list_page(self, page: int = 1, page_size: int = 20, query: str = "") -> dict:
        endpoint = f"{self.COLLECTION}:list"
        response = self.client.request_envelope(
            endpoint, params=self._list_params(page, page_size, query),
        )
        count = response.meta.get("count") if isinstance(response.meta, dict) else None
        if type(count) is not int or count < 0:
            raise NocoBaseError("protocol", None, endpoint)
        return {"rows": self._rows(response.data, endpoint), "count": count}

    def find_by_phone(self, phone: str) -> dict | None:
        phone = str(phone or "").strip()
        if not phone:
            return None
        endpoint = f"{self.COLLECTION}:list"
        data = self.client.request(endpoint, params={
            "pageSize": 2,
            "filter": {"phone": {"$eq": phone}},
        })
        rows = self._rows(data, endpoint)
        if len(rows) > 1:
            raise NocoBaseError("protocol", None, endpoint)
        return rows[0] if rows else None

    def get(self, identifier: int) -> dict | None:
        data = self.client.request(f"{self.COLLECTION}:get", params={"filterByTk": self._identifier(identifier)})
        if data is None:
            return None
        if not isinstance(data, dict):
            raise NocoBaseError("protocol", None, f"{self.COLLECTION}:get")
        return from_nocobase(data)

    def create(self, values: dict) -> int:
        data = self.client.request(f"{self.COLLECTION}:create", method="POST", body=to_nocobase(values))
        if not isinstance(data, dict) or type(data.get("id")) is not int:
            raise NocoBaseError("protocol", None, f"{self.COLLECTION}:create")
        return data["id"]

    def update(self, identifier: int, values: dict) -> None:
        self.client.request(f"{self.COLLECTION}:update", method="POST",
                            params={"filterByTk": self._identifier(identifier)}, body=to_nocobase(values))

    def delete(self, identifier: int) -> bool:
        data = self.client.request(f"{self.COLLECTION}:destroy", method="POST",
                                   params={"filterByTk": self._identifier(identifier)})
        return type(data) is int and data > 0

    @staticmethod
    def _identifier(value: int) -> int:
        if type(value) is not int or value <= 0:
            raise ValueError("人才记录编号无效")
        return value
