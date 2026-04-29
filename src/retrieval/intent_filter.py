"""
Clinical intent filter to keep evidence aligned to query components.
"""


def matches_intent(doc: dict, query: str) -> bool:
    text = f"{doc.get('metadata', {}).get('title', '')} {doc.get('text', '')}".lower()
    q = query.lower()

    aspirin = "aspirin" in q
    mortality = "mortality" in q or "death" in q
    condition = "myocardial infarction" in q or " mi " in f" {q} " or "heart attack" in q

    score = 0
    if aspirin and "aspirin" in text:
        score += 1
    if mortality and any(k in text for k in ["mortality", "death", "survival"]):
        score += 1
    if condition and any(k in text for k in ["myocardial infarction", " mi ", "heart attack"]):
        score += 1

    # Apply strong gating only when at least two clinical components are present in query.
    active_components = int(aspirin) + int(mortality) + int(condition)
    if active_components >= 2:
        return score >= 2
    return True
