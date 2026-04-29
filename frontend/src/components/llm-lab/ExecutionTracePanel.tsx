"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

export interface ToolStep {
  tool: string;
  input: string;
  output: string;
  reasoning: string;
  duration_ms: number;
  skipped?: boolean;
}

interface ExecutionTracePanelProps {
  steps: ToolStep[];
}

function toolLabel(tool: string): string {
  if (tool === "planner") return "Planner";
  if (tool === "pubmed_search") return "PubMed Search";
  if (tool === "analysis") return "Analysis";
  return tool;
}

export default function ExecutionTracePanel({ steps }: ExecutionTracePanelProps) {
  const [openStep, setOpenStep] = useState<number | null>(0);

  if (steps.length === 0) return null;

  return (
    <aside className="sticky top-24 rounded-2xl border border-white/10 bg-[#101427] p-4">
      <p className="mb-3 text-[11px] uppercase tracking-[0.2em] text-slate-400">Execution Trace</p>
      <div className="space-y-2">
        {steps.map((step, idx) => {
          const isOpen = openStep === idx;
          return (
            <div key={`${step.tool}-${idx}`} className="rounded-xl border border-white/10 bg-white/[0.02]">
              <button
                onClick={() => setOpenStep(isOpen ? null : idx)}
                className="w-full px-3 py-2 text-left"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs text-slate-200">
                    {idx + 1}. {toolLabel(step.tool)}
                  </p>
                  <span className="text-[10px] text-slate-500">{Math.round(step.duration_ms)} ms</span>
                </div>
                <p className="mt-1 line-clamp-1 text-[11px] text-slate-400">
                  {step.reasoning || (step.skipped ? "Step skipped" : "Execution complete")}
                </p>
              </button>
              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden border-t border-white/10"
                  >
                    <div className="space-y-2 px-3 py-3 text-[11px] text-slate-400">
                      <div>
                        <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">Input</p>
                        <p className="line-clamp-3 whitespace-pre-wrap">{step.input || "None"}</p>
                      </div>
                      <div>
                        <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">Output</p>
                        <p className="line-clamp-5 whitespace-pre-wrap">{step.output || "No output"}</p>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
