"""
LLM Lab agent — hardened MCP-style tool orchestration.

Hardening applied:
  ✓ Task 1 — Explicit ALLOWED_TOOLS validation; unknown tools skipped + logged
  ✓ Task 2 — Context capped at MAX_CONTEXT_CHARS; per-abstract truncation in tools.py
  ✓ Task 4 — asyncio.wait_for timeouts on both PubMed and LLM calls
  ✓ Task 5 — MAX_TOOL_CALLS_PER_QUERY cap enforced during plan validation
  ✓ Task 7 — Confidence note appended to every synthesized answer

Isolation still intact:
  ✗ No MedTruthPipeline / RAGChain / MEDEVA scoring
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass

from src.llm.fallback_client import generate_text_with_fallback
from src.mcp.tools import pubmed_search

logger = logging.getLogger(__name__)

# ── Safety constants ──────────────────────────────────────────────────────────

ALLOWED_TOOLS: frozenset[str] = frozenset({"pubmed_search", "analysis"})
MAX_PUBMED_STEPS       = 2      # at most 2 PubMed calls per run
MAX_TOOL_CALLS_PER_QUERY = 5   # hard cap on total executable steps (excl. planner)
MAX_CONTEXT_CHARS      = 8_000  # rolling context window sent to each LLM call
PUBMED_TIMEOUT_S       = 9.0    # asyncio.wait_for timeout for PubMed HTTP calls
LLM_TIMEOUT_S          = 15.0   # asyncio.wait_for timeout for LLM synthesis calls

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

JSON format:
{
  "plan": [
    {"tool": "pubmed_search", "input": "<search query>", "reasoning": "<why>"},
    {"tool": "analysis",      "input": "<synthesis goal>", "reasoning": "<why>"}
  ]
}\
"""

_ANALYSIS_SYSTEM = """\
You are a medical research assistant.
Synthesize the provided research context into a clear, structured answer.
Base your answer ONLY on the provided context — do not introduce outside facts.

Format your response as:
1. DIRECT ANSWER — one or two sentences
2. KEY FINDINGS — bullet points from the research
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

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "input": self.input,
            "output": self.output,
            "reasoning": self.reasoning,
            "duration_ms": round(self.duration_ms, 1),
            "skipped": self.skipped,
        }


@dataclass
class AgentResponse:
    answer: str
    steps: list[ToolStep]
    tools_used: list[str]
    total_duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "steps": [s.to_dict() for s in self.steps],
            "tools_used": self.tools_used,
            "total_duration_ms": round(self.total_duration_ms, 1),
        }

# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate_context(context_parts: list[str]) -> str:
    """
    Join accumulated context and truncate to MAX_CONTEXT_CHARS.
    Truncation keeps the END (most recent context) since it is most relevant
    to the next synthesis step.
    """
    full = "\n\n".join(context_parts)
    if len(full) <= MAX_CONTEXT_CHARS:
        return full
    truncated = full[-MAX_CONTEXT_CHARS:]
    # Find the first newline so we don't cut mid-sentence
    first_nl = truncated.find("\n")
    if first_nl > 0:
        truncated = truncated[first_nl + 1:]
    return "[…context truncated to last 8 000 chars…]\n\n" + truncated


def _validate_plan(raw_plan: list[dict], query: str) -> list[dict]:
    """
    Enforce ALLOWED_TOOLS, step caps, and correct sequencing.
    Returns a safe, executable plan — never raises.
    """
    validated: list[dict] = []
    seen_pubmed = 0
    seen_analysis = 0

    for step in raw_plan:
        tool = step.get("tool", "")

        # Task 1 — reject unknown tools
        if tool not in ALLOWED_TOOLS:
            logger.warning("Planner emitted unknown tool %r — skipping step", tool)
            continue

        if tool == "pubmed_search":
            if seen_pubmed >= MAX_PUBMED_STEPS:
                logger.debug("Planner exceeded max pubmed_search steps — skipping")
                continue
            seen_pubmed += 1

        elif tool == "analysis":
            if seen_analysis >= 1:
                logger.debug("Duplicate analysis step — skipping")
                continue
            seen_analysis += 1

        validated.append(step)

        # Task 5 — hard cap on executable steps
        if len(validated) >= MAX_TOOL_CALLS_PER_QUERY:
            logger.debug("Hit MAX_TOOL_CALLS_PER_QUERY=%d — truncating plan", MAX_TOOL_CALLS_PER_QUERY)
            break

    # Always ensure we end with analysis
    if not validated or validated[-1].get("tool") != "analysis":
        validated.append({
            "tool": "analysis",
            "input": "Summarize all gathered findings",
            "reasoning": "Mandatory final synthesis step",
        })

    return validated

# ── Agent ─────────────────────────────────────────────────────────────────────

class LabAgent:
    """
    Hardened MCP-style agent for LLM Lab.

    Plan → Validate → Execute (with timeouts) → Synthesize → Confidence note
    """

    async def _plan(self, query: str) -> list[dict]:
        """Ask the LLM to produce a tool plan, then validate it."""
        try:
            # Task 4 — timeout on planner LLM call
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
            logger.warning("Planner LLM timed out — using default plan")
            return _validate_plan([], query)
        except Exception:
            logger.debug("Planner LLM failed — using default plan", exc_info=True)
            return _validate_plan([], query)

    async def _execute_step(self, step: dict, context: str) -> ToolStep:
        tool      = step.get("tool", "analysis")
        inp       = str(step.get("input", "")).strip()
        reasoning = str(step.get("reasoning", "")).strip()
        started   = time.perf_counter()
        output    = ""

        # ── PubMed search ──────────────────────────────────────────────────
        if tool == "pubmed_search":
            try:
                # Task 4 — 9s timeout on PubMed HTTP
                output = await asyncio.wait_for(
                    pubmed_search(inp, max_results=5),
                    timeout=PUBMED_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                output = f"PubMed search timed out after {PUBMED_TIMEOUT_S:.0f}s — step skipped."
                logger.warning("pubmed_search timed out for query: %r", inp)
            except Exception as exc:
                output = f"PubMed search failed: {exc}"
                logger.warning("pubmed_search error for query %r: %s", inp, exc)

        # ── LLM analysis / synthesis ───────────────────────────────────────
        elif tool == "analysis":
            ctx = context.strip() or "No prior research context available."
            user_prompt = (
                f"Synthesis goal: {inp}\n\n"
                f"Research context:\n{ctx}"
            )
            try:
                # Task 4 — 15s timeout on LLM synthesis
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
            except asyncio.TimeoutError:
                output = "Analysis step timed out — synthesis incomplete."
                logger.warning("Analysis LLM call timed out")
            except Exception as exc:
                output = f"Analysis step failed: {exc}"

        else:
            # Should not reach here after _validate_plan — defensive fallback
            output = f"Tool '{tool}' is not in ALLOWED_TOOLS — step skipped."
            logger.error("Unexpected tool in _execute_step: %r", tool)

        return ToolStep(
            tool=tool,
            input=inp,
            output=output,
            reasoning=reasoning,
            duration_ms=(time.perf_counter() - started) * 1_000,
        )

    async def run(self, query: str) -> AgentResponse:
        total_start = time.perf_counter()
        steps: list[ToolStep] = []

        # ── Planning ────────────────────────────────────────────────────────
        plan_start = time.perf_counter()
        plan = await self._plan(query)
        plan_ms = (time.perf_counter() - plan_start) * 1_000
        steps.append(ToolStep(
            tool="planner",
            input=query,
            output=json.dumps(plan, indent=2),
            reasoning=f"Validated plan: {len(plan)} step(s)",
            duration_ms=plan_ms,
        ))

        # ── Execution ───────────────────────────────────────────────────────
        context_parts: list[str] = []
        answer = ""

        for step_plan in plan:
            # Task 2 — build truncated context before each step
            context = _truncate_context(context_parts)
            result = await self._execute_step(step_plan, context)
            steps.append(result)

            if result.tool == "pubmed_search" and result.output:
                context_parts.append(f"PubMed results for {result.input!r}:\n{result.output}")
            elif result.tool == "analysis" and result.output:
                answer = result.output

        # ── Task 7 — Confidence note ─────────────────────────────────────
        if not answer:
            answer = context_parts[-1] if context_parts else "The agent could not generate an answer."
        answer = answer.rstrip() + _CONFIDENCE_NOTE

        tools_used = list(dict.fromkeys(s.tool for s in steps))
        return AgentResponse(
            answer=answer,
            steps=steps,
            tools_used=tools_used,
            total_duration_ms=(time.perf_counter() - total_start) * 1_000,
        )
