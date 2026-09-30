"""Resolve NocoBase talent IDs from SQLite-backed business modules."""

from __future__ import annotations

import re
import sqlite3


class RemoteCandidateReference:
    def __init__(self, candidates):
        self.candidates = candidates

    @staticmethod
    def _identifier(value: int) -> int:
        if type(value) is not int or value <= 0:
            raise ValueError("人才记录编号无效")
        return value

    def profile(self, identifier: int) -> dict | None:
        return self.candidates.get(self._identifier(identifier))

    def exists(self, identifier: int) -> bool:
        try:
            return self.profile(identifier) is not None
        except ValueError:
            return False

    def label(self, identifier: int) -> str:
        row = self.profile(identifier)
        return str(row.get("name") or "") if row else ""

    def find_by_phone(self, phone: str) -> dict | None:
        row = self.candidates.find_by_phone(str(phone or "").strip())
        return self.profile(row["id"]) if row else None


_CANDIDATE_REFERENCE = re.compile(
    r"(\bcandidate_id\s+INTEGER)\s+REFERENCES\s+[\"`\[]?candidates[\"`\]]?"
    r"\s*\(\s*[\"`\[]?id[\"`\]]?\s*\)"
    r"(?:\s+ON\s+DELETE\s+(?:RESTRICT|CASCADE|SET\s+NULL|NO\s+ACTION))?"
    r"(?:\s+ON\s+UPDATE\s+(?:RESTRICT|CASCADE|SET\s+NULL|NO\s+ACTION))?",
    re.IGNORECASE,
)


def _row_value(row, key: str, index: int):
    try:
        return row[key]
    except (TypeError, IndexError):
        return row[index]


def upgrade_remote_candidate_foreign_keys(
    connection: sqlite3.Connection,
    tables=("applications", "interviews", "employees"),
) -> int:
    """Remove only legacy candidate FKs while retaining rows and other constraints."""
    targets = []
    for table in tables:
        foreign_keys = list(connection.execute(f'PRAGMA foreign_key_list("{table}")'))
        if not any(
            str(_row_value(row, "from", 3)).lower() == "candidate_id"
            and str(_row_value(row, "table", 2)).lower() == "candidates"
            for row in foreign_keys
        ):
            continue
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,),
        ).fetchone()
        sql = _row_value(schema, "sql", 0) if schema else None
        rewritten = _CANDIDATE_REFERENCE.sub(r"\1", str(sql or ""))
        if not sql or rewritten == sql:
            raise RuntimeError(f"无法安全升级{table}的人才外键")
        indexes = [
            _row_value(row, "sql", 0)
            for row in connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
                (table,),
            )
        ]
        columns = [str(_row_value(row, "name", 1))
                   for row in connection.execute(f'PRAGMA table_info("{table}")')]
        targets.append((table, rewritten, indexes, columns))
    if not targets:
        return 0

    connection.commit()
    foreign_keys_enabled = bool(connection.execute("PRAGMA foreign_keys").fetchone()[0])
    legacy_alter = bool(connection.execute("PRAGMA legacy_alter_table").fetchone()[0])
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute("PRAGMA legacy_alter_table=ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        for table, create_sql, indexes, columns in targets:
            legacy = "__remote_ref_legacy_" + table
            connection.execute(f'ALTER TABLE "{table}" RENAME TO "{legacy}"')
            connection.execute(create_sql)
            names = ",".join('"' + name.replace('"', '""') + '"' for name in columns)
            connection.execute(
                f'INSERT INTO "{table}" ({names}) SELECT {names} FROM "{legacy}"'
            )
            connection.execute(f'DROP TABLE "{legacy}"')
            for index_sql in indexes:
                connection.execute(index_sql)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute(f"PRAGMA legacy_alter_table={'ON' if legacy_alter else 'OFF'}")
        connection.execute(f"PRAGMA foreign_keys={'ON' if foreign_keys_enabled else 'OFF'}")
    return len(targets)
