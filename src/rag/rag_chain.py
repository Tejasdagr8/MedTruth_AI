"""
RAG generation chain using Anthropic Claude.
Enforces strict citation grounding — model is instructed to answer ONLY
from provided context and mark every claim with [n] citation markers.
"""

import os
from dataclasses import dataclass
from typing import Optional

from src.llm.fallback_client import generate_text_with_fallback
from src.rag.citation_anchor import Citation, anchor_citations_in_text, build_citations, format_bibliography
from src.rag.grounding import filter_grounded_sentences
from src.ranking.medeva_scorer import (
    compute_response_confidence,
    get_rejection_threshold,
    should_reject_response,
)

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_CONTEXT_TOKENS = 6000  # conservative limit for context window

SYSTEM_PROMPT = """You are MedTruth AI, a medical evidence assistant. Your ONLY job is to answer questions strictly based on the provided research context.

STRICT RULES:
1. Answer ONLY using information present in the numbered [SOURCE n] blocks below.
2. Every factual claim in your answer MUST be followed by [n] where n is the source number.
3. If the answer cannot be determined from the sources, respond with exactly:
   "INSUFFICIENT_EVIDENCE: The available peer-reviewed sources do not contain enough information to answer this question reliably."
4. NEVER introduce information not present in the sources — not from training data, not from general knowledge.
5. Do NOT speculate, extrapolate, or infer beyond what sources explicitly state.
6. If sources conflict, acknowledge the conflict and cite both: "Study A [n] found X while Study B [m] found Y."
7. Use precise medical terminology from the sources.
8. Do not recommend specific treatments or dosages to individuals — state findings only.

FORMAT:
FORMAT STRICTLY:
1. DIRECT ANSWER:
(Answer the question clearly in 1-2 sentences)
2. SUPPORTING EVIDENCE:
(List key findings from studies with [n])
3. LIMITATIONS / CONTEXT:
(Explain uncertainty, indirect evidence, or conflicts)
4. EVIDENCE QUALITY:
(Summarize study types: RCTs, meta-analysis, etc.)
"""

INSUFFICIENT_EVIDENCE_MARKER = "INSUFFICIENT_EVIDENCE:"


def _build_context_block(docs: list[dict]) -> str:
    """Format top-k docs into numbered source blocks for the prompt."""
    blocks = []
    for i, doc in enumerate(docs, start=1):
        meta = doc.get("metadata", {})
        medeva = doc.get("medeva", {})
        study_type = meta.get("study_type", "unknown")
        journal = meta.get("journal", "")
        year = meta.get("pub_year", "")
        band = medeva.get("confidence_band", "")
        text = doc.get("text", "")[:1200]  # truncate long abstracts

        header = (
            f"[SOURCE {i}] {journal} ({year}) | "
            f"Study type: {study_type} | Evidence quality: {band}"
        )
        blocks.append(f"{header}\n{text}")

    return "\n\n---\n\n".join(blocks)


def _truncate_context(context: str, max_chars: int = MAX_CONTEXT_TOKENS * 4) -> str:
    return context[:max_chars]


def _apply_confidence_tone(answer: str, confidence: float) -> str:
    if not answer.strip():
        return answer
    if confidence < 0.60:
        prefix = (
            "Evidence is suggestive but not definitive, and findings should be interpreted "
            "with caution. "
        )
    elif confidence < 0.75:
        prefix = "Evidence is moderately strong but includes some uncertainty. "
    else:
        prefix = "Evidence is strong and consistent across retrieved sources. "
    return prefix + answer


@dataclass
class RAGResponse:
    answer: str
    citations: list[Citation]
    confidence: float
    confidence_band: str
    rejected: bool
    rejection_reason: Optional[str]
    bibliography: str
    evidence_summary: str
    fallback_mode: bool = False
    provider_used: str = "none"
    mode: str = "evidence_based"
    fallback_reason: Optional[str] = None
    provider_attempts: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "confidence": self.confidence,
            "confidence_band": self.confidence_band,
            "rejected": self.rejected,
            "rejection_reason": self.rejection_reason,
            "bibliography": self.bibliography,
            "evidence_summary": self.evidence_summary,
            "fallback_mode": self.fallback_mode,
            "provider_used": self.provider_used,
            "mode": self.mode,
            "fallback_reason": self.fallback_reason,
            "provider_attempts": self.provider_attempts or [],
        }


class MedTruthRAGChain:
    def __init__(self, model: str = CLAUDE_MODEL):
        self.model = model

    def _build_evidence_summary(self, docs: list[dict]) -> str:
        from collections import Counter
        types = [d.get("metadata", {}).get("study_type", "unknown") for d in docs]
        counts = Counter(types)
        type_labels = {
            "systematic_review_meta_analysis": "systematic review/meta-analysis",
            "rct_double_blind": "double-blind RCT",
            "rct_single_blind": "RCT",
            "cohort_study_prospective": "prospective cohort study",
            "cohort_study_retrospective": "retrospective cohort study",
            "case_control": "case-control study",
            "cross_sectional": "cross-sectional study",
            "case_report_series": "case report/series",
            "expert_opinion": "expert opinion/review",
        }
        lines = ["Evidence includes:"]
        high_quality = 0
        priority = [
            "systematic_review_meta_analysis",
            "rct_double_blind",
            "rct_single_blind",
            "cohort_study_prospective",
            "cohort_study_retrospective",
            "case_control",
            "cross_sectional",
            "case_report_series",
            "expert_opinion",
        ]

        def _pluralize(label: str, count: int) -> str:
            if count == 1:
                return label
            if label.endswith("analysis"):
                return label[:-2] + "es"  # analysis -> analyses
            if label.endswith("s"):
                return label
            return label + "s"

        for t in priority:
            count = counts.get(t, 0)
            if count == 0:
                continue
            label = type_labels.get(t, t)
            lines.append(f"- {count} {_pluralize(label, count)}")
            if t in {"systematic_review_meta_analysis", "rct_double_blind", "rct_single_blind"}:
                high_quality += count

        if high_quality >= 3:
            overall = "HIGH"
        elif high_quality >= 1:
            overall = "MODERATE-HIGH"
        else:
            overall = "MODERATE"
        lines.append(f"Overall evidence strength: {overall}")
        return "\n".join(lines)

    def _build_extractive_summary(self, docs: list[dict], max_items: int = 3) -> str:
        key_findings: list[str] = []
        for doc in docs[:max_items]:
            text = str(doc.get("text", ""))
            sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 80]
            for sentence in sentences:
                if any(k in sentence.lower() for k in ["reduce", "improve", "effective", "risk"]):
                    key_findings.append(sentence + ".")
                    break

        if not key_findings:
            key_findings.append(
                "Available studies suggest potential clinical benefit, but the retrieved evidence is limited and should be interpreted cautiously."
            )

        summary_points = [f"- {line}" for line in key_findings[:max_items]]
        return (
            "Evidence-Based Summary\n\n"
            "Summary of findings:\n"
            + "\n".join(summary_points)
            + "\n\nEvidence quality:\n"
            + "- Based on systematic reviews and clinical studies from retrieved sources."
        )

    def generate(
        self,
        query: str,
        docs: list[dict],
        semantic_similarities: Optional[list[float]] = None,
        has_conflict: bool = False,
    ) -> RAGResponse:
        if not docs:
            return RAGResponse(
                answer="",
                citations=[],
                confidence=0.0,
                confidence_band="LOW",
                rejected=True,
                rejection_reason="No relevant peer-reviewed sources found for this query.",
                bibliography="",
                evidence_summary="",
                provider_used="none",
                mode="fallback",
                fallback_reason="retrieval_empty",
                provider_attempts=[],
            )

        confidence, band = compute_response_confidence(docs, semantic_similarities)

        threshold = get_rejection_threshold(docs)
        if should_reject_response(confidence, docs):
            return RAGResponse(
                answer="",
                citations=[],
                confidence=confidence,
                confidence_band=band,
                rejected=True,
                rejection_reason=(
                    f"Evidence quality insufficient to answer reliably "
                    f"(MEDEVA confidence: {confidence:.2f}, threshold: {threshold:.2f}). "
                    f"The available sources do not provide strong enough evidence."
                ),
                bibliography="",
                evidence_summary=self._build_evidence_summary(docs),
                provider_used="none",
                mode="fallback",
                fallback_reason="low_confidence_evidence",
                provider_attempts=[],
            )

        context = _truncate_context(_build_context_block(docs))
        user_message = f"RESEARCH CONTEXT:\n\n{context}\n\n---\n\nQUESTION: {query}"

        try:
            raw_answer, provider, provider_attempts = generate_text_with_fallback(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_message,
                max_tokens=1024,
            )
            provider = provider or "unknown"
        except Exception as exc:
            citations = build_citations(docs)
            fallback_answer = self._build_extractive_summary(docs)
            attempts = getattr(exc, "attempts", [])
            return RAGResponse(
                answer=fallback_answer,
                citations=citations,
                confidence=confidence,
                confidence_band=band,
                rejected=False,
                rejection_reason=None,
                bibliography=format_bibliography(citations),
                evidence_summary=self._build_evidence_summary(docs),
                fallback_mode=True,
                provider_used="none",
                mode="evidence_only",
                fallback_reason="provider_error_after_evidence",
                provider_attempts=attempts,
            )

        # Check if model itself flagged insufficient evidence
        if raw_answer.startswith(INSUFFICIENT_EVIDENCE_MARKER):
            return RAGResponse(
                answer="",
                citations=[],
                confidence=confidence,
                confidence_band=band,
                rejected=True,
                rejection_reason=raw_answer[len(INSUFFICIENT_EVIDENCE_MARKER):].strip(),
                bibliography="",
                evidence_summary=self._build_evidence_summary(docs),
                provider_used=provider,
                mode="fallback",
                fallback_reason="insufficient_evidence_marker",
                provider_attempts=provider_attempts,
            )

        citations = build_citations(docs)
        grounded_answer = filter_grounded_sentences(raw_answer, docs)
        toned_answer = _apply_confidence_tone(grounded_answer, confidence)
        if has_conflict:
            toned_answer = (
                "Some retrieved studies show conflicting or heterogeneous findings. "
                + toned_answer
            )
        anchored_answer = anchor_citations_in_text(toned_answer, citations)
        bibliography = format_bibliography(citations)
        evidence_summary = self._build_evidence_summary(docs)

        return RAGResponse(
            answer=anchored_answer,
            citations=citations,
            confidence=confidence,
            confidence_band=band,
            rejected=False,
            rejection_reason=None,
            bibliography=bibliography,
            evidence_summary=evidence_summary,
            provider_used=provider,
            mode="evidence_based",
            fallback_reason=None,
            provider_attempts=provider_attempts,
        )
