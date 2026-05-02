"""
Source validation gate.

The point here is simple: I don't want the system to silently answer from WebMD or
a retracted paper someone uploaded to ResearchGate. Every document must clear at least
one signal before it reaches the ranker.

The signal priority is:
  1. Blocked domain → hard reject, no further checks
  2. ISSN match → most reliable for journals with known ISSNs
  3. PMID → confirms MEDLINE indexing, which has its own quality bar
  4. DOI prefix → publisher-level trust (not perfect — Elsevier hosts both Lancet and junk)
  5. Journal name regex → fallback, prone to false positives but catches edge cases
  6. Source tag → weakest, basically just "came from PubMed API"

Note on DOI prefix splitting: DOIs look like 10.XXXX/suffix, so the publisher prefix is
everything before the first "/". I originally split on "." which gave "10" and "XXXX/suffix"
— caught this during testing when nothing matched. Now splits on "/" like it should.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.config.trusted_journals import AHA_ISSNS, AHA_DOI_PREFIX, is_aha_journal


class ValidationStatus(str, Enum):
    TRUSTED = "trusted"
    REJECTED = "rejected"
    UNVERIFIABLE = "unverifiable"


@dataclass
class ValidationResult:
    status: ValidationStatus
    reason: str
    trust_tier: int       # 1 = highest (Cochrane/WHO), 2 = top journals, 3 = acceptable
    is_aha: bool = False  # True when journal is an AHA publication


# ISSN whitelist for trusted journals (print + electronic)
TRUSTED_ISSNS = {
    # BMJ
    "0959-8138", "1756-1833",
    # The Lancet
    "0140-6736", "1474-547X",
    # Nature Medicine
    "1078-8956", "1546-170X",
    # Cochrane Database
    "1361-6137", "1469-493X",
    # NEJM
    "0028-4793", "1533-4406",
    # JAMA
    "0098-7484", "1538-3598",
    # Annals of Internal Medicine
    "0003-4819", "1539-3704",
    # PLoS Medicine
    "1549-1277", "1549-1676",
    # WHO Bulletin
    "0042-9686", "1564-0604",
    # AHA journals (12 journals, sourced from trusted_journals.py)
    *AHA_ISSNS,
}

TRUSTED_JOURNAL_PATTERNS = [
    re.compile(r"bmj|british medical journal", re.I),
    re.compile(r"\blancet\b", re.I),
    re.compile(r"nature medicine", re.I),
    re.compile(r"cochrane", re.I),
    re.compile(r"world health organ|who bulletin", re.I),
    re.compile(r"new england journal of medicine|nejm", re.I),
    re.compile(r"\bjama\b|journal of the american medical association", re.I),
    re.compile(r"annals of internal medicine", re.I),
    re.compile(r"plos medicine", re.I),
    re.compile(r"pubmed|medline", re.I),
    # AHA journals
    re.compile(r"^circulation$|circulation research|circulation: |circulation cardiovascular", re.I),
    re.compile(r"^stroke$", re.I),
    re.compile(r"^hypertension$", re.I),
    re.compile(r"journal of the american heart association|\bjaha\b", re.I),
    re.compile(r"arteriosclerosis.{0,10}thrombosis.{0,10}vascular biology|\batvb\b", re.I),
]

TRUSTED_SOURCES = {"pubmed", "europepmc", "cochrane", "who", "cdc"}

TRUSTED_DOI_PREFIXES = {
    "10.1136",   # BMJ
    "10.1016",   # Lancet (Elsevier — yes, Elsevier publishes a lot of things, but Lancet specifically)
    "10.1038",   # Nature
    "10.1002",   # Cochrane / Wiley
    "10.1001",   # JAMA / AMA
    "10.7326",   # Annals of Internal Medicine
    "10.1371",   # PLoS Medicine
    "10.2471",   # WHO Bulletin
    "10.1161",   # AHA (Circulation family, Stroke, Hypertension)
    # TODO: consider adding 10.1056 (NEJM) — currently caught by journal name regex
}

BLOCKED_DOMAIN_PATTERNS = [
    re.compile(r"wikipedia\.org", re.I),
    re.compile(r"webmd\.com", re.I),
    re.compile(r"healthline\.com", re.I),
    re.compile(r"mayoclinic\.org/blogs", re.I),
    re.compile(r"reddit\.com", re.I),
    re.compile(r"quora\.com", re.I),
    re.compile(r"medium\.com", re.I),
    re.compile(r"blogspot\.com", re.I),
    re.compile(r"wordpress\.com", re.I),
    re.compile(r"news\..*\.com", re.I),
]


def _check_doi(doi: Optional[str]) -> Optional[ValidationResult]:
    if not doi:
        return None
    clean = doi.strip()
    # Strip URL wrappers so bare DOIs and URLs both work
    for url_prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if clean.lower().startswith(url_prefix):
            clean = clean[len(url_prefix):]
            break
    # DOI structure: 10.XXXX/suffix — publisher prefix is everything before the first "/"
    prefix = clean.split("/")[0]
    if prefix in TRUSTED_DOI_PREFIXES:
        return ValidationResult(
            status=ValidationStatus.TRUSTED,
            reason=f"DOI prefix {prefix} belongs to trusted publisher",
            trust_tier=2,
        )
    return None


def _check_journal(journal: str) -> Optional[ValidationResult]:
    for pattern in TRUSTED_JOURNAL_PATTERNS:
        if pattern.search(journal):
            tier = 1 if pattern.search("cochrane") or pattern.search("who") else 2
            return ValidationResult(
                status=ValidationStatus.TRUSTED,
                reason=f"Journal '{journal}' matches trusted journal list",
                trust_tier=tier,
            )
    return None


def _check_source_tag(source: str) -> Optional[ValidationResult]:
    if source.lower() in TRUSTED_SOURCES:
        tier = 1 if source.lower() in ("cochrane", "who") else 2
        return ValidationResult(
            status=ValidationStatus.TRUSTED,
            reason=f"Source '{source}' is in trusted source registry",
            trust_tier=tier,
        )
    return None


def _check_pmid(pmid: Optional[str]) -> Optional[ValidationResult]:
    # PMID is the strongest signal after ISSN — MEDLINE has its own indexing criteria
    # and won't include pure grey literature or blog posts. The regex just validates
    # format; we're not hitting the NCBI API to verify existence.
    if pmid and re.match(r"^\d{1,10}$", str(pmid).strip()):
        return ValidationResult(
            status=ValidationStatus.TRUSTED,
            reason=f"PMID {pmid} confirms PubMed/MEDLINE indexing",
            trust_tier=2,
        )
    return None


def validate_document(
    source: str = "",
    journal: str = "",
    doi: Optional[str] = None,
    pmid: Optional[str] = None,
    issn: Optional[str] = None,
    url: Optional[str] = None,
) -> ValidationResult:
    """
    Multi-signal validation. Returns TRUSTED only if at least one signal passes.
    Returns REJECTED if a blocked domain is detected.
    Sets is_aha=True when any signal identifies the document as an AHA journal.
    """
    aha = is_aha_journal(journal) or (
        doi is not None and doi.strip().lstrip("https://doi.org/").startswith(AHA_DOI_PREFIX)
    ) or (issn is not None and issn in AHA_ISSNS)

    # Hard block check first
    if url:
        for blocked in BLOCKED_DOMAIN_PATTERNS:
            if blocked.search(url):
                return ValidationResult(
                    status=ValidationStatus.REJECTED,
                    reason=f"URL matches blocked domain pattern: {url}",
                    trust_tier=0,
                    is_aha=False,
                )

    # ISSN check
    if issn and issn in TRUSTED_ISSNS:
        return ValidationResult(
            status=ValidationStatus.TRUSTED,
            reason=f"ISSN {issn} is in trusted journal registry",
            trust_tier=2,
            is_aha=issn in AHA_ISSNS,
        )

    # PMID check (strongest signal — means it's in MEDLINE)
    result = _check_pmid(pmid)
    if result:
        result.is_aha = aha
        return result

    # DOI prefix check
    result = _check_doi(doi)
    if result:
        result.is_aha = aha
        return result

    # Journal name check
    if journal:
        result = _check_journal(journal)
        if result:
            result.is_aha = aha
            return result

    # Source tag check
    if source:
        result = _check_source_tag(source)
        if result:
            result.is_aha = aha
            return result

    return ValidationResult(
        status=ValidationStatus.UNVERIFIABLE,
        reason="No trusted signal found (PMID, DOI, ISSN, or journal name)",
        trust_tier=0,
        is_aha=False,
    )


def validate_retrieval_doc(doc: dict) -> ValidationResult:
    """Convenience wrapper for the unified retrieval doc format."""
    meta = doc.get("metadata", {})
    return validate_document(
        source=meta.get("source", ""),
        journal=meta.get("journal", ""),
        doi=meta.get("doi"),
        pmid=meta.get("pmid"),
        url=meta.get("url"),
    )


def filter_trusted_docs(docs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Split documents into trusted and rejected lists.
    Returns (trusted_docs, rejected_docs).
    Stamps is_aha into doc metadata so downstream scorers and UI can use it.
    """
    trusted, rejected = [], []
    for doc in docs:
        result = validate_retrieval_doc(doc)
        doc["validation"] = {
            "status": result.status,
            "reason": result.reason,
            "trust_tier": result.trust_tier,
            "is_aha": result.is_aha,
        }
        # Stamp is_aha into metadata so MEDEVA and citation anchor can read it
        doc.setdefault("metadata", {})["is_aha"] = result.is_aha
        if result.status == ValidationStatus.TRUSTED:
            trusted.append(doc)
        else:
            rejected.append(doc)
    return trusted, rejected
