"use client";

import { ReactNode, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getUserHistory, deleteSavedAnswer, UserProfile, SavedAnswer } from "@/lib/api";
import { signIn, useSession } from "next-auth/react";
import { RotateCcw, Trash2, BookmarkCheck, Clock, Sparkles, Activity, Search, SlidersHorizontal } from "lucide-react";

const BAND_PILL: Record<string, string> = {
  HIGH: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300",
  MEDIUM: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300",
  LOW: "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300",
};

function formatSavedAt(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function getInitial(name?: string | null, email?: string | null) {
  if (name?.trim()) return name.trim()[0].toUpperCase();
  if (email?.trim()) return email.trim()[0].toUpperCase();
  return "U";
}

export default function ProfilePage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingHash, setDeletingHash] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [savedSearch, setSavedSearch] = useState("");
  const [bandFilter, setBandFilter] = useState<"ALL" | "HIGH" | "MEDIUM" | "LOW">("ALL");

  const load = async () => {
    if (!session?.user?.email) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getUserHistory(session.user.email);
      setProfile(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load profile.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.user?.email]);

  const handleReRun = (query: string) => {
    router.push(`/?q=${encodeURIComponent(query)}`);
  };

  const handleDelete = async (item: SavedAnswer) => {
    if (!session?.user?.email || !item.answer_hash) return;
    setDeletingHash(item.answer_hash);
    setDeleteError(null);
    try {
      await deleteSavedAnswer(session.user.email, item.answer_hash);
      setProfile((prev) =>
        prev
          ? {
              ...prev,
              saved_answers: prev.saved_answers.filter(
                (s) => s.answer_hash !== item.answer_hash
              ),
            }
          : prev
      );
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to delete answer. Please try again.";
      setDeleteError(msg);
      // Auto-dismiss after 4 s so the banner doesn't linger.
      setTimeout(() => setDeleteError(null), 4000);
    } finally {
      setDeletingHash(null);
    }
  };

  const recentQueries = useMemo(
    () => (profile?.query_history ?? []).slice().reverse().slice(0, 8),
    [profile?.query_history]
  );

  const savedAnswers = useMemo(
    () => (profile?.saved_answers ?? []).slice().reverse().slice(0, 12),
    [profile?.saved_answers]
  );

  const avgConfidence = useMemo(() => {
    const values = (profile?.saved_answers ?? [])
      .map((s) => s.confidence)
      .filter((v): v is number => typeof v === "number");
    if (values.length === 0) return null;
    return Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 100);
  }, [profile?.saved_answers]);

  const highConfidenceCount = useMemo(
    () => (profile?.saved_answers ?? []).filter((s) => s.confidence_band === "HIGH").length,
    [profile?.saved_answers]
  );

  const filteredSavedAnswers = useMemo(() => {
    const q = savedSearch.trim().toLowerCase();
    return savedAnswers.filter((item) => {
      const matchesText =
        q.length === 0 ||
        item.query.toLowerCase().includes(q) ||
        item.answer.toLowerCase().includes(q) ||
        (item.mode ?? "").toLowerCase().includes(q);
      const matchesBand = bandFilter === "ALL" || item.confidence_band === bandFilter;
      return matchesText && matchesBand;
    });
  }, [savedAnswers, savedSearch, bandFilter]);

  if (status === "loading") {
    return (
      <main className="min-h-screen bg-slate-50 p-8 text-sm text-slate-600 dark:bg-slate-950 dark:text-slate-300">
        Loading session...
      </main>
    );
  }

  if (!session?.user) {
    return (
      <main className="flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 text-center">
          <h1 className="text-lg font-semibold">Sign in to view your profile</h1>
          <p className="mt-2 text-sm text-slate-600">
            Your profile stores query history, saved answers, and usage insights.
          </p>
          <button
            onClick={() => signIn("google")}
            className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm text-white"
          >
            Sign in with Google
          </button>
          <Link href="/" className="mt-3 block text-xs text-blue-600">
            Back to MedTruth
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 p-6 dark:from-slate-950 dark:to-slate-950">
      <div className="mx-auto max-w-5xl space-y-5">
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-5 text-white">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-full bg-white/20 text-base font-semibold">
                  {getInitial(session.user?.name, session.user?.email)}
                </div>
                <div>
                  <h1 className="text-xl font-semibold">Profile</h1>
                  <p className="text-sm text-blue-100">{session.user.email}</p>
                </div>
              </div>
              <Link
                href="/"
                className="rounded-lg border border-white/40 bg-white/10 px-3 py-1.5 text-xs font-medium text-white hover:bg-white/20"
              >
                Back to MedTruth
              </Link>
            </div>
          </div>
          <div className="px-6 py-4 text-sm text-slate-600 dark:text-slate-300">
            Most searched condition:{" "}
            <span className="font-semibold text-emerald-700 dark:text-emerald-400">
              {profile?.most_searched_condition ?? "No trend yet"}
            </span>
          </div>
        </section>

        {loading && (
          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
            Loading your data...
          </div>
        )}
        {error && <div className="text-sm text-red-600">Error: {error}</div>}
        {deleteError && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300">
            {deleteError}
          </div>
        )}

        {!loading && !error && profile && (
          <div className="grid gap-4">
            <section className="grid gap-4 md:grid-cols-3">
              <StatCard
                icon={<Activity className="h-4 w-4 text-blue-500" />}
                label="Queries Executed"
                value={profile.usage_count}
              />
              <StatCard
                icon={<BookmarkCheck className="h-4 w-4 text-indigo-500" />}
                label="Saved Answers"
                value={profile.saved_answers.length}
              />
              <StatCard
                icon={<Sparkles className="h-4 w-4 text-emerald-500" />}
                label="Most Searched"
                value={profile.most_searched_condition ?? "No trend"}
              />
            </section>

            <section className="grid gap-4 md:grid-cols-2">
              <StatCard
                icon={<Sparkles className="h-4 w-4 text-violet-500" />}
                label="Avg Confidence"
                value={avgConfidence != null ? `${avgConfidence}%` : "—"}
              />
              <StatCard
                icon={<BookmarkCheck className="h-4 w-4 text-emerald-500" />}
                label="High Confidence Saves"
                value={highConfidenceCount}
              />
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
              <h2 className="mb-3 flex items-center gap-2 font-medium text-slate-800 dark:text-slate-200">
                <Search className="h-4 w-4 text-blue-500" />
                Recent Queries
              </h2>
              {recentQueries.length === 0 ? (
                <p className="text-sm text-slate-500">No queries yet.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {recentQueries.map((q, i) => (
                    <button
                      key={`${q}-${i}`}
                      onClick={() => handleReRun(q)}
                      className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-700 transition hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-blue-600 dark:hover:text-blue-300"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
              <h2 className="mb-3 flex items-center gap-2 font-medium text-slate-800 dark:text-slate-200">
                <BookmarkCheck className="h-4 w-4 text-blue-500" />
                Saved Answers
              </h2>
              <div className="mb-3 grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                  <input
                    value={savedSearch}
                    onChange={(e) => setSavedSearch(e.target.value)}
                    placeholder="Search saved answers..."
                    className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-slate-700 outline-none transition focus:border-blue-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:focus:border-blue-700"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <SlidersHorizontal className="h-4 w-4 text-slate-400" />
                  <select
                    value={bandFilter}
                    onChange={(e) => setBandFilter(e.target.value as "ALL" | "HIGH" | "MEDIUM" | "LOW")}
                    className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 outline-none transition focus:border-blue-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:focus:border-blue-700"
                  >
                    <option value="ALL">All bands</option>
                    <option value="HIGH">High only</option>
                    <option value="MEDIUM">Medium only</option>
                    <option value="LOW">Low only</option>
                  </select>
                </div>
              </div>
              {savedAnswers.length === 0 ? (
                <p className="text-sm text-slate-500">
                  No saved answers yet. Save one from the main query screen.
                </p>
              ) : filteredSavedAnswers.length === 0 ? (
                <p className="text-sm text-slate-500">
                  No saved answers match your current filters.
                </p>
              ) : (
                <div className="space-y-3">
                  {filteredSavedAnswers.map((item, idx) => (
                    <SavedAnswerCard
                      key={`${item.answer_hash ?? idx}`}
                      item={item}
                      onReRun={handleReRun}
                      onDelete={handleDelete}
                      isDeleting={deletingHash === item.answer_hash}
                    />
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </main>
  );
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <div className="mb-2 flex items-center gap-2">{icon}<p className="text-xs uppercase tracking-wide text-slate-500">{label}</p></div>
      <p className="text-xl font-semibold text-slate-900 dark:text-slate-100">{value}</p>
    </div>
  );
}

function SavedAnswerCard({
  item,
  onReRun,
  onDelete,
  isDeleting,
}: {
  item: SavedAnswer;
  onReRun: (q: string) => void;
  onDelete: (item: SavedAnswer) => void;
  isDeleting: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const confidence = item.confidence != null ? Math.round(item.confidence * 100) : null;

  return (
    <article className="rounded-xl border border-slate-200 bg-slate-50 p-4 transition hover:border-slate-300 dark:border-slate-700 dark:bg-slate-800/60 dark:hover:border-slate-600">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <button
          onClick={() => setExpanded((p) => !p)}
          className="flex-1 text-left text-sm font-medium text-slate-800 hover:text-blue-700 dark:text-slate-200 dark:hover:text-blue-400"
        >
          {item.query}
        </button>
        <div className="flex flex-shrink-0 items-center gap-1">
          <button
            onClick={() => onReRun(item.query)}
            title="Re-run this query"
            className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-500 transition hover:border-blue-300 hover:text-blue-600 dark:border-slate-600 dark:bg-slate-700 dark:hover:text-blue-400"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => onDelete(item)}
            disabled={isDeleting}
            title="Delete saved answer"
            className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-400 transition hover:border-rose-300 hover:text-rose-500 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-700"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Metadata pills */}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {item.saved_at && (
          <span className="flex items-center gap-1 text-xs text-slate-400">
            <Clock className="h-3 w-3" />
            {formatSavedAt(item.saved_at)}
          </span>
        )}
        {confidence != null && item.confidence_band && (
          <span
            className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
              BAND_PILL[item.confidence_band] ?? BAND_PILL.LOW
            }`}
          >
            {confidence}% · {item.confidence_band}
          </span>
        )}
        {item.mode && (
          <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-400">
            {item.mode.replace(/_/g, " ")}
          </span>
        )}
        {item.citations_count != null && item.citations_count > 0 && (
          <span className="text-xs text-slate-400">{item.citations_count} citations</span>
        )}
      </div>

      {/* Expandable answer preview */}
      {expanded && (
        <p className="mt-3 rounded-lg bg-white px-3 py-2 text-xs leading-relaxed text-slate-600 dark:bg-slate-900/40 dark:text-slate-400">
          {item.answer.slice(0, 600)}
          {item.answer.length > 600 && "…"}
        </p>
      )}
    </article>
  );
}
