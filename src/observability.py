"""
Lightweight per-request observability primitives.

Kept dependency-free so both the `api` layer and `src` library code
can import without circular deps.

Usage
-----
API middleware sets the request_id once per request:
    from src.observability import request_id
    request_id.set(uuid.uuid4().hex[:12])

All logger calls made during that request (including inside threads
spawned via asyncio.to_thread, which inherit the context) will then
have `record.request_id` injected automatically by RequestIDFilter.
"""

import contextvars
import logging

# Set once per HTTP request in main.py middleware.
# Python propagates ContextVar values into threads created by asyncio.to_thread,
# so this is visible inside the synchronous pipeline and LLM client too.
request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIDFilter(logging.Filter):
    """
    Injects the current request_id into every log record.
    Add to the root logger once at startup to cover all named loggers.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()  # type: ignore[attr-defined]
        return True
