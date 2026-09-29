"""Secret-free diagnostics for NocoBase route failures."""

from __future__ import annotations

import json
import logging
import time
import uuid


LOGGER = logging.getLogger("nocobase_sync")


def record(action: str, *, status: int | None, elapsed: float,
           diagnostic_id: str | None = None) -> str:
    identifier = diagnostic_id or uuid.uuid4().hex[:12]
    LOGGER.error(json.dumps({
        "diagnostic_id": identifier,
        "action": str(action),
        "status": status,
        "elapsed_ms": max(0, round(elapsed * 1000)),
    }, ensure_ascii=False, separators=(",", ":")))
    return identifier
