"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Database,
  Gauge,
  Filter,
  FlaskConical,
  Loader2,
  LucideIcon,
  Search,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getModesHealth, getProvidersHealth, ModesHealth, ProvidersHealth } from "@/lib/api";
import { ArchitectureDiagram } from "@/components/ArchitectureDiagram";

const PIPELINE_STEPS = [
  {
    id: "query",
    short: "Query",
    icon: Sparkles,
    title: "Understand your question",
    description: "We detect the medical intent and route your question to the right evidence path.",
  },
  {
    id: "search",
    short: "Search",
    icon: Search,
    title: "Search trusted sources",
    description: "We retrieve candidate studies from PubMed, EuropePMC, WHO, and Cochrane concurrently.",
  },
  {
    id: "filter",
    short: "Filter",
    icon: Filter,
    title: "Filter weak evidence",
    description: "Low-quality, duplicate, and weakly relevant studies are removed before anything reaches the LLM.",
  },
  {
    id: "rank",
    short: "Rank",
    icon: BarChart3,
    title: "Rank strongest studies",
    description: "MEDEVA scoring weighs study design, journal impact, recency, citation count, and sample size.",
  },
  {
    id: "score",
    short: "Score",
    icon: FlaskConical,
    title: "Score confidence",
    description: "We combine support, contradiction, and quality signals into a confidence explanation.",
  },
  {
    id: "answer",
    short: "Answer",
    icon: Database,
    title: "Generate grounded answer",
    description: "The response is generated with visible citations and explicit mode transparency.",
  },
];

const TRUST_POINTS = [
  "Only real studies from trusted sources are used",
  "Evidence is filtered and ranked before answering",
  "Confidence is computed, not guessed",
  "Every answer includes visible citations you can verify",
];

const JOURNEY_STEPS = [
  { icon: "🧑", text: "You ask: \"Does aspirin reduce mortality in acute MI?\"" },
  { icon: "🔍", text: "We search trusted medical sources and collect candidate studies." },
  { icon: "🧹", text: "Weak, duplicate, or low-relevance studies are filtered out." },
  { icon: "🏆", text: "The strongest studies are prioritized by MEDEVA score." },
  { icon: "📊", text: "Confidence is computed from evidence quality and consistency." },
  { icon: "🧠", text: "You get a grounded answer with explicit transparency." },
];

const FAILURE_CASES = [
  {
    icon: TriangleAlert,
    title: "No strong direct studies found",
    detail: "We switch to general explanation mode and clearly label it.",
  },
  {
    icon: Gauge,
    title: "AI provider becomes unavailable",
    detail: "We still return evidence summaries instead of hallucinating details.",
  },
  {
    icon: ShieldCheck,
    title: "Studies disagree with each other",
    detail: "Confidence is lowered automatically and uncertainty is surfaced.",
  },
];

const BEFORE_BULLETS = [
  "Generates text from training patterns — no retrieval",
  "Cannot cite or verify specific studies",
  "Sounds confident even when evidence is absent",
  "No degradation path — gives an answer regardless",
  "Confidence is opaque, never explained",
];

const AFTER_BULLETS = [
  "Retrieves real peer-reviewed studies for every question",
  "Filters weak and irrelevant studies before answering",
  "Computes confidence from measurable quality signals",
  "Degrades gracefully — clearly labels when evidence is absent",
  "Shows citations, study types, and confidence breakdown",
];

const EXAMPLE_BREAKDOWN = [
  { label: "Studies found", value: "42", accent: "text-slate-900 dark:text-white" },
  { label: "High-quality used", value: "8", accent: "text-emerald-700 dark:text-emerald-300" },
  { label: "Excluded", value: "34", accent: "text-rose-600 dark:text-rose-300" },
  { label: "Confidence", value: "HIGH", accent: "text-blue-700 dark:text-blue-300" },
];


const WHY_ARCHITECTURE_MATTERS = [
  "Prevents hallucination by grounding answers to retrieved evidence.",
  "Handles provider failures gracefully with explicit degraded modes.",
  "Always shows evidence or clearly explains when direct evidence is absent.",
  "Computes confidence from measurable signals, not vague model certainty.",
];

function topProviderSummary(providersHealth: ProvidersHealth | null): { name: string; successRate: number } {
  if (!providersHealth) return { name: "N/A", successRate: 0 };
  const entries = Object.entries(providersHealth.providers);
  if (!entries.length) return { name: "N/A", successRate: 0 };

  const ranked = entries
    .map(([name, stats]) => {
      const total = stats.success + stats.failure;
      const successRate = total === 0 ? 0 : (stats.success / total) * 100;
      return { name, successRate, total };
    })
    .sort((a, b) => b.successRate - a.successRate || b.total - a.total);

  return { name: ranked[0].name, successRate: Math.round(ranked[0].successRate) };
}

function buildLiveMetrics(modesHealth: ModesHealth | null, providersHealth: ProvidersHealth | null) {
  if (!modesHealth) return [];
  const topProvider = topProviderSummary(providersHealth);
  const cacheRate =
    modesHealth.requests > 0 ? Math.round((modesHealth.cache_hits / modesHealth.requests) * 100) : 0;

  return [
    { label: "Queries observed", value: String(modesHealth.requests) },
    { label: "Cache hit rate", value: `${cacheRate}%` },
    { label: "Evidence-based responses", value: `${modesHealth.mode_percentages.evidence_based}%` },
    { label: "General explanation responses", value: `${modesHealth.mode_percentages.general_explanation}%` },
    { label: "Fallback responses", value: `${modesHealth.mode_percentages.fallback}%` },
    { label: "Top provider reliability", value: `${topProvider.name} (${topProvider.successRate}%)` },
  ];
}

export default function HowItWorksPage() {
  const [showTechnical, setShowTechnical] = useState(false);
  const [progress, setProgress] = useState(0);
  const [hoveredStep, setHoveredStep] = useState<string | null>(null);
  const [modesHealth, setModesHealth] = useState<ModesHealth | null>(null);
  const [providersHealth, setProvidersHealth] = useState<ProvidersHealth | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(true);
  const [metricsError, setMetricsError] = useState<string | null>(null);

  useEffect(() => {
    const id = window.setInterval(() => {
      setProgress((prev) => (prev + 1) % PIPELINE_STEPS.length);
    }, 1300);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    let mounted = true;
    const loadHealth = async () => {
      try {
        const [modes, providers] = await Promise.all([getModesHealth(), getProvidersHealth()]);
        if (!mounted) return;
        setModesHealth(modes);
        setProvidersHealth(providers);
        setMetricsError(null);
      } catch {
        if (!mounted) return;
        setMetricsError("Live metrics unavailable right now.");
      } finally {
        if (mounted) setMetricsLoading(false);
      }
    };

    loadHealth();
    const poll = window.setInterval(loadHealth, 12000);
    return () => {
      mounted = false;
      window.clearInterval(poll);
    };
  }, []);

  const activeStepId = hoveredStep ?? PIPELINE_STEPS[progress].id;
  const activeStep = useMemo(
    () => PIPELINE_STEPS.find((step) => step.id === activeStepId) ?? PIPELINE_STEPS[0],
    [activeStepId],
  );
  const liveMetrics = useMemo(() => buildLiveMetrics(modesHealth, providersHealth), [modesHealth, providersHealth]);
  const confidentModes = modesHealth?.mode_percentages.evidence_based ?? 0;
  const filteredModes = modesHealth?.error_signals.retrieval_empty_count ?? 0;

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 py-8 text-slate-900 dark:from-[#0b1220] dark:to-[#0a0f1c] dark:text-slate-100">
      <div className="space-y-8">
        <div className="w-full px-0">
        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-[#111827]">
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-300">Core Product Feature</p>
          <h1 className="mt-2 text-3xl font-bold">How MedTruth Works</h1>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            This system does NOT guess — it uses real medical research.
          </p>
          <div className="mt-4">
            <Link
              href="/"
              className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              Back to Ask
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </header>
        </div>

        {/* ─── Animated pipeline ─────────────────────────────────────── */}
        <div className="w-full px-0">
        <section className="w-full rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-[#111827]">
          <h2 className="text-xl font-semibold">How your question flows through MedTruth</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Your question travels through a visible evidence path before any answer is shown.
            Click any step or watch it advance.
          </p>

          <div className="relative mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/50">
            {/* gradient track */}
            <div className="absolute left-5 right-5 top-1/2 hidden h-[2px] -translate-y-1/2 bg-gradient-to-r from-blue-400 via-cyan-400 to-violet-400 opacity-80 md:block" />
            <div className="grid gap-6 md:grid-cols-6">
              {PIPELINE_STEPS.map((step, index) => {
                const Icon = step.icon;
                const isProgressed = index <= progress;
                const isActive = step.id === activeStepId || index === progress;
                return (
                  <motion.button
                    key={step.id}
                    type="button"
                    onMouseEnter={() => setHoveredStep(step.id)}
                    onMouseLeave={() => setHoveredStep(null)}
                    onClick={() => setProgress(index)}
                    className={`relative rounded-xl p-3 text-left transition-all duration-300 ${
                      isActive
                        ? "bg-blue-500/10 scale-105 ring-2 ring-blue-400/40 shadow-lg"
                        : isProgressed
                          ? "opacity-80"
                          : "opacity-40"
                    }`}
                    initial={{ opacity: 0.5, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.22, delay: index * 0.03 }}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.97 }}
                  >
                    {isActive && (
                      <motion.div
                        layoutId="pipeline-glow"
                        className="absolute inset-0 rounded-xl bg-blue-400/10 dark:bg-blue-400/15"
                        transition={{ type: "spring", stiffness: 200, damping: 28 }}
                      />
                    )}
                    <div className="flex items-center justify-between gap-2">
                      <div className={`inline-flex rounded-lg p-1.5 ${isActive ? "bg-blue-500/20 text-blue-400" : "bg-white/5 text-slate-400"}`}>
                        <Icon className="h-3.5 w-3.5" />
                      </div>
                    </div>
                    <p className={`mt-2 text-xs font-medium ${isActive ? "text-blue-400" : "text-slate-500"}`}>
                      {step.short}
                    </p>
                  </motion.button>
                );
              })}
            </div>
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={activeStep.id}
              className="mt-4 rounded-xl border border-blue-200 bg-blue-50 p-4 dark:border-blue-700/40 dark:bg-blue-900/20"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18 }}
            >
              <p className="text-sm font-semibold text-blue-900 dark:text-blue-100">{activeStep.title}</p>
              <p className="mt-1 text-sm text-blue-800/80 dark:text-blue-200/80">{activeStep.description}</p>
            </motion.div>
          </AnimatePresence>
        </section>
        </div>

        <div className="w-full space-y-8 px-0">
        {/* ─── Journey steps ──────────────────────────────────────────── */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-[#111827]">
          <h2 className="text-xl font-semibold">What happens to YOUR question</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            This is the path your question takes from ask to answer.
          </p>
          <div className="mt-4 space-y-2">
            {JOURNEY_STEPS.map((step, idx) => (
              <motion.div
                key={step.text}
                className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800/60"
                initial={{ opacity: 0, x: -10 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, amount: 0.5 }}
                transition={{ delay: idx * 0.06, duration: 0.22 }}
              >
                <span className="mr-2">{step.icon}</span>
                {step.text}
              </motion.div>
            ))}
          </div>
        </section>
        </div>

        {/* ─── Architecture diagram ───────────────────────────────────── */}
        <div className="w-full px-0">
        <section className="w-full rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-[#111827]">
          <h2 className="text-xl font-semibold">System architecture</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Three distinct layers — click any node to see what it does. Data flows live between layers.
          </p>
          <div className="mt-5">
            <ArchitectureDiagram />
          </div>
        </section>
        </div>

        <div className="w-full space-y-8 px-0">
        {/* ─── Before vs After ────────────────────────────────────────── */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-[#111827]">
          <h2 className="text-xl font-semibold">Why this is different from typical AI</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 dark:border-rose-700/50 dark:bg-rose-900/20">
              <p className="flex items-center gap-2 text-sm font-semibold text-rose-800 dark:text-rose-300">
                <XCircle className="h-4 w-4 shrink-0" />
                Typical AI behavior
              </p>
              <ul className="mt-3 space-y-2">
                {BEFORE_BULLETS.map((b) => (
                  <li key={b} className="flex items-start gap-2 text-sm text-rose-700 dark:text-rose-300">
                    <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-60" />
                    {b}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-700/50 dark:bg-emerald-900/20">
              <p className="flex items-center gap-2 text-sm font-semibold text-emerald-800 dark:text-emerald-300">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                MedTruth behavior
              </p>
              <ul className="mt-3 space-y-2">
                {AFTER_BULLETS.map((b) => (
                  <li key={b} className="flex items-start gap-2 text-sm text-emerald-700 dark:text-emerald-300">
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-70" />
                    {b}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* ─── Live metrics ───────────────────────────────────────────── */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-[#111827]">
          <h2 className="text-xl font-semibold">Live system proof</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            These numbers are pulled from backend observability endpoints, not hardcoded.
          </p>
          {metricsLoading && (
            <div className="mt-4 inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading live metrics...
            </div>
          )}
          {metricsError && !metricsLoading && (
            <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-300">
              {metricsError}
            </p>
          )}
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {liveMetrics.map((metric, idx) => (
              <motion.div
                key={metric.label}
                className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/60"
                initial={{ opacity: 0, y: 8 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.4 }}
                transition={{ delay: idx * 0.04, duration: 0.2 }}
                whileHover={{ scale: 1.03 }}
              >
                <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{metric.label}</p>
                <p className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-100">{metric.value}</p>
              </motion.div>
            ))}
          </div>
        </section>

        {/* ─── Failure transparency ───────────────────────────────────── */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-[#111827]">
          <h2 className="text-xl font-semibold">Even when things go wrong, we show it</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Transparency is built into every degraded path, not hidden behind generic errors.
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {FAILURE_CASES.map((item, idx) => {
              const Icon: LucideIcon = item.icon;
              return (
                <motion.div
                  key={item.title}
                  className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/60"
                  initial={{ opacity: 0, y: 8 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.4 }}
                  transition={{ delay: idx * 0.05, duration: 0.2 }}
                  whileHover={{ scale: 1.03 }}
                >
                  <div className="inline-flex rounded-lg bg-amber-50 p-2 dark:bg-amber-500/10">
                    <Icon className="h-4 w-4 text-amber-600 dark:text-amber-300" />
                  </div>
                  <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{item.title}</p>
                  <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{item.detail}</p>
                </motion.div>
              );
            })}
          </div>
          <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900 dark:border-blue-700/40 dark:bg-blue-900/20 dark:text-blue-200">
            Current live signal: {confidentModes}% evidence-based responses, {filteredModes} retrieval-empty events observed.
          </div>
        </section>

        {/* ─── Real example ───────────────────────────────────────────── */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-[#111827]">
          <h2 className="text-xl font-semibold">Real example</h2>
          <div className="mt-3 space-y-3 text-sm">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
              <p className="font-medium">Query</p>
              <p className="mt-1 text-slate-600 dark:text-slate-300">
                Does aspirin reduce mortality in acute myocardial infarction?
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
              <p className="font-medium">System path</p>
              <p className="mt-1 text-slate-600 dark:text-slate-300">
                Search trusted studies → Filter weak studies → Rank strongest evidence → Score reliability → Generate answer
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
              <p className="font-medium">What happened internally</p>
              <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {EXAMPLE_BREAKDOWN.map((item) => (
                  <motion.div
                    key={item.label}
                    className="rounded-lg border border-slate-200 bg-white p-2.5 text-center dark:border-slate-600 dark:bg-slate-700"
                    whileHover={{ scale: 1.05 }}
                  >
                    <p className={`text-lg font-bold ${item.accent}`}>{item.value}</p>
                    <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{item.label}</p>
                  </motion.div>
                ))}
              </div>
            </div>
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 dark:border-emerald-700/50 dark:bg-emerald-900/20">
              <p className="font-medium text-emerald-800 dark:text-emerald-300">Bottom line</p>
              <p className="mt-1 text-emerald-700 dark:text-emerald-300">
                Aspirin reduces mortality in acute MI based on strong clinical evidence and guideline-aligned data.
              </p>
            </div>
          </div>
        </section>

        {/* ─── Trust ──────────────────────────────────────────────────── */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-[#111827]">
          <h2 className="text-xl font-semibold">Why you can trust this approach</h2>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {TRUST_POINTS.map((point) => (
              <motion.div
                key={point}
                className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm dark:border-slate-700 dark:bg-slate-800"
                whileHover={{ scale: 1.02 }}
              >
                <div className="flex items-start gap-2">
                  <ShieldCheck className="mt-0.5 h-4 w-4 text-blue-600 dark:text-blue-300" />
                  <span>{point}</span>
                </div>
              </motion.div>
            ))}
          </div>
          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/60">
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Why this architecture matters</p>
            <div className="mt-2 space-y-1.5 text-sm text-slate-700 dark:text-slate-300">
              {WHY_ARCHITECTURE_MATTERS.map((item) => (
                <p key={item}>• {item}</p>
              ))}
            </div>
          </div>
        </section>

        {/* ─── Technical details ──────────────────────────────────────── */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-[#111827]">
          <button
            onClick={() => setShowTechnical((prev) => !prev)}
            className="w-full text-left text-sm font-semibold text-slate-900 dark:text-slate-100"
          >
            ⚙️ Technical details {showTechnical ? "▲" : "▼"}
          </button>
          <AnimatePresence initial={false}>
            {showTechnical && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.22 }}
                className="mt-3 space-y-2 overflow-hidden text-sm text-slate-700 dark:text-slate-300"
              >
                <p>• Retrieval from vetted medical databases with source validation gate.</p>
                <p>• MEDEVA scoring weighs study design, journal impact factor, recency, citation count, and sample size.</p>
                <p>• LLM fallback order: Groq → Gemini → Anthropic. Retries only on transient errors (timeout, 429, 5xx).</p>
                <p>• Stickiness biases toward the last successful provider unless it accumulates failures.</p>
                <p>• Entailment checks verify generated claims against retrieved source documents.</p>
                <p>• Response generation is grounded to retrieved evidence and linked citations.</p>
              </motion.div>
            )}
          </AnimatePresence>
        </section>
        </div>
      </div>
    </main>
  );
}
