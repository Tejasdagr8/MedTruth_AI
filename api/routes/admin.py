"""
Internal admin API — NOT for public exposure.

All routes require the X-Admin-Key header to match ADMIN_SECRET from environment.
Set ADMIN_SECRET to a long random string; leave it unset to disable the panel.

Auth hardening
--------------
- Rate-limited to 5 failed attempts per 60 s per source IP.
  Only failed (wrong-key) attempts count; correct access is never throttled.
- ADMIN_SECRET must be set in the environment; the panel returns 503 otherwise.

Data integrity
--------------
- /admin/users, /admin/user/:email, /admin/activity require MongoDB to be reachable.
  They return 503 rather than silently serving stale in-memory data.
- /admin/failures and /admin/health work without Mongo (in-memory fallback).

Endpoints
---------
GET /admin/users            — summary row per registered user
GET /admin/user/{email}     — full profile for one user
GET /admin/activity         — last 20 queries across all users
GET /admin/failures         — last 100 failure events (Mongo if available, else in-memory)
GET /admin/health           — LLM provider metrics snapshot
"""

import logging
import os
import time
from collections import defaultdict

from fastapi import APIRouter, Header, HTTPException, Request

from api.failure_log import failure_store_available, get_failures
from src.db.user_store import UserStore
from src.llm.fallback_client import get_provider_metrics

logger = logging.getLogger(__name__)
router = APIRouter()
_store = UserStore()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")

# ── Rate limiter (failed attempts only) ───────────────────────────────────────

_FAIL_WINDOW_S = 60.0   # sliding window duration
_FAIL_MAX      = 5      # max failed attempts per IP per window

# ip → list of monotonic timestamps of failed attempts
_fail_log: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    """Raise 429 if this IP has exceeded the failed-attempt limit."""
    now = time.monotonic()
    _fail_log[ip] = [t for t in _fail_log[ip] if now - t < _FAIL_WINDOW_S]
    if len(_fail_log[ip]) >= _FAIL_MAX:
        logger.warning("[admin] rate-limited IP=%s (>%d failures in %.0fs)", ip, _FAIL_MAX, _FAIL_WINDOW_S)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed admin requests. Try again in {int(_FAIL_WINDOW_S)}s.",
        )


def _record_fail(ip: str) -> None:
    _fail_log[ip].append(time.monotonic())


# ── Guards ────────────────────────────────────────────────────────────────────

def _require_admin(request: Request, key: str | None) -> None:
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)

    if not ADMIN_SECRET:
        raise HTTPException(status_code=503, detail="Admin panel disabled — ADMIN_SECRET not set")

    if not key or key != ADMIN_SECRET:
        _record_fail(ip)
        logger.warning("[admin] rejected request from IP=%s — invalid key", ip)
        raise HTTPException(status_code=401, detail="Invalid admin key")


def _require_mongo() -> None:
    """
    Admin data routes must show truth, not a silent fallback.
    Returning 503 is preferable to showing stale in-memory data as if it were real.
    """
    if not _store.persistent_available:
        raise HTTPException(
            status_code=503,
            detail="Admin data requires persistent storage — MongoDB is currently unavailable",
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/admin/users")
def admin_list_users(
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    _require_admin(request, x_admin_key)
    _require_mongo()
    users = _store.list_users()
    return {"users": users, "total": len(users)}


@router.get("/admin/user/{email}")
def admin_get_user(
    email: str,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    _require_admin(request, x_admin_key)
    _require_mongo()
    return _store.get_user(email.lower())


@router.get("/admin/activity")
def admin_activity(
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    _require_admin(request, x_admin_key)
    _require_mongo()
    activity = _store.get_recent_activity(limit=20)
    return {"activity": activity, "count": len(activity)}


@router.get("/admin/failures")
def admin_failures(
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    _require_admin(request, x_admin_key)
    failures = get_failures()
    return {
        "failures": failures,
        "count": len(failures),
        "persistent": failure_store_available(),
    }


@router.get("/admin/health")
def admin_health(
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    _require_admin(request, x_admin_key)
    return {"providers": get_provider_metrics()}
