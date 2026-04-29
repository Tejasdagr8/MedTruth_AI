"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getUserHistory, deleteSavedAnswer, UserProfile, SavedAnswer } from "@/lib/api";
import { signIn, useSession } from "next-auth/react";
import { RotateCcw, Trash2, BookmarkCheck, Clock } from "lucide-react";

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

export default function ProfilePage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingHash, setDeletingHash] = useState<string | null>(null);

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
    } catch {
      // Silent — deletion failure is non-critical
    } finally {
      setDeletingHash(null);
    }
  };

  if (status === "loading") {
    return <main className="p-8 text-sm text-slate-600">Loading session...</main>;
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
    <main className="min-h-screen bg-slate-50 p-6 dark:bg-slate-950">
      <div className="mx-auto max-w-4xl space-y-4">
        <div className="rounded-xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-900">
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Profile</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">{session.user.email}</p>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-500">
            Most searched condition:{" "}
            <span className="font-semibold text-emerald-700 dark:text-emerald-400">
              {profile?.most_searched_condition ?? "No trend yet"}
            </span>
          </p>
        </div>

        {loading && <div className="text-sm text-slate-600">Loading your data...</div>}
        {error && <div className="text-sm text-red-600">Error: {error}</div>}

        {!loading && !error && profile && (
          <div className="grid gap-4 md:grid-cols-2">
            <section className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
              <h2 className="mb-2 font-medium text-slate-800 dark:text-slate-200">Usage</h2>
              <p className="text-sm text-slate-700 dark:text-slate-300">
                Queries executed: {profile.usage_count}
              </p>
              <p className="text-sm text-slate-700 dark:text-slate-300">
                Saved answers: {profile.saved_answers.length}
              </p>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
              <h2 className="mb-2 font-medium text-slate-800 dark:text-slate-200">Recent Queries</h2>
              {profile.query_history.length === 0 ? (
                <p className="text-sm text-slate-500">No queries yet.</p>
              ) : (
                <ul className="space-y-1 text-sm text-slate-700 dark:text-slate-300">
                  {profile.query_history.slice(0, 8).map((q, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span className="text-slate-400">•</span>
                      <button
                        onClick={() => handleReRun(q)}
                        className="text-left text-blue-600 hover:underline dark:text-blue-400"
                      >
                        {q}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-4 md:col-span-2 dark:border-slate-700 dark:bg-slate-900">
              <h2 className="mb-3 flex items-center gap-2 font-medium text-slate-800 dark:text-slate-200">
                <BookmarkCheck className="h-4 w-4 text-blue-500" />
                Saved Answers
              </h2>
              {profile.saved_answers.length === 0 ? (
                <p className="text-sm text-slate-500">
                  No saved answers yet. Save one from the main query screen.
                </p>
              ) : (
                <div className="space-y-3">
                  {profile.saved_answers
                    .slice()
                    .reverse()
                    .slice(0, 10)
                    .map((item, idx) => (
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
    <article className="rounded-xl border border-slate-100 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/60">
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
        <p className="mt-3 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
          {item.answer.slice(0, 600)}
          {item.answer.length > 600 && "…"}
        </p>
      )}
    </article>
  );
}
