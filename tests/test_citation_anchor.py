import pytest
from src.rag.citation_anchor import build_citations, anchor_citations_in_text, format_bibliography


def _make_doc(i: int, pmid: str, title: str, journal: str, year: int):
    return {
        "id": f"pmid:{pmid}",
        "text": f"{title}. Abstract text here.",
        "metadata": {
            "pmid": pmid,
            "doi": f"10.1136/bmj.{i}",
            "title": title,
            "journal": journal,
            "pub_year": year,
            "authors": ["Smith J", "Jones A", "Brown K", "Wilson D"],
            "source": "pubmed",
        },
        "medeva": {"total": 0.82, "confidence_band": "HIGH"},
    }


def test_build_citations_indexed_from_one():
    docs = [_make_doc(1, "11111111", "Test Study", "The Lancet", 2022)]
    citations = build_citations(docs)
    assert len(citations) == 1
    assert citations[0].index == 1
    assert citations[0].pmid == "11111111"


def test_citations_url_uses_pmid():
    docs = [_make_doc(1, "22222222", "Another Study", "BMJ", 2023)]
    citations = build_citations(docs)
    assert "22222222" in citations[0].url


def test_anchor_removes_orphan_markers():
    text = "Drug X reduces mortality [1] and also affects BP [99]."
    docs = [_make_doc(1, "33333333", "Drug X Study", "Lancet", 2021)]
    citations = build_citations(docs)
    anchored = anchor_citations_in_text(text, citations)
    assert "[99]" not in anchored
    assert "[1]" in anchored


def test_bibliography_format():
    docs = [_make_doc(1, "44444444", "Metformin Trial", "NEJM", 2020)]
    citations = build_citations(docs)
    bib = format_bibliography(citations)
    assert "Metformin Trial" in bib
    assert "NEJM" in bib
    assert "2020" in bib
    assert "44444444" in bib
