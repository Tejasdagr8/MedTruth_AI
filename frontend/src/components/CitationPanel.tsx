"use client";

import { Citation } from "@/lib/api";

interface Props {
  citations: Citation[];
  highlightedSourceIndex?: number | null;
}

const BAND_BADGE: Record<string, string> = {
  HIGH:   "bg-green-100 text-green-800",
  MEDIUM: "bg-yellow-100 text-yellow-800",
  LOW:    "bg-red-100 text-red-800",
};

const SOURCE_LABEL: Record<string, string> = {
  pubmed:    "PubMed",
  europepmc: "Europe PMC",
  cochrane:  "Cochrane",
  who:       "WHO",
  cdc:       "CDC",
};

export default function CitationPanel({ citations, highlightedSourceIndex = null }: Props) {
  if (!citations.length) return null;

  return (
    <div className="space-y-3">
      <h3 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500">
        {citations.length} source{citations.length !== 1 ? "s" : ""}
      </h3>
      <div className="space-y-3">
        {citations.slice(0, 6).map((c) => (
          <div
            key={c.index}
            id={`source-${c.index}`}
            className={`rounded-xl border bg-white p-3.5 shadow-sm transition-all duration-200 hover:border-blue-300 hover:shadow-md dark:bg-slate-900 ${
              highlightedSourceIndex === c.index
                ? "border-blue-400 ring-2 ring-blue-100/60 dark:border-blue-500 dark:ring-blue-500/20"
                : "border-slate-200/70 dark:border-slate-800"
            }`}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className="text-xs font-bold text-slate-400">[{c.index}]</span>
                  <span className="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700 font-medium">
                    {SOURCE_LABEL[c.source] ?? c.source}
                  </span>
                  {c.is_aha && (
                    <span
                      title="American Heart Association journal"
                      className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200 font-semibold"
                    >
                      &#9829; AHA
                    </span>
                  )}
                  {c.confidence_band && (
                    <span
                      className={`text-xs px-2 py-0.5 rounded font-medium ${
                        BAND_BADGE[c.confidence_band] ?? ""
                      }`}
                    >
                      MEDEVA {c.medeva_total?.toFixed(2)}
                    </span>
                  )}
                </div>
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="line-clamp-2 text-sm font-semibold text-slate-800 hover:text-blue-600"
                >
                  {c.title}
                </a>
                <p className="mt-1 text-xs text-slate-500">
                  {c.authors.slice(0, 3).join(", ")}
                  {c.authors.length > 3 ? " et al." : ""} •{" "}
                  <em>{c.journal}</em> ({c.pub_year})
                </p>
                <div className="mt-2 text-[10px] text-slate-400 dark:text-slate-500">
                  MEDEVA {c.medeva_total?.toFixed(2) ?? "—"}
                </div>
              </div>
              {c.url && (
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 whitespace-nowrap text-xs font-semibold text-blue-600 hover:text-blue-700"
                >
                  View →
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
