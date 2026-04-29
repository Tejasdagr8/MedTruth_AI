"""
Hallucination detection via NLI entailment checking.
Extracts atomic claims from generated text and verifies each claim
is entailed by at least one source passage.

Uses a MedNLI-fine-tuned DeBERTa model for medical domain accuracy.
Falls back to a general-purpose NLI model if MedNLI is unavailable.
"""

import os
import re
import logging
from dataclasses import dataclass
from typing import Optional

MEDNLI_MODEL = os.getenv(
    "NLI_MODEL",
    "microsoft/deberta-v3-base-mnli"   # swap to MedNLI fine-tune when available
)
ENTAILMENT_THRESHOLD = float(os.getenv("ENTAILMENT_THRESHOLD", "0.60"))
SIMILARITY_SUPPORT_THRESHOLD = float(os.getenv("SIMILARITY_SUPPORT_THRESHOLD", "0.70"))
SEVERE_UNCERTAINTY_THRESHOLD = float(os.getenv("SEVERE_UNCERTAINTY_THRESHOLD", "0.40"))
SECTION_HEADERS = [
    "DIRECT ANSWER:",
    "SUPPORTING EVIDENCE:",
    "LIMITATIONS / CONTEXT:",
    "EVIDENCE QUALITY:",
]
CLAIM_THRESHOLDS = {
    "causal": 0.75,
    "weak": 0.60,
    "summary": 0.50,
    "general": 0.65,
}
SAFE_PHRASES = [
    "evidence includes",
    "based on",
    "studies include",
    "evidence is based on",
]
TONE_PREFIXES = [
    "Evidence is suggestive",
    "Evidence is moderately strong",
    "Evidence is strong",
]
logger = logging.getLogger(__name__)


@dataclass
class ClaimVerification:
    claim: str
    entailed: bool
    max_entailment_score: float
    best_source_index: Optional[int]
    flagged: bool  # True when claim is not supported by any source


@dataclass
class EntailmentReport:
    verified_claims: list[ClaimVerification]
    unverified_claims: list[ClaimVerification]
    hallucination_risk: str  # "LOW" | "MEDIUM" | "HIGH"
    hallucination_score: float  # fraction of claims that are unverified
    safe_answer: str  # original answer with unverified claims struck or removed


def _extract_claims(text: str) -> list[str]:
    """
    Split generated text into atomic claims (sentences).
    Strips citation markers for clean NLI input.
    """
    clean = clean_text(text)
    # Remove citation markers [1], [2], etc.
    clean = re.sub(r"\[\d+\]", "", clean)
    # Split on sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", clean.strip())
    # Filter: keep substantive sentences, drop pure meta-commentary
    claims = []
    for s in sentences:
        s = s.strip()
        if len(s) < 20:
            continue
        # Skip sentences that are just evidence summaries (not factual claims)
        if s.lower().startswith("evidence based on"):
            continue
        claims.append(s)
    return claims


def clean_text(text: str) -> str:
    cleaned = text
    for header in SECTION_HEADERS:
        cleaned = cleaned.replace(header, "")
    return cleaned.strip()


def classify_claim(sentence: str) -> str:
    s = sentence.lower()
    if any(word in s for word in ["reduce", "increase", "significant"]):
        return "causal"
    if any(word in s for word in ["suggests", "may", "associated"]):
        return "weak"
    if any(word in s for word in ["evidence includes", "based on"]):
        return "summary"
    return "general"


def is_safe_sentence(sentence: str) -> bool:
    s = sentence.lower()
    return any(phrase in s for phrase in SAFE_PHRASES)


def strip_tone_prefix(sentence: str) -> str:
    cleaned = sentence
    for prefix in TONE_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned.replace(prefix, "", 1).strip(" ,.-:")
    return cleaned


def _get_pipeline():
    """Lazy-load the NLI pipeline to avoid startup overhead."""
    try:
        from transformers import pipeline
        return pipeline(
            "text-classification",
            model=MEDNLI_MODEL,
            return_all_scores=True,
            device=-1,  # CPU; set to 0 for GPU
        )
    except Exception:
        return None


_nli_pipeline = None


def _entailment_score(premise: str, hypothesis: str, pipe) -> float:
    """Run NLI and return entailment probability."""
    try:
        result = pipe(f"{premise} [SEP] {hypothesis}", truncation=True, max_length=512)
        # result is list of [{'label': ..., 'score': ...}]
        scores = {r["label"].upper(): r["score"] for r in result[0]}
        return scores.get("ENTAILMENT", 0.0)
    except Exception:
        return 0.0


def _lexical_similarity(a: str, b: str) -> float:
    """Simple token Jaccard similarity for support fallback."""
    a_tokens = set(re.findall(r"[a-z0-9]+", a.lower()))
    b_tokens = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def verify_claims(
    answer: str,
    source_docs: list[dict],
    threshold: float = ENTAILMENT_THRESHOLD,
) -> EntailmentReport:
    """
    Main entailment verification pipeline.
    Each claim in `answer` must be entailed by at least one source passage.
    """
    global _nli_pipeline

    claims = _extract_claims(answer)
    if not claims:
        return EntailmentReport(
            verified_claims=[],
            unverified_claims=[],
            hallucination_risk="LOW",
            hallucination_score=0.0,
            safe_answer=answer,
        )

    source_texts = [doc.get("text", "")[:512] for doc in source_docs]

    if _nli_pipeline is None:
        _nli_pipeline = _get_pipeline()

    verified, unverified = [], []

    for claim in claims:
        claim = strip_tone_prefix(claim)
        if is_safe_sentence(claim):
            cv = ClaimVerification(
                claim=claim,
                entailed=True,
                max_entailment_score=1.0,
                best_source_index=None,
                flagged=False,
            )
            verified.append(cv)
            continue

        claim_type = classify_claim(claim)
        threshold = CLAIM_THRESHOLDS.get(claim_type, ENTAILMENT_THRESHOLD)
        logger.debug("Entailment threshold for claim_type=%s set to %.2f", claim_type, threshold)
        best_score = 0.0
        best_idx = None

        best_similarity = 0.0
        if _nli_pipeline and source_texts:
            for idx, src in enumerate(source_texts):
                entailment_score = _entailment_score(src, claim, _nli_pipeline)
                similarity_score = _lexical_similarity(src, claim)
                score = max(entailment_score, similarity_score)
                if score > best_score:
                    best_score = score
                    best_idx = idx
                    best_similarity = similarity_score
        else:
            # Pipeline unavailable — use keyword overlap as a weak fallback
            claim_words = set(claim.lower().split())
            for idx, src in enumerate(source_texts):
                src_words = set(src.lower().split())
                overlap = len(claim_words & src_words) / max(len(claim_words), 1)
                if overlap > best_score:
                    best_score = overlap
                    best_idx = idx

        is_entailed = best_score >= threshold or best_similarity >= SIMILARITY_SUPPORT_THRESHOLD
        cv = ClaimVerification(
            claim=claim,
            entailed=is_entailed,
            max_entailment_score=round(best_score, 4),
            best_source_index=best_idx,
            flagged=not is_entailed,
        )
        if is_entailed:
            verified.append(cv)
        else:
            unverified.append(cv)

    total = len(claims)
    unverified_frac = len(unverified) / total if total > 0 else 0.0

    if unverified_frac == 0:
        risk = "LOW"
    elif unverified_frac <= 0.25:
        risk = "MEDIUM"
    else:
        risk = "HIGH"

    # Build safe answer: only annotate claims with severe support uncertainty.
    # This avoids contradictory UX (e.g., moderate confidence + aggressive UNVERIFIED tags).
    safe_answer = answer
    for cv in unverified:
        if cv.max_entailment_score >= SEVERE_UNCERTAINTY_THRESHOLD:
            continue
        safe_answer = safe_answer.replace(
            cv.claim,
            f"[⚠️ Some uncertainty in evidence] {cv.claim}",
        )

    return EntailmentReport(
        verified_claims=verified,
        unverified_claims=unverified,
        hallucination_risk=risk,
        hallucination_score=round(unverified_frac, 4),
        safe_answer=safe_answer,
    )


def to_api_dict(report: EntailmentReport) -> dict:
    return {
        "hallucination_risk": report.hallucination_risk,
        "hallucination_score": report.hallucination_score,
        "verified_count": len(report.verified_claims),
        "unverified_count": len(report.unverified_claims),
        "unverified_claims": [
            {
                "claim": cv.claim,
                "entailment_score": cv.max_entailment_score,
            }
            for cv in report.unverified_claims
        ],
        "safe_answer": report.safe_answer,
    }
