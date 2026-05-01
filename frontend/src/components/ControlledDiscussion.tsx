"use client";

import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, ArrowRight, CheckCircle, HelpCircle, Send, XCircle } from "lucide-react";
import { useState } from "react";
import {
  submitDiscussion,
  type CommentValidation,
  type DiscussionSubmission,
} from "@/lib/api";

interface ControlledDiscussionProps {
  query: string;
  answer: string;
  evidenceTitles: string[];
  anchorSentence?: string;
  userEmail?: string;
  answerId?: string;
  onQuerySuggestion?: (query: string) => void;
}

type CommentState =
  | { phase: "idle" }
  | { phase: "validating" }
  | {
      phase: "result";
      validation: CommentValidation;
      comment: string;
      submission: DiscussionSubmission;
    }
  | { phase: "error"; message: string };

export default function ControlledDiscussion({
  query,
  answer,
  evidenceTitles,
  anchorSentence,
  userEmail,
  answerId,
  onQuerySuggestion,
}: ControlledDiscussionProps) {
  const [open, setOpen]       = useState(false);
  const [comment, setComment] = useState("");
  const [state, setState]     = useState<CommentState>({ phase: "idle" });

  const handleSubmit = async () => {
    const text = comment.trim();
    if (!text || text.length < 5) return;
    if (!userEmail) {
      setState({ phase: "error", message: "Sign in to submit notes for moderation." });
      return;
    }
    setState({ phase: "validating" });
    try {
      const result = await submitDiscussion(userEmail, {
        query,
        answer_id: answerId ?? null,
        comment: text,
        answer,
        evidence_titles: evidenceTitles,
        anchor_sentence: anchorSentence ?? null,
      });
      setState({
        phase: "result",
        validation: result.validation,
        comment: text,
        submission: result.submission,
      });
    } catch {
      setState({ phase: "error", message: "Submission failed. Try again later." });
    }
  };

  const reset = () => {
    setComment("");
    setState({ phase: "idle" });
  };

  return (
    <div className="mt-4">
      {/* Toggle label */}
      <button
        onClick={() => setOpen((p) => !p)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-[11px] font-medium uppercase tracking-widest text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300">
          Add a question or note
        </span>
        <span className="text-[11px] text-slate-300 dark:text-slate-600">{open ? "▾" : "▸"}</span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            {/* Helper text */}
            <p className="mt-3 text-xs leading-relaxed text-slate-400 dark:text-slate-500">
              Ask a question or add a note about this answer — it will be checked against
              the supporting evidence before surfacing.
              {anchorSentence && (
                <span className="ml-1 italic opacity-80">
                  Anchored to: &ldquo;{anchorSentence.slice(0, 70)}…&rdquo;
                </span>
              )}
            </p>

            {/* Input or result */}
            {state.phase === "idle" || state.phase === "error" ? (
              <div className="mt-3 space-y-2">
                {state.phase === "error" && (
                  <div className="flex items-center gap-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600 dark:bg-rose-900/20 dark:text-rose-400">
                    <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
                    {state.message}
                  </div>
                )}
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  rows={3}
                  maxLength={1000}
                  placeholder="e.g. What about patients with kidney disease? Is there a contraindication?"
                  className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 placeholder-slate-300 outline-none transition focus:border-blue-300 focus:bg-white focus:ring-0 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200 dark:placeholder-slate-600 dark:focus:border-blue-700 dark:focus:bg-slate-800"
                />
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-slate-300 dark:text-slate-600">
                    {comment.length}/1000
                  </span>
                  <button
                    onClick={handleSubmit}
                    disabled={comment.trim().length < 5 || !userEmail}
                    className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    <Send className="h-3 w-3" />
                    Submit for review
                  </button>
                </div>
              </div>
            ) : state.phase === "validating" ? (
              <div className="mt-3 flex items-center gap-2 text-xs text-slate-400">
                <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-200 border-t-slate-500" />
                Checking against evidence…
              </div>
            ) : (
              <ModerationResult
                state={state}
                onQuerySuggestion={onQuerySuggestion}
                onReset={reset}
              />
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Moderation result ─────────────────────────────────────────────────────────

function ModerationResult({
  state,
  onQuerySuggestion,
  onReset,
}: {
  state: Extract<CommentState, { phase: "result" }>;
  onQuerySuggestion?: (q: string) => void;
  onReset: () => void;
}) {
  const { validation } = state;
  const statusLabel =
    validation.action === "approved"
      ? "approved"
      : validation.action === "held_for_review"
        ? "in review"
        : validation.action === "blocked"
          ? "blocked"
          : "converted";

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-3 space-y-3"
    >
      {/* ── VALID ─────────────────────────────────────────────────────────── */}
      {validation.type === "VALID" && (
        <div className="flex items-start gap-2.5 rounded-xl bg-emerald-50 px-4 py-3 dark:bg-emerald-900/20">
          <CheckCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald-500" />
          <div>
            <p className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
              {validation.action === "held_for_review"
                ? "Submitted for review"
                : "Consistent with the evidence"}
            </p>
            <p className="mt-0.5 text-[11px] text-emerald-600/80 dark:text-emerald-400/80">
              {validation.action === "held_for_review"
                ? "Your note will be reviewed before being shown publicly."
                : validation.reason || "Your note aligns with the retrieved evidence."}
            </p>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-500 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400">
        <p>
          Submission status:{" "}
          <span className="font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
            {statusLabel}
          </span>
        </p>
        <p>
          Submitted at: {new Date(state.submission.created_at).toLocaleString()}
        </p>
      </div>

      {/* ── QUESTION → offer to search ────────────────────────────────────── */}
      {validation.type === "QUESTION" && (
        <div className="rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 dark:border-blue-900/40 dark:bg-blue-950/20">
          <div className="flex items-start gap-2.5">
            <HelpCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-blue-500" />
            <div className="min-w-0">
              <p className="text-xs font-medium text-blue-700 dark:text-blue-300">
                That looks like a question
              </p>
              {validation.query_suggestion && (
                <>
                  <p className="mt-1 text-[11px] text-blue-600 dark:text-blue-400">
                    Want to search for:
                  </p>
                  <p className="mt-0.5 text-xs font-semibold text-blue-800 dark:text-blue-200">
                    &ldquo;{validation.query_suggestion}&rdquo;
                  </p>
                  {onQuerySuggestion && (
                    <button
                      onClick={() => onQuerySuggestion(validation.query_suggestion!)}
                      className="mt-2 flex items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 py-1 text-xs font-medium text-blue-700 transition hover:bg-blue-50 dark:border-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
                    >
                      Search this question
                      <ArrowRight className="h-3 w-3" />
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── MISINFORMATION — calm, clear ────────────────────────────────────── */}
      {validation.type === "MISINFORMATION" && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800/60">
          <div className="flex items-start gap-2.5">
            <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-rose-400" />
            <div>
              <p className="text-xs font-medium text-slate-700 dark:text-slate-200">
                Not supported by the available evidence
              </p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
                {validation.reason || "The retrieved studies do not support this claim."}
              </p>
              {validation.suggested_action && (
                <p className="mt-1.5 text-[11px] text-slate-400 dark:text-slate-500">
                  {validation.suggested_action}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <button
        onClick={onReset}
        className="text-[11px] text-slate-400 underline-offset-2 hover:text-slate-500 hover:underline dark:text-slate-500 dark:hover:text-slate-400"
      >
        Submit another note
      </button>
    </motion.div>
  );
}
