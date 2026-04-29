"""
LLM-powered query refinement for medical database retrieval.

Single call, low token budget, always falls back to the original query on any
failure so it never blocks the retrieval pipeline.
"""

import json
import hashlib
import logging
import re
import threading
import time
from typing import NamedTuple

from src.llm.fallback_client import generate_text_with_fallback

logger = logging.getLogger(__name__)

_INTENT_OPTIONS = frozenset({"treatment", "mechanism", "diagnosis", "risk", "general"})
_STATUS_SUCCESS = "success"
_STATUS_FAILED = "failed"
_CACHE_TTL_SECONDS = 600
_REFINER_CACHE: dict[str, tuple[float, "RefinedQuery"]] = {}
_REFINER_CACHE_LOCK = threading.Lock()

_SYSTEM_PROMPT = (
    "You are a medical query reformulation specialist.\n"
    "Your ONLY job is to reformat a user health question for PubMed/EuropePMC retrieval.\n\n"
    "RULES:\n"
    "- Do NOT answer the question\n"
    "- Do NOT add medical claims or facts not present in the original query\n"
    "- Expand abbreviations, add MeSH-aligned synonyms, clarify vague phrasing\n"
    "- Return ONLY valid JSON — no markdown fences, no extra text\n\n"
    "JSON schema (return exactly this structure):\n"
    "{\n"
    '  "refined_query": "<MeSH-optimized query string for database search>",\n'
    '  "expanded_terms": ["<synonym1>", "<synonym2>", "<synonym3>"],\n'
    '  "detected_intent": "<treatment|mechanism|diagnosis|risk|general>"\n'
    "}"
)


class RefinedQuery(NamedTuple):
    refined_query: str
    expanded_terms: list[str]
    detected_intent: str  # one of: treatment, mechanism, diagnosis, risk, general
    status: str           # success | failed


def _cache_key(query: str) -> str:
    normalized = " ".join(query.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> RefinedQuery | None:
    now = time.time()
    with _REFINER_CACHE_LOCK:
        item = _REFINER_CACHE.get(key)
        if not item:
            return None
        ts, value = item
        if now - ts > _CACHE_TTL_SECONDS:
            _REFINER_CACHE.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: RefinedQuery) -> None:
    with _REFINER_CACHE_LOCK:
        _REFINER_CACHE[key] = (time.time(), value)


def refine_query(raw_query: str) -> RefinedQuery:
    """
    Refine a raw user query for medical database retrieval.

    Returns the original query unchanged on any failure — never raises.
    """
    fallback = RefinedQuery(raw_query, [], "general", _STATUS_FAILED)
    key = _cache_key(raw_query)
    if cached := _cache_get(key):
        return cached
    try:
        text, _, _ = generate_text_with_fallback(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=f"Reformulate for medical database retrieval:\n\n{raw_query}",
            max_tokens=200,
        )
        # Strip markdown code fences if the model wrapped the JSON
        json_match = re.search(r"\{.*?\}", text, re.DOTALL)
        if not json_match:
            logger.warning("Query refinement parse failed (no JSON) for %r", raw_query)
            _cache_set(key, fallback)
            return fallback

        data = json.loads(json_match.group(0))

        refined = str(data.get("refined_query") or raw_query).strip() or raw_query
        terms = [str(t).strip() for t in (data.get("expanded_terms") or []) if t][:6]
        intent = str(data.get("detected_intent") or "general").lower()
        if intent not in _INTENT_OPTIONS:
            intent = "general"

        refined_query = RefinedQuery(
            refined_query=refined,
            expanded_terms=terms,
            detected_intent=intent,
            status=_STATUS_SUCCESS,
        )
        _cache_set(key, refined_query)
        return refined_query

    except Exception:
        logger.warning("Query refinement failed for %r — using original query", raw_query, exc_info=True)
        _cache_set(key, fallback)
        return fallback
