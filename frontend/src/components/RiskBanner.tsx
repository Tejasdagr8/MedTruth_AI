"use client";

import { RiskFlag } from "@/lib/api";

interface Props {
  flags: RiskFlag[];
}

const COLOR_MAP: Record<string, string> = {
  red:   "risk-red",
  amber: "risk-amber",
  blue:  "risk-blue",
};

export default function RiskBanner({ flags }: Props) {
  if (!flags.length) return null;

  return (
    <div className="space-y-2 my-4">
      {flags.map((flag, i) => (
        <div
          key={i}
          className={`p-4 rounded-r-lg ${COLOR_MAP[flag.banner_color] ?? "risk-amber"}`}
        >
          <div className="flex items-start gap-2">
            <span className="text-lg leading-none mt-0.5">
              {flag.banner_color === "red" ? "🔴" : flag.banner_color === "amber" ? "🟡" : "🔵"}
            </span>
            <div>
              <p className="font-semibold text-sm text-slate-800">
                {flag.level} RISK — {flag.category}
              </p>
              <p className="text-sm text-slate-700 mt-1">{flag.message}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
