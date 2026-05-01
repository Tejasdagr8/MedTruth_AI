"use client";

import AnswerResponseCard from "@/components/AnswerResponseCard";
import ChatInput from "@/components/ChatInput";
import CitationPanel from "@/components/CitationPanel";
import RelatedQuestions from "@/components/RelatedQuestions";
import Sidebar from "@/components/Sidebar";
import SignInButton from "@/components/SignInButton";
import {
  ModesHealth,
  ProvidersHealth,
  QueryResponse,
  getModesHealth,
  getProvidersHealth,
  getUserHistory,
  queryMedTruth,
  saveAnswer,
  syncUser,
} from "@/lib/api";
import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { signIn, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

type ChatTurn = {
  id: string;
  query: string;
  result?: QueryResponse;
  loading: boolean;
};

type SavedInsight = {
  query: string;
  answer: string;
  savedAt: string;
};

const EXAMPLE_QUERIES = [
  "Does aspirin reduce mortality in acute myocardial infarction?",
  "Is CBT effective for major depressive disorder?",
  "Metformin and cardiovascular risk in type 2 diabetes?",
  "Side effects of long-term corticosteroid use?",
  "Aspirin vs clopidogrel in acute coronary syndrome?",
];

const PIPELINE_MESSAGES = [
  "Searching trusted medical sources…",
  "Analyzing clinical evidence…",
  "Evaluating study reliability…",
  "Generating evidence-based answer…",
];

export default function Home() {
  const { data: session } = useSession();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [recentHistory, setRecentHistory] = useState<string[]>([]);
  const [savedAnswers, setSavedAnswers] = useState<SavedInsight[]>([]);
  const [savedCount, setSavedCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [thinkingStep, setThinkingStep] = useState(0);
  const [showSources, setShowSources] = useState(true);
  const [showMobileSources, setShowMobileSources] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [highlightedSourceIndex, setHighlightedSourceIndex] = useState<number | null>(null);
  const [savingTurnId, setSavingTurnId] = useState<string | null>(null);
  const [savedTurnIds, setSavedTurnIds] = useState<string[]>([]);
  const [failedTurnIds, setFailedTurnIds] = useState<string[]>([]);
  const [showDebugPanel, setShowDebugPanel] = useState(false);
  const [modesHealth, setModesHealth] = useState<ModesHealth | null>(null);
  const [providersHealth, setProvidersHealth] = useState<ProvidersHealth | null>(null);

  const activeTurn = turns[turns.length - 1];
  const activeResult = activeTurn?.result ?? null;

  useEffect(() => {
    const root = document.documentElement;
    const savedTheme = localStorage.getItem("theme");
    const shouldUseDark =
      savedTheme === "dark" || (!savedTheme && window.matchMedia("(prefers-color-scheme: dark)").matches);
    root.classList.toggle("dark", shouldUseDark);
    setDarkMode(shouldUseDark);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const enabled = params.get("debug") === "1";
    setShowDebugPanel(enabled);
    // Handle ?q= re-run from profile page
    const qParam = params.get("q");
    if (qParam) {
      window.history.replaceState({}, "", "/");
      // Defer to next tick so handleSubmit ref is ready
      setTimeout(() => handleSubmit(qParam), 0);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!showDebugPanel) return;
    let mounted = true;
    const loadHealth = async () => {
      try {
        const [modes, providers] = await Promise.all([getModesHealth(), getProvidersHealth()]);
        if (!mounted) return;
        setModesHealth(modes);
        setProvidersHealth(providers);
      } catch {
        // Silent in debug panel mode; avoids interrupting chat UX.
      }
    };
    loadHealth();
    const poll = setInterval(loadHealth, 10000);
    return () => {
      mounted = false;
      clearInterval(poll);
    };
  }, [showDebugPanel]);

  useEffect(() => {
    if (!loading) return;
    const t = setInterval(() => {
      setThinkingStep((s) => (s + 1) % PIPELINE_MESSAGES.length);
    }, 1200);
    return () => clearInterval(t);
  }, [loading]);

  useEffect(() => {
    if (!session?.user?.email) return;
    let mounted = true;
    getUserHistory(session.user.email)
      .then((profile) => {
        if (!mounted) return;
        setSavedCount(profile.saved_answers.length);
        setRecentHistory(profile.query_history.slice(-10).reverse());
        const deduped = profile.saved_answers
          .slice()
          .reverse()
          .filter((item) => item.query && item.answer)
          .filter((item, index, arr) => arr.findIndex((x) => x.query === item.query) === index)
          .map((item) => ({ query: item.query, answer: item.answer, savedAt: item.saved_at }));
        setSavedAnswers(deduped.slice(0, 10));
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        console.error("Failed to load user history:", err);
        // Non-fatal — sidebar history just stays empty; do not interrupt chat UX.
      });
    return () => {
      mounted = false;
    };
  }, [session?.user?.email]);

  const inputSuggestions = useMemo(() => {
    const value = query.toLowerCase();
    if (!value) return [];
    if (value.includes("aspirin")) {
      return ["aspirin dose MI", "aspirin vs clopidogrel", "aspirin bleeding risk"];
    }
    if (value.includes("statin")) {
      return ["statin intensity guidelines", "statin adverse effects", "statin primary prevention"];
    }
    return EXAMPLE_QUERIES.filter((item) => item.toLowerCase().includes(value)).slice(0, 3);
  }, [query]);

  const handleSubmit = async (q?: string) => {
    const finalQuery = (q ?? query).trim();
    if (!finalQuery) return;

    if (finalQuery.length < 10) {
      setTurns((prev) => [
        ...prev,
        {
          id: `${Date.now()}-hint`,
          query: finalQuery,
          loading: false,
          result: undefined,
        },
      ]);
      return;
    }

    const turnId = `${Date.now()}`;
    setLoading(true);
    setQuery("");
    setTurns((prev) => [...prev, { id: turnId, query: finalQuery, loading: true }]);
    setRecentHistory((prev) => [finalQuery, ...prev.filter((item) => item !== finalQuery)].slice(0, 10));

    try {
      const data = await queryMedTruth(finalQuery, 8, true, true, session?.user?.email ?? undefined);
      setTurns((prev) =>
        prev.map((turn) => (turn.id === turnId ? { ...turn, loading: false, result: data } : turn))
      );
      if (session?.user?.email) {
        await syncUser({
          email: session.user.email,
          name: session.user.name,
          image: session.user.image,
        });
        await handleSaveTurn({
          id: turnId,
          query: finalQuery,
          loading: false,
          result: data,
        });
      }
    } catch {
      const errorResult: QueryResponse = {
        query: finalQuery,
        domain: "general",
        answer:
          "Could not reach the backend service. Please confirm the API is running and reachable, then try again.",
        confidence: 0,
        confidence_band: "LOW",
        rejected: true,
        rejection_reason: "network_error",
        citations: [],
        bibliography: "",
        evidence_summary: "Request failed before retrieval completed.",
        risk_flags: [],
        overall_risk: "NONE",
        contradictions: [],
        hallucination_check: null,
        sources_retrieved: 0,
        sources_trusted: 0,
        sources_rejected: 0,
        mode: "fallback",
        fallback_reason: "provider_error_after_retrieval_empty",
        provider_used: "none",
      };
      setTurns((prev) =>
        prev.map((turn) => (turn.id === turnId ? { ...turn, loading: false, result: errorResult } : turn))
      );
    } finally {
      setLoading(false);
    }
  };

  const jumpToSource = (sourceIndex: number) => {
    setHighlightedSourceIndex(sourceIndex);
    const el = document.getElementById(`source-${sourceIndex}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const handleSaveTurn = async (turn: ChatTurn) => {
    if (!session?.user?.email || !turn.result) return;
    const answerText = turn.result.answer;
    if (savedTurnIds.includes(turn.id)) return;
    setSavingTurnId(turn.id);
    setFailedTurnIds((prev) => prev.filter((id) => id !== turn.id));
    try {
      await saveAnswer(session.user.email, {
        query: turn.query,
        answer: turn.result.answer,
        confidence: turn.result.confidence,
        confidence_band: turn.result.confidence_band,
        mode: turn.result.mode,
        citations_count: turn.result.citations?.length ?? 0,
      });
      setSavedTurnIds((prev) => [...prev, turn.id]);
      setSavedCount((prev) => prev + 1);
      setSavedAnswers((prev) => {
        const nextItem = { query: turn.query, answer: answerText, savedAt: new Date().toISOString() };
        return [nextItem, ...prev.filter((item) => item.query !== turn.query)].slice(0, 10);
      });
      router.refresh();
    } catch {
      setFailedTurnIds((prev) => [...prev, turn.id]);
    } finally {
      setSavingTurnId((prev) => (prev === turn.id ? null : prev));
    }
  };

  const handleSavedClick = (saved: SavedInsight) => {
    void handleSubmit(saved.query);
  };

  const toggleTheme = () => {
    const root = document.documentElement;
    const isDark = root.classList.toggle("dark");
    localStorage.setItem("theme", isDark ? "dark" : "light");
    setDarkMode(isDark);
  };

  return (
      <div className="flex min-h-screen w-full bg-gradient-to-b from-slate-50 to-slate-100 text-slate-900 transition-colors dark:from-[#0b1220] dark:to-[#0a0f1c] dark:text-slate-100">
        <Sidebar
          suggestions={EXAMPLE_QUERIES}
          history={recentHistory}
          savedAnswers={savedAnswers}
          savedCount={savedCount}
          userName={session?.user?.name}
          onSuggestionClick={(q) => handleSubmit(q)}
          onHistoryClick={(q) => handleSubmit(q)}
          onSavedClick={handleSavedClick}
          onNewQuery={() => setTurns([])}
        />

        <main className="w-full flex-1 px-4 py-6 md:px-6">
          <div className="w-full space-y-5">
          <header className="mb-4 flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-md backdrop-blur dark:border-slate-700 dark:bg-white/5">
            <div>
              <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">MedTruth AI</h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">ASK → THINKING → ANSWER → TRUST → EXPLORE</p>
            </div>
            <div className="flex items-center gap-2">
              <Link
                href="/admin"
                className="rounded-xl border border-slate-300 px-3 py-1.5 text-xs text-slate-700 dark:border-slate-600 dark:text-slate-200"
              >
                Admin
              </Link>
              <button
                onClick={toggleTheme}
                className="rounded-xl border border-slate-300 px-3 py-1.5 text-xs text-slate-700 dark:border-slate-600 dark:text-slate-200"
              >
                {darkMode ? "Light" : "Dark"}
              </button>
              <SignInButton />
            </div>
          </header>
          {showDebugPanel && (
            <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <p className="font-semibold text-slate-900 dark:text-slate-100">Internal System Health</p>
              <div className="mt-2 grid gap-3 md:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Modes</p>
                  <p className="mt-1 text-slate-700 dark:text-slate-300">
                    Requests: {modesHealth?.requests ?? "—"} · Cache hits: {modesHealth?.cache_hits ?? "—"}
                  </p>
                  {modesHealth && (
                    <div className="mt-1 space-y-0.5 text-slate-600 dark:text-slate-400">
                      <p>evidence_based: {modesHealth.mode_percentages.evidence_based}%</p>
                      <p>evidence_only: {modesHealth.mode_percentages.evidence_only}%</p>
                      <p>general_explanation: {modesHealth.mode_percentages.general_explanation}%</p>
                      <p>fallback: {modesHealth.mode_percentages.fallback}%</p>
                    </div>
                  )}
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Providers</p>
                  <div className="mt-1 space-y-0.5 text-slate-600 dark:text-slate-400">
                    {providersHealth
                      ? Object.entries(providersHealth.providers).map(([name, m]) => (
                          <p key={name}>
                            {name}: ok {m.success} / fail {m.failure} · last {m.last_latency_ms}ms
                          </p>
                        ))
                      : "Loading..."}
                  </div>
                  {activeResult?.request_id && (
                    <p className="mt-2 font-mono text-[11px] text-slate-500 dark:text-slate-600">
                      Last request_id: <span className="select-all text-slate-400">{activeResult.request_id}</span>
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="flex gap-5">
            <section className="min-w-0 flex-1 space-y-5 py-4">
              {/* Hero landing state — fills the viewport so there's no void */}
              {turns.length === 0 && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  className="flex min-h-[62vh] flex-col items-center justify-center px-4 py-12 text-center"
                >
                  <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 shadow-lg shadow-blue-900/40">
                    <span className="text-2xl">🔬</span>
                  </div>
                  <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 md:text-xl">
                    Ask an evidence-based medical question
                  </h2>
                  <p className="mt-2.5 max-w-xl text-sm text-slate-500 dark:text-slate-400">
                    Powered by peer-reviewed sources: PubMed · BMJ · The Lancet · WHO · Cochrane
                  </p>
                  <div className="mt-5 flex flex-wrap justify-center gap-2">
                    {["PubMed", "BMJ", "The Lancet", "WHO", "Cochrane", "Nature Med"].map((s) => (
                      <span
                        key={s}
                        className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 shadow-sm dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                  <div className="mt-8 w-full max-w-lg space-y-2">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-600">
                      Try asking
                    </p>
                    {EXAMPLE_QUERIES.map((q) => (
                      <button
                        key={q}
                        onClick={() => handleSubmit(q)}
                        className="flex w-full items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 shadow-sm transition-all hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-300 dark:hover:border-blue-500/60 dark:hover:bg-blue-950/40 dark:hover:text-blue-300"
                      >
                        <span className="shrink-0 text-slate-300 dark:text-slate-600">↗</span>
                        {q}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}

              {/* Chat turns */}
              <AnimatePresence>
                {turns.map((turn, idx) => (
                  <motion.div
                    key={turn.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.2 }}
                    className="space-y-3"
                  >
                    {/* User bubble */}
                    <div className="mb-4 flex justify-end">
                      <div className="max-w-[80%] rounded-2xl bg-blue-600 px-4 py-3 text-sm text-white shadow-md shadow-blue-900/30">
                        {turn.query}
                      </div>
                    </div>

                    {/* Thinking state — 3 bouncing dots + pipeline progress */}
                    {turn.loading && (
                      <div className="mb-4 max-w-[90%] rounded-2xl border border-slate-200 bg-white/60 p-4 backdrop-blur dark:border-[#1f2937] dark:bg-white/5 md:p-5">
                        <div className="flex items-center gap-3">
                          <div className="flex items-end gap-1">
                            {[0, 150, 300].map((delay) => (
                              <div
                                key={delay}
                                className="h-2 w-2 animate-bounce rounded-full bg-blue-500"
                                style={{ animationDelay: `${delay}ms` }}
                              />
                            ))}
                          </div>
                          <p className="text-sm font-medium text-slate-600 dark:text-slate-300">
                            {PIPELINE_MESSAGES[thinkingStep]}
                          </p>
                        </div>
                        <div className="mt-3 flex gap-2">
                          {PIPELINE_MESSAGES.map((step, i) => (
                            <div
                              key={step}
                              className={`h-1 flex-1 rounded-full transition-all duration-500 ${
                                i <= thinkingStep ? "bg-blue-500" : "bg-slate-200 dark:bg-slate-700"
                              }`}
                            />
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Short query hint */}
                    {!turn.loading && !turn.result && (
                      <div className="mb-4 max-w-[90%] rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
                        Try a more specific question, e.g.:
                        <div className="mt-2 space-y-1 text-slate-500 dark:text-slate-500">
                          <p>• Does aspirin reduce mortality in MI?</p>
                          <p>• Is CBT effective for depression?</p>
                        </div>
                      </div>
                    )}

                    {turn.result && (
                      <>
                        <AnswerResponseCard
                          query={turn.query}
                          result={turn.result}
                          currentUserEmail={session?.user?.email ?? undefined}
                          onSentenceHover={setHighlightedSourceIndex}
                          onSentenceClick={jumpToSource}
                          onSave={() => handleSaveTurn(turn)}
                          canSave={Boolean(session?.user?.email)}
                          onRequireSignIn={() => signIn("google")}
                          onRelatedQuery={(q) => handleSubmit(q)}
                          saveState={
                            savingTurnId === turn.id
                              ? "saving"
                              : savedTurnIds.includes(turn.id)
                                ? "saved"
                                : failedTurnIds.includes(turn.id)
                                  ? "error"
                                  : "idle"
                          }
                        />
                        {(turn.result.related_questions?.length ?? 0) > 0 && (
                          <RelatedQuestions
                            questions={turn.result.related_questions!}
                            onSelect={(q) => handleSubmit(q)}
                          />
                        )}
                      </>
                    )}
                    {idx < turns.length - 1 && <div className="my-4 border-t border-slate-200 dark:border-slate-800" />}
                  </motion.div>
                ))}
              </AnimatePresence>

              {/* Spacer — keeps last turn above the sticky input dock */}
              <div className="h-32" />

              <ChatInput
                value={query}
                loading={loading}
                suggestions={inputSuggestions}
                onChange={setQuery}
                onSubmit={() => handleSubmit()}
              />
            </section>

            {showSources && activeResult && (
              <aside className="hidden w-72 lg:block">
                <div className="sticky top-6 rounded-2xl border border-slate-200/70 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                  <p className="mb-0.5 text-[11px] font-medium uppercase tracking-widest text-slate-400 dark:text-slate-500">Sources</p>
                  <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
                    Hover a sentence · click to jump
                  </p>
                  <CitationPanel
                    citations={activeResult.citations}
                    highlightedSourceIndex={highlightedSourceIndex}
                  />
                </div>
              </aside>
            )}
          </div>
          </div>
        </main>

        {activeResult && (
          <>
            <button
              onClick={() => setShowSources((prev) => !prev)}
              className="fixed bottom-20 right-4 hidden rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm shadow-md lg:block dark:border-slate-700 dark:bg-slate-900"
            >
              {showSources ? "Hide Sources" : "Show Sources"}
            </button>
            <button
              onClick={() => setShowMobileSources(true)}
              className="fixed bottom-4 right-4 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm shadow-md lg:hidden dark:border-slate-700 dark:bg-slate-900"
            >
              Sources
            </button>
          </>
        )}

        {showMobileSources && activeResult && (
          <div className="fixed inset-0 z-50 bg-slate-900/50 lg:hidden" onClick={() => setShowMobileSources(false)}>
            <div
              onClick={(e) => e.stopPropagation()}
              className="absolute bottom-0 left-0 right-0 max-h-[75vh] rounded-t-2xl bg-white p-4 dark:bg-slate-900"
            >
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold">Live Evidence View</h3>
                <button
                  onClick={() => setShowMobileSources(false)}
                  className="rounded-lg border border-slate-300 px-2 py-1 text-xs dark:border-slate-600"
                >
                  Close
                </button>
              </div>
              <CitationPanel citations={activeResult.citations} highlightedSourceIndex={highlightedSourceIndex} />
            </div>
          </div>
        )}
      </div>
  );
}
