"use client";

import { Citation } from "@/lib/api";
import { useState } from "react";

interface Props {
  citations: Citation[];
}

export default function MEDEVABreakdown({ citations }: Props) {
  const [open, setOpen] = useState(false);

  const scored = citations.filter((c) => c.medeva_total !== null);
  if (!scored.length) return null;

  return (
    <div className="mt-4">
      <button
        className="text-xs text-blue-600 hover:underline flex items-center gap-1"
        onClick={() => setOpen(!open)}
      >
        {open ? "▲ Hide" : "▼ Show"} MEDEVA Score Breakdown
      </button>
      {open && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-slate-100">
                <th className="text-left p-2 border border-slate-200">#</th>
                <th className="text-left p-2 border border-slate-200">Journal</th>
                <th className="text-left p-2 border border-slate-200">Study Type</th>
                <th className="text-right p-2 border border-slate-200">MEDEVA</th>
                <th className="text-right p-2 border border-slate-200">Band</th>
              </tr>
            </thead>
            <tbody>
              {scored.map((c) => (
                <tr key={c.index} className="hover:bg-slate-50">
                  <td className="p-2 border border-slate-200 font-mono">[{c.index}]</td>
                  <td className="p-2 border border-slate-200 max-w-[180px] truncate">
                    {c.journal}
                  </td>
                  <td className="p-2 border border-slate-200 text-slate-500">
                    {c.source}
                  </td>
                  <td className="p-2 border border-slate-200 text-right font-mono font-semibold">
                    {c.medeva_total?.toFixed(3)}
                  </td>
                  <td className="p-2 border border-slate-200 text-right">
                    <span
                      className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                        c.confidence_band === "HIGH"
                          ? "bg-green-100 text-green-800"
                          : c.confidence_band === "MEDIUM"
                          ? "bg-yellow-100 text-yellow-800"
                          : "bg-red-100 text-red-800"
                      }`}
                    >
                      {c.confidence_band}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
