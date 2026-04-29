"""
Mongo-backed user profile store for query history and saved answers.
"""

import os
import hashlib
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError


MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "medtruth_ai")
logger = logging.getLogger(__name__)


class UserStore:
    def __init__(self, mongo_uri: str = MONGO_URI, db_name: str = MONGO_DB):
        self._mongo_uri = mongo_uri
        self._db_name = db_name
        self._memory: dict[str, dict[str, Any]] = {}
        self._users: Collection | None = None
        self._persistent_available = False
        self._connect()

    def _connect(self) -> None:
        try:
            self._client = MongoClient(self._mongo_uri, serverSelectionTimeoutMS=1500)
            self._db = self._client[self._db_name]
            # Fail fast when Mongo is unreachable instead of lazily failing on first write.
            self._client.admin.command("ping")
            self._users = self._db["users"]
            self._users.create_index("email", unique=True)
            self._persistent_available = True
            logger.info("Mongo connected for user store")
        except PyMongoError:
            logger.exception("Mongo connection failed; falling back to in-memory user store")
            self._users = None
            self._persistent_available = False

    @property
    def persistent_available(self) -> bool:
        if not self._persistent_available:
            self._connect()
        return self._persistent_available

    def _ensure_users_collection(self) -> Collection | None:
        if self._users is None or not self._persistent_available:
            self._connect()
        return self._users

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

        result = users.update_one(
            {"email": email},
            {"$pull": {"saved_answers": {"answer_hash": answer_hash}}},
        )
        return result.modified_count > 0

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
