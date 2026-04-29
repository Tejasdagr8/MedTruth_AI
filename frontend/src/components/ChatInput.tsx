"use client";

interface ChatInputProps {
  value: string;
  loading: boolean;
  suggestions: string[];
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export default function ChatInput({ value, loading, suggestions, onChange, onSubmit }: ChatInputProps) {
  return (
    /* Sticky dock — spans full width, anchored to the bottom, integrated with the page */
    <div className="sticky bottom-0 z-30 border-t border-slate-200/70 bg-white/95 px-0 pb-4 pt-3 backdrop-blur-sm dark:border-slate-800 dark:bg-[#0b1220]/95">
      {/* Autocomplete suggestions */}
      {suggestions.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {suggestions.map((item) => (
            <button
              key={item}
              onClick={() => onChange(item)}
              className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 shadow-sm transition-colors hover:border-blue-400 hover:text-blue-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:text-blue-300"
            >
              {item}
            </button>
          ))}
        </div>
      )}

      {/* Input row */}
      <div className="flex items-end gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm ring-1 ring-slate-200/60 transition-all duration-200 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-400/30 dark:border-slate-700 dark:bg-[#111827] dark:ring-white/5 dark:focus-within:border-blue-500">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
          rows={1}
          placeholder="Ask a medical question (e.g., Does aspirin reduce mortality in heart attack?)"
          className="flex-1 resize-none bg-transparent text-sm leading-relaxed text-slate-800 outline-none placeholder:text-slate-400 dark:text-slate-100 dark:placeholder:text-slate-500"
        />
        <button
          onClick={onSubmit}
          disabled={loading || !value.trim()}
          className="flex shrink-0 items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-500 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? (
            <>
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Thinking
            </>
          ) : (
            <>
              Ask
              <span className="text-xs text-blue-300">↵</span>
            </>
          )}
        </button>
      </div>

      <p className="mt-1.5 text-center text-[10px] text-slate-400 dark:text-slate-600">
        Shift+Enter for new line · Sources: PubMed · BMJ · The Lancet · WHO · Cochrane
      </p>
    </div>
  );
}
