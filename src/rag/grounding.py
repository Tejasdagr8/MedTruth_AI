"""
Answer grounding helpers to keep generated text evidence-linked.
"""

import re


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _similarity(sentence: str, source: str) -> float:
    sent_tokens = _tokenize(sentence)
    src_tokens = _tokenize(source)
    if not sent_tokens or not src_tokens:
        return 0.0
    return len(sent_tokens & src_tokens) / len(sent_tokens | src_tokens)


def filter_grounded_sentences(answer: str, docs: list[dict], min_similarity: float = 0.70) -> str:
    """
    Keep only answer sentences that are supported by retrieved evidence text.
    Support is satisfied by either:
      - direct substring match in any source text, or
      - token similarity with any source text >= min_similarity.
    """
    if not answer.strip() or not docs:
        return answer

    source_texts = [d.get("text", "").lower() for d in docs if d.get("text")]
    if not source_texts:
        return answer

    kept: list[str] = []
    sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
    for sentence in sentences:
        s = sentence.strip()
        if len(s) < 20:
            continue
        s_lower = s.lower()
        if any(s_lower in src for src in source_texts):
            kept.append(s)
            continue

        best_similarity = 0.0
        for src in source_texts:
            sim = _similarity(s_lower, src)
            if sim > best_similarity:
                best_similarity = sim
        if best_similarity >= min_similarity:
            kept.append(s)

    if not kept:
        return answer
    return " ".join(kept)
