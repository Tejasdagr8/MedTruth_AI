"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useMemo, useState } from "react";
import ExecutionTracePanel, { ToolStep } from "@/components/llm-lab/ExecutionTracePanel";
import LabCommandInput from "@/components/llm-lab/LabCommandInput";
import LabTimeline from "@/components/llm-lab/LabTimeline";
import { FlaskConical, Search, Sparkles, Workflow } from "lucide-react";

interface LabResult {
  answer: string;
  steps: ToolStep[];
  tools_used: string[];
  total_duration_ms: number;
}

// ── Config ────────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL!;

const TOOL_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  planner:       { bg: "bg-amber-500/15",   text: "text-amber-300",   label: "Planner"        },
  pubmed_search: { bg: "bg-blue-500/15",    text: "text-blue-300",    label: "PubMed Search"  },
  analysis:      { bg: "bg-purple-500/15",  text: "text-purple-300",  label: "Analysis"       },
};

const LOADING_MESSAGES = [
  "Planning steps…",
  "Searching PubMed…",
  "Analyzing results…",
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function LLMLabPage() {
  const [query, setQuery]             = useState("");
  const [loading, setLoading]         = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [result, setResult]           = useState<LabResult | null>(null);
  const [error, setError]             = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);

  const activeTimelineStep = useMemo(() => {
    if (loading) return Math.min(loadingStep, 3);
    if (result) return 3;
    return 0;
  }, [loading, loadingStep, result]);

  const handleSubmit = async () => {
    const q = query.trim();
    if (!q || loading) return;

    setLoading(true);
    setResult(null);
    setError(null);
    setLoadingStep(0);
    setShowPreview(false);

    // Animate loading messages while the request is in flight
    const msgTimer = setInterval(
      () => setLoadingStep((s) => (s + 1) % LOADING_MESSAGES.length),
      1400
    );

    try {
      const res = await fetch(`${API_BASE}/llm-lab/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      setResult(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      clearInterval(msgTimer);
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#090b16] text-slate-100">
      {/* ── Nav bar ──────────────────────────────────────────────────────── */}
      <div className="sticky top-0 z-20 border-b border-white/[0.07] bg-[#090b16]/90 backdrop-blur-sm">
        <div className="flex items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <span className="rounded-md bg-purple-500/20 px-2 py-0.5 text-[11px] font-bold uppercase tracking-widest text-purple-400 ring-1 ring-inset ring-purple-500/30">
              Experimental
            </span>
            <span className="text-sm font-semibold text-slate-200">MCP Interface</span>
          </div>
          <Link
            href="/"
            className="text-xs text-slate-500 transition-colors hover:text-slate-300"
          >
            ← Back to MedTruth AI
          </Link>
        </div>
      </div>

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight text-white">🧪 LLM Lab</h1>
          <p className="text-sm text-slate-300">Tool-Orchestrated AI Reasoning Engine</p>
          <p className="text-xs uppercase tracking-[0.2em] text-violet-300/85">Plan → Execute → Synthesize</p>
        </div>

        {/* ── Warning banner ────────────────────────────────────────────── */}
        <div className="rounded-xl border border-amber-500/25 bg-amber-500/[0.08] px-4 py-3">
          <p className="text-xs leading-relaxed text-amber-300/90">
            <span className="font-semibold">⚠ Experimental mode.</span>{" "}
            This module uses free-form LLM + PubMed tool orchestration and does{" "}
            <em>not</em> apply evidence-quality filters, MEDEVA scoring, or the
            hallucination safeguards used in the main MedTruth pipeline. Results
            may be incomplete or inaccurate.{" "}
            <strong>Do not use for clinical decisions.</strong>
          </p>
        </div>

        <div className="rounded-2xl bg-[#11162a]/70 p-5">
          <p className="mb-3 text-sm font-medium text-slate-200">What this system can do</p>
          <div className="grid gap-2 text-sm text-slate-300 md:grid-cols-2">
            <p className="flex items-center gap-2"><Search className="h-4 w-4 text-blue-300" />Search PubMed in real-time</p>
            <p className="flex items-center gap-2"><Workflow className="h-4 w-4 text-violet-300" />Perform multi-step reasoning</p>
            <p className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-indigo-300" />Synthesize research findings</p>
            <p className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-cyan-300" />Explore hypotheses beyond strict evidence filtering</p>
          </div>
        </div>

        <LabCommandInput
          query={query}
          loading={loading}
          onChange={(value) => {
            setQuery(value);
            setShowPreview(value.trim().length > 0);
          }}
          onSubmit={handleSubmit}
        />

        {showPreview && !loading && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-xl border border-violet-400/30 bg-violet-500/10 px-4 py-3 text-sm text-violet-100"
          >
            <p className="mb-1 font-medium">This query may:</p>
            <p>• search PubMed</p>
            <p>• analyze studies</p>
            <p>• generate synthesis</p>
          </motion.div>
        )}

        <LabTimeline activeIndex={activeTimelineStep} />

        {/* ── Error ─────────────────────────────────────────────────────── */}
        {error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="rounded-xl border border-rose-500/25 bg-rose-500/[0.08] px-4 py-3 text-sm text-rose-300"
          >
            {error}
          </motion.div>
        )}

        {/* ── Loading trace ─────────────────────────────────────────────── */}
        {loading && (
          <div className="rounded-xl border border-white/10 bg-[#111427] p-4">
            <AnimatePresence mode="wait">
              <motion.p
                key={LOADING_MESSAGES[loadingStep]}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="text-sm text-slate-300"
              >
                {LOADING_MESSAGES[loadingStep]}
              </motion.p>
            </AnimatePresence>
          </div>
        )}

        {/* ── Result ────────────────────────────────────────────────────── */}
        {result && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]"
          >
            <div className="space-y-4">
              <div className="rounded-xl border border-white/[0.08] bg-white/[0.04] p-6">
                <div className="mb-4 flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">
                    Final Answer
                  </span>
                  <span className="text-[10px] text-slate-700">
                    {result.total_duration_ms.toFixed(0)} ms total
                  </span>
                  {result.tools_used.map((t) => {
                    const style = TOOL_STYLE[t] ?? { bg: "bg-slate-800", text: "text-slate-400", label: t };
                    return (
                      <span
                        key={t}
                        className={`rounded-full px-2.5 py-0.5 text-[10px] font-medium ${style.bg} ${style.text}`}
                      >
                        {style.label}
                      </span>
                    );
                  })}
                </div>

                <div className="space-y-3 text-[15px] leading-7 text-slate-200">
                  {result.answer
                    .split(/\n+/)
                    .filter(Boolean)
                    .map((para, i) => (
                      <p key={i}>{para}</p>
                    ))}
                </div>
              </div>

              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
                Experimental output — not clinically validated
              </div>
            </div>

            <ExecutionTracePanel steps={result.steps} />

            {/* Footer disclaimer */}
            <p className="lg:col-span-2 pb-4 text-[11px] text-slate-700">
              ⚠ This response was generated without evidence-quality filters.
              For evidence-based answers, use{" "}
              <Link href="/" className="text-purple-500 hover:text-purple-400 underline">
                MedTruth AI
              </Link>
              .
            </p>
          </motion.div>
        )}
      </div>
    </div>
  );
}
