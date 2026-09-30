"""Data-only models used by the read-only migration checker and executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class MigrationIssue:
    kind: str
    entity: str
    local_id: int | None = None
    archive_no: str = ""

    def redacted(self) -> dict:
        return {
            "kind": self.kind,
            "entity": self.entity,
            "local_id": self.local_id,
            "archive_no": self.archive_no,
        }


@dataclass
class MigrationInventory:
    source: dict[str, list[dict]]
    target: dict[str, list[dict]]
    counts: dict[str, int]
    digests: dict[str, str]
    issues: list[MigrationIssue] = field(default_factory=list)
    preflight_ok: bool = True


@dataclass(frozen=True)
class MigrationReport:
    generated_at: datetime
    expires_at: datetime
    eligible: bool
    counts: dict[str, int]
    digests: dict[str, str]
    issues: tuple[MigrationIssue, ...]

    def redacted(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "eligible": self.eligible,
            "counts": dict(self.counts),
            "digests": dict(self.digests),
            "issues": [issue.redacted() for issue in self.issues],
        }
