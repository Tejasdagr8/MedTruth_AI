"""
User data store — MongoDB with in-memory fallback.

The in-memory fallback exists because: (a) Render free tier restarts frequently,
(b) I wanted the API to stay up during Mongo outages without throwing 500s.
The tradeoff is that data doesn't survive process restarts when Mongo is down —
that's acceptable for the use case (research tool, not banking).

The reconnect rate-limiting (_CONNECT_RETRY_TTL) matters more than it sounds.
Without it, every request under Mongo outage pays a 1.5s serverSelectionTimeoutMS
penalty, which tanks the API completely.

Saved answers are keyed by SHA256(answer) so re-saving the same answer is idempotent.
The hash is computed on the full answer text, not the query, so the same query can
produce different saved answers if the evidence changes (different top-K, new papers).
"""

import os
import hashlib
import logging
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError


MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "medtruth_ai")
logger = logging.getLogger(__name__)

# When Mongo is unreachable, wait this long before attempting another ping.
# Without this, every persistent_available check blocks for serverSelectionTimeoutMS (1.5 s).
_CONNECT_RETRY_TTL = 10.0  # seconds


class UserStore:
    def __init__(self, mongo_uri: str = MONGO_URI, db_name: str = MONGO_DB):
        self._mongo_uri = mongo_uri
        self._db_name = db_name
        self._memory: dict[str, dict[str, Any]] = {}
        self._memory_discussions: list[dict[str, Any]] = []
        self._users: Collection | None = None
        self._discussions: Collection | None = None
        self._persistent_available = False
        self._last_connect_attempt: float = 0.0
        self._connect()

    def _connect(self) -> None:
        self._last_connect_attempt = time.monotonic()
        try:
            self._client = MongoClient(self._mongo_uri, serverSelectionTimeoutMS=1500)
            self._db = self._client[self._db_name]
            # Fail fast when Mongo is unreachable instead of lazily failing on first write.
            self._client.admin.command("ping")
            self._users = self._db["users"]
            self._users.create_index("email", unique=True)
            self._discussions = self._db["discussions"]
            self._discussions.create_index("created_at")
            self._discussions.create_index("user_email")
            self._persistent_available = True
            logger.info("Mongo connected for user store")
        except PyMongoError:
            logger.exception("Mongo connection failed; falling back to in-memory user store")
            self._users = None
            self._discussions = None
            self._persistent_available = False

    def _should_retry_connect(self) -> bool:
        """True when enough time has passed to attempt another Mongo ping."""
        return time.monotonic() - self._last_connect_attempt >= _CONNECT_RETRY_TTL

    @property
    def persistent_available(self) -> bool:
        if self._persistent_available:
            return True
        # Rate-limit reconnect attempts — avoid 1.5 s penalty on every request when Mongo is down.
        if self._should_retry_connect():
            self._connect()
        return self._persistent_available

    def _ensure_users_collection(self) -> Collection | None:
        if self._users is not None and self._persistent_available:
            return self._users
        if self._should_retry_connect():
            self._connect()
        return self._users

    def _ensure_discussions_collection(self) -> Collection | None:
        if self._discussions is not None and self._persistent_available:
            return self._discussions
        if self._should_retry_connect():
            self._connect()
        return self._discussions

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _extract_top_condition(queries: list[str]) -> str | None:
        if not queries:
            return None
        words = []
        stop = {"what", "does", "with", "from", "that", "this", "and", "for", "the", "is", "are"}
        for q in queries:
            for word in q.lower().replace("?", "").split():
                if len(word) > 3 and word not in stop:
                    words.append(word)
        if not words:
            return None
        return Counter(words).most_common(1)[0][0]

    @staticmethod
    def _answer_hash(answer: str) -> str:
        return hashlib.sha256(answer.encode("utf-8")).hexdigest()

    def sync_user(self, email: str, name: str | None, image: str | None) -> dict[str, Any]:
        now = self._now()
        users = self._ensure_users_collection()
        if users is None:
            existing = self._memory.get(email, {})
            self._memory[email] = {
                "email": email,
                "name": name,
                "image": image,
                "created_at": existing.get("created_at", now),
                "query_history": existing.get("query_history", []),
                "saved_answers": existing.get("saved_answers", []),
                "usage_count": existing.get("usage_count", 0),
            }
        else:
            try:
                users.update_one(
                    {"email": email},
                    {
                        "$set": {"email": email, "name": name, "image": image, "updated_at": now},
                        "$setOnInsert": {
                            "created_at": now,
                            "query_history": [],
                            "saved_answers": [],
                            "usage_count": 0,
                        },
                    },
                    upsert=True,
                )
            except PyMongoError:
                logger.exception("Failed to sync user profile for %s", email)
                raise
        return self.get_user(email)

    def record_query(self, email: str, query: str) -> None:
        users = self._ensure_users_collection()
        if users is None:
            user = self._memory.setdefault(
                email,
                {
                    "email": email,
                    "name": "",
                    "image": None,
                    "created_at": self._now(),
                    "query_history": [],
                    "saved_answers": [],
                    "usage_count": 0,
                },
            )
            user["usage_count"] = int(user.get("usage_count", 0)) + 1
            user["query_history"] = [*user.get("query_history", []), query][-50:]
            return
        try:
            users.update_one(
                {"email": email},
                {
                    "$setOnInsert": {
                        "email": email,
                        "name": "",
                        "image": None,
                        "created_at": self._now(),
                        "query_history": [],
                        "saved_answers": [],
                        "usage_count": 0,
                    },
                    "$inc": {"usage_count": 1},
                    "$push": {"query_history": {"$each": [query], "$slice": -50}},
                },
                upsert=True,
            )
        except PyMongoError:
            logger.exception("Failed to record query for %s", email)
            raise

    def save_answer(
        self,
        email: str,
        query: str,
        answer: str,
        *,
        confidence: float | None = None,
        confidence_band: str | None = None,
        mode: str | None = None,
        citations_count: int | None = None,
    ) -> None:
        """
        Save an answer with optional version metadata.
        Duplicate hashes are removed before inserting so every save is a fresh snapshot.
        """
        answer_hash = self._answer_hash(answer)
        logger.info("Saving answer for %s", email)
        doc: dict[str, Any] = {
            "query": query,
            "answer": answer,
            "answer_hash": answer_hash,
            "saved_at": self._now(),
        }
        if confidence is not None:
            doc["confidence"] = round(confidence, 3)
        if confidence_band is not None:
            doc["confidence_band"] = confidence_band
        if mode is not None:
            doc["mode"] = mode
        if citations_count is not None:
            doc["citations_count"] = citations_count

        users = self._ensure_users_collection()
        if users is None:
            user = self._memory.setdefault(
                email,
                {
                    "email": email,
                    "name": "",
                    "image": None,
                    "created_at": self._now(),
                    "query_history": [],
                    "saved_answers": [],
                    "usage_count": 0,
                },
            )
            saved = user.get("saved_answers", [])
            filtered = [s for s in saved if s.get("answer_hash") != answer_hash]
            user["saved_answers"] = [*filtered, doc][-50:]
            return
        try:
            users.update_one(
                {"email": email},
                {"$pull": {"saved_answers": {"answer_hash": answer_hash}}},
            )
            users.update_one(
                {"email": email},
                {
                    "$setOnInsert": {
                        "email": email,
                        "name": "",
                        "image": None,
                        "created_at": self._now(),
                        "query_history": [],
                        "usage_count": 0,
                    },
                    "$push": {
                        "saved_answers": {
                            "$each": [doc],
                            "$slice": -50,
                        }
                    }
                },
                upsert=True,
            )
        except PyMongoError:
            logger.exception("Failed to save answer for %s", email)
            raise

    def delete_saved_answer(self, email: str, answer_hash: str) -> bool:
        """Remove a saved answer by hash. Returns True if an entry was removed."""
        users = self._ensure_users_collection()
        if users is None:
            user = self._memory.get(email)
            if not user:
                return False
            before = len(user.get("saved_answers", []))
            user["saved_answers"] = [
                s for s in user.get("saved_answers", []) if s.get("answer_hash") != answer_hash
            ]
            return len(user["saved_answers"]) < before

        try:
            result = users.update_one(
                {"email": email},
                {"$pull": {"saved_answers": {"answer_hash": answer_hash}}},
            )
            return result.modified_count > 0
        except PyMongoError:
            logger.exception("Failed to delete saved answer %s for %s", answer_hash, email)
            raise

    def list_users(self) -> list[dict[str, Any]]:
        """Return a summary row for every user (for the admin panel users table)."""
        users = self._ensure_users_collection()
        if users is None:
            return [
                {
                    "email": u["email"],
                    "name": u.get("name") or "",
                    "usage_count": u.get("usage_count", 0),
                    "saved_answers_count": len(u.get("saved_answers", [])),
                    "last_query": (u.get("query_history") or [None])[-1],
                }
                for u in self._memory.values()
            ]
        try:
            docs = list(users.find(
                {},
                {"_id": 0, "email": 1, "name": 1, "usage_count": 1,
                 "saved_answers": 1, "query_history": 1},
            ))
        except PyMongoError:
            logger.exception("list_users failed")
            return []
        return [
            {
                "email": d.get("email", ""),
                "name": d.get("name") or "",
                "usage_count": d.get("usage_count", 0),
                "saved_answers_count": len(d.get("saved_answers", [])),
                "last_query": (d.get("query_history") or [None])[-1],
            }
            for d in docs
        ]

    def get_recent_activity(self, limit: int = 20) -> list[dict[str, Any]]:
        # TODO: add timestamps to query_history entries so this can be sorted by actual time.
        # Right now we just take the last N queries per user and flatten — the ordering
        # is "recent per user" not "globally recent", which is fine for the admin panel.
        """Return the most recent queries across all users (no timestamps — best-effort)."""
        users = self._ensure_users_collection()
        if users is None:
            items: list[dict[str, Any]] = []
            for u in self._memory.values():
                for q in reversed(u.get("query_history", [])[-5:]):
                    items.append({"email": u["email"], "query": q})
            return items[:limit]
        try:
            docs = list(users.find(
                {"query_history.0": {"$exists": True}},
                {"_id": 0, "email": 1, "query_history": 1},
            ).limit(20))
        except PyMongoError:
            logger.exception("get_recent_activity failed")
            return []
        items = []
        for doc in docs:
            for q in reversed((doc.get("query_history") or [])[-5:]):
                items.append({"email": doc.get("email", ""), "query": q})
        return items[:limit]

    def save_discussion(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Persist moderated discussion submission and return stored payload."""
        doc = {**entry, "created_at": self._now()}
        discussions = self._ensure_discussions_collection()
        if discussions is None:
            self._memory_discussions = [doc, *self._memory_discussions][:500]
            return doc
        try:
            result = discussions.insert_one(doc)
            return {**doc, "id": str(result.inserted_id)}
        except PyMongoError:
            logger.exception("Failed to save discussion for %s", entry.get("user_email", "unknown"))
            raise

    def list_discussions(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return latest moderated discussion submissions for admin panel."""
        discussions = self._ensure_discussions_collection()
        if discussions is None:
            return self._memory_discussions[:limit]
        try:
            docs = list(
                discussions.find({}, {"_id": 0})
                .sort("created_at", -1)
                .limit(limit)
            )
            return docs
        except PyMongoError:
            logger.exception("Failed to list discussions")
            return []

    def get_user(self, email: str) -> dict[str, Any]:
        users = self._ensure_users_collection()
        if users is None:
            doc = self._memory.get(email)
        else:
            doc = users.find_one({"email": email}, {"_id": 0})
        if not doc:
            return {
                "id": email,
                "email": email,
                "name": "",
                "image": None,
                "created_at": self._now(),
                "query_history": [],
                "saved_answers": [],
                "usage_count": 0,
                "most_searched_condition": None,
            }
        return {
            "id": doc.get("email"),
            "email": doc.get("email"),
            "name": doc.get("name") or "",
            "image": doc.get("image"),
            "created_at": doc.get("created_at", self._now()),
            "query_history": doc.get("query_history", []),
            "saved_answers": doc.get("saved_answers", []),
            "usage_count": doc.get("usage_count", 0),
            "most_searched_condition": self._extract_top_condition(doc.get("query_history", [])),
        }
