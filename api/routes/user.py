"""
User profile endpoints for auth sync, history, and saved answers.
"""

import re

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from src.db.user_store import UserStore

router = APIRouter()
store = UserStore()


def _assert_identity(email_header: str | None) -> str:
    if not email_header:
        raise HTTPException(status_code=401, detail="Missing X-User-Email header")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_header):
        raise HTTPException(status_code=401, detail="Invalid user identity")
    return email_header.lower()


class UserSyncRequest(BaseModel):
    email: str
    name: str | None = None
    image: str | None = None


class SaveAnswerRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=500)
    answer: str = Field(..., min_length=10, max_length=12000)
    # Optional versioning metadata
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_band: str | None = None
    mode: str | None = None
    citations_count: int | None = Field(default=None, ge=0)


@router.post("/user/sync")
def sync_user(request: UserSyncRequest, x_user_email: str | None = Header(default=None)):
    identity = _assert_identity(x_user_email)
    if request.email.lower() != identity:
        raise HTTPException(status_code=403, detail="Identity mismatch")
    return store.sync_user(identity, request.name, request.image)


@router.get("/user/history")
def get_history(x_user_email: str | None = Header(default=None)):
    identity = _assert_identity(x_user_email)
    return store.get_user(identity)


@router.post("/user/save")
def save_answer(request: SaveAnswerRequest, x_user_email: str | None = Header(default=None)):
    identity = _assert_identity(x_user_email)
    if not store.persistent_available:
        raise HTTPException(status_code=503, detail="Persistent user store unavailable")
    store.save_answer(
        identity,
        request.query,
        request.answer,
        confidence=request.confidence,
        confidence_band=request.confidence_band,
        mode=request.mode,
        citations_count=request.citations_count,
    )
    return {"status": "saved"}


@router.get("/user/storage-health")
def storage_health():
    return {
        "persistent_available": store.persistent_available,
        "backend": "mongo" if store.persistent_available else "memory_fallback",
    }


@router.delete("/user/saved/{answer_hash}")
def delete_saved_answer(answer_hash: str, x_user_email: str | None = Header(default=None)):
    identity = _assert_identity(x_user_email)
    removed = store.delete_saved_answer(identity, answer_hash)
    if not removed:
        raise HTTPException(status_code=404, detail="Saved answer not found")
    return {"status": "deleted"}
