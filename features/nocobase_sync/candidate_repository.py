"""Repository for the NocoBase recruitment talent-pool main collection."""

from __future__ import annotations

from .candidate_mapping import from_nocobase, to_nocobase
from .client import NocoBaseClient, NocoBaseError


class CandidateRepository:
    COLLECTION = "campus_talent_pool"

    def __init__(self, client: NocoBaseClient):
        self.client = client

    def list(self, page: int = 1, page_size: int = 20, query: str = "") -> list[dict]:
        if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError("页码或每页条数无效")
        params = {"page": page, "pageSize": page_size, "sort": "-createdAt"}
        query = str(query or "").strip()
        if query:
            params["filter"] = {"$or": [
                {"Number": {"$includes": query}},
                {"name": {"$includes": query}},
            ]}
        data = self.client.request(f"{self.COLLECTION}:list", params=params)
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise NocoBaseError("protocol", None, f"{self.COLLECTION}:list")
        return [from_nocobase(row) for row in data]

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
