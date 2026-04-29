"""
LLM-powered related question generator.

Single call, low token budget, never blocks the pipeline on failure.
Questions are grounded in the query + answer context — no hallucination.
"""

import json
import logging
import re

from src.llm.fallback_client import generate_text_with_fallback

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a medical research assistant helping users explore medical topics in depth.\n"
    "Given a question, an answer, and the evidence titles used, generate follow-up questions.\n\n"
    "RULES:\n"
    "- Each question must be directly motivated by the answer or evidence\n"
    "- Do NOT introduce medical claims not present in the answer\n"
    "- Questions should expand understanding, not repeat the original\n"
    "- Keep each question under 100 characters\n"
    "- Return ONLY a valid JSON array of strings — no markdown, no explanation\n\n"
    'Example output: ["What is the mechanism of action?", "Are there contraindications?"]'
)


def generate_related_questions(
    query: str,
    answer: str,
    evidence: list[str],
    n: int = 5,
) -> list[str]:
    """
    Generate follow-up questions grounded in the query + answer.
    Returns an empty list on any failure — never raises.
    """
    try:
        titles_block = "\n".join(f"- {t}" for t in evidence[:4])
        user_prompt = (
            f"Original question: {query}\n\n"
            f"Answer (excerpt): {answer[:700]}\n\n"
            f"Evidence used:\n{titles_block or '(no citations)'}\n\n"
            f"Generate {n} follow-up questions as a JSON array."
        )
        text, _, _ = generate_text_with_fallback(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=280,
        )
        json_match = re.search(r"\[.*?\]", text, re.DOTALL)
        if not json_match:
            return []
        questions = json.loads(json_match.group(0))
        return [str(q).strip().rstrip("?").strip() + "?" for q in questions if q and len(str(q)) > 8][:n]
    except Exception:
        logger.debug("Related questions generation failed for %r", query, exc_info=True)
        return []
