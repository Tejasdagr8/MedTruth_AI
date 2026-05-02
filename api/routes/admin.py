"""
Admin API — internal only.

This is not hardened for public exposure. The X-Admin-Key check is a shared secret,
not a proper auth system. It's fine for a single-operator tool but would need proper
role-based auth before going multi-tenant.

ADMIN_SECRET unset → 503 (panel disabled). This is intentional — I'd rather get a
clear error than accidentally expose it with an empty/default key.

There's no rate limiting on these endpoints. Doesn't matter much since they're
operator-only, but worth noting.
"""

import logging
import os

from fastapi import APIRouter, Header, HTTPException, Request

from api.failure_log import failure_store_available, get_failures
from src.db.user_store import UserStore
from src.llm.fallback_client import get_provider_metrics

logger = logging.getLogger(__name__)
router = APIRouter()
_store = UserStore()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")


# ── Guards ────────────────────────────────────────────────────────────────────

def _require_admin(request: Request, key: str | None) -> None:
    ip = request.client.host if request.client else "unknown"

    # Read at request-time so .env-loaded values and runtime env updates are honored.
    admin_secret = os.getenv("ADMIN_SECRET", "")
    if not admin_secret:
        raise HTTPException(status_code=503, detail="Admin panel disabled — ADMIN_SECRET not set")

    if not key or key != admin_secret:
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


@router.get("/admin/discussions")
def admin_discussions(
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    _require_admin(request, x_admin_key)
    _require_mongo()
    discussions = _store.list_discussions(limit=100)
    return {"discussions": discussions, "count": len(discussions)}


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
