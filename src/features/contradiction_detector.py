"""
Contradiction detector — finds pairs of retrieved studies with conflicting conclusions.
Uses sentence embeddings to cluster documents by topic, then checks conclusion polarity
within each cluster. High topic similarity + low conclusion similarity = contradiction.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ContradictionPair:
    doc_a_index: int
    doc_b_index: int
    doc_a_title: str
    doc_b_title: str
    doc_a_conclusion: str
    doc_b_conclusion: str
    doc_a_medeva: float
    doc_b_medeva: float
    topic_similarity: float
    conclusion_similarity: float
    contradiction_score: float   # higher = more likely a contradiction
    higher_evidence_index: int   # which doc has higher MEDEVA score
    summary: str

    def to_dict(self) -> dict:
        return {
            "doc_a": {
                "index": self.doc_a_index,
                "title": self.doc_a_title,
                "conclusion": self.doc_a_conclusion,
                "medeva_score": self.doc_a_medeva,
            },
            "doc_b": {
                "index": self.doc_b_index,
                "title": self.doc_b_title,
                "conclusion": self.doc_b_conclusion,
                "medeva_score": self.doc_b_medeva,
            },
            "topic_similarity": round(self.topic_similarity, 3),
            "conclusion_similarity": round(self.conclusion_similarity, 3),
            "contradiction_score": round(self.contradiction_score, 3),
            "higher_evidence_index": self.higher_evidence_index,
            "summary": self.summary,
        }


def _extract_conclusion(text: str) -> str:
    """
    Heuristically extract the conclusion sentence(s) from an abstract.
    Looks for conclusion section headers or the final 1-2 sentences.
    """
    conclusion_patterns = [
        r"(?:conclusion[s]?|interpretation[s]?|findings?|summary)[:\s]+(.+?)(?:\n|$)",
        r"(?:in conclusion[,\s]|we conclude[d\s]|these results? suggest[s\s])(.+?)(?:\.|$)",
    ]
    text_lower = text.lower()
    for pat in conclusion_patterns:
        m = re.search(pat, text_lower, re.IGNORECASE | re.DOTALL)
        if m:
            result = m.group(1).strip()
            if len(result) > 30:
                return result[:400]

    # Fall back: last 2 sentences
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(sentences[-2:]) if len(sentences) >= 2 else text[-300:]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _get_embedder():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(
            "pritamdeka/BioBERT-mnli-snli-scinli-scitail-mednli-stsb"
        )
    except Exception:
        return None


_embedder = None


def detect_contradictions(
    docs: list[dict],
    topic_threshold: float = 0.75,
    conclusion_threshold: float = 0.45,
    min_contradiction_score: float = 0.30,
) -> list[ContradictionPair]:
    """
    Find contradictory pairs among retrieved documents.

    A pair is a contradiction when:
    - topic_similarity >= topic_threshold  (they're about the same thing)
    - conclusion_similarity < conclusion_threshold (conclusions diverge)

    contradiction_score = topic_similarity * (1 - conclusion_similarity)
    """
    global _embedder

    if len(docs) < 2:
        return []

    if _embedder is None:
        _embedder = _get_embedder()

    conclusions = [_extract_conclusion(doc.get("text", "")) for doc in docs]
    full_texts = [doc.get("text", "")[:512] for doc in docs]

    if _embedder:
        topic_embs = _embedder.encode(full_texts, normalize_embeddings=True).tolist()
        conc_embs = _embedder.encode(conclusions, normalize_embeddings=True).tolist()
    else:
        # No embedder: use simple word-overlap as proxy
        def word_overlap(a: str, b: str) -> float:
            wa, wb = set(a.lower().split()), set(b.lower().split())
            if not wa or not wb:
                return 0.0
            return len(wa & wb) / max(len(wa | wb), 1)

        n = len(docs)
        pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                ts = word_overlap(full_texts[i], full_texts[j])
                cs = word_overlap(conclusions[i], conclusions[j])
                score = ts * (1 - cs)
                if ts >= topic_threshold and cs < conclusion_threshold and score >= min_contradiction_score:
                    _append_pair(pairs, docs, conclusions, i, j, ts, cs, score)
        return pairs

    n = len(docs)
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            ts = _cosine_similarity(topic_embs[i], topic_embs[j])
            cs = _cosine_similarity(conc_embs[i], conc_embs[j])
            score = ts * (1 - cs)
            if ts >= topic_threshold and cs < conclusion_threshold and score >= min_contradiction_score:
                _append_pair(pairs, docs, conclusions, i, j, ts, cs, score)

    return sorted(pairs, key=lambda p: p.contradiction_score, reverse=True)


def _append_pair(
    pairs: list,
    docs: list[dict],
    conclusions: list[str],
    i: int,
    j: int,
    ts: float,
    cs: float,
    score: float,
) -> None:
    meta_a = docs[i].get("metadata", {})
    meta_b = docs[j].get("metadata", {})
    medeva_a = docs[i].get("medeva", {}).get("total", 0.0)
    medeva_b = docs[j].get("medeva", {}).get("total", 0.0)
    higher = i + 1 if medeva_a >= medeva_b else j + 1

    title_a = meta_a.get("title", f"Study {i+1}")
    title_b = meta_b.get("title", f"Study {j+1}")
    year_a = meta_a.get("pub_year", "")
    year_b = meta_b.get("pub_year", "")
    type_a = meta_a.get("study_type", "study")
    type_b = meta_b.get("study_type", "study")

    higher_label = "A" if higher == i + 1 else "B"
    summary = (
        f"Study A ({type_a}, {year_a}, MEDEVA={medeva_a:.2f}) and "
        f"Study B ({type_b}, {year_b}, MEDEVA={medeva_b:.2f}) address the same topic "
        f"but reach conflicting conclusions. "
        f"Higher-evidence Study {higher_label} should be given precedence."
    )

    pairs.append(ContradictionPair(
        doc_a_index=i + 1,
        doc_b_index=j + 1,
        doc_a_title=title_a,
        doc_b_title=title_b,
        doc_a_conclusion=conclusions[i][:300],
        doc_b_conclusion=conclusions[j][:300],
        doc_a_medeva=round(medeva_a, 3),
        doc_b_medeva=round(medeva_b, 3),
        topic_similarity=ts,
        conclusion_similarity=cs,
        contradiction_score=score,
        higher_evidence_index=higher,
        summary=summary,
    ))
