"""
Tests for AHA journal integration across config, validator, and MEDEVA scorer.
"""

import pytest
from src.config.trusted_journals import (
    is_aha_journal,
    lookup_journal,
    AHA_ISSNS,
    AHA_DOI_PREFIX,
)
from src.validation.source_validator import (
    ValidationStatus,
    validate_document,
    filter_trusted_docs,
)
from src.ranking.medeva_scorer import score_document, AHA_AUTHORITY_BONUS


# ── config tests ──────────────────────────────────────────────────────────────

def test_circulation_is_aha():
    assert is_aha_journal("Circulation") is True

def test_circulation_research_is_aha():
    assert is_aha_journal("Circulation Research") is True

def test_stroke_is_aha():
    assert is_aha_journal("Stroke") is True

def test_hypertension_is_aha():
    assert is_aha_journal("Hypertension") is True

def test_jaha_is_aha():
    assert is_aha_journal("Journal of the American Heart Association") is True

def test_atvb_is_aha():
    assert is_aha_journal("Arteriosclerosis, Thrombosis, and Vascular Biology") is True

def test_case_insensitive_match():
    assert is_aha_journal("CIRCULATION") is True
    assert is_aha_journal("stroke") is True

def test_non_aha_journal_is_false():
    assert is_aha_journal("The Lancet") is False
    assert is_aha_journal("Nature Medicine") is False
    assert is_aha_journal("Random Blog") is False

def test_lookup_returns_entry():
    entry = lookup_journal("Circulation")
    assert entry is not None
    assert entry.authority_org == "AHA"
    assert entry.doi_prefix == "10.1161"

def test_aha_issns_populated():
    assert len(AHA_ISSNS) > 0
    assert "0009-7322" in AHA_ISSNS   # Circulation print ISSN
    assert "1524-4539" in AHA_ISSNS   # Circulation electronic ISSN
    assert "0039-2499" in AHA_ISSNS   # Stroke print ISSN

def test_aha_doi_prefix():
    assert AHA_DOI_PREFIX == "10.1161"


# ── validator tests ───────────────────────────────────────────────────────────

def test_circulation_doi_is_trusted():
    result = validate_document(doi="10.1161/CIRCULATIONAHA.123.056789")
    assert result.status == ValidationStatus.TRUSTED
    assert result.is_aha is True

def test_circulation_issn_is_trusted():
    result = validate_document(issn="0009-7322")
    assert result.status == ValidationStatus.TRUSTED
    assert result.is_aha is True

def test_stroke_journal_name_is_trusted():
    result = validate_document(journal="Stroke", pmid="12345678")
    assert result.status == ValidationStatus.TRUSTED
    assert result.is_aha is True

def test_non_aha_doc_has_is_aha_false():
    result = validate_document(doi="10.1136/bmj.p1234", journal="BMJ")
    assert result.status == ValidationStatus.TRUSTED
    assert result.is_aha is False

def test_filter_stamps_is_aha_into_metadata():
    docs = [
        {
            "id": "pmid:11111111",
            "text": "Circulation study",
            "metadata": {
                "pmid": "11111111",
                "journal": "Circulation",
                "source": "pubmed",
                "doi": "10.1161/CIRCULATIONAHA.121.000001",
            },
        },
        {
            "id": "pmid:22222222",
            "text": "Lancet study",
            "metadata": {
                "pmid": "22222222",
                "journal": "The Lancet",
                "source": "pubmed",
            },
        },
    ]
    trusted, _ = filter_trusted_docs(docs)
    aha_doc = next(d for d in trusted if "Circulation" in d["metadata"]["journal"])
    lancet_doc = next(d for d in trusted if "Lancet" in d["metadata"]["journal"])
    assert aha_doc["metadata"]["is_aha"] is True
    assert lancet_doc["metadata"]["is_aha"] is False


# ── MEDEVA scorer tests ───────────────────────────────────────────────────────

def _make_doc(journal: str, study_type: str, is_aha: bool = False) -> dict:
    return {
        "id": "test",
        "text": "test abstract",
        "metadata": {
            "journal": journal,
            "study_type": study_type,
            "pub_year": 2023,
            "citation_count": 100,
            "sample_size": 500,
            "source": "pubmed",
            "is_aha": is_aha,
        },
    }

def test_aha_doc_receives_authority_bonus():
    # Compare AHA journal vs non-AHA journal with identical study type/year/citations.
    # Circulation (AHA) vs a generic trusted journal — bonus should differentiate them.
    aha_doc     = _make_doc("Circulation", "rct_double_blind", is_aha=True)
    non_aha_doc = _make_doc("Unknown Trusted Journal", "rct_double_blind", is_aha=False)
    aha_score     = score_document(aha_doc)
    non_aha_score = score_document(non_aha_doc)
    assert aha_score.is_aha is True
    assert aha_score.authority_bonus == AHA_AUTHORITY_BONUS
    assert non_aha_score.authority_bonus == 0.0
    # AHA doc should outscore a generic journal of equal evidence level
    assert aha_score.total > non_aha_score.total

def test_aha_bonus_in_breakdown_dict():
    doc = _make_doc("Circulation", "rct_single_blind", is_aha=True)
    result = score_document(doc)
    assert result.to_dict()["is_aha"] is True
    assert result.to_dict()["breakdown"]["authority_bonus"] == AHA_AUTHORITY_BONUS

def test_aha_detected_from_journal_name_without_flag():
    doc = _make_doc("Circulation", "rct_double_blind", is_aha=False)
    result = score_document(doc)
    assert result.is_aha is True

def test_aha_total_capped_at_one():
    doc = _make_doc("Circulation", "systematic_review_meta_analysis", is_aha=True)
    doc["metadata"]["citation_count"] = 100000
    doc["metadata"]["sample_size"] = 100000
    result = score_document(doc)
    assert result.total <= 1.0

def test_circulation_impact_factor_in_scorer():
    doc = _make_doc("Circulation", "rct_double_blind", is_aha=True)
    score = score_document(doc)
    # Circulation IF ~37.8 / 80 ≈ 0.47; expect a meaningful IF score
    assert score.impact_factor_score >= 0.40

def test_stroke_impact_factor_in_scorer():
    doc = _make_doc("Stroke", "cohort_study_prospective", is_aha=True)
    score = score_document(doc)
    assert score.impact_factor_score >= 0.10
