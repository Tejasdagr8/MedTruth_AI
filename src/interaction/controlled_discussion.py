"""
AI-moderated discussion layer for MedTruth AI.

Comments must be anchored to a specific sentence OR a citation.
Every comment is classified by the LLM before it can surface.

Classification outcomes:
  VALID          — factually consistent; safe to display
  QUESTION       — user is asking; convert to a new query suggestion
  MISINFORMATION — contradicts evidence or is medically unsafe; blocked

Design principles:
  - No unstructured threads; every comment has an evidence anchor
  - Low temperature for deterministic, reproducible moderation
  - Safe fallback: if the LLM is unavailable, hold the comment for review
    rather than auto-approving or auto-blocking
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal

from src.llm.fallback_client import generate_text_with_fallback

logger = logging.getLogger(__name__)

CommentType = Literal["VALID", "QUESTION", "MISINFORMATION"]

_MODERATION_PROMPT = (
    "You are a medical evidence fact-checker and content moderator.\n"
    "You will be given:\n"
    "  1. An excerpt from an evidence-based medical answer\n"
    "  2. The titles of key supporting studies\n"
    "  3. Optionally, the specific sentence or citation the comment is tied to\n"
    "  4. A user comment\n\n"
    "Classify the comment into exactly one of:\n"
    "  VALID          — adds value, is consistent with the evidence, no misinformation\n"
    "  QUESTION       — is actually a question or request for clarification\n"
    "  MISINFORMATION — contradicts the evidence, contains false claims, or is medically unsafe\n\n"
    "Return ONLY valid JSON — no markdown, no explanation outside the JSON:\n"
    "{\n"
    '  "type": "VALID|QUESTION|MISINFORMATION",\n'
    '  "confidence": <float 0.0-1.0>,\n'
    '  "reason": "<one sentence explaining the classification>",\n'
    '  "suggested_action": "<one sentence — what to do with this comment>",\n'
    '  "query_suggestion": "<if type=QUESTION: rephrase the question as a database search query; otherwise null>"\n'
    "}"
)


@dataclass(frozen=True)
class CommentValidation:
    type: CommentType
    confidence: float
    reason: str
    suggested_action: str
    query_suggestion: str | None  # set only when type == "QUESTION"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "suggested_action": self.suggested_action,
            "query_suggestion": self.query_suggestion,
            "action": _action_for_type(self.type, self.confidence),
        }


def _action_for_type(comment_type: CommentType, confidence: float) -> str:
    if comment_type == "MISINFORMATION":
        return "blocked"
    if comment_type == "QUESTION":
        return "converted_to_query"
    # VALID: show if confidence is reasonable, hold if moderation is uncertain
    return "approved" if confidence >= 0.6 else "held_for_review"


def validate_comment(
    comment: str,
    answer: str,
    evidence_titles: list[str],
    *,
    anchor_sentence: str | None = None,
    anchor_citation_title: str | None = None,
) -> CommentValidation:
    """
    Validate and classify a user comment against the evidence context.

    Args:
        comment: The user's comment text (5–1000 chars).
        answer: The MedTruth answer the comment is attached to.
        evidence_titles: Top citation titles for evidence context.
        anchor_sentence: The specific answer sentence this comment targets.
        anchor_citation_title: The specific citation this comment targets.

    Returns:
        CommentValidation with type, confidence, reason, and suggested action.
        Falls back to a HELD state (not auto-approved) if the LLM is unavailable.
    """
    # Safe fallback: hold for manual review rather than auto-approve/block
    moderation_unavailable = CommentValidation(
        type="VALID",
        confidence=0.0,
        reason="Moderation service temporarily unavailable — comment held for review.",
        suggested_action="Hold for manual review before displaying.",
        query_suggestion=None,
    )

    try:
        anchor_ctx = ""
        if anchor_sentence:
            anchor_ctx = f'\nAnchor sentence: "{anchor_sentence[:200]}"'
        elif anchor_citation_title:
            anchor_ctx = f'\nAnchor citation: "{anchor_citation_title[:120]}"'

        titles_block = "\n".join(f"- {t}" for t in evidence_titles[:5])
        user_prompt = (
            f"Answer excerpt:\n{answer[:600]}\n\n"
            f"Supporting evidence titles:\n{titles_block or '(none)'}"
            f"{anchor_ctx}\n\n"
            f'User comment: "{comment[:800]}"'
        )

        text, _, _ = generate_text_with_fallback(
            system_prompt=_MODERATION_PROMPT,
            user_prompt=user_prompt,
            max_tokens=220,
        )

        json_match = re.search(r"\{.*?\}", text, re.DOTALL)
        if not json_match:
            return moderation_unavailable

        data = json.loads(json_match.group(0))

        raw_type = str(data.get("type", "VALID")).upper().strip()
        comment_type: CommentType = (
            raw_type if raw_type in ("VALID", "QUESTION", "MISINFORMATION") else "VALID"
        )
        confidence = float(data.get("confidence", 0.5))
        confidence = round(max(0.0, min(1.0, confidence)), 3)

        return CommentValidation(
            type=comment_type,
            confidence=confidence,
            reason=str(data.get("reason", ""))[:300],
            suggested_action=str(data.get("suggested_action", ""))[:300],
            query_suggestion=data.get("query_suggestion") or None,
        )

    except Exception:
        logger.warning("Comment moderation failed", exc_info=True)
        return moderation_unavailable
