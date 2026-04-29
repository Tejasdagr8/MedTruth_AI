"use client";

import Link from "next/link";

interface SidebarProps {
  suggestions: string[];
  history: string[];
  savedAnswers: Array<{ query: string; answer: string; savedAt: string }>;
  savedCount: number;
  userName?: string | null;
  onSuggestionClick: (query: string) => void;
  onHistoryClick: (query: string) => void;
  onSavedClick: (item: { query: string; answer: string; savedAt: string }) => void;
  onNewQuery: () => void;
}

function timeAgo(ts: string) {
  const parsed = new Date(ts).getTime();
  if (Number.isNaN(parsed)) return "";
  const diff = Date.now() - parsed;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function exactTime(ts: string) {
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) return "Unknown time";
  return parsed.toLocaleString();
}

export default function Sidebar({
  suggestions,
  history,
  savedAnswers,
  savedCount,
  userName,
  onSuggestionClick,
  onHistoryClick,
  onSavedClick,
  onNewQuery,
}: SidebarProps) {
  return (
    <aside className="hidden w-[260px] shrink-0 flex-col gap-5 border-r border-slate-200 bg-white/95 p-4 backdrop-blur-sm dark:border-slate-700 dark:bg-[#0b1220] lg:flex">
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">MedTruth AI</h1>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Medical intelligence interface</p>
      </div>

      <button
        onClick={onNewQuery}
        className="w-full rounded-2xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all duration-200 hover:scale-[1.01] hover:bg-blue-700"
      >
        + New Query
      </button>

      <Link
        href="/how-it-works"
        className="block rounded-2xl border border-blue-200 bg-gradient-to-br from-blue-50 to-indigo-50 p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md dark:border-blue-700/50 dark:from-blue-950/40 dark:to-indigo-950/40"
      >
        <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">🧠 How MedTruth Works</p>
        <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
          See how MedTruth builds answers from real medical evidence, step by step.
        </p>
      </Link>

      <Link
        href="/llm-lab"
        className="block rounded-2xl border border-purple-200/60 bg-gradient-to-br from-purple-50/80 to-slate-50 p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md dark:border-purple-800/40 dark:from-purple-950/30 dark:to-slate-900"
      >
        <div className="flex items-center gap-2">
          <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">⚗️ LLM Lab</p>
          <span className="rounded-full bg-purple-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-purple-600 dark:bg-purple-900/40 dark:text-purple-400">
            Experimental
          </span>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          Free-form queries with step-by-step tool tracing. No evidence filters.
        </p>
      </Link>

      <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Recent Queries
        </h2>
        {history.length === 0 ? (
          <p className="px-2 py-1 text-sm text-slate-400 dark:text-slate-500">No recent queries yet</p>
        ) : (
          <div className="space-y-1.5">
            {history.slice(0, 8).map((item) => (
              <button
                key={item}
                onClick={() => onHistoryClick(item)}
                className="w-full truncate rounded-xl px-2 py-2 text-left text-sm text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                title={item}
              >
                {item}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          📌 Your Saved Insights
        </h2>
        {savedAnswers.length === 0 ? (
          <p className="px-2 py-1 text-sm text-slate-400 dark:text-slate-500">No saved answers yet</p>
        ) : (
          <div className="space-y-1.5">
            {savedAnswers.slice(0, 5).map((item, index) => (
              <button
                key={`${item.query}-${item.savedAt}`}
                onClick={() => onSavedClick(item)}
                className={`w-full rounded-xl px-2 py-2 text-left text-sm text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100 ${
                  index === 0 ? "bg-blue-50 dark:bg-blue-500/10" : ""
                }`}
                title={`${item.query} • Saved ${exactTime(item.savedAt)}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
                    <span className="truncate">{item.query}</span>
                  </div>
                  <span
                    className="shrink-0 text-[11px] text-slate-400 dark:text-slate-500"
                    title={exactTime(item.savedAt)}
                  >
                    {timeAgo(item.savedAt)}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Suggested Questions
        </h2>
        <div className="space-y-1.5">
          {suggestions.slice(0, 5).map((item) => (
            <button
              key={item}
              onClick={() => onSuggestionClick(item)}
              className="w-full rounded-xl px-2 py-2 text-left text-sm text-slate-700 transition-colors hover:bg-blue-50 hover:text-blue-700 dark:text-slate-200 dark:hover:bg-slate-800 dark:hover:text-blue-300"
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-3 text-sm text-slate-500 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
        {savedCount > 0 ? `${savedCount} saved evidence responses` : "No saved responses yet"}
      </div>

      <div className="mt-auto space-y-2">
        <Link
          href="/profile"
          className="block w-full rounded-2xl border border-slate-300 py-2 text-center text-sm text-slate-700 transition-colors hover:border-slate-400 dark:border-slate-600 dark:text-slate-200 dark:hover:border-slate-500"
        >
          {userName ? `Profile • ${userName}` : "Profile"}
        </Link>
      </div>
    </aside>
  );
}
