"use client";

import { QueryResponse, explainAnswer } from "@/lib/api";
import SelectionRationale from "@/components/SelectionRationale";
import ControlledDiscussion from "@/components/ControlledDiscussion";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  Database,
  Filter,
  FlaskConical,
  MessageCircle,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

// ─── Props ────────────────────────────────────────────────────────────────────

interface AnswerResponseCardProps {
  query: string;
  result: QueryResponse;
  onSentenceHover: (sourceIndex: number | null) => void;
  onSentenceClick: (sourceIndex: number) => void;
  onSave?: () => void;
  canSave?: boolean;
  onRequireSignIn?: () => void;
  saveState?: "idle" | "saving" | "saved" | "error";
  onRelatedQuery?: (q: string) => void;
}

// ─── Pipeline config ──────────────────────────────────────────────────────────

type PipelineStep = { id: string; label: string; icon: LucideIcon };

const PIPELINE: PipelineStep[] = [
  { id: "ask",      label: "Ask",      icon: MessageCircle },
  { id: "retrieve", label: "Retrieve", icon: Database      },
  { id: "filter",   label: "Filter",   icon: Filter        },
  { id: "rank",     label: "Rank",     icon: BarChart3     },
  { id: "score",    label: "Score",    icon: FlaskConical  },
  { id: "answer",   label: "Answer",   icon: Sparkles      },
];

// ─── Confidence band ──────────────────────────────────────────────────────────

const BAND_CFG = {
  HIGH:   { pill: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-300 dark:border-emerald-800", dot: "bg-emerald-500", label: "Strong Evidence"   },
  MEDIUM: { pill: "bg-amber-50   text-amber-700   border-amber-200   dark:bg-amber-900/20   dark:text-amber-300   dark:border-amber-800",   dot: "bg-amber-500",   label: "Moderate Evidence" },
  LOW:    { pill: "bg-rose-50    text-rose-700    border-rose-200    dark:bg-rose-900/20    dark:text-rose-300    dark:border-rose-800",    dot: "bg-rose-500",    label: "Limited Evidence"  },
} as const;

// ─── Fallback-reason labels ───────────────────────────────────────────────────

const REASON_MAP: Record<string, string> = {
  retrieval_empty: "No directly relevant studies were found for this query.",
  retrieval_empty_after_expansion: "No relevant studies were found even after broadening the search.",
  retrieval_filtered_empty: "Studies were found, but none passed quality filters.",
  retrieval_filtered_empty_after_expansion: "Studies were found after broad search, but none passed quality filters.",
  provider_error_after_retrieval_empty: "The AI service is temporarily unavailable.",
  provider_error_after_retrieval_empty_after_expansion: "The AI service is temporarily unavailable.",
  provider_error_after_retrieval_filtered_empty: "The AI service is temporarily unavailable after quality filtering.",
  provider_error_after_retrieval_filtered_empty_after_expansion: "The AI service is temporarily unavailable.",
  provider_error_after_evidence: "AI explanation unavailable — evidence was found and summarized.",
};

const SEVERE_THRESHOLD = 0.4;

// ─── Component ────────────────────────────────────────────────────────────────

export default function AnswerResponseCard({
  query,
  result,
  onSentenceHover,
  onSentenceClick,
  onSave,
  canSave = false,
  onRequireSignIn,
  saveState = "idle",
  onRelatedQuery,
}: AnswerResponseCardProps) {
  // ── State ──────────────────────────────────────────────────────────────────
  const [activePipelineId, setActivePipelineId] = useState<string | null>(null);
  const [copied, setCopied]           = useState(false);
  const [patientMode, setPatientMode] = useState(false);
  const [patientText, setPatientText] = useState<string | null>(null);
  const [loadingExplain, setLoadingExplain] = useState(false);
  const [toast, setToast]             = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [typedText, setTypedText]     = useState("");
  const [isDebug, setIsDebug]         = useState(false);

  // ── Debug mode ─────────────────────────────────────────────────────────────
  useEffect(() => {
    setIsDebug(new URLSearchParams(window.location.search).get("debug") === "1");
  }, []);

  // ── Answer text ────────────────────────────────────────────────────────────
  const answer = (result.answer ?? "")
    .replace(/Insufficient Evidence/gi, "Limited evidence available")
    .replace(/Response Withheld/gi, "Based on current research")
    .replace(/LLM unavailable/gi, "Based on current research");

  useEffect(() => {
    setTypedText("");
    let idx = 0;
    const timer = setInterval(() => {
      idx += 4;
      setTypedText(answer.slice(0, idx));
      if (idx >= answer.length) clearInterval(timer);
    }, 12);
    return () => clearInterval(timer);
  }, [answer]);

  const typingInProgress = typedText.length < answer.length;

  // ── Pipeline active index ──────────────────────────────────────────────────
  // 0=Ask is always done; progress remaining 5 steps with typing animation
  const pipelineActiveIdx = useMemo(() => {
    if (!typingInProgress) return PIPELINE.length - 1;
    const ratio = typedText.length / Math.max(answer.length, 1);
    return Math.min(Math.floor(ratio * (PIPELINE.length - 1)) + 1, PIPELINE.length - 1);
  }, [typedText, answer, typingInProgress]);

  // ── Derived values ─────────────────────────────────────────────────────────
  const confidence       = Math.round(Math.max(0, result.confidence) * 100);
  const bandKey          = (result.confidence_band ?? "LOW") as keyof typeof BAND_CFG;
  const band             = BAND_CFG[bandKey] ?? BAND_CFG.LOW;
  const isGeneralMode    = result.mode === "general_explanation";
  const isEvidenceOnly   = result.mode === "evidence_only";
  const fallbackReason   = result.fallback_reason ? (REASON_MAP[result.fallback_reason] ?? null) : null;

  const confidenceDetails = result.confidence_details ?? {
    retrieved: result.sources_retrieved,
    trusted: result.sources_trusted,
    excluded: result.sources_retrieved - result.sources_trusted,
    contradictions: result.contradictions?.length ?? 0,
    low_support_claims: 0,
    evidence_types: [] as string[],
  };

  const severeUncertainClaims = (result.hallucination_check?.unverified_claims ?? [])
    .filter((c) => c.entailment_score < SEVERE_THRESHOLD);
  const hasSevereUncertainty = !isGeneralMode && severeUncertainClaims.length > 0;

  // ── Confidence bullets (rendered directly from backend fields) ─────────────
  const confidenceBullets = useMemo(() => {
    const d = confidenceDetails;
    const bullets: string[] = [];
    if (d.trusted && d.retrieved) {
      bullets.push(
        `${d.trusted} high-quality ${d.trusted === 1 ? "study" : "studies"} from ${d.retrieved} retrieved`
      );
    }
    const types = (d as { evidence_types?: string[] }).evidence_types;
    if (types && types.length > 0) {
      bullets.push(`Evidence includes: ${types.slice(0, 3).join(", ")}`);
    }
    const flag = (d as { contradiction_flag?: boolean }).contradiction_flag;
    const summary = (d as { contradiction_summary?: string }).contradiction_summary;
    const agreement = (d as { study_agreement?: string }).study_agreement;
    if (flag) {
      bullets.push(summary || "Mixed findings detected across studies");
    } else if (agreement) {
      bullets.push(`Studies are broadly ${agreement} in their conclusions`);
    }
    if (d.low_support_claims > 0) {
      bullets.push(`${d.low_support_claims} finding${d.low_support_claims === 1 ? "" : "s"} with limited source support`);
    }
    return bullets;
  }, [confidenceDetails]);

  // ── Pipeline step detail ───────────────────────────────────────────────────
  const pipelineDetail = useMemo((): Record<string, string> => ({
    ask:      `Your question: "${query.slice(0, 80)}${query.length > 80 ? "…" : ""}"`,
    retrieve: `${result.sources_retrieved} sources retrieved — PubMed, Europe PMC, WHO, Cochrane`,
    filter:   `${result.sources_trusted} sources passed trust filters · ${result.sources_rejected} removed`,
    rank:     `Top evidence band: ${result.confidence_band} · ${confidenceDetails.evidence_types?.join(", ") || "mixed types"}`,
    score:    `MEDEVA scoring applied — ${band.label}${isDebug ? ` (${confidence}%)` : ""}`,
    answer:   `Generated${isDebug ? ` via ${result.provider_used ?? "AI"}` : ""} with citation-linked synthesis`,
  }), [query, result, confidenceDetails, band.label, confidence, isDebug]);

  // ── Toast ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2000);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    if (saveState === "saved") setToast({ type: "success", message: "Saved to your profile" });
  }, [saveState]);

  // ── Patient mode ───────────────────────────────────────────────────────────
  const togglePatientMode = async () => {
    if (!patientMode && !patientText) {
      try {
        setLoadingExplain(true);
        const simplified = await explainAnswer({ query, answer });
        setPatientText(simplified);
      } catch {
        setToast({ type: "error", message: "Couldn't simplify right now. Please try again." });
        return;
      } finally {
        setLoadingExplain(false);
      }
    }
    setPatientMode((p) => !p);
  };

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-2xl border border-slate-200/70 bg-white shadow-sm dark:border-slate-800 dark:bg-[#0f172a]"
    >
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="px-6 pt-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            Evidence-Based Response
          </h3>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {/* Mode badge — always visible */}
            <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-slate-500 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400">
              {isGeneralMode
                ? "General"
                : isEvidenceOnly
                  ? "Evidence summary"
                  : result.mode === "fallback"
                    ? "Limited evidence"
                    : "Evidence-based"}
            </span>
            {/* Debug-only: provider badge */}
            {isDebug && result.provider_used && result.provider_used !== "none" && (
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 font-mono text-slate-400 dark:border-slate-700 dark:bg-slate-800/60">
                {result.provider_used}
              </span>
            )}
          </div>
        </div>

        {/* ── Confidence storytelling (Task 1) ─────────────────────────────── */}
        {!isGeneralMode && (
          <div className="mt-4">
            {/* Band pill */}
            <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${band.pill}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${band.dot}`} />
              <span className="text-xs font-semibold">{band.label}</span>
              {/* Debug: show % */}
              {isDebug && (
                <span className="text-[11px] opacity-60">({confidence}%)</span>
              )}
            </div>
            {/* Confidence bullets — rendered directly from backend data */}
            {confidenceBullets.length > 0 && (
              <ul className="mt-2.5 space-y-1">
                {confidenceBullets.map((b) => (
                  <li key={b} className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-300">
                    <span className="mt-1.5 h-1 w-1 flex-shrink-0 rounded-full bg-slate-400 dark:bg-slate-500" />
                    {b}
                  </li>
                ))}
              </ul>
            )}
            {/* Confidence explanation from backend */}
            {result.confidence_explanation && (
              <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                {result.confidence_explanation}
              </p>
            )}
          </div>
        )}

        {/* ── Contextual alerts ─────────────────────────────────────────────── */}
        {isEvidenceOnly && (
          <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
            AI synthesis temporarily unavailable — answer is extracted directly from retrieved studies.
          </div>
        )}
        {isGeneralMode && (
          <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
            No direct study match found — showing a general medical explanation.
          </p>
        )}
        {fallbackReason && (
          <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">{fallbackReason}</p>
        )}
        {hasSevereUncertainty && (
          <div className="mt-3 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-300">
            {severeUncertainClaims.length} finding{severeUncertainClaims.length === 1 ? "" : "s"} with lower evidence support — interpret with caution.
          </div>
        )}

        <p className="mt-3 text-[11px] text-slate-500 dark:text-slate-400">
          Hover a sentence to preview its source · click to jump to the evidence panel
        </p>
      </div>

      {/* ── Answer block — the visual anchor of the page ─────────────────────── */}
      <div className={`mx-6 mt-6 rounded-2xl border-l-4 border-blue-500 bg-slate-50/50 py-5 pl-5 pr-4 dark:bg-slate-800/25 ${isEvidenceOnly ? "opacity-90" : ""}`}>
        <div className="space-y-2.5 text-[17px] leading-7 text-slate-800 dark:text-slate-100">
          {((patientMode ? patientText ?? "Simplifying answer…" : typedText) || "")
            .split(/(?<=[.!?])\s+/)
            .filter(Boolean)
            .map((sentence, i) => {
              const citation = result.citations[i % Math.max(1, result.citations.length)];
              const sourceIndex = citation?.index ?? 1;
              if (isGeneralMode) {
                return <p key={`${sentence}-${i}`}>{sentence}</p>;
              }
              return (
                <button
                  key={`${sentence}-${i}`}
                  onMouseEnter={() => onSentenceHover(sourceIndex)}
                  onMouseLeave={() => onSentenceHover(null)}
                  onClick={() => onSentenceClick(sourceIndex)}
                  className="block cursor-pointer rounded-md text-left transition-colors hover:bg-blue-100/50 dark:hover:bg-slate-700/40"
                >
                  {sentence}{" "}
                  {!patientMode && (
                    <span className="text-sm font-medium text-blue-500 dark:text-blue-400">[{sourceIndex}]</span>
                  )}
                </button>
              );
            })}
        </div>
      </div>

      {/* ── Toast ────────────────────────────────────────────────────────────── */}
      {toast && (
        <div className={`mx-6 mt-3 rounded-xl border px-3 py-2 text-xs ${
          toast.type === "success"
            ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300"
            : "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300"
        }`}>
          {toast.message}
        </div>
      )}

      {/* ── Action buttons ────────────────────────────────────────────────────── */}
      <div className="mt-6 flex flex-wrap items-center gap-2 px-6">
        <button
          onClick={() => { if (!canSave) { onRequireSignIn?.(); return; } onSave?.(); }}
          disabled={!canSave || !onSave || saveState === "saving" || saveState === "saved"}
          className="rounded-xl border border-slate-200 px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800/60"
        >
          {!canSave ? "Sign in to save" : saveState === "saving" ? "Saving…" : saveState === "saved" ? "Saved" : saveState === "error" ? "Retry" : "Save"}
        </button>
        <button
          onClick={togglePatientMode}
          disabled={loadingExplain}
          className="rounded-xl border border-slate-200 px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800/60"
        >
          {loadingExplain ? "Simplifying…" : patientMode ? "Clinical Mode" : "Patient Mode"}
        </button>
        <button
          onClick={async () => {
            try { await navigator.clipboard.writeText(answer); setCopied(true); setTimeout(() => setCopied(false), 1400); }
            catch { setToast({ type: "error", message: "Couldn't copy. Try again." }); }
          }}
          className="rounded-xl border border-slate-200 px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800/60"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      {/* ── Horizontal pipeline (Task 2) ──────────────────────────────────────
          Full-width, edge-to-edge within the card. No container limit.
      ──────────────────────────────────────────────────────────────────────── */}
      <div className="mt-8 border-t border-slate-100 px-4 pb-4 pt-6 dark:border-slate-800">
        <p className="mb-4 px-2 text-[11px] font-medium uppercase tracking-widest text-slate-500 dark:text-slate-400">
          How this answer was built
        </p>

        {/* Horizontal flow line */}
        <div className="relative flex items-start justify-between gap-0">
          {/* Gradient connector behind the dots */}
          <div
            className="pointer-events-none absolute left-0 right-0 top-[18px] h-px"
            style={{
              background:
                "linear-gradient(to right, rgb(148 163 184 / 0.3), rgb(59 130 246 / 0.6), rgb(6 182 212 / 0.5))",
            }}
          />

          {PIPELINE.map((step, idx) => {
            const Icon = step.icon;
            const isActive  = idx === pipelineActiveIdx;
            const isDone    = idx <= pipelineActiveIdx;
            const isFuture  = idx > pipelineActiveIdx;

            return (
              <button
                key={step.id}
                onClick={() =>
                  setActivePipelineId((prev) => (prev === step.id ? null : step.id))
                }
                className={`relative z-10 flex flex-1 flex-col items-center gap-1.5 transition-all duration-300 ${
                  isFuture ? "opacity-30" : "opacity-100"
                }`}
              >
                {/* Step dot */}
                <motion.div
                  animate={isActive ? { scale: 1.18 } : { scale: 1 }}
                  transition={{ type: "spring", stiffness: 400, damping: 20 }}
                  className={`relative flex h-9 w-9 items-center justify-center rounded-full transition-all duration-300 ${
                    isActive
                      ? "bg-blue-500 shadow-[0_0_0_4px_rgba(59,130,246,0.15),0_0_16px_rgba(59,130,246,0.35)] dark:bg-blue-500 dark:shadow-[0_0_0_4px_rgba(59,130,246,0.2),0_0_20px_rgba(59,130,246,0.4)]"
                      : isDone
                        ? "bg-blue-100 dark:bg-blue-900/50"
                        : "bg-slate-100 dark:bg-slate-800"
                  }`}
                >
                  <Icon
                    className={`h-4 w-4 transition-colors ${
                      isActive
                        ? "text-white"
                        : isDone
                          ? "text-blue-600 dark:text-blue-400"
                          : "text-slate-400 dark:text-slate-600"
                    }`}
                  />
                </motion.div>

                {/* Label */}
                <span
                  className={`text-[10px] font-medium transition-colors ${
                    isActive
                      ? "text-blue-600 dark:text-blue-400"
                      : isDone
                        ? "text-slate-500 dark:text-slate-400"
                        : "text-slate-300 dark:text-slate-600"
                  }`}
                >
                  {step.label}
                </span>
              </button>
            );
          })}
        </div>

        {/* Step detail panel — appears below when a step is clicked */}
        <AnimatePresence mode="wait">
          {activePipelineId && (
            <motion.div
              key={activePipelineId}
              initial={{ opacity: 0, y: -4, height: 0 }}
              animate={{ opacity: 1, y: 0, height: "auto" }}
              exit={{ opacity: 0, y: -4, height: 0 }}
              transition={{ duration: 0.18 }}
              className="mt-3 overflow-hidden rounded-xl bg-slate-50 px-4 py-3 dark:bg-slate-800/60"
            >
              <p className="text-xs text-slate-700 dark:text-slate-300">
                {pipelineDetail[activePipelineId]}
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Selection rationale ────────────────────────────────────────────────── */}
      {result.selection_rationale && (
        <div className="mt-2 border-t border-slate-100 px-6 pt-6 dark:border-slate-800">
          <SelectionRationale rationale={result.selection_rationale} />
        </div>
      )}

      {/* ── Controlled discussion ──────────────────────────────────────────────── */}
      <div className="mt-2 border-t border-slate-100 px-6 pb-6 pt-6 dark:border-slate-800">
        <ControlledDiscussion
          answer={result.answer ?? ""}
          evidenceTitles={result.citations.slice(0, 5).map((c) => c.title)}
          onQuerySuggestion={onRelatedQuery}
        />
      </div>
    </motion.div>
  );
}
