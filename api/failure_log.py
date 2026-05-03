"""
Failure log for the admin panel.

Every record_failure() call:
  1. Appends to an in-memory ring buffer (always, used as hot cache and fallback).
  2. Persists to the `query_failures` MongoDB collection (if available).

get_failures() reads from MongoDB first; falls back to the in-memory deque when
Mongo is unavailable, with a 30-second reconnect TTL to avoid hammering a down DB.
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from pymongo import DESCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from src.db.mongo_connection import create_mongo_client

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB",  "medtruth_ai")

_MAX_MEMORY   = 100   # ring-buffer capacity
_RETRY_TTL    = 30.0  # seconds between reconnect attempts when Mongo is down

_cache: deque[dict[str, Any]] = deque(maxlen=_MAX_MEMORY)


class _FailureStore:
    """Lightweight Mongo-backed store with in-memory ring buffer as fallback."""

    def __init__(self) -> None:
        self._col:          Collection | None = None
        self._last_attempt: float             = 0.0
        self._connect()

    def _connect(self) -> None:
        self._last_attempt = time.monotonic()
        try:
            client = create_mongo_client(MONGO_URI)
            client.admin.command("ping")
            col = client[MONGO_DB]["query_failures"]
            col.create_index([("timestamp", DESCENDING)])
            self._col = col
            logger.info("failure_log: MongoDB connected")
        except PyMongoError:
            logger.warning("failure_log: MongoDB unavailable — using in-memory buffer only")
            self._col = None

    def _get_col(self) -> Collection | None:
        if self._col is not None:
            return self._col
        if time.monotonic() - self._last_attempt >= _RETRY_TTL:
            self._connect()
        return self._col

    @property
    def available(self) -> bool:
        return self._get_col() is not None

    def insert(self, doc: dict[str, Any]) -> None:
        col = self._get_col()
        if col is None:
            return
        try:
            col.insert_one({**doc})
        except PyMongoError:
            logger.warning("failure_log: Mongo insert failed", exc_info=True)

    def recent(self, limit: int = _MAX_MEMORY) -> list[dict[str, Any]]:
        col = self._get_col()
        if col is None:
            return list(_cache)
        try:
            return list(col.find({}, {"_id": 0}).sort("timestamp", DESCENDING).limit(limit))
        except PyMongoError:
            logger.warning("failure_log: Mongo read failed, returning in-memory buffer", exc_info=True)
            return list(_cache)


_store = _FailureStore()


def record_failure(
    *,
    request_id: str,
    query: str,
    mode: str,
    fallback_reason: str,
    provider_used: str,
) -> None:
    doc: dict[str, Any] = {
        "request_id":    request_id,
        "query":         query[:200],
        "mode":          mode,
        "fallback_reason": fallback_reason,
        "provider_used": provider_used,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
    }
    _cache.appendleft(doc)  # always update hot cache
    _store.insert(doc)      # persist (no-op if Mongo is down)


def get_failures(limit: int = _MAX_MEMORY) -> list[dict[str, Any]]:
    return _store.recent(limit)


def failure_store_available() -> bool:
    return _store.available
