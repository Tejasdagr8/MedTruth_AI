"use client";

import { useState } from "react";
import { ContradictionPair } from "@/lib/api";

interface Props {
  pairs: ContradictionPair[];
}

export default function ContradictionAlert({ pairs }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (!pairs.length) return null;

  return (
    <div className="mt-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-amber-500 text-lg">⚠️</span>
        <h3 className="text-sm font-semibold text-amber-800">
          {pairs.length} Study Contradiction{pairs.length > 1 ? "s" : ""} Detected
        </h3>
      </div>
      <div className="space-y-2">
        {pairs.map((pair, i) => (
          <div
            key={i}
            className="border border-amber-200 rounded-lg bg-amber-50 overflow-hidden"
          >
            <button
              className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-amber-100 transition-colors"
              onClick={() => setExpanded(expanded === i ? null : i)}
            >
              <span className="text-sm font-medium text-amber-900">
                [{pair.doc_a.index}] vs [{pair.doc_b.index}] — Contradiction score:{" "}
                <strong>{(pair.contradiction_score * 100).toFixed(0)}%</strong>
              </span>
              <span className="text-amber-600">{expanded === i ? "▲" : "▼"}</span>
            </button>

            {expanded === i && (
              <div className="px-4 pb-4 space-y-3 text-sm">
                <p className="text-amber-800 italic">{pair.summary}</p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-white rounded p-3 border border-amber-200">
                    <p className="font-semibold text-slate-700 mb-1 text-xs uppercase tracking-wide">
                      Study A — MEDEVA {pair.doc_a.medeva_score.toFixed(2)}
                    </p>
                    <p className="text-slate-600 line-clamp-2 text-xs">{pair.doc_a.title}</p>
                    <p className="text-slate-500 mt-2 text-xs">{pair.doc_a.conclusion}</p>
                  </div>
                  <div className="bg-white rounded p-3 border border-amber-200">
                    <p className="font-semibold text-slate-700 mb-1 text-xs uppercase tracking-wide">
                      Study B — MEDEVA {pair.doc_b.medeva_score.toFixed(2)}
                    </p>
                    <p className="text-slate-600 line-clamp-2 text-xs">{pair.doc_b.title}</p>
                    <p className="text-slate-500 mt-2 text-xs">{pair.doc_b.conclusion}</p>
                  </div>
                </div>
                <p className="text-xs text-amber-700 font-medium">
                  Higher-evidence study [{pair.higher_evidence_index}] given precedence in the answer.
                </p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
