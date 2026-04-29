"""
MedTruth AI — FastAPI application entry point.
"""

import logging
import time
import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.observability import RequestIDFilter, request_id

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """
    Add the RequestIDFilter to the root logger so every log line (across all
    modules, including asyncio.to_thread workers) carries request_id= automatically.
    Idempotent — safe to call multiple times (e.g., during testing).
    """
    root = logging.getLogger()
    if not any(isinstance(f, RequestIDFilter) for f in root.filters):
        root.addFilter(RequestIDFilter())
    if not root.level:
        root.setLevel(logging.INFO)


_configure_logging()

from api.routes import admin, contradictions, discuss, explain, llm_lab, query, user, validate

load_dotenv()


def _allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]

app = FastAPI(
    title="MedTruth AI",
    description=(
        "Evidence-grounded medical Q&A system. "
        "Answers are sourced exclusively from PubMed, BMJ, The Lancet, "
        "Nature Medicine, WHO, CDC, and Cochrane Reviews."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id_middleware(request: Request, call_next):
    """Set a per-request correlation ID; return it as X-Request-ID for client tracing."""
    rid = uuid.uuid4().hex[:12]
    request_id.set(rid)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.time() - start):.3f}s"
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    rid = request_id.get()
    logger.exception(
        "Unhandled exception rid=%s on %s %s", rid, request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": rid},
    )


# Register routers
app.include_router(admin.router, prefix="/api/v1", tags=["Admin"])
app.include_router(query.router, prefix="/api/v1", tags=["Query"])
app.include_router(validate.router, prefix="/api/v1", tags=["Validation"])
app.include_router(explain.router, prefix="/api/v1", tags=["Explain"])
app.include_router(contradictions.router, prefix="/api/v1", tags=["Contradictions"])
app.include_router(user.router, prefix="/api/v1", tags=["User"])
app.include_router(discuss.router, prefix="/api/v1", tags=["Discussion"])
app.include_router(llm_lab.router, prefix="/api/v1", tags=["LLM Lab"])


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "MedTruth AI",
        "trusted_sources": [
            "PubMed", "BMJ", "The Lancet", "Nature Medicine",
            "WHO", "CDC", "Cochrane Reviews",
        ],
    }


@app.get("/")
def root():
    return {
        "message": "MedTruth AI API",
        "docs": "/docs",
        "version": "1.0.0",
    }
