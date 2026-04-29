"""
LLM Lab tool implementations.

Lightweight wrappers — no MEDEVA scoring, no trust filtering.
Output is normalized into a structured format that is easier for the LLM to reason over.
"""

import re
import xml.etree.ElementTree as ET

import httpx

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Per-article limits
_ABSTRACT_MAX_CHARS = 800
_MAX_RESULTS_DEFAULT = 5


def _infer_study_type(text: str) -> str:
    """Basic keyword inference — good enough for context labelling."""
    t = text.lower()
    if any(k in t for k in ["systematic review", "meta-analysis", "meta analysis"]):
        return "Systematic review / Meta-analysis"
    if any(k in t for k in ["randomized controlled trial", "randomised controlled trial", "double-blind", "double blind", "rct"]):
        return "Randomized controlled trial"
    if any(k in t for k in ["randomized", "randomised", "placebo-controlled"]):
        return "Randomized study"
    if any(k in t for k in ["cohort study", "prospective cohort", "prospective study"]):
        return "Prospective cohort study"
    if any(k in t for k in ["retrospective", "medical records"]):
        return "Retrospective study"
    if any(k in t for k in ["case-control", "case control"]):
        return "Case-control study"
    if any(k in t for k in ["cross-sectional", "survey"]):
        return "Cross-sectional study"
    return "Observational / review"


def _extract_key_finding(abstract: str) -> str:
    """
    Pull the last sentence that contains an outcome-related keyword.
    Falls back to the last sentence.
    """
    sentences = re.split(r"(?<=[.!?])\s+", abstract.strip())
    outcome_kw = {"significant", "effective", "result", "found", "conclude",
                  "showed", "demonstrated", "reduced", "improved", "associated"}
    # Search from end
    for sent in reversed(sentences):
        if any(k in sent.lower() for k in outcome_kw):
            return sent.strip()
    return sentences[-1].strip() if sentences else ""


def _format_article(idx: int, title: str, journal: str, year: str, abstract: str) -> str:
    """
    Convert raw fields into a structured, LLM-friendly block.
    Keeps token cost predictable and synthesis quality high.
    """
    # Trim abstract and extract summary (first 2 sentences) + key finding
    abstract_clean = abstract.strip()
    sentences = re.split(r"(?<=[.!?])\s+", abstract_clean)
    summary = " ".join(sentences[:3]).strip()
    if len(summary) > _ABSTRACT_MAX_CHARS:
        summary = summary[:_ABSTRACT_MAX_CHARS] + "…"

    key_finding = _extract_key_finding(abstract_clean)
    if key_finding in summary:
        key_finding = ""  # skip duplicate

    study_type = _infer_study_type(f"{title} {abstract_clean}")

    lines = [
        f"[Study {idx}]",
        f"  Title:      {title}",
        f"  Journal:    {journal} ({year})",
        f"  Study type: {study_type}",
        f"  Summary:    {summary}",
    ]
    if key_finding:
        lines.append(f"  Finding:    {key_finding}")

    return "\n".join(lines)


async def pubmed_search(query: str, max_results: int = _MAX_RESULTS_DEFAULT) -> str:
    """
    Search PubMed and return normalized, structured article summaries.
    Each result is formatted as a labelled block — no raw XML passed to the LLM.
    """
    async with httpx.AsyncClient(timeout=9.0) as client:
        resp = await client.get(ESEARCH_URL, params={
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance",
        })
        resp.raise_for_status()
        pmids: list[str] = resp.json().get("esearchresult", {}).get("idlist", [])
        if not pmids:
            return "No PubMed results found for this query."

        resp = await client.get(EFETCH_URL, params={
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "xml",
            "retmode": "xml",
        })
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    results: list[str] = []

    for i, article in enumerate(root.findall(".//PubmedArticle"), start=1):
        title_el = article.find(".//ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else ""

        abstract_parts = article.findall(".//AbstractText")
        abstract = " ".join("".join(p.itertext()) for p in abstract_parts).strip()

        journal_el = article.find(".//Journal/Title")
        journal = journal_el.text.strip() if journal_el is not None else "Unknown"

        year_el = article.find(".//PubDate/Year")
        year = year_el.text if year_el is not None else "n.d."

        if title and abstract:
            results.append(_format_article(i, title, journal, year, abstract))

    if not results:
        return "PubMed returned no abstracts for this query."

    header = f"Found {len(results)} result(s) for: {query!r}\n"
    return header + "\n\n".join(results)
