"""
LLM Lab agent — hardened MCP-style tool orchestration.

Hardening applied:
  ✓ #1 — Explicit ALLOWED_TOOLS + required-field schema validation; unknown/malformed tools skipped
  ✓ #2 — Step output validation with fail-fast on critical (analysis) failure
  ✓ #3 — Structured [MCP] server logs per step; status/error/confidence in AgentResponse
  ✓ #4 — Validated plan exposed as top-level field before execution results
  ✓ #5 — PubMed result cache (5-min TTL) delegated to tools.py
  ✓ #6 — Confidence band (LOW/MEDIUM/HIGH) derived from retrieved evidence quality
  ✓ #7 — Analysis prompt enforces claim-level grounding; hallucination guardrail
  ✓ Context capped at MAX_CONTEXT_CHARS; per-abstract truncation in tools.py
  ✓ asyncio.wait_for timeouts on both PubMed and LLM calls
  ✓ MAX_TOOL_CALLS_PER_QUERY cap enforced during plan validation

Isolation still intact:
  ✗ No MedTruthPipeline / RAGChain / MEDEVA scoring
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field

from src.llm.fallback_client import generate_text_with_fallback
from src.mcp.tools import pubmed_search

logger = logging.getLogger(__name__)

# ── Safety constants ──────────────────────────────────────────────────────────

ALLOWED_TOOLS: frozenset[str] = frozenset({"pubmed_search", "analysis"})
MAX_PUBMED_STEPS         = 2       # at most 2 PubMed calls per run
MAX_TOOL_CALLS_PER_QUERY = 5       # hard cap on total executable steps (excl. planner)
MAX_CONTEXT_CHARS        = 8_000   # rolling context window sent to each LLM call
PUBMED_TIMEOUT_S         = 9.0     # asyncio.wait_for timeout for PubMed HTTP calls
LLM_TIMEOUT_S            = 15.0    # asyncio.wait_for timeout for LLM synthesis calls
MIN_PUBMED_OUTPUT_CHARS  = 80      # below this → step treated as failed/empty

_CONFIDENCE_NOTE = (
    "\n\n---\n"
    "*This is an experimental AI-generated response based on abstract-level evidence "
    "retrieved from PubMed. It has not been validated against full clinical evidence and "
    "may not reflect current medical consensus. Do not use for clinical decisions.*"
)

# ── Prompts ───────────────────────────────────────────────────────────────────

_PLANNER_SYSTEM = """\
You are a research planning agent.
Given a user query, decide which tools to call and in what order.

Available tools (ONLY these two are allowed):
  pubmed_search — searches PubMed for peer-reviewed papers (use at most twice)
  analysis      — synthesizes all gathered context into a final answer (MUST be last)

Rules:
  - Return ONLY valid JSON — no markdown fences, no extra text.
  - Always end with exactly one "analysis" step.
  - Total steps including analysis must not exceed 5.
  - Every step MUST include a non-empty "input" string.

JSON format:
{
  "plan": [
    {"tool": "pubmed_search", "input": "<search query>", "reasoning": "<why>"},
    {"tool": "analysis",      "input": "<synthesis goal>", "reasoning": "<why>"}
  ]
}\
"""

# ✓ #7 — Claim-level grounding instruction; hallucination guardrail
_ANALYSIS_SYSTEM = """\
You are a medical research assistant.
Synthesize the provided research context into a clear, structured answer.
Base your answer ONLY on the provided context — do not introduce outside facts.
Every factual claim MUST be directly traceable to a [Study N] listed in the context.
If a claim cannot be traced to a listed study, omit it entirely.

Format your response as:
1. DIRECT ANSWER — one or two sentences
2. KEY FINDINGS — bullet points from the research, each citing the source [Study N]
3. LIMITATIONS — any caveats, gaps, or conflicts in the evidence\
"""

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ToolStep:
    tool: str
    input: str
    output: str = ""
    reasoning: str = ""
    duration_ms: float = 0.0
    skipped: bool = False
    status: str = "success"   # "success" | "failed" | "skipped"
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "input": self.input,
            "output": self.output,
            "reasoning": self.reasoning,
            "duration_ms": round(self.duration_ms, 1),
            "skipped": self.skipped,
            "status": self.status,
            "error": self.error,
        }


@dataclass
class AgentResponse:
    answer: str
    steps: list[ToolStep]
    tools_used: list[str]
    total_duration_ms: float = 0.0
    status: str = "success"           # "success" | "failed" | "partial"
    error: str = ""
    confidence: str = "LOW"           # ✓ #6 — LOW / MEDIUM / HIGH
    confidence_reason: str = ""
    plan: list[dict] = field(default_factory=list)  # ✓ #4 — plan before execution

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "steps": [s.to_dict() for s in self.steps],
            "tools_used": self.tools_used,
            "total_duration_ms": round(self.total_duration_ms, 1),
            "status": self.status,
            "error": self.error,
            "confidence": self.confidence,
            "confidence_reason": self.confidence_reason,
            "plan": self.plan,
        }

# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate_context(context_parts: list[str]) -> str:
    """
    Join accumulated context and truncate to MAX_CONTEXT_CHARS.
    Keeps the END (most recent context) since it is most relevant to synthesis.
    """
    full = "\n\n".join(context_parts)
    if len(full) <= MAX_CONTEXT_CHARS:
        return full
    truncated = full[-MAX_CONTEXT_CHARS:]
    first_nl = truncated.find("\n")
    if first_nl > 0:
        truncated = truncated[first_nl + 1:]
    return "[…context truncated to last 8 000 chars…]\n\n" + truncated


def _validate_plan(raw_plan: list[dict], query: str) -> list[dict]:
    """
    ✓ #1 — Enforce ALLOWED_TOOLS, required-field schema, step caps, and correct sequencing.
    Returns a safe, executable plan — never raises.
    """
    validated: list[dict] = []
    seen_pubmed = 0
    seen_analysis = 0

    for step in raw_plan:
        tool = step.get("tool", "")

        # Reject unknown tools
        if tool not in ALLOWED_TOOLS:
            logger.warning("[MCP] Planner emitted unknown tool %r — skipping step", tool)
            continue

        # Schema validation: require non-empty "input"
        inp = step.get("input", "")
        if not isinstance(inp, str) or not inp.strip():
            logger.warning("[MCP] Step for tool %r missing required 'input' field — skipping", tool)
            continue

        if tool == "pubmed_search":
            if seen_pubmed >= MAX_PUBMED_STEPS:
                logger.debug("[MCP] Exceeded max pubmed_search steps — skipping")
                continue
            seen_pubmed += 1

        elif tool == "analysis":
            if seen_analysis >= 1:
                logger.debug("[MCP] Duplicate analysis step — skipping")
                continue
            seen_analysis += 1

        validated.append(step)

        if len(validated) >= MAX_TOOL_CALLS_PER_QUERY:
            logger.debug("[MCP] Hit MAX_TOOL_CALLS_PER_QUERY=%d — truncating plan", MAX_TOOL_CALLS_PER_QUERY)
            break

    # Always ensure we end with analysis
    if not validated or validated[-1].get("tool") != "analysis":
        validated.append({
            "tool": "analysis",
            "input": "Summarize all gathered findings",
            "reasoning": "Mandatory final synthesis step",
        })

    return validated


def _compute_confidence(steps: list[ToolStep]) -> tuple[str, str]:
    """
    ✓ #6 — Derive LOW/MEDIUM/HIGH band from retrieved evidence.
    Returns (band, reason).
    """
    pubmed_steps = [
        s for s in steps
        if s.tool == "pubmed_search" and s.status == "success"
    ]
    if not pubmed_steps:
        return "LOW", "No PubMed results retrieved"

    study_count = sum(s.output.count("[Study ") for s in pubmed_steps)
    has_high_quality = any(
        any(kw in s.output for kw in [
            "Systematic review", "Meta-analysis", "Randomized controlled"
        ])
        for s in pubmed_steps
    )

    if study_count >= 3 and has_high_quality:
        return "HIGH", f"{study_count} studies including systematic reviews/RCTs"
    if study_count >= 2 or has_high_quality:
        return "MEDIUM", f"{study_count} study(ies) found"
    return "LOW", f"Only {study_count} study(ies) found — limited evidence base"


def _is_analysis_failed(output: str) -> bool:
    return (
        not output.strip()
        or output.startswith("Analysis step timed out")
        or output.startswith("Analysis step failed")
    )

# ── Agent ─────────────────────────────────────────────────────────────────────

class LabAgent:
    """
    Hardened MCP-style agent for LLM Lab.

    Plan → Validate → Execute (with timeouts + output validation) → Synthesize → Confidence note
    """

    async def _plan(self, query: str) -> list[dict]:
        """Ask the LLM to produce a tool plan, then validate it."""
        try:
            raw_text, _, _ = await asyncio.wait_for(
                asyncio.to_thread(
                    generate_text_with_fallback,
                    _PLANNER_SYSTEM,
                    f"User query: {query}",
                    320,
                ),
                timeout=LLM_TIMEOUT_S,
            )
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if not match:
                return _validate_plan([], query)
            data = json.loads(match.group(0))
            raw_plan = data.get("plan", [])
            if not isinstance(raw_plan, list):
                return _validate_plan([], query)
            return _validate_plan(raw_plan, query)

        except asyncio.TimeoutError:
            logger.warning("[MCP] Planner LLM timed out — using default plan")
            return _validate_plan([], query)
        except Exception:
            logger.debug("[MCP] Planner LLM failed — using default plan", exc_info=True)
            return _validate_plan([], query)

    async def _execute_step(self, step: dict, context: str) -> ToolStep:
        tool      = step.get("tool", "analysis")
        inp       = str(step.get("input", "")).strip()
        reasoning = str(step.get("reasoning", "")).strip()
        started   = time.perf_counter()
        output    = ""
        status    = "success"
        error     = ""

        # ── PubMed search ──────────────────────────────────────────────────
        if tool == "pubmed_search":
            try:
                output = await asyncio.wait_for(
                    pubmed_search(inp, max_results=5),
                    timeout=PUBMED_TIMEOUT_S,
                )
                # ✓ #2 — validate output is substantial
                if len(output) < MIN_PUBMED_OUTPUT_CHARS:
                    status = "failed"
                    error = f"PubMed returned insufficient results ({len(output)} chars)"
                    logger.warning("[MCP] pubmed_search returned too little for query %r", inp)
            except asyncio.TimeoutError:
                output = f"PubMed search timed out after {PUBMED_TIMEOUT_S:.0f}s — step skipped."
                status = "failed"
                error = "timeout"
                logger.warning("[MCP] pubmed_search timed out for query: %r", inp)
            except Exception as exc:
                output = f"PubMed search failed: {exc}"
                status = "failed"
                error = str(exc)
                logger.warning("[MCP] pubmed_search error for query %r: %s", inp, exc)

        # ── LLM analysis / synthesis ───────────────────────────────────────
        elif tool == "analysis":
            ctx = context.strip() or "No prior research context available."
            user_prompt = (
                f"Synthesis goal: {inp}\n\n"
                f"Research context:\n{ctx}"
            )
            try:
                raw_text, _, _ = await asyncio.wait_for(
                    asyncio.to_thread(
                        generate_text_with_fallback,
                        _ANALYSIS_SYSTEM,
                        user_prompt,
                        900,
                    ),
                    timeout=LLM_TIMEOUT_S,
                )
                output = raw_text.strip()
                if not output:
                    status = "failed"
                    error = "LLM returned empty response"
            except asyncio.TimeoutError:
                output = "Analysis step timed out — synthesis incomplete."
                status = "failed"
                error = "timeout"
                logger.warning("[MCP] Analysis LLM call timed out")
            except Exception as exc:
                output = f"Analysis step failed: {exc}"
                status = "failed"
                error = str(exc)

        else:
            output = f"Tool '{tool}' is not in ALLOWED_TOOLS — step skipped."
            status = "skipped"
            logger.error("[MCP] Unexpected tool in _execute_step: %r", tool)

        duration_ms = (time.perf_counter() - started) * 1_000
        # ✓ #3 — structured per-step server log
        logger.info("[MCP] Step %-14s took %6.0fms | status=%s", tool, duration_ms, status)

        return ToolStep(
            tool=tool,
            input=inp,
            output=output,
            reasoning=reasoning,
            duration_ms=duration_ms,
            status=status,
            error=error,
        )

    async def run(self, query: str) -> AgentResponse:
        total_start = time.perf_counter()
        steps: list[ToolStep] = []
        overall_status = "success"
        overall_error = ""

        # ── Planning ────────────────────────────────────────────────────────
        plan_start = time.perf_counter()
        plan = await self._plan(query)
        plan_ms = (time.perf_counter() - plan_start) * 1_000
        # ✓ #3 — log planner step
        logger.info("[MCP] Step %-14s took %6.0fms | status=success", "planner", plan_ms)
        steps.append(ToolStep(
            tool="planner",
            input=query,
            output=json.dumps(plan, indent=2),
            reasoning=f"Validated plan: {len(plan)} step(s)",
            duration_ms=plan_ms,
            status="success",
        ))

        # ── Execution ───────────────────────────────────────────────────────
        context_parts: list[str] = []
        answer = ""

        for step_plan in plan:
            context = _truncate_context(context_parts)
            result = await self._execute_step(step_plan, context)
            steps.append(result)

            if result.tool == "pubmed_search" and result.status == "success":
                context_parts.append(f"PubMed results for {result.input!r}:\n{result.output}")

            elif result.tool == "analysis":
                # ✓ #2 — fail-fast on critical step failure
                if _is_analysis_failed(result.output):
                    overall_status = "failed"
                    overall_error = result.error or "Analysis step produced no usable output"
                    answer = "Unable to complete analysis due to a tool failure. Please try again."
                    break
                answer = result.output
                if result.status == "failed":
                    overall_status = "partial"

        # ── Confidence note + band ──────────────────────────────────────────
        if not answer and overall_status != "failed":
            answer = context_parts[-1] if context_parts else "The agent could not generate an answer."
            overall_status = "partial"

        answer = answer.rstrip() + _CONFIDENCE_NOTE

        # ✓ #6 — compute confidence band from evidence steps
        confidence, confidence_reason = _compute_confidence(steps)

        tools_used = list(dict.fromkeys(s.tool for s in steps))
        total_ms = (time.perf_counter() - total_start) * 1_000
        logger.info(
            "[MCP] Query complete | status=%s | confidence=%s | total=%.0fms",
            overall_status, confidence, total_ms,
        )

        return AgentResponse(
            answer=answer,
            steps=steps,
            tools_used=tools_used,
            total_duration_ms=total_ms,
            status=overall_status,
            error=overall_error,
            confidence=confidence,
            confidence_reason=confidence_reason,
            plan=plan,  # ✓ #4 — expose validated plan before execution results
        )
