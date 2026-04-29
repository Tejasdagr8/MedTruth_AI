"""
LLM Lab API — hardened experimental agent endpoint.

Hardening applied here:
  ✓ Task 5 — Per-IP sliding-window rate limit (20 req / 60 s)
"""

import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.mcp.agent import LabAgent

router = APIRouter()
_agent = LabAgent()

# ── Rate limiter (in-memory sliding window) ───────────────────────────────────

_RATE_WINDOW_S = 60.0   # seconds
_RATE_MAX_REQS = 20     # requests per window per IP

# ip → list of request timestamps within the current window
_ip_timestamps: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    window = _ip_timestamps[ip]
    # Evict timestamps outside the current window
    _ip_timestamps[ip] = [t for t in window if now - t < _RATE_WINDOW_S]
    if len(_ip_timestamps[ip]) >= _RATE_MAX_REQS:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: max {_RATE_MAX_REQS} requests per "
                f"{int(_RATE_WINDOW_S)}s per IP. Please wait and try again."
            ),
        )
    _ip_timestamps[ip].append(now)

# ── Request / Response ────────────────────────────────────────────────────────

class LabRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)


@router.post("/llm-lab/query")
async def lab_query(request: Request, payload: LabRequest) -> dict:
    """
    Run the LLM Lab MCP-style agent on a free-form query.

    Rate-limited to 20 requests / 60 s per IP.
    Not connected to the main RAG pipeline.
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    response = await _agent.run(payload.query)
    return response.to_dict()
