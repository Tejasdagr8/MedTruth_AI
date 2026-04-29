"use client";

interface LabTimelineProps {
  activeIndex: number;
}

const STEPS = ["Plan", "Search", "Analyze", "Answer"];

export default function LabTimeline({ activeIndex }: LabTimelineProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-[#101427] p-4">
      <p className="mb-3 text-[11px] uppercase tracking-[0.2em] text-slate-400">
        Execution Timeline
      </p>
      <div className="flex items-center gap-2">
        {STEPS.map((step, idx) => {
          const isDone = idx < activeIndex;
          const isActive = idx === activeIndex;
          return (
            <div key={step} className="flex min-w-0 flex-1 items-center gap-2">
              <div
                className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                  isDone
                    ? "bg-emerald-400"
                    : isActive
                      ? "animate-pulse bg-violet-400"
                      : "bg-slate-700"
                }`}
              />
              <span
                className={`truncate text-xs ${
                  isDone || isActive ? "text-slate-200" : "text-slate-500"
                }`}
              >
                {step}
              </span>
              {idx < STEPS.length - 1 && (
                <div className={`h-px flex-1 ${idx < activeIndex ? "bg-violet-400/60" : "bg-slate-700"}`} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
