"""
Lightweight heuristic contradiction detector for evidence sets.

Uses outcome-polarity keyword matching on conclusion sentences.
No embeddings, no model calls — fast path for enriching confidence metadata.

For the full embedding-based detector (with paired study analysis), see
src/features/contradiction_detector.py.
"""

import re
from dataclasses import dataclass

from src.features.contradiction_detector import detect_contradictions

# Phrases that signal negative / null outcomes
_NEGATIVE = frozenset([
    "no significant", "not effective", "no benefit", "no improvement",
    "no difference", "no effect", "did not reduce", "did not improve",
    "did not show", "failed to", "ineffective", "no significant difference",
    "null result", "negative result", "no statistically significant",
    "not associated", "no association",
])

# Phrases that signal positive outcomes
_POSITIVE = frozenset([
    "significant improvement", "significantly improved", "significantly reduced",
    "significantly lower", "significantly higher", "effective treatment",
    "beneficial", "reduced risk", "decreased risk", "protective effect",
    "superior to", "better than", "positive effect", "positive association",
    "statistically significant", "clinically significant",
])


@dataclass(frozen=True)
class ContradictionSignal:
    contradiction_flag: bool
    summary: str
    positive_count: int
    negative_count: int
    confidence_score: float


def _polarity(text: str) -> int:
    """Return +1 (positive outcome), -1 (negative/null), or 0 (neutral)."""
    t = text.lower()
    neg = sum(1 for phrase in _NEGATIVE if phrase in t)
    pos = sum(1 for phrase in _POSITIVE if phrase in t)
    if neg > pos:
        return -1
    if pos > neg:
        return 1
    return 0


def _conclusion_tail(text: str, n_sentences: int = 3) -> str:
    """Extract the last n sentences, where conclusions typically live."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[-n_sentences:]) if len(parts) >= n_sentences else text


def detect_contradiction_signal(docs: list[dict]) -> ContradictionSignal:
    """
    Heuristic contradiction flag across top-ranked docs.

    Checks whether the document set contains both clearly positive and clearly
    negative outcome signals, suggesting mixed evidence.
    """
    if len(docs) < 2:
        return ContradictionSignal(
            contradiction_flag=False,
            summary="Insufficient studies for conflict assessment.",
            positive_count=0,
            negative_count=0,
            confidence_score=0.0,
        )

    polarities = [_polarity(_conclusion_tail(doc.get("text", ""))) for doc in docs[:8]]
    pos = sum(1 for p in polarities if p > 0)
    neg = sum(1 for p in polarities if p < 0)
    neutrals = sum(1 for p in polarities if p == 0)
    total_scored = max(pos + neg + neutrals, 1)

    # Fast heuristic confidence is weaker when most docs are neutral/unclear.
    heuristic_confidence = min(1.0, (pos + neg) / total_scored)
    weak_signal = (pos == 0 and neg == 0) or heuristic_confidence < 0.45

    if pos >= 1 and neg >= 1:
        return ContradictionSignal(
            contradiction_flag=True,
            summary=(
                f"Studies show mixed results: "
                f"{pos} {'study' if pos == 1 else 'studies'} report positive outcomes "
                f"while {neg} {'report' if neg == 1 else 'reports'} negative or null findings."
            ),
            positive_count=pos,
            negative_count=neg,
            confidence_score=max(0.55, heuristic_confidence),
        )

    # Hybrid fallback: if heuristic signal is weak/uncertain, run embedding detector.
    if weak_signal:
        pairs = detect_contradictions(docs[:8])
        if pairs:
            top = pairs[0]
            return ContradictionSignal(
                contradiction_flag=True,
                summary=top.summary,
                positive_count=pos,
                negative_count=neg,
                confidence_score=min(1.0, max(0.5, top.contradiction_score)),
            )

    return ContradictionSignal(
        contradiction_flag=False,
        summary="Retrieved studies are broadly consistent in their conclusions.",
        positive_count=pos,
        negative_count=neg,
        confidence_score=max(0.35, heuristic_confidence),
    )
