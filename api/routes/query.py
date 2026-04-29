"""
Main /query endpoint — RAG pipeline from user question to grounded answer.

Flow (simplified by graph_pipeline.py):

  1. Cache check
  2. Query refinement (LLM — fast, single call)
  3. Async retrieval across all trusted sources
  4. MedTruthPipeline.run() — LangGraph graph handles all post-retrieval logic
  5. Build QueryResponse from final pipeline state
"""

import asyncio
import hashlib
import logging
import os
import re
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import (
    get_cochrane_client,
    get_europepmc_client,
    get_pipeline,
    get_pubmed_client,
    get_who_client,
)
from api.failure_log import record_failure as _record_failure
from src.llm.fallback_client import get_provider_metrics
from src.observability import request_id as _request_id
from src.rag.graph_pipeline import MedTruthPipeline, PipelineState
from src.retrieval.domain_classifier import detect_domain
from src.retrieval.query_refiner import refine_query
from src.db.user_store import UserStore

router = APIRouter()
user_store = UserStore()
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
logger = logging.getLogger(__name__)

# Global cap on the refine + retrieve + pipeline wall time.
# Configurable via env so ops can tune without a redeploy.
QUERY_PIPELINE_TIMEOUT_S = float(os.getenv("QUERY_PIPELINE_TIMEOUT_S", "45"))

QUERY_MODE_CACHE_TTL_SECONDS = 60
_QUERY_MODE_CACHE: dict[str, tuple[float, dict]] = {}
_MODE_METRICS = {
    "total_requests": 0,
    "cache_hits": 0,
    "evidence_based": 0,
    "evidence_only": 0,
    "general_explanation": 0,
    "fallback": 0,
    "provider_error": 0,
    "retrieval_empty": 0,
}


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email))


# ── Request / Response models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=500)
    top_k: int = Field(default=8, ge=1, le=20)
    enable_entailment_check: bool = Field(default=True)
    enable_contradiction_check: bool = Field(default=True)


class QueryResponse(BaseModel):
    query: str
    domain: str
    answer: str
    confidence: float
    confidence_band: str
    rejected: bool
    rejection_reason: Optional[str]
    citations: list[dict]
    bibliography: str
    evidence_summary: str
    risk_flags: list[dict]
    overall_risk: str
    contradictions: list[dict]
    hallucination_check: Optional[dict]
    sources_retrieved: int
    sources_trusted: int
    sources_rejected: int
    mode: str = "evidence_based"
    fallback_reason: Optional[str] = None
    provider_used: str = "none"
    provider_attempts: list[str] = Field(default_factory=list)
    confidence_details: dict = Field(default_factory=dict)
    confidence_explanation: str = ""
    related_questions: list[str] = Field(default_factory=list)
    selection_rationale: dict = Field(default_factory=dict)
    refiner_status: str = "success"
    trace: list[str] = Field(default_factory=list)


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_key(query: str, top_k: int, entailment: bool, contradictions: bool) -> str:
    raw = f"{query.strip().lower()}|{top_k}|{int(entailment)}|{int(contradictions)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _read_cache(key: str) -> Optional[QueryResponse]:
    entry = _QUERY_MODE_CACHE.get(key)
    if not entry:
        return None
    ts, payload = entry
    if time.time() - ts > QUERY_MODE_CACHE_TTL_SECONDS:
        _QUERY_MODE_CACHE.pop(key, None)
        return None
    try:
        return QueryResponse(**payload)
    except Exception:
        _QUERY_MODE_CACHE.pop(key, None)
        return None


def _write_cache(key: str, response: QueryResponse) -> QueryResponse:
    _QUERY_MODE_CACHE[key] = (time.time(), response.model_dump())
    _record_mode_metrics(response, cache_hit=False)
    return response


def _record_mode_metrics(response: QueryResponse, cache_hit: bool = False) -> None:
    _MODE_METRICS["total_requests"] += 1
    if cache_hit:
        _MODE_METRICS["cache_hits"] += 1
    mode = response.mode or "fallback"
    if mode in _MODE_METRICS:
        _MODE_METRICS[mode] += 1
    if response.fallback_reason and "provider_error" in response.fallback_reason:
        _MODE_METRICS["provider_error"] += 1
    if response.fallback_reason and "retrieval_empty" in response.fallback_reason:
        _MODE_METRICS["retrieval_empty"] += 1


# ── Broad-query expansion (keyword heuristic, runs before refiner) ────────────

def _expand_query_if_broad(query: str) -> tuple[str, bool]:
    q = query.strip()
    tokens = re.findall(r"[a-z0-9]+", q.lower())
    broad_markers = {"simple", "basics", "overview", "general", "explain"}
    medical_terms = {
        "aspirin", "metformin", "statin", "hypertension", "diabetes", "myocardial",
        "infarction", "stroke", "depression", "cbt", "corticosteroid", "heart",
    }
    is_broad = len(tokens) <= 6 and (
        any(t in broad_markers for t in tokens)
        or not any(t in medical_terms for t in tokens)
    )
    if not is_broad:
        return q, False
    return f"{q} mechanism of action clinical uses effectiveness safety adverse effects", True


# ── Async retrieval fan-out ───────────────────────────────────────────────────

async def _retrieve_all(
    query: str,
    pubmed,
    europepmc,
    who,
    cochrane,
    expanded_terms: list[str] | None = None,
) -> list[dict]:
    """Fan-out retrieval across all sources concurrently."""
    results = await asyncio.gather(
        pubmed.retrieve(query, expanded_terms=expanded_terms),
        europepmc.retrieve(query, expanded_terms=expanded_terms),
        who.retrieve(query),
        cochrane.retrieve(query),
        return_exceptions=True,
    )
    all_docs = []
    for result in results:
        if isinstance(result, Exception):
            continue
        for item in result:
            all_docs.append(item.to_retrieval_doc())
    return all_docs


# ── Pipeline helper ───────────────────────────────────────────────────────────

async def _run_pipeline(
    original_query: str,
    effective_query: str,
    was_expanded: bool,
    domain: str,
    req: QueryRequest,
    pubmed,
    europepmc,
    who,
    cochrane,
    pipeline: MedTruthPipeline,
) -> tuple[str, str, PipelineState]:
    """
    The slow part of the query flow: refine → retrieve → LangGraph pipeline.
    Extracted so it can be wrapped in asyncio.wait_for by the endpoint.
    Returns (effective_query_after_refinement, refiner_status, pipeline_state).
    """
    refined = await asyncio.to_thread(refine_query, effective_query)
    effective = refined.refined_query

    raw_docs = await _retrieve_all(
        effective,
        pubmed,
        europepmc,
        who,
        cochrane,
        expanded_terms=refined.expanded_terms or None,
    )

    initial_state: PipelineState = {
        "original_query": original_query,
        "effective_query": effective,
        "domain": domain,
        "top_k": req.top_k,
        "enable_entailment_check": req.enable_entailment_check,
        "enable_contradiction_check": req.enable_contradiction_check,
        "was_expanded": was_expanded,
        "raw_docs": raw_docs,
        "trusted_docs": [],
        "rejected_docs": [],
        "top_docs": [],
        "semantic_similarities": None,
        "no_docs_reason": "",
        "rag_response": None,
        "final_answer": "",
        "provider_used": "none",
        "provider_attempts": [],
        "mode": "fallback",
        "fallback_reason": None,
        "citations": [],
        "bibliography": "",
        "evidence_summary": "",
        "confidence": 0.4,
        "confidence_band": "LOW",
        "rejected": False,
        "rejection_reason": None,
        "hallucination_dict": None,
        "contradictions": [],
        "has_conflict": False,
        "contradiction_flag": False,
        "contradiction_summary": "",
        "contradiction_confidence": 0.0,
        "risk_flags": [],
        "overall_risk": "none",
        "confidence_details": {},
        "confidence_explanation": "",
        "selection_rationale": {},
        "related_questions": [],
        "trace": [],
        "transitions": [],
        "failure_paths": [],
    }

    state = await asyncio.to_thread(pipeline.run, initial_state)
    return effective, refined.status, state


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    request: QueryRequest,
    pubmed=Depends(get_pubmed_client),
    europepmc=Depends(get_europepmc_client),
    who=Depends(get_who_client),
    cochrane=Depends(get_cochrane_client),
    pipeline: MedTruthPipeline = Depends(get_pipeline),
    x_user_email: str | None = Header(default=None),
):
    original_query = request.query

    # 1. User activity tracking — non-critical; never blocks query processing
    if x_user_email and is_valid_email(x_user_email):
        try:
            user_store.record_query(x_user_email.lower(), original_query)
        except Exception:
            logger.warning("record_query failed for %s — continuing", x_user_email, exc_info=True)

    # 1. Cache check
    cache_key = _cache_key(
        original_query,
        request.top_k,
        request.enable_entailment_check,
        request.enable_contradiction_check,
    )
    if cached := _read_cache(cache_key):
        _record_mode_metrics(cached, cache_hit=True)
        return cached

    # 2. Instant path — no I/O, no LLM
    effective_query, was_expanded = _expand_query_if_broad(original_query)
    domain = detect_domain(original_query)

    # 3–5. Slow path: refine → retrieve → pipeline (all I/O; guarded by global timeout)
    rid = _request_id.get()
    t0 = time.perf_counter()
    logger.info("[query] rid=%s status=start query=%r", rid, original_query[:80])
    try:
        effective_query, refiner_status, state = await asyncio.wait_for(
            _run_pipeline(
                original_query, effective_query, was_expanded, domain,
                request, pubmed, europepmc, who, cochrane, pipeline,
            ),
            timeout=QUERY_PIPELINE_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.warning(
            "[query] rid=%s status=timeout limit_s=%.0f duration_ms=%.0f query=%r",
            rid, QUERY_PIPELINE_TIMEOUT_S, duration_ms, original_query[:80],
        )
        return JSONResponse(
            status_code=504,
            content={
                "error": (
                    f"Request timed out after {QUERY_PIPELINE_TIMEOUT_S:.0f}s. "
                    "Please try a more specific query or try again shortly."
                ),
                "request_id": rid,
            },
        )

    duration_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "[query] rid=%s status=done mode=%s provider=%s confidence=%.2f duration_ms=%.0f",
        rid, state["mode"], state["provider_used"], state["confidence"], duration_ms,
    )

    # Capture non-evidence responses for the admin failure panel.
    if state["mode"] in {"fallback", "evidence_only"} and state.get("fallback_reason"):
        _record_failure(
            request_id=rid,
            query=original_query,
            mode=state["mode"],
            fallback_reason=state["fallback_reason"],
            provider_used=state.get("provider_used") or "none",
        )

    # 6. Assemble QueryResponse from final pipeline state
    response = QueryResponse(
        query=original_query,
        domain=domain,
        answer=state["final_answer"],
        confidence=state["confidence"],
        confidence_band=state["confidence_band"],
        rejected=state["rejected"],
        rejection_reason=state["rejection_reason"],
        citations=state["citations"],
        bibliography=state["bibliography"],
        evidence_summary=state["evidence_summary"],
        risk_flags=state["risk_flags"],
        overall_risk=state["overall_risk"],
        contradictions=state["contradictions"],
        hallucination_check=state["hallucination_dict"],
        sources_retrieved=len(state["raw_docs"]),
        sources_trusted=len(state["trusted_docs"]),
        sources_rejected=len(state["rejected_docs"]),
        mode=state["mode"],
        fallback_reason=state["fallback_reason"],
        provider_used=state["provider_used"],
        provider_attempts=state["provider_attempts"],
        confidence_details=state["confidence_details"],
        confidence_explanation=state["confidence_explanation"],
        related_questions=state.get("related_questions", []),
        selection_rationale=state.get("selection_rationale", {}),
        refiner_status=refiner_status,
        trace=state.get("trace", []),
    )

    return _write_cache(cache_key, response)


# ── Health endpoints ──────────────────────────────────────────────────────────

@router.get("/health/modes")
def query_modes_health():
    total = max(_MODE_METRICS["total_requests"], 1)
    return {
        "requests": _MODE_METRICS["total_requests"],
        "cache_hits": _MODE_METRICS["cache_hits"],
        "mode_counts": {
            "evidence_based": _MODE_METRICS["evidence_based"],
            "evidence_only": _MODE_METRICS["evidence_only"],
            "general_explanation": _MODE_METRICS["general_explanation"],
            "fallback": _MODE_METRICS["fallback"],
        },
        "mode_percentages": {
            "evidence_based": round(_MODE_METRICS["evidence_based"] * 100 / total, 2),
            "evidence_only": round(_MODE_METRICS["evidence_only"] * 100 / total, 2),
            "general_explanation": round(_MODE_METRICS["general_explanation"] * 100 / total, 2),
            "fallback": round(_MODE_METRICS["fallback"] * 100 / total, 2),
        },
        "error_signals": {
            "provider_error_count": _MODE_METRICS["provider_error"],
            "retrieval_empty_count": _MODE_METRICS["retrieval_empty"],
        },
    }


@router.get("/health/providers")
def provider_health():
    return {"providers": get_provider_metrics()}
