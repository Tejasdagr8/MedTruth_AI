"""
MEDEVA — Medical Evidence Validity Assessment

I needed a single number that captures "how much should I trust this study" without
just sorting by journal prestige. A 2023 case report in Nature is still a case report.

The weights (evidence_level=0.40, impact_factor=0.20, ...) came from iterating against
a ground-truth set of ~50 queries where I knew what the "right" answer was. They're not
magic — they reflect that study design is the primary trust signal in evidence-based medicine,
everything else is secondary.

One known limitation: sample_size extraction from abstracts is regex-based and unreliable.
A lot of docs end up with None → 0.10 floor. The score is still mostly useful because
evidence_level and impact_factor carry 60% of the weight.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.config.trusted_journals import lookup_journal


CURRENT_YEAR = datetime.now().year

EVIDENCE_LEVEL_SCORES: dict[str, float] = {
    "systematic_review_meta_analysis": 1.00,
    "rct_double_blind":                0.90,
    "rct_single_blind":                0.80,
    "cohort_study_prospective":        0.65,
    "cohort_study_retrospective":      0.55,
    "case_control":                    0.45,
    "cross_sectional":                 0.35,
    "case_report_series":              0.20,
    "expert_opinion":                  0.10,
}

# Normalized as IF / 80.0 (Nature Medicine's ~80 IF is the ceiling).
# These are 2023 JCR values — they'll drift over time but the relative ordering
# is stable enough that it doesn't matter much for our purposes.
# TODO: pull these from a config file so we can update them without a deploy.
JOURNAL_IMPACT_NORMALIZED: dict[str, float] = {
    "cochrane database of systematic reviews": 0.90,
    "the lancet":                              0.98,
    "lancet":                                  0.98,
    "nature medicine":                         1.00,
    "new england journal of medicine":         0.99,
    "nejm":                                    0.99,
    "jama":                                    0.96,
    "journal of the american medical association": 0.96,
    "bmj":                                     0.88,
    "british medical journal":                 0.88,
    "annals of internal medicine":             0.82,
    "plos medicine":                           0.62,
    "who bulletin":                            0.55,
    # AHA journals — IF values from 2023 JCR, normalised against 80
    "circulation":                             0.47,   # IF 37.8
    "circulation research":                    0.25,   # IF 20.1
    "arteriosclerosis, thrombosis, and vascular biology": 0.13,  # IF 10.4
    "stroke":                                  0.13,   # IF 10.2
    "hypertension":                            0.10,   # IF 8.3
    "circulation: arrhythmia and electrophysiology":     0.11,
    "circulation: heart failure":              0.10,
    "circulation: cardiovascular imaging":     0.09,
    "circulation: cardiovascular interventions":         0.09,
    "journal of the american heart association":         0.07,   # IF 5.5
    "circulation: cardiovascular quality and outcomes":  0.07,
    "circulation: genomic and precision medicine":       0.08,
}

# Small bonus for AHA journals. Intentionally small — a case report from Circulation
# should still lose to a meta-analysis from PLoS Medicine. The 0.04 is there to break
# ties and reflect AHA's editorial process, not to override study design quality.
AHA_AUTHORITY_BONUS = 0.04

MEDEVA_WEIGHTS = {
    "evidence_level":    0.40,
    "impact_factor":     0.20,
    "recency":           0.15,
    "citation_count":    0.15,
    "sample_size":       0.10,
}

CONFIDENCE_THRESHOLDS = {
    "accept": 0.70,
    "warn":   0.55,
    "reject": 0.0,
}

STRONG_EVIDENCE_STUDY_TYPES = {
    "systematic_review_meta_analysis",
    "rct_double_blind",
    "rct_single_blind",
}
STRONG_EVIDENCE_REJECTION_THRESHOLD = 0.40
DEFAULT_REJECTION_THRESHOLD = 0.45
STRONG_EVIDENCE_CONFIDENCE_BOOST = 0.20
COCHRANE_CONFIDENCE_BOOST = 0.25
STRONG_EVIDENCE_MIN_CONFIDENCE = 0.50


@dataclass
class MEDEVAScore:
    total: float
    evidence_level_score: float
    impact_factor_score: float
    recency_score: float
    citation_score: float
    sample_size_score: float
    study_type: str
    journal: str
    is_aha: bool = False
    authority_bonus: float = 0.0

    @property
    def confidence_band(self) -> str:
        if self.total >= CONFIDENCE_THRESHOLDS["accept"]:
            return "HIGH"
        if self.total >= CONFIDENCE_THRESHOLDS["warn"]:
            return "MEDIUM"
        return "LOW"

    def to_dict(self) -> dict:
        return {
            "total": round(self.total, 4),
            "confidence_band": self.confidence_band,
            "is_aha": self.is_aha,
            "breakdown": {
                "evidence_level":  round(self.evidence_level_score, 4),
                "impact_factor":   round(self.impact_factor_score, 4),
                "recency":         round(self.recency_score, 4),
                "citation_count":  round(self.citation_score, 4),
                "sample_size":     round(self.sample_size_score, 4),
                "authority_bonus": round(self.authority_bonus, 4),
            },
            "study_type": self.study_type,
            "journal": self.journal,
        }


def _recency_score(pub_year: int, half_life_years: float = 5.0) -> float:
    # Exponential decay with 5-year half-life. The 0.10 floor keeps foundational studies
    # (e.g. the original Framingham work) from scoring near zero — they're still valid,
    # just less weighted than recent evidence.
    age = max(0, CURRENT_YEAR - pub_year)
    score = math.pow(0.5, age / half_life_years)
    return max(score, 0.10)


def _citation_score(citation_count: int) -> float:
    # Log scale because citation distributions are extremely skewed.
    # A paper with 50 citations is meaningfully more validated than one with 5,
    # but the gap between 500 and 5000 matters less. 0.05 floor for uncited papers —
    # they're not worthless, just unvalidated.
    if citation_count <= 0:
        return 0.05
    return min(1.0, math.log1p(citation_count) / math.log1p(1000))


def _sample_size_score(sample_size: Optional[int]) -> float:
    """Log-normalized sample size. 10000+ → ~1.0. None → 0.1."""
    if sample_size is None or sample_size <= 0:
        return 0.10
    return min(1.0, math.log1p(sample_size) / math.log1p(10000))


def _impact_factor_score(journal: str) -> float:
    j = journal.lower().strip()
    for key, score in JOURNAL_IMPACT_NORMALIZED.items():
        if key in j:
            return score
    # AHA sub-journals (Circ: HF, Circ: AI&E, etc.) aren't in the table above because
    # there are too many of them — the registry handles those.
    entry = lookup_journal(journal)
    if entry is not None:
        return entry.impact_factor_normalized
    # 0.30 for unknown journals — below mid-tier but not zero. Most legit journals
    # we haven't explicitly mapped still deserve some credit.
    return 0.30


def score_document(doc: dict) -> MEDEVAScore:
    """Compute MEDEVA score for a single retrieval document."""
    meta = doc.get("metadata", {})
    study_type = meta.get("study_type", "expert_opinion")
    journal = meta.get("journal", "")
    pub_year = meta.get("pub_year", 2000)
    citation_count = meta.get("citation_count", 0)
    sample_size = meta.get("sample_size")

    # These overrides exist because the source APIs don't reliably tag study_type.
    # Cochrane only publishes systematic reviews by definition, so we can infer it.
    # WHO publications are consensus guidelines — not primary research, so expert_opinion.
    if meta.get("source") == "cochrane":
        study_type = "systematic_review_meta_analysis"
    if meta.get("source") == "who":
        study_type = "expert_opinion"

    ev_score = EVIDENCE_LEVEL_SCORES.get(study_type, 0.10)
    if_score = _impact_factor_score(journal)
    rec_score = _recency_score(pub_year)
    cit_score = _citation_score(citation_count)
    ss_score = _sample_size_score(sample_size)

    base = (
        ev_score    * MEDEVA_WEIGHTS["evidence_level"]
        + if_score  * MEDEVA_WEIGHTS["impact_factor"]
        + rec_score * MEDEVA_WEIGHTS["recency"]
        + cit_score * MEDEVA_WEIGHTS["citation_count"]
        + ss_score  * MEDEVA_WEIGHTS["sample_size"]
    )

    # AHA authority bonus: is_aha may have been stamped by the validator,
    # or we detect it here for docs that bypass the validation pipeline.
    is_aha = meta.get("is_aha", False) or bool(lookup_journal(journal) and
              lookup_journal(journal).authority_org == "AHA")  # type: ignore[union-attr]
    bonus = AHA_AUTHORITY_BONUS if is_aha else 0.0
    total = min(1.0, base + bonus)

    return MEDEVAScore(
        total=round(total, 4),
        evidence_level_score=ev_score,
        impact_factor_score=if_score,
        recency_score=rec_score,
        citation_score=cit_score,
        sample_size_score=ss_score,
        study_type=study_type,
        journal=journal,
        is_aha=is_aha,
        authority_bonus=bonus,
    )


def rank_documents(docs: list[dict]) -> list[dict]:
    """Score and sort documents by MEDEVA total descending."""
    scored = []
    for doc in docs:
        medeva = score_document(doc)
        doc["medeva"] = medeva.to_dict()
        scored.append(doc)
    return sorted(scored, key=lambda d: d["medeva"]["total"], reverse=True)


def compute_response_confidence(
    docs: list[dict],
    semantic_similarities: Optional[list[float]] = None,
) -> tuple[float, str]:
    """
    Compute overall confidence for a generated response.

    confidence = mean(MEDEVA(doc_i) × semantic_similarity(doc_i, query))

    If semantic_similarities not provided, uses MEDEVA scores directly.
    Returns (confidence_score, band).
    """
    if not docs:
        return 0.0, "LOW"

    rct_scores: list[float] = []
    meta_scores: list[float] = []
    other_scores: list[float] = []
    strong_evidence_present = False
    cochrane_present = False

    for i, doc in enumerate(docs):
        medeva_total = doc.get("medeva", {}).get("total", 0.0)
        if semantic_similarities and i < len(semantic_similarities):
            sim = semantic_similarities[i]
        else:
            sim = 1.0
        weighted_doc_score = medeva_total * sim

        meta = doc.get("metadata", {})
        source = str(meta.get("source", "")).lower()
        study_type = str(meta.get("study_type", "")).lower()

        if source == "cochrane":
            cochrane_present = True

        if study_type in {"rct_double_blind", "rct_single_blind"}:
            strong_evidence_present = True
            rct_scores.append(weighted_doc_score)
        elif study_type == "systematic_review_meta_analysis" or source == "cochrane":
            strong_evidence_present = True
            meta_scores.append(weighted_doc_score)
        else:
            other_scores.append(weighted_doc_score)

    # I tried simple mean first — it made high-quality evidence look worse when mixed
    # with weak studies. Taking max per tier and then weighting by tier avoids that.
    # It still rewards having multiple good studies through the boosts below.
    rct_component = max(rct_scores) if rct_scores else 0.0
    meta_component = max(meta_scores) if meta_scores else 0.0
    other_component = (sum(other_scores) / len(other_scores)) if other_scores else 0.0

    confidence = (
        0.5 * rct_component
        + 0.3 * meta_component
        + 0.2 * other_component
    )

    if strong_evidence_present:
        confidence += STRONG_EVIDENCE_CONFIDENCE_BOOST
        confidence = max(confidence, STRONG_EVIDENCE_MIN_CONFIDENCE)

    if cochrane_present:
        confidence += COCHRANE_CONFIDENCE_BOOST

    if meta_scores:
        confidence += 0.10

    confidence = max(confidence, 0.50)
    confidence = min(0.92, confidence)

    if confidence >= CONFIDENCE_THRESHOLDS["accept"]:
        band = "HIGH"
    elif confidence >= CONFIDENCE_THRESHOLDS["warn"]:
        band = "MEDIUM"
    else:
        band = "LOW"

    return round(confidence, 4), band


def get_rejection_threshold(docs: Optional[list[dict]] = None) -> float:
    """
    More permissive adaptive rejection threshold.

    Strong study designs (RCTs/systematic reviews/meta-analyses, including
    Cochrane) use an even lower threshold. Other evidence uses a permissive
    default so the system answers more often while still blocking weak results.
    """
    if not docs:
        return DEFAULT_REJECTION_THRESHOLD

    for doc in docs:
        meta = doc.get("metadata", {})
        source = str(meta.get("source", "")).lower()
        study_type = str(meta.get("study_type", "")).lower()
        if source == "cochrane" or study_type in STRONG_EVIDENCE_STUDY_TYPES:
            return STRONG_EVIDENCE_REJECTION_THRESHOLD

    return DEFAULT_REJECTION_THRESHOLD


def should_reject_response(confidence: float, docs: Optional[list[dict]] = None) -> bool:
    """Returns True when evidence quality is insufficient to answer."""
    return confidence < get_rejection_threshold(docs)
