"""
MedTruth AI — FastAPI application entry point.
"""

import time

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import contradictions, discuss, explain, llm_lab, query, user, validate

load_dotenv()

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
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.time() - start):.3f}s"
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# Register routers
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
