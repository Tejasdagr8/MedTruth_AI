"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import type { SelectionRationale } from "@/lib/api";

interface SelectionRationaleProps {
  rationale: SelectionRationale;
}

const BAND_COLOURS: Record<string, string> = {
  HIGH:   "text-emerald-700 bg-emerald-50 dark:text-emerald-300 dark:bg-emerald-900/20",
  MEDIUM: "text-amber-700   bg-amber-50   dark:text-amber-300   dark:bg-amber-900/20",
  LOW:    "text-rose-700    bg-rose-50    dark:text-rose-300    dark:bg-rose-900/20",
};

export default function SelectionRationale({ rationale }: SelectionRationaleProps) {
  const [open, setOpen] = useState(false);

  if (!rationale || !rationale.why_selected?.length) return null;

  return (
    <div className="mt-4">
      {/* Toggle */}
      <button
        onClick={() => setOpen((p) => !p)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-[11px] font-medium uppercase tracking-widest text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300">
          Why these studies?
        </span>
        <span className="text-[11px] text-slate-300 dark:text-slate-600">{open ? "▾" : "▸"}</span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            {/* Filter summary — slim bar */}
            <p className="mt-3 text-[11px] text-slate-400 dark:text-slate-500">
              {rationale.filter_summary}
            </p>

            {/* ── Selected evidence ──────────────────────────────────────────── */}
            <div className="mt-4">
              <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-widest text-slate-600 dark:text-slate-300">
                Selected Evidence
              </p>
              <ul className="space-y-3">
                {rationale.why_selected.map((item, i) => (
                  <li key={i} className="flex items-start gap-3">
                    {/* Accent line */}
                    <div className="mt-1.5 h-3 w-0.5 flex-shrink-0 rounded-full bg-blue-300 dark:bg-blue-700" />
                    <div className="min-w-0">
                      <p className="line-clamp-2 text-xs font-medium text-slate-700 dark:text-slate-200">
                        {item.title}
                      </p>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        {/* Study type chip */}
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                          {item.study_type}
                        </span>
                        {/* Journal */}
                        {item.journal && (
                          <span className="text-[10px] text-slate-500 dark:text-slate-400">
                            {item.journal}
                          </span>
                        )}
                        {/* Year */}
                        {item.pub_year && (
                          <span className="text-[10px] text-slate-400 dark:text-slate-500">
                            {item.pub_year}
                          </span>
                        )}
                        {/* MEDEVA score — kept subtle */}
                        {item.confidence_band && (
                          <span className={`rounded-full px-2 py-0.5 text-[10px] opacity-75 ${BAND_COLOURS[item.confidence_band] ?? BAND_COLOURS.LOW}`}>
                            {item.medeva_score} MEDEVA
                          </span>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            {/* ── Excluded evidence ──────────────────────────────────────────── */}
            {rationale.why_excluded.length > 0 && (
              <div className="mt-5">
                <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500">
                  Excluded Evidence (and why)
                </p>
                <ul className="space-y-1.5">
                  {rationale.why_excluded.map((reason, i) => (
                    <li key={i} className="flex items-start gap-2 text-[11px] text-slate-400 dark:text-slate-500">
                      <span className="mt-1 h-1 w-1 flex-shrink-0 rounded-full bg-slate-300 dark:bg-slate-600" />
                      {reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
