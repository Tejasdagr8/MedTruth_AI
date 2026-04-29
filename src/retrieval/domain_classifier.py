"""
Lightweight query domain classifier for retrieval routing.
"""


def detect_domain(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ["depression", "cbt", "therapy", "mental", "anxiety", "psychotherapy"]):
        return "mental_health"
    if any(k in q for k in ["myocardial", "heart", "cardio", "aspirin", "stroke", "cardiac"]):
        return "cardiology"
    return "general"
