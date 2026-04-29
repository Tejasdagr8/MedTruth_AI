"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  BarChart3,
  ChevronDown,
  Database,
  Filter,
  Gauge,
  Network,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  Waypoints,
  Zap,
} from "lucide-react";
import { ComponentType, useEffect, useState } from "react";

type IconComponent = ComponentType<{ className?: string }>;

interface NodeDef {
  readonly id: string;
  readonly label: string;
  readonly sublabel: string;
  readonly icon: IconComponent;
}

interface LayerDef {
  readonly id: string;
  readonly label: string;
  readonly labelColor: string;
  readonly borderColor: string;
  readonly bgColor: string;
  readonly nodes: readonly NodeDef[];
}

const LAYERS: LayerDef[] = [
  {
    id: "interface",
    label: "Layer 1 — Frontend Interface",
    labelColor: "text-blue-600 dark:text-blue-400",
    borderColor: "border-blue-200 dark:border-blue-800/50",
    bgColor: "bg-blue-50/60 dark:bg-blue-900/10",
    nodes: [
      { id: "user",     label: "User Query",   sublabel: "natural language",       icon: Sparkles },
      { id: "frontend", label: "Next.js",       sublabel: "trust signals + modes",  icon: Network  },
      { id: "api",      label: "API Layer",     sublabel: "/api/v1/query",          icon: Server   },
    ],
  },
  {
    id: "engine",
    label: "Layer 2 — Core Engine",
    labelColor: "text-violet-600 dark:text-violet-400",
    borderColor: "border-violet-200 dark:border-violet-800/50",
    bgColor: "bg-violet-50/60 dark:bg-violet-900/10",
    nodes: [
      { id: "orchestrator", label: "Orchestrator",   sublabel: "query.py",              icon: Waypoints },
      { id: "retrieval",    label: "Retrieval",      sublabel: "PubMed + EuropePMC",     icon: Search    },
      { id: "ranking",      label: "Filter + MEDEVA",sublabel: "dedupe + score",          icon: BarChart3 },
      { id: "decision",     label: "Decision Engine",sublabel: "mode selection",          icon: Gauge     },
    ],
  },
  {
    id: "ai",
    label: "Layer 3 — AI + Safety",
    labelColor: "text-emerald-600 dark:text-emerald-400",
    borderColor: "border-emerald-200 dark:border-emerald-800/50",
    bgColor: "bg-emerald-50/60 dark:bg-emerald-900/10",
    nodes: [
      { id: "llm",      label: "LLM Fallback",    sublabel: "Groq → Gemini → Anthropic", icon: Database   },
      { id: "safety",   label: "Safety + Scoring",sublabel: "entailment + confidence",   icon: ShieldCheck },
      { id: "response", label: "Response",         sublabel: "citations + mode",          icon: Zap        },
    ],
  },
];

// gradient and packet colour for each inter-layer connector (index = top layer index)
const CONNECTOR_GRADIENT = [
  "from-blue-400 to-violet-400",
  "from-violet-400 to-emerald-400",
] as const;

const CONNECTOR_PACKET = [
  "bg-violet-400 shadow-[0_0_10px_4px_rgba(139,92,246,0.75)]",
  "bg-emerald-400 shadow-[0_0_10px_4px_rgba(16,185,129,0.75)]",
] as const;

const NODE_DETAILS: Record<string, { title: string; content: string; bullets: string[] }> = {
  user: {
    title: "User Query",
    content:
      "Questions start as plain natural language. They are validated (5–500 chars), sanitised, and structured before entering the pipeline.",
    bullets: [
      "Optional email header enables per-user query history.",
      "Vague queries get an automatic expansion pass to improve recall.",
    ],
  },
  frontend: {
    title: "Next.js Frontend",
    content:
      "The frontend never renders a bare AI response. Every answer arrives with a mode badge, confidence band, and evidence metadata.",
    bullets: [
      "Renders evidence_based, evidence_only, general_explanation, and fallback modes with distinct UI.",
      "Shows MEDEVA score breakdowns, source counts, and contradiction alerts inline.",
    ],
  },
  api: {
    title: "API Layer — /api/v1/query",
    content:
      "A FastAPI endpoint that receives a structured query payload and returns a deterministic response schema with full trust metadata.",
    bullets: [
      "Exposes /health/modes and /health/providers for live observability.",
      "Response always includes: mode, confidence, provider_attempts, risk_flags, citations.",
    ],
  },
  orchestrator: {
    title: "Query Orchestrator (query.py)",
    content:
      "Coordinates retrieval fan-out, ranking, mode selection, risk flagging, and final response assembly.",
    bullets: [
      "Mode stabilisation cache (60 s TTL) prevents mode flapping on repeat queries.",
      "Domain classifier routes queries to relevant evidence sub-filters.",
    ],
  },
  retrieval: {
    title: "Retrieval Layer",
    content:
      "Concurrent fan-out across PubMed, EuropePMC, WHO, and Cochrane. All four sources queried in parallel via asyncio.gather.",
    bullets: [
      "Query expansion adds mechanism / safety / efficacy terms for broad queries.",
      "Vector store searched for cached documents in the same pass.",
    ],
  },
  ranking: {
    title: "Filtering + MEDEVA Ranking",
    content:
      "Candidates are deduplicated, filtered by source trust and clinical intent, then scored and sorted by MEDEVA.",
    bullets: [
      "MEDEVA weights: evidence level 40%, impact factor 20%, recency 15%, citations 15%, sample size 10%.",
      "Falls back to pre-filtered pool if quality gates remove all candidates.",
    ],
  },
  decision: {
    title: "Decision Engine (Core Differentiator)",
    content:
      "Explicitly selects a response mode based on evidence availability and provider behaviour — not a best-effort LLM call.",
    bullets: [
      "Strong evidence → evidence_based mode.",
      "Evidence present, provider fails → evidence_only mode.",
      "No strong direct evidence → general_explanation mode.",
      "Full failure path → safe fallback mode.",
    ],
  },
  llm: {
    title: "LLM Fallback Layer",
    content:
      "Multi-provider generation with smart retry, stickiness, and transient-error-only retry gating.",
    bullets: [
      "Provider order: Groq (fastest/cheapest) → Gemini → Anthropic.",
      "Retries only on transient errors (timeout, 429, 5xx) — skips auth failures immediately.",
      "Stickiness biases toward the last successful provider unless failure count ≥ 3.",
    ],
  },
  safety: {
    title: "Safety + Scoring",
    content:
      "Generated outputs are checked for support against source documents before confidence is exposed.",
    bullets: [
      "Entailment scores each claim against retrieved evidence.",
      "Study contradictions are detected and surfaced in the response.",
      "Final confidence is computed from evidence signals, not claimed by the model.",
    ],
  },
  response: {
    title: "Response Delivery",
    content:
      "The final payload includes the answer, all trust metadata, and everything the frontend needs for transparent rendering.",
    bullets: [
      "Includes mode, confidence_band, confidence_details, provider_attempts, risk_flags.",
      "No generic error messages — every degraded path carries a specific label and reason.",
    ],
  },
};

// ─── Sub-components ────────────────────────────────────────────────────────────

function VerticalConnector({
  gradient,
  packetColor,
  isActive,
}: {
  gradient: string;
  packetColor: string;
  isActive: boolean;
}) {
  return (
    <div className="flex justify-center py-0.5">
      <div className="relative flex h-10 w-0.5 items-start justify-center">
        {/* gradient line */}
        <div className={`h-full w-full rounded-full bg-gradient-to-b ${gradient} opacity-50`} />
        {/* chevron head */}
        <ChevronDown className="absolute -bottom-1.5 -left-[5px] h-3 w-3 text-slate-400 dark:text-slate-500" />
        {/* animated data packet */}
        <AnimatePresence>
          {isActive && (
            <motion.div
              key="packet"
              className={`absolute -left-[3px] h-2 w-2 rounded-full ${packetColor}`}
              initial={{ top: 0, opacity: 0 }}
              animate={{ top: "calc(100% - 8px)", opacity: [0, 1, 1, 0] }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.85, ease: "easeInOut" }}
            />
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function ArchNode({
  node,
  isSelected,
  isLayerActive,
  onClick,
}: {
  node: NodeDef;
  isSelected: boolean;
  isLayerActive: boolean;
  onClick: () => void;
}) {
  const Icon = node.icon;
  return (
    <motion.button
      type="button"
      onClick={onClick}
      className={`relative flex flex-col items-start rounded-xl border px-3 py-2.5 text-left transition-colors ${
        isSelected
          ? "border-blue-400 bg-blue-50 shadow-[0_0_0_2px_rgba(59,130,246,0.25),0_8px_20px_rgba(15,23,42,0.08)] dark:border-blue-400/60 dark:bg-blue-500/15"
          : isLayerActive
            ? "border-slate-300 bg-white shadow-sm dark:border-slate-600 dark:bg-slate-800/80"
            : "border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800"
      }`}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.96 }}
    >
      {isSelected && (
        <motion.div
          className="absolute inset-0 rounded-xl bg-blue-400/10 dark:bg-blue-400/15"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        />
      )}
      <div
        className={`relative inline-flex rounded-lg p-1.5 ${
          isSelected ? "bg-blue-100 dark:bg-blue-500/30" : "bg-slate-100 dark:bg-slate-700"
        }`}
      >
        <Icon
          className={`h-3.5 w-3.5 ${
            isSelected ? "text-blue-600 dark:text-blue-300" : "text-slate-600 dark:text-slate-300"
          }`}
        />
      </div>
      <p
        className={`relative mt-1.5 text-xs font-semibold leading-tight ${
          isSelected ? "text-blue-800 dark:text-blue-200" : "text-slate-800 dark:text-slate-100"
        }`}
      >
        {node.label}
      </p>
      <p className="relative mt-0.5 text-xs leading-tight text-slate-500 dark:text-slate-400">
        {node.sublabel}
      </p>
    </motion.button>
  );
}

// ─── Main export ───────────────────────────────────────────────────────────────

export function ArchitectureDiagram() {
  const [selectedNode, setSelectedNode] = useState<string>("decision");
  // cycles between 0 and 1 — which inter-layer connector carries the live packet
  const [flowStep, setFlowStep] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => {
      setFlowStep((prev) => (prev + 1) % 2);
    }, 1800);
    return () => window.clearInterval(id);
  }, []);

  // both layers adjacent to the active connector are considered "active"
  const activeLayerSet = new Set([flowStep, flowStep + 1]);

  const detail = NODE_DETAILS[selectedNode];

  return (
    <div className="space-y-1">
      {/* ── Layered rows ─────────────────────────────────────── */}
      {LAYERS.map((layer, layerIdx) => {
        const isLayerActive = activeLayerSet.has(layerIdx);
        return (
          <div key={layer.id}>
            <motion.div
              className={`rounded-2xl border p-3 transition-shadow ${layer.borderColor} ${layer.bgColor}`}
              animate={
                isLayerActive
                  ? { boxShadow: "0 0 0 1px rgba(99,102,241,0.08), 0 6px 20px rgba(15,23,42,0.07)" }
                  : { boxShadow: "none" }
              }
              transition={{ duration: 0.35 }}
            >
              <p className={`mb-2.5 text-xs font-bold uppercase tracking-wider ${layer.labelColor}`}>
                {layer.label}
              </p>

              <div className="flex flex-wrap items-center gap-2">
                {layer.nodes.map((node, nodeIdx) => (
                  <div key={node.id} className="flex items-center gap-2">
                    <ArchNode
                      node={node}
                      isSelected={selectedNode === node.id}
                      isLayerActive={isLayerActive}
                      onClick={() => setSelectedNode(node.id)}
                    />
                    {nodeIdx < layer.nodes.length - 1 && (
                      <ArrowRight className="hidden h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500 md:block" />
                    )}
                  </div>
                ))}
              </div>
            </motion.div>

            {/* connector between this layer and the next */}
            {layerIdx < LAYERS.length - 1 && (
              <VerticalConnector
                gradient={CONNECTOR_GRADIENT[layerIdx]}
                packetColor={CONNECTOR_PACKET[layerIdx]}
                isActive={flowStep === layerIdx}
              />
            )}
          </div>
        );
      })}

      {/* ── Detail panel ─────────────────────────────────────── */}
      <AnimatePresence mode="wait">
        <motion.div
          key={selectedNode}
          className="mt-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/60"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.18 }}
        >
          <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{detail.title}</p>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{detail.content}</p>
          <ul className="mt-3 space-y-1.5">
            {detail.bullets.map((b) => (
              <li key={b} className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400" />
                {b}
              </li>
            ))}
          </ul>
        </motion.div>
      </AnimatePresence>

      {/* ── Decision Engine modes ─────────────────────────────── */}
      <div className="mt-3 rounded-xl border border-violet-200 bg-violet-50 p-4 dark:border-violet-700/40 dark:bg-violet-900/20">
        <p className="text-sm font-semibold text-violet-900 dark:text-violet-200">
          🧠 Decision Engine — core differentiator
        </p>
        <p className="mt-1 text-xs text-violet-700 dark:text-violet-300">
          Most AI systems have one path. This one has four, each explicitly labelled.
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {[
            { dot: "bg-emerald-400", text: "Strong evidence → evidence_based" },
            { dot: "bg-amber-400",   text: "Evidence + provider fails → evidence_only" },
            { dot: "bg-blue-400",    text: "No direct evidence → general_explanation" },
            { dot: "bg-rose-400",    text: "Full failure path → safe fallback" },
          ].map(({ dot, text }) => (
            <p
              key={text}
              className="flex items-center gap-2 rounded-lg bg-violet-100/60 px-2 py-1.5 text-sm text-violet-900 dark:bg-violet-800/20 dark:text-violet-200"
            >
              <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
              {text}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}
