"""
Query-document relevance filtering to reduce retrieval noise.
"""

import re


def query_keywords(query: str) -> set[str]:
    stop_words = {
        "the", "and", "for", "with", "that", "this", "from", "into", "does", "what",
        "when", "where", "which", "about", "acute", "chronic", "effect", "effects",
        "reduce", "reduces", "risk", "outcome", "outcomes", "patients",
    }
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    return {t for t in tokens if len(t) > 2 and t not in stop_words}


def is_relevant(doc: dict, query: str) -> bool:
    """Filter out noisy retrievals that do not overlap with query concepts."""
    text = f"{doc.get('metadata', {}).get('title', '')} {doc.get('text', '')}".lower()
    keywords = query_keywords(query)
    if not keywords:
        return True
    strong_terms = [k for k in keywords if len(k) > 4]
    strong_match = any(k in text for k in strong_terms) if strong_terms else False
    matched = sum(1 for k in keywords if k in text)
    required_overlap = max(2, len(keywords) // 4)
    return strong_match and matched >= required_overlap
