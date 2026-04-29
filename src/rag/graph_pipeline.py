"""
LangGraph-based control-flow pipeline for MedTruth AI.

Replaces the branching if/else ladder in api/routes/query.py with a
structured state graph. All post-retrieval logic lives here:

  filter_rank
      ↓
  [no top_docs] → general_explanation ──┐
      ↓                                 │
    generate                            │
      ↓                                 │
  [LLM failed]   → evidence_only ──────┤
  [RAG rejected] → limited_evidence ───┤
  [success]      → verify              │
                      ↓                │
                   finalize ←──────────┘
                      ↓
                     END

Dependencies (vector_store, rag_chain) are injected at construction time.
Call pipeline.run(initial_state) from the async endpoint after retrieval.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from src.features.contradiction_detector import detect_contradictions
from src.features.risk_flagging import flag_query, get_overall_risk_level
from src.hallucination.entailment_checker import to_api_dict, verify_claims
from src.interaction.related_questions import generate_related_questions
from src.llm.fallback_client import generate_text_with_fallback
from src.rag.contradiction_detector import detect_contradiction_signal
from src.ranking.medeva_scorer import rank_documents
from src.retrieval.intent_filter import matches_intent
from src.retrieval.relevance_filter import is_relevant
from src.validation.source_validator import filter_trusted_docs

logger = logging.getLogger(__name__)

_MEDEVA_FLOOR = 0.30


# ── State ─────────────────────────────────────────────────────────────────────

class PipelineState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────────
    original_query: str
    effective_query: str        # refined or expanded query used for retrieval
    domain: str
    top_k: int
    enable_entailment_check: bool
    enable_contradiction_check: bool
    was_expanded: bool          # True if broad-query expansion was applied

    # ── Raw retrieval input ───────────────────────────────────────────────────
    raw_docs: list[dict]

    # ── Intermediate ──────────────────────────────────────────────────────────
    trusted_docs: list[dict]
    rejected_docs: list[dict]
    top_docs: list[dict]
    semantic_similarities: Optional[list[float]]
    no_docs_reason: str         # reason code when top_docs is empty

    # ── Generation ────────────────────────────────────────────────────────────
    rag_response: Any           # RAGResponse dataclass; None until generate node
    final_answer: str
    provider_used: str
    provider_attempts: list[str]
    mode: str                   # evidence_based | evidence_only | general_explanation | fallback
    fallback_reason: Optional[str]
    citations: list[dict]
    bibliography: str
    evidence_summary: str
    confidence: float
    confidence_band: str
    rejected: bool
    rejection_reason: Optional[str]

    # ── Verification ──────────────────────────────────────────────────────────
    hallucination_dict: Optional[dict]

    # ── Contradiction + safety ────────────────────────────────────────────────
    contradictions: list[dict]
    has_conflict: bool
    contradiction_flag: bool
    contradiction_summary: str
    contradiction_confidence: float
    risk_flags: list[dict]
    overall_risk: str

    # ── Confidence (final) ────────────────────────────────────────────────────
    confidence_details: dict
    confidence_explanation: str

    # ── Selection rationale (Task 3) ──────────────────────────────────────────
    selection_rationale: dict   # why studies were chosen/filtered
    related_questions: list[str]
    trace: list[str]
    transitions: list[str]
    failure_paths: list[str]


# ── Shared helpers ────────────────────────────────────────────────────────────

def _friendly_evidence_type(study_type: str) -> str:
    return {
        "systematic_review_meta_analysis": "Meta-analysis",
        "rct_double_blind": "Double-blind RCT",
        "rct_single_blind": "RCT",
        "cohort_study_prospective": "Prospective cohort",
        "cohort_study_retrospective": "Retrospective cohort",
        "case_control": "Case-control",
        "cross_sectional": "Cross-sectional",
        "case_report_series": "Case report/series",
        "expert_opinion": "Expert opinion/review",
    }.get(study_type, "Other clinical evidence")


def _build_confidence_details(state: PipelineState) -> dict:
    top_docs = state.get("top_docs") or []
    hallucination = state.get("hallucination_dict") or {}

    evidence_types: list[str] = []
    seen: set[str] = set()
    for d in top_docs:
        label = _friendly_evidence_type(d.get("metadata", {}).get("study_type", ""))
        if label not in seen:
            evidence_types.append(label)
            seen.add(label)

    low_support = sum(
        1 for c in hallucination.get("unverified_claims", [])
        if c.get("entailment_score", 1.0) < 0.4
    )

    contradiction_flag = state.get("contradiction_flag", False)
    contradiction_confidence = float(state.get("contradiction_confidence", 0.0) or 0.0)
    agreement_level = "mixed" if contradiction_flag else ("high" if len(top_docs) >= 3 else "moderate")
    diversity_summary = (
        "Broad evidence mix" if len(evidence_types) >= 3 else "Limited evidence diversity"
    )
    return {
        "retrieved": len(state.get("raw_docs") or []),
        "trusted": len(state.get("trusted_docs") or []),
        "excluded": len(state.get("rejected_docs") or []),
        "contradictions": len(state.get("contradictions") or []),
        "low_support_claims": low_support,
        "evidence_types": evidence_types[:5],
        # Enhanced fields (Task 4 + 5)
        "contradiction_flag": contradiction_flag,
        "contradiction_confidence": round(contradiction_confidence, 3),
        "contradiction_summary": state.get("contradiction_summary", ""),
        "study_agreement_level": agreement_level,
        "evidence_diversity": len(evidence_types),
        "evidence_diversity_summary": diversity_summary,
    }


def _build_confidence_explanation(confidence: float, mode: str, details: dict) -> str:
    if mode == "general_explanation":
        return "General medical explanation mode: no strong query-specific study match was available."
    if mode == "evidence_only":
        return (
            "Evidence was retrieved and summarized, but full language generation "
            "was temporarily unavailable."
        )
    if mode == "fallback":
        return (
            "Limited evidence mode: provider or evidence constraints reduced confidence "
            "in a fully grounded answer."
        )

    # evidence_based — build a rich explanation
    parts: list[str] = []
    if confidence >= 0.7:
        parts.append("Based on multiple high-quality studies")
    elif confidence >= 0.5:
        parts.append("Based on moderate-quality evidence")
    else:
        parts.append("Based on limited evidence")

    if details.get("contradiction_flag") or details.get("contradictions", 0) > 0:
        parts.append("with mixed or conflicting findings across retrieved studies")
    elif details.get("trusted", 0) >= 3:
        parts.append("with largely consistent findings")
    else:
        parts.append("with some uncertainty")

    diversity = details.get("evidence_diversity", 0)
    if diversity >= 3:
        parts.append(f"from {diversity} different study types")
    elif diversity > 0:
        parts.append("from a narrower evidence base")

    agreement = details.get("study_agreement_level")
    if agreement:
        parts.append(f"Study agreement level is {agreement}")

    return " ".join(parts) + "."


def _build_selection_rationale(state: "PipelineState") -> dict:
    """
    Compute why top documents were selected and what was filtered — no LLM needed.
    Sourced entirely from existing metadata already present in the pipeline state.
    """
    top_docs = state.get("top_docs") or []
    raw_count = len(state.get("raw_docs") or [])
    trusted_count = len(state.get("trusted_docs") or [])
    rejected_count = len(state.get("rejected_docs") or [])

    why_selected: list[dict] = []
    for doc in top_docs[:5]:
        meta = doc.get("metadata", {})
        medeva = doc.get("medeva", {})
        title = (meta.get("title") or "Untitled")[:70]
        study_type = _friendly_evidence_type(meta.get("study_type", ""))
        journal = (meta.get("journal") or "")[:40]
        score = round(medeva.get("total", 0.0), 2)
        band = medeva.get("confidence_band", "")
        pub_year = meta.get("pub_year", "")
        why_selected.append({
            "title": title,
            "study_type": study_type,
            "journal": journal,
            "pub_year": pub_year,
            "medeva_score": score,
            "confidence_band": band,
            "reason": (
                f"{study_type} published in {journal} ({pub_year}). "
                f"MEDEVA evidence quality score: {score} ({band})."
            ),
        })

    why_excluded: list[str] = []
    if rejected_count > 0:
        why_excluded.append(
            f"{rejected_count} sources removed by trust filter "
            "(journals not in the verified trusted-source list)."
        )
    quality_gap = trusted_count - len(top_docs)
    if quality_gap > 0:
        why_excluded.append(
            f"{quality_gap} sources removed by MEDEVA quality floor "
            f"(score below {_MEDEVA_FLOOR:.2f}) or relevance/intent filters."
        )

    return {
        "why_selected": why_selected,
        "why_excluded": why_excluded,
        "filter_summary": (
            f"{raw_count} retrieved → {trusted_count} passed trust filter "
            f"→ {len(top_docs)} used for answer generation"
        ),
    }


def _append_trace(
    state: PipelineState,
    node_name: str,
    transition: str | None = None,
    failure_path: str | None = None,
) -> dict:
    trace = [*(state.get("trace") or []), node_name]
    transitions = state.get("transitions") or []
    failure_paths = state.get("failure_paths") or []
    if transition:
        transitions = [*transitions, transition]
    if failure_path:
        failure_paths = [*failure_paths, failure_path]
    return {
        "trace": trace,
        "transitions": transitions,
        "failure_paths": failure_paths,
    }


def _build_limited_evidence_answer(query: str, docs: list[dict]) -> str:
    points: list[str] = []
    for doc in docs[:3]:
        sentences = [s.strip() for s in str(doc.get("text", "")).split(".") if len(s.strip()) > 60]
        if sentences:
            points.append(sentences[0] + ".")
    if not points:
        points.append("Available peer-reviewed evidence is limited for this exact formulation.")
    return (
        "Limited Evidence Available\n\n"
        f"Question: {query}\n\n"
        "Summary of available evidence:\n"
        + "\n".join(f"- {p}" for p in points[:3])
    )


def _generate_general_explanation(query: str) -> tuple[str, str, list[str]]:
    system_prompt = (
        "You are a medical assistant.\n"
        "Explain concepts in simple language for general education.\n"
        "Do NOT make diagnosis-specific clinical claims.\n"
        "Do NOT provide treatment plans or dosage advice.\n"
        "Keep the response concise, practical, and safe."
    )
    user_prompt = (
        f"Explain this in simple terms: {query}\n\n"
        "Return:\n"
        "1) A short plain-language explanation (2-4 sentences)\n"
        "2) A safety note that this is general education and not medical advice."
    )
    text, provider, attempts = generate_text_with_fallback(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=320,
    )
    safe_text = (
        "General Explanation\n\n"
        "While no strong clinical studies were found for this exact query, "
        "here is a general medical explanation:\n\n"
        f"{text.strip()}\n\n"
        "Note: This is general educational information and not based on "
        "query-specific clinical evidence."
    )
    return safe_text, provider, attempts


# ── Pipeline ──────────────────────────────────────────────────────────────────

class MedTruthPipeline:
    """
    Compiled LangGraph pipeline for post-retrieval processing.

    Instantiate once (via api/dependencies.py) and reuse across requests.
    """

    def __init__(self, vector_store: Any, rag_chain: Any) -> None:
        self.vector_store = vector_store
        self.rag_chain = rag_chain
        self._compiled = self._build_and_compile()

    # ── Node: Filter + Rank ───────────────────────────────────────────────────

    def _node_filter_rank(self, state: PipelineState) -> dict:
        raw_docs = state.get("raw_docs") or []
        query = state["effective_query"]
        domain = state["domain"]
        top_k = state["top_k"]

        trusted_docs, rejected_docs = filter_trusted_docs(raw_docs)

        def _matches_domain(doc: dict) -> bool:
            text = f"{doc.get('metadata', {}).get('title', '')} {doc.get('text', '')}".lower()
            if domain == "mental_health":
                return any(k in text for k in ["depression", "cbt", "psychotherapy", "mental", "anxiety"])
            if domain == "cardiology":
                return any(k in text for k in ["heart", "myocardial", "cardiac", "cardio", "aspirin"])
            return True

        # Augment with cached vector-store docs
        try:
            cached = [
                d for d in self.vector_store.search_with_medeva(query, top_k=5)
                if _matches_domain(d)
            ]
            trusted_docs.extend(cached)
        except Exception:
            logger.warning("Vector search failed for query: %s", query, exc_info=True)

        # Deduplicate by doc ID
        seen_ids: set[str] = set()
        deduped: list[dict] = []
        for doc in trusted_docs:
            if doc["id"] not in seen_ids:
                seen_ids.add(doc["id"])
                deduped.append(doc)

        deduped = [d for d in deduped if _matches_domain(d)]

        # Clinical intent alignment (prefer docs that match query intent)
        intent_docs = [d for d in deduped if matches_intent(d, query)]
        if intent_docs:
            deduped = intent_docs

        # Concept-overlap relevance filter
        relevant_docs = [d for d in deduped if is_relevant(d, query)]
        if not relevant_docs and deduped:
            relevant_docs = deduped
        if relevant_docs:
            deduped = relevant_docs

        # MEDEVA ranking + quality floor
        ranked = rank_documents(deduped)
        top_docs = [
            d for d in ranked[:top_k]
            if d.get("medeva", {}).get("total", 0.0) > _MEDEVA_FLOOR
        ]

        # Classify the reason for empty results (used for fallback_reason strings)
        no_docs_reason = ""
        if not top_docs:
            if not raw_docs:
                no_docs_reason = "retrieval_empty"
            elif not trusted_docs:
                no_docs_reason = "no_trusted_sources"
            else:
                no_docs_reason = "retrieval_filtered_empty"
            if state.get("was_expanded"):
                no_docs_reason += "_after_expansion"

        # Vector store upsert (non-critical; errors are suppressed)
        if top_docs:
            try:
                self.vector_store.upsert_documents(top_docs)
            except Exception:
                logger.warning("Vector store upsert failed", exc_info=True)

        # Semantic similarities for confidence scoring
        semantic_similarities = None
        if top_docs:
            try:
                semantic_similarities = self.vector_store.get_semantic_similarities(query, top_docs)
            except Exception:
                pass

        transition = "filter_rank->generate" if top_docs else "filter_rank->general_explanation"
        failure_path = no_docs_reason if no_docs_reason else None
        return {
            "trusted_docs": trusted_docs,
            "rejected_docs": rejected_docs,
            "top_docs": top_docs,
            "semantic_similarities": semantic_similarities,
            "no_docs_reason": no_docs_reason,
            **_append_trace(state, "filter_rank", transition=transition, failure_path=failure_path),
        }

    # ── Node: Generate ────────────────────────────────────────────────────────

    def _node_generate(self, state: PipelineState) -> dict:
        top_docs = state["top_docs"]
        query = state["effective_query"]

        # Full embedding-based contradiction detection (for the contradictions field)
        contradictions: list[dict] = []
        has_conflict = False
        if state["enable_contradiction_check"] and len(top_docs) >= 2:
            pairs = detect_contradictions(top_docs)
            contradictions = [p.to_dict() for p in pairs[:3]]
            has_conflict = bool(contradictions)

        # Lightweight heuristic signal (for confidence_details enrichment)
        signal = detect_contradiction_signal(top_docs)

        rag_response = self.rag_chain.generate(
            query=query,
            docs=top_docs,
            semantic_similarities=state.get("semantic_similarities"),
            has_conflict=has_conflict,
        )

        if rag_response.fallback_mode:
            generate_transition = "generate->evidence_only"
        elif rag_response.rejected:
            generate_transition = "generate->limited_evidence"
        else:
            generate_transition = "generate->verify"

        return {
            "rag_response": rag_response,
            "contradictions": contradictions,
            "has_conflict": has_conflict,
            "contradiction_flag": signal.contradiction_flag,
            "contradiction_summary": signal.summary,
            "contradiction_confidence": signal.confidence_score,
            **_append_trace(state, "generate", transition=generate_transition),
        }

    # ── Node: Verify (hallucination check) ───────────────────────────────────

    def _node_verify(self, state: PipelineState) -> dict:
        rag_response = state["rag_response"]
        final_answer = rag_response.answer
        hallucination_dict = None

        if state["enable_entailment_check"] and final_answer and not rag_response.fallback_mode:
            try:
                report = verify_claims(final_answer, state["top_docs"])
                hallucination_dict = to_api_dict(report)
                final_answer = report.safe_answer
            except Exception:
                logger.warning("Hallucination check failed", exc_info=True)

        return {
            "final_answer": final_answer,
            "hallucination_dict": hallucination_dict,
            "mode": "evidence_based",
            "provider_used": rag_response.provider_used,
            "provider_attempts": rag_response.provider_attempts or [],
            "citations": [c.to_dict() for c in rag_response.citations],
            "bibliography": rag_response.bibliography,
            "evidence_summary": rag_response.evidence_summary,
            "confidence": rag_response.confidence,
            "confidence_band": rag_response.confidence_band,
            "rejected": False,
            "rejection_reason": None,
            "fallback_reason": None,
            **_append_trace(state, "verify", transition="verify->finalize"),
        }

    # ── Node: Evidence Only (LLM down, extractive summary) ───────────────────

    def _node_evidence_only(self, state: PipelineState) -> dict:
        rag = state["rag_response"]
        return {
            "final_answer": rag.answer,
            "hallucination_dict": None,
            "mode": "evidence_only",
            "fallback_reason": rag.fallback_reason or "provider_error_after_evidence",
            "provider_used": rag.provider_used,
            "provider_attempts": rag.provider_attempts or [],
            "citations": [c.to_dict() for c in rag.citations],
            "bibliography": rag.bibliography,
            "evidence_summary": rag.evidence_summary,
            "confidence": rag.confidence,
            "confidence_band": rag.confidence_band,
            "rejected": False,
            "rejection_reason": None,
            **_append_trace(
                state,
                "evidence_only",
                transition="evidence_only->finalize",
                failure_path=rag.fallback_reason or "provider_error_after_evidence",
            ),
        }

    # ── Node: Limited Evidence (RAG rejected due to quality) ─────────────────

    def _node_limited_evidence(self, state: PipelineState) -> dict:
        rag = state["rag_response"]
        original_query = state["original_query"]
        top_docs = state.get("top_docs") or []

        return {
            "final_answer": _build_limited_evidence_answer(original_query, top_docs),
            "hallucination_dict": None,
            "mode": rag.mode if rag else "fallback",
            "fallback_reason": rag.fallback_reason if rag else "insufficient_evidence",
            "provider_used": rag.provider_used if rag else "none",
            "provider_attempts": (rag.provider_attempts or []) if rag else [],
            "citations": [],
            "bibliography": "",
            "evidence_summary": rag.evidence_summary if rag else "",
            "confidence": rag.confidence if rag else 0.4,
            "confidence_band": rag.confidence_band if rag else "LOW",
            "rejected": False,
            "rejection_reason": None,
            **_append_trace(
                state,
                "limited_evidence",
                transition="limited_evidence->finalize",
                failure_path=(rag.fallback_reason if rag else "insufficient_evidence"),
            ),
        }

    # ── Node: General Explanation (no usable evidence) ───────────────────────

    def _node_general_explanation(self, state: PipelineState) -> dict:
        original_query = state["original_query"]
        no_docs_reason = state.get("no_docs_reason") or "retrieval_empty"

        try:
            text, provider, attempts = _generate_general_explanation(original_query)
            return {
                "final_answer": text,
                "hallucination_dict": None,
                "mode": "general_explanation",
                "fallback_reason": no_docs_reason,
                "provider_used": provider,
                "provider_attempts": attempts,
                "citations": [],
                "bibliography": "",
                "evidence_summary": (
                    "General educational explanation mode "
                    "(no query-specific evidence passed quality filters)."
                ),
                "confidence": 0.4,
                "confidence_band": "LOW",
                "rejected": False,
                "rejection_reason": None,
                **_append_trace(
                    state,
                    "general_explanation",
                    transition="general_explanation->finalize",
                    failure_path=no_docs_reason,
                ),
            }
        except Exception as exc:
            attempts = getattr(exc, "attempts", [])
            return {
                "final_answer": _build_limited_evidence_answer(
                    original_query, state.get("top_docs") or []
                ),
                "hallucination_dict": None,
                "mode": "fallback",
                "fallback_reason": f"provider_error_after_{no_docs_reason}",
                "provider_used": "none",
                "provider_attempts": attempts,
                "citations": [],
                "bibliography": "",
                "evidence_summary": "",
                "confidence": 0.4,
                "confidence_band": "LOW",
                "rejected": False,
                "rejection_reason": None,
                **_append_trace(
                    state,
                    "general_explanation",
                    transition="general_explanation->finalize",
                    failure_path=f"provider_error_after_{no_docs_reason}",
                ),
            }

    # ── Node: Finalize (risk + confidence, common to all paths) ──────────────

    def _node_finalize(self, state: PipelineState) -> dict:
        original_query = state["original_query"]
        final_answer = state.get("final_answer", "")

        risk_flags_raw = flag_query(original_query, final_answer)
        risk_flags = [f.to_dict() for f in risk_flags_raw]
        overall_risk = get_overall_risk_level(risk_flags_raw).value

        confidence_details = _build_confidence_details(state)
        confidence_explanation = _build_confidence_explanation(
            confidence=state.get("confidence", 0.4),
            mode=state.get("mode", "fallback"),
            details=confidence_details,
        )

        selection_rationale = _build_selection_rationale(state)
        citation_titles = [
            c.get("title", "")
            for c in (state.get("citations") or [])
            if isinstance(c, dict) and c.get("title")
        ]
        related_questions: list[str] = []
        if state.get("mode") in {"evidence_based", "evidence_only", "general_explanation"}:
            related_questions = generate_related_questions(
                query=state["original_query"],
                answer=state.get("final_answer", ""),
                evidence=citation_titles,
                n=4,
            )

        return {
            "risk_flags": risk_flags,
            "overall_risk": overall_risk,
            "confidence_details": confidence_details,
            "confidence_explanation": confidence_explanation,
            "selection_rationale": selection_rationale,
            "related_questions": related_questions,
            **_append_trace(state, "finalize", transition="finalize->END"),
        }

    # ── Routing ───────────────────────────────────────────────────────────────

    @staticmethod
    def _route_after_filter(
        state: PipelineState,
    ) -> Literal["generate", "general_explanation"]:
        return "generate" if state.get("top_docs") else "general_explanation"

    @staticmethod
    def _route_after_generate(
        state: PipelineState,
    ) -> Literal["verify", "evidence_only", "limited_evidence"]:
        rag = state.get("rag_response")
        if rag is None:
            return "limited_evidence"
        if rag.fallback_mode:
            return "evidence_only"
        if rag.rejected:
            return "limited_evidence"
        return "verify"

    # ── Graph construction ────────────────────────────────────────────────────

    def _build_and_compile(self):
        graph = StateGraph(PipelineState)

        graph.add_node("filter_rank", self._node_filter_rank)
        graph.add_node("generate", self._node_generate)
        graph.add_node("verify", self._node_verify)
        graph.add_node("evidence_only", self._node_evidence_only)
        graph.add_node("limited_evidence", self._node_limited_evidence)
        graph.add_node("general_explanation", self._node_general_explanation)
        graph.add_node("finalize", self._node_finalize)

        graph.add_edge(START, "filter_rank")

        graph.add_conditional_edges(
            "filter_rank",
            self._route_after_filter,
            {"generate": "generate", "general_explanation": "general_explanation"},
        )
        graph.add_conditional_edges(
            "generate",
            self._route_after_generate,
            {
                "verify": "verify",
                "evidence_only": "evidence_only",
                "limited_evidence": "limited_evidence",
            },
        )

        graph.add_edge("verify", "finalize")
        graph.add_edge("evidence_only", "finalize")
        graph.add_edge("limited_evidence", "finalize")
        graph.add_edge("general_explanation", "finalize")
        graph.add_edge("finalize", END)

        return graph.compile()

    def run(self, state: PipelineState) -> PipelineState:
        """Execute the pipeline graph (synchronous, call after async retrieval)."""
        return self._compiled.invoke(state)
