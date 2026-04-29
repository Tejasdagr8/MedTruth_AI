import pytest
from src.validation.source_validator import ValidationStatus, validate_document, filter_trusted_docs


def test_pubmed_pmid_is_trusted():
    result = validate_document(pmid="12345678")
    assert result.status == ValidationStatus.TRUSTED


def test_cochrane_doi_is_trusted():
    result = validate_document(doi="10.1002/14651858.CD012345.pub2")
    assert result.status == ValidationStatus.TRUSTED


def test_bmj_doi_is_trusted():
    result = validate_document(doi="10.1136/bmj.p1234")
    assert result.status == ValidationStatus.TRUSTED


def test_lancet_journal_name_is_trusted():
    result = validate_document(journal="The Lancet")
    assert result.status == ValidationStatus.TRUSTED


def test_nature_medicine_is_trusted():
    result = validate_document(journal="Nature Medicine")
    assert result.status == ValidationStatus.TRUSTED


def test_wikipedia_is_blocked():
    result = validate_document(url="https://wikipedia.org/wiki/Aspirin")
    assert result.status == ValidationStatus.REJECTED


def test_webmd_is_blocked():
    result = validate_document(url="https://webmd.com/heart-disease/guide")
    assert result.status == ValidationStatus.REJECTED


def test_unknown_source_is_unverifiable():
    result = validate_document(journal="Random Blog Journal", source="unknown")
    assert result.status == ValidationStatus.UNVERIFIABLE


def test_filter_trusted_docs():
    docs = [
        {"id": "1", "text": "a", "metadata": {"pmid": "99999999", "source": "pubmed", "journal": "BMJ"}},
        {"id": "2", "text": "b", "metadata": {"url": "https://wikipedia.org/wiki/X"}},
    ]
    trusted, rejected = filter_trusted_docs(docs)
    assert len(trusted) == 1
    assert len(rejected) == 1
    assert trusted[0]["id"] == "1"
