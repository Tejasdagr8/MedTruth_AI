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


def create_mongo_client(uri: str) -> MongoClient:
    """
    Build a MongoClient with timeouts suitable for Atlas over the public internet.

    Env:
      MONGO_SERVER_SELECTION_TIMEOUT_MS — default 10000
      MONGO_CONNECT_TIMEOUT_MS — default 20000
      MONGO_TLS_DISABLE_OCSP — if true, set tlsDisableOCSPEndpointCheck=True (Atlas TLS workaround)
    """
    sel_ms = int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "10000"))
    conn_ms = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "20000"))
    kwargs: dict = {
        "serverSelectionTimeoutMS": sel_ms,
        "connectTimeoutMS": conn_ms,
    }
    if _truthy("MONGO_TLS_DISABLE_OCSP"):
        kwargs["tlsDisableOCSPEndpointCheck"] = True
    return MongoClient(uri, **kwargs)
