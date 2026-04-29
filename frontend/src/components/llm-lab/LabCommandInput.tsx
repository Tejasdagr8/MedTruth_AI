"use client";

import { motion } from "framer-motion";

interface LabCommandInputProps {
  query: string;
  loading: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export default function LabCommandInput({
  query,
  loading,
  onChange,
  onSubmit,
}: LabCommandInputProps) {
  const hasText = query.trim().length > 0;

  return (
    <div className="rounded-2xl border border-white/10 bg-[#121427]/90 p-4 shadow-[0_0_0_1px_rgba(167,139,250,0.08),0_10px_40px_rgba(2,6,23,0.55)]">
      <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] text-slate-400">
        Command Input
        <motion.span
          animate={{ opacity: [1, 0.2, 1] }}
          transition={{ duration: 1.1, repeat: Number.POSITIVE_INFINITY }}
          className="h-3 w-1 rounded-full bg-violet-400"
        />
      </div>

      <textarea
        value={query}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSubmit();
          }
        }}
        rows={5}
        placeholder={"Try: Compare metformin vs GLP-1 agonists for cardiovascular outcomes in T2D\nor: Summarize evidence on CBT efficacy in adolescents with MDD"}
        className="w-full resize-none rounded-xl border border-white/10 bg-[#0d1020] px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 outline-none transition focus:border-violet-400/60 focus:shadow-[0_0_0_1px_rgba(167,139,250,0.45),0_0_28px_rgba(99,102,241,0.25)]"
      />

      <div className="mt-3 flex items-center justify-between">
        <p className="text-xs text-slate-500">
          Press Enter to execute, Shift+Enter for newline.
        </p>
        <button
          onClick={onSubmit}
          disabled={loading || !hasText}
          className="rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:from-violet-500 hover:to-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? "Executing..." : "Run Query"}
        </button>
      </div>
    </div>
  );
}
