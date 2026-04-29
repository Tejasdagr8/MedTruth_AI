import pytest
from src.ranking.medeva_scorer import (
    get_rejection_threshold,
    score_document,
    rank_documents,
    compute_response_confidence,
    should_reject_response,
)


def _make_doc(study_type: str, journal: str, pub_year: int, citations: int, sample: int | None):
    return {
        "id": "test",
        "text": "test",
        "metadata": {
            "study_type": study_type,
            "journal": journal,
            "pub_year": pub_year,
            "citation_count": citations,
            "sample_size": sample,
            "source": "pubmed",
        },
    }


def test_systematic_review_scores_highest():
    sr = _make_doc("systematic_review_meta_analysis", "cochrane database of systematic reviews", 2023, 500, 5000)
    rct = _make_doc("rct_double_blind", "the lancet", 2022, 100, 300)
    case = _make_doc("case_report_series", "bmj", 2020, 5, 3)

    sr_score = score_document(sr).total
    rct_score = score_document(rct).total
    case_score = score_document(case).total

    assert sr_score > rct_score > case_score


def test_recent_paper_scores_higher_than_old():
    recent = _make_doc("rct_single_blind", "the lancet", 2024, 50, 200)
    old = _make_doc("rct_single_blind", "the lancet", 2005, 50, 200)

    assert score_document(recent).total > score_document(old).total


def test_high_citations_boost_score():
    many = _make_doc("cohort_study_prospective", "bmj", 2020, 2000, 500)
    few = _make_doc("cohort_study_prospective", "bmj", 2020, 0, 500)

    assert score_document(many).total > score_document(few).total


def test_confidence_band_high():
    doc = _make_doc("systematic_review_meta_analysis", "cochrane database of systematic reviews", 2023, 1000, 10000)
    score = score_document(doc)
    assert score.confidence_band == "HIGH"


def test_should_reject_when_confidence_too_low():
    assert should_reject_response(0.39) is True
    assert should_reject_response(0.70) is False


def test_adaptive_rejection_threshold_for_strong_evidence():
    strong_docs = [
        _make_doc("rct_double_blind", "the lancet", 2022, 100, 300),
    ]
    weak_docs = [
        _make_doc("case_report_series", "bmj", 2020, 5, 10),
    ]

    assert get_rejection_threshold(strong_docs) == 0.35
    assert get_rejection_threshold(weak_docs) == 0.40
    assert should_reject_response(0.40, strong_docs) is False
    assert should_reject_response(0.39, weak_docs) is True


def test_rank_documents_sorted():
    docs = [
        _make_doc("case_report_series", "bmj", 2015, 5, None),
        _make_doc("systematic_review_meta_analysis", "cochrane database of systematic reviews", 2023, 500, 5000),
        _make_doc("rct_double_blind", "the lancet", 2021, 200, 800),
    ]
    ranked = rank_documents(docs)
    scores = [d["medeva"]["total"] for d in ranked]
    assert scores == sorted(scores, reverse=True)


def test_compute_response_confidence_prioritizes_strong_evidence():
    docs = [
        {
            "metadata": {"study_type": "rct_double_blind", "source": "pubmed"},
            "medeva": {"total": 0.82},
        },
        {
            "metadata": {
                "study_type": "systematic_review_meta_analysis",
                "source": "cochrane",
            },
            "medeva": {"total": 0.78},
        },
        {
            "metadata": {"study_type": "case_report_series", "source": "pubmed"},
            "medeva": {"total": 0.30},
        },
    ]
    confidence, band = compute_response_confidence(docs)
    assert confidence >= 0.70
    assert band in {"HIGH", "MEDIUM"}


def test_compute_response_confidence_stays_low_for_weak_evidence():
    docs = [
        {
            "metadata": {"study_type": "case_report_series", "source": "pubmed"},
            "medeva": {"total": 0.30},
        },
        {
            "metadata": {"study_type": "expert_opinion", "source": "who"},
            "medeva": {"total": 0.22},
        },
    ]
    confidence, band = compute_response_confidence(docs)
    assert confidence < 0.55
    assert band == "LOW"
