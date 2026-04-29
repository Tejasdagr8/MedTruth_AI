"use client";

interface Props {
  band: "HIGH" | "MEDIUM" | "LOW";
  score: number;
}

export default function ConfidenceBadge({ band, score }: Props) {
  const safeScore = Math.max(0.4, score);
  const pct = Math.round(safeScore * 100);
  const toneClass =
    pct >= 70
      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
      : pct >= 50
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : "bg-orange-50 text-orange-700 border-orange-200";
  const label =
    band === "HIGH"
      ? "Strong clinical evidence"
      : band === "MEDIUM"
      ? "Moderate supporting evidence"
      : "Limited but relevant evidence";

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-semibold transition-all duration-200 hover:scale-[1.02] ${toneClass}`}
      title={`Confidence score: ${pct}%`}
    >
      <span>{label}</span>
      <span className="h-4 w-px bg-current/25" />
      <span className="text-xs font-bold uppercase tracking-wide">Confidence: {pct}%</span>
    </span>
  );
}
