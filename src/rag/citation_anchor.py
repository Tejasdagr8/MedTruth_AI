"""
Citation post-processor.
Maps [1], [2], ... inline markers in LLM output to full bibliographic references.
Builds the citation panel metadata for the frontend.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Citation:
    index: int
    pmid: Optional[str]
    doi: Optional[str]
    title: str
    authors: list[str]
    journal: str
    pub_year: int
    source: str
    medeva_total: Optional[float]
    confidence_band: Optional[str]
    url: str
    is_aha: bool = False

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "pmid": self.pmid,
            "doi": self.doi,
            "title": self.title,
            "authors": self.authors[:3],  # first 3 authors for display
            "journal": self.journal,
            "pub_year": self.pub_year,
            "source": self.source,
            "medeva_total": self.medeva_total,
            "confidence_band": self.confidence_band,
            "url": self.url,
            "is_aha": self.is_aha,
        }


def _build_url(meta: dict) -> str:
    pmid = meta.get("pmid")
    doi = meta.get("doi")
    if pmid:
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    if doi:
        return f"https://doi.org/{doi}"
    handle = meta.get("handle")
    if handle:
        return f"https://iris.who.int/handle/{handle}"
    return ""


def build_citations(docs: list[dict]) -> list[Citation]:
    """Build Citation objects from top-k retrieved docs (1-indexed)."""
    citations = []
    for i, doc in enumerate(docs, start=1):
        meta = doc.get("metadata", {})
        medeva = doc.get("medeva", {})
        authors = meta.get("authors", [])
        if isinstance(authors, str):
            import json
            try:
                authors = json.loads(authors)
            except Exception:
                authors = [authors]

        citations.append(Citation(
            index=i,
            pmid=meta.get("pmid"),
            doi=meta.get("doi"),
            title=meta.get("title", "Unknown Title"),
            authors=authors,
            journal=meta.get("journal", ""),
            pub_year=meta.get("pub_year", 0),
            source=meta.get("source", "unknown"),
            medeva_total=medeva.get("total"),
            confidence_band=medeva.get("confidence_band"),
            url=_build_url(meta),
            is_aha=bool(meta.get("is_aha", False) or medeva.get("is_aha", False)),
        ))
    return citations


def anchor_citations_in_text(text: str, citations: list[Citation]) -> str:
    """
    Replace bare [n] markers with enriched [n] that the frontend can hyperlink.
    Also ensures every citation referenced in text is present in the list.
    """
    # Validate all referenced indices exist
    referenced = set(int(m) for m in re.findall(r"\[(\d+)\]", text))
    available = {c.index for c in citations}
    orphans = referenced - available
    if orphans:
        # Remove orphaned citation markers from text
        for idx in orphans:
            text = text.replace(f"[{idx}]", "")
    return text.strip()


def format_bibliography(citations: list[Citation]) -> str:
    """Plain-text bibliography for the response footer."""
    lines = []
    for c in citations:
        authors_str = (
            ", ".join(c.authors[:3]) + (" et al." if len(c.authors) > 3 else "")
        )
        lines.append(
            f"[{c.index}] {authors_str}. \"{c.title}\". "
            f"{c.journal} ({c.pub_year}). {c.url}"
        )
    return "\n".join(lines)
