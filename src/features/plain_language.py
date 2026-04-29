"""
Plain language translator — rewrites medical jargon into patient-friendly text
at approximately 8th-grade reading level, preserving all citation markers.
"""

import re

from src.llm.fallback_client import generate_text_with_fallback

PLAIN_LANGUAGE_SYSTEM = """You are a medical communication specialist. Your task is to rewrite a technical medical answer into plain English at approximately an 8th-grade reading level, suitable for patients without medical training.

STRICT RULES:
1. Preserve ALL citation markers exactly as they appear (e.g., [1], [2], [3]).
2. Replace medical jargon with everyday words. Examples:
   - "myocardial infarction" → "heart attack"
   - "hypertension" → "high blood pressure"
   - "analgesic" → "painkiller"
   - "contraindicated" → "not safe to use"
   - "statistically significant" → "shown to make a real difference"
3. Keep the same structure and all the same facts — do NOT add or remove information.
4. Use short sentences (under 20 words when possible).
5. Avoid Latin abbreviations (e.g., "i.e.", "e.g.", "et al.") — spell them out.
6. Keep numbers and statistics, but explain their meaning (e.g., "18% lower risk" → "18% lower chance").
7. Do NOT remove the evidence quality summary at the end.
"""


def _extract_citation_markers(text: str) -> list[str]:
    return re.findall(r"\[\d+\]", text)


def translate_to_plain_language(technical_answer: str) -> str:
    """
    Rewrite a technical medical answer in plain language.
    Citation markers [n] are preserved exactly.
    """
    if not technical_answer.strip():
        return technical_answer

    user_prompt = (
        f"Please rewrite the following medical answer in plain English. "
        f"Remember to keep all citation markers like [1], [2], etc.\n\n"
        f"MEDICAL ANSWER:\n{technical_answer}"
    )
    plain, _provider = generate_text_with_fallback(
        system_prompt=PLAIN_LANGUAGE_SYSTEM,
        user_prompt=user_prompt,
        max_tokens=1024,
    )

    # Verify all original citation markers survived
    original_markers = set(_extract_citation_markers(technical_answer))
    plain_markers = set(_extract_citation_markers(plain))
    missing = original_markers - plain_markers

    if missing:
        # Append any missing markers with a note
        plain += (
            f"\n\n(Sources referenced: "
            + ", ".join(sorted(missing, key=lambda x: int(x[1:-1])))
            + ")"
        )

    return plain
