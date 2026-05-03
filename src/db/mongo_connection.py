"""
Shared MongoClient construction for Atlas + constrained cloud egress.

Some hosts (e.g. Render) hit TLS handshake failures against Atlas when OCSP
stapling / OCSP responder checks cannot complete. Atlas documents optional
workarounds; we expose them via environment variables rather than hard-coding.
"""

from __future__ import annotations

import os

from pymongo import MongoClient


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _falsy(name: str) -> bool:
    """Explicit opt-out: false / 0 / no / off."""
    return os.getenv(name, "").strip().lower() in ("0", "false", "no", "off")


def _on_render() -> bool:
    """Render sets RENDER=true on web services."""
    return _truthy("RENDER")


def _tls_disable_ocsp() -> bool:
    """
    Prefer tlsDisableOCSPEndpointCheck when Atlas TLS fails on cloud egress (OCSP).

    - Explicit MONGO_TLS_DISABLE_OCSP=true → on
    - On Render (RENDER=true), default on unless MONGO_TLS_DISABLE_OCSP=false
    - Else off (local dev keeps strict TLS unless you set the env)
    """
    if _truthy("MONGO_TLS_DISABLE_OCSP"):
        return True
    if _on_render() and not _falsy("MONGO_TLS_DISABLE_OCSP"):
        return True
    return False


def create_mongo_client(uri: str) -> MongoClient:
    """
    Build a MongoClient with timeouts suitable for Atlas over the public internet.

    Env:
      MONGO_SERVER_SELECTION_TIMEOUT_MS — default 10000
      MONGO_CONNECT_TIMEOUT_MS — default 20000
      MONGO_TLS_DISABLE_OCSP — force OCSP workaround on/off; on Render defaults to on
    """
    sel_ms = int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "10000"))
    conn_ms = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "20000"))
    kwargs: dict = {
        "serverSelectionTimeoutMS": sel_ms,
        "connectTimeoutMS": conn_ms,
    }
    if _tls_disable_ocsp():
        kwargs["tlsDisableOCSPEndpointCheck"] = True
    return MongoClient(uri, **kwargs)
