"use client";

import { useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

type AdminUser = {
  email: string;
  name: string;
  usage_count: number;
  saved_answers_count: number;
  last_query: string | null;
};

type UserDetail = {
  email: string;
  name: string;
  usage_count: number;
  query_history: string[];
  saved_answers: Array<{
    query: string;
    mode?: string;
    confidence?: number;
    saved_at: string;
  }>;
};

type ActivityItem = { email: string; query: string };

type FailureItem = {
  request_id: string;
  query: string;
  mode: string;
  fallback_reason: string;
  provider_used: string;
  timestamp: string;
};

type DiscussionItem = {
  user_email: string;
  query: string;
  comment: string;
  validation: "VALID" | "QUESTION" | "MISINFORMATION";
  confidence: number;
  action: "approved" | "held_for_review" | "blocked" | "converted_to_query";
  created_at: string;
  query_suggestion?: string | null;
};

type ProviderHealth = Record<string, {
  success: number;
  failure: number;
  total_calls: number;
  success_rate: number | null;       // pre-computed server-side
  last_latency_ms: number;           // last successful call
  last_fail_latency_ms: number;      // last failed attempt (0 if never failed)
}>;

type Tab = "users" | "activity" | "discussions" | "failures" | "health";

// ── API helpers ───────────────────────────────────────────────────────────────

const BASE = process.env.NEXT_PUBLIC_API_URL!;

async function adminFetch<T>(path: string, key: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "X-Admin-Key": key },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} — ${body}`);
  }
  return res.json() as Promise<T>;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const [key, setKey]               = useState("");
  const [authed, setAuthed]         = useState(false);
  const [tab, setTab]               = useState<Tab>("users");
  const [users, setUsers]           = useState<AdminUser[]>([]);
  const [selectedUser, setSelectedUser] = useState<UserDetail | null>(null);
  const [activity, setActivity]     = useState<ActivityItem[]>([]);
  const [discussions, setDiscussions] = useState<DiscussionItem[]>([]);
  const [failures, setFailures]     = useState<FailureItem[]>([]);
  const [providers, setProviders]   = useState<ProviderHealth>({});
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState<string | null>(null);

  // ── Auth ───────────────────────────────────────────────────────────────────

  const connect = async (adminKey: string) => {
    setLoading(true);
    setError(null);
    try {
      const [u, a, d, f, h] = await Promise.all([
        adminFetch<{ users: AdminUser[] }>("/admin/users", adminKey),
        adminFetch<{ activity: ActivityItem[] }>("/admin/activity", adminKey),
        adminFetch<{ discussions: DiscussionItem[] }>("/admin/discussions", adminKey),
        adminFetch<{ failures: FailureItem[] }>("/admin/failures", adminKey),
        adminFetch<{ providers: ProviderHealth }>("/admin/health", adminKey),
      ]);
      setUsers(u.users);
      setActivity(a.activity);
      setDiscussions(d.discussions);
      setFailures(f.failures);
      setProviders(h.providers);
      setAuthed(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  const refresh = async () => {
    if (!key) return;
    setError(null);
    try {
      const [u, a, d, f, h] = await Promise.all([
        adminFetch<{ users: AdminUser[] }>("/admin/users", key),
        adminFetch<{ activity: ActivityItem[] }>("/admin/activity", key),
        adminFetch<{ discussions: DiscussionItem[] }>("/admin/discussions", key),
        adminFetch<{ failures: FailureItem[] }>("/admin/failures", key),
        adminFetch<{ providers: ProviderHealth }>("/admin/health", key),
      ]);
      setUsers(u.users);
      setActivity(a.activity);
      setDiscussions(d.discussions);
      setFailures(f.failures);
      setProviders(h.providers);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Refresh failed");
    }
  };

  const loadUser = async (email: string) => {
    setError(null);
    try {
      const data = await adminFetch<UserDetail>(`/admin/user/${encodeURIComponent(email)}`, key);
      setSelectedUser(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load user");
    }
  };

  // ── Login screen ───────────────────────────────────────────────────────────

  if (!authed) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 p-6">
        <div className="w-full max-w-sm space-y-3 rounded-lg border border-slate-700 bg-slate-900 p-6">
          <h1 className="font-mono text-sm font-semibold text-slate-300">
            MedTruth · Internal Admin
          </h1>
          <p className="font-mono text-xs text-slate-500">Admin key required</p>
          <input
            type="password"
            placeholder="ADMIN_SECRET"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && key && connect(key)}
            className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-slate-500 focus:ring-0"
          />
          {error && (
            <p className="font-mono text-xs text-rose-400">{error}</p>
          )}
          <button
            onClick={() => key && connect(key)}
            disabled={!key || loading}
            className="w-full rounded bg-slate-700 px-3 py-2 font-mono text-sm text-slate-100 hover:bg-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? "Connecting…" : "Connect"}
          </button>
        </div>
      </main>
    );
  }

  // ── Admin dashboard ────────────────────────────────────────────────────────

  const TABS: { id: Tab; label: string }[] = [
    { id: "users",    label: `users (${users.length})` },
    { id: "activity", label: `activity (${activity.length})` },
    { id: "discussions", label: `discussions (${discussions.length})` },
    { id: "failures", label: `failures (${failures.length})` },
    { id: "health",   label: "health" },
  ];

  return (
    <main className="min-h-screen bg-slate-950 p-6 font-mono text-slate-100">
      <div className="mx-auto max-w-5xl space-y-4">

        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <span className="text-xs text-slate-500">MedTruth · Internal Admin Panel</span>
          <div className="flex items-center gap-3">
            <button
              onClick={refresh}
              className="text-xs text-slate-500 hover:text-slate-300"
            >
              ↻ refresh
            </button>
            <button
              onClick={() => { setAuthed(false); setKey(""); setSelectedUser(null); }}
              className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-500 hover:border-slate-500 hover:text-slate-300"
            >
              disconnect
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => { setTab(id); if (id !== "users") setSelectedUser(null); }}
              className={`rounded px-3 py-1 text-xs transition-colors ${
                tab === id
                  ? "bg-slate-700 text-slate-100"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Error banner */}
        {error && (
          <div className="flex items-center justify-between rounded border border-rose-800 bg-rose-950/60 px-3 py-2">
            <span className="text-xs text-rose-400">{error}</span>
            <button onClick={() => setError(null)} className="text-xs text-rose-600 hover:text-rose-400">✕</button>
          </div>
        )}

        {/* ── Users tab ──────────────────────────────────────────────────────── */}
        {tab === "users" && (
          <div className="grid gap-4 lg:grid-cols-2">
            {/* Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-normal">Email</th>
                    <th className="pb-2 pr-4 text-right font-normal">Queries</th>
                    <th className="pb-2 text-right font-normal">Saved</th>
                  </tr>
                </thead>
                <tbody>
                  {users.length === 0 && (
                    <tr>
                      <td colSpan={3} className="py-4 text-slate-600">No users yet.</td>
                    </tr>
                  )}
                  {users.map((u) => (
                    <tr
                      key={u.email}
                      onClick={() => { loadUser(u.email); }}
                      className={`cursor-pointer border-b border-slate-800/40 transition-colors hover:bg-slate-800/40 ${
                        selectedUser?.email === u.email ? "bg-slate-800/60" : ""
                      }`}
                    >
                      <td className="py-2 pr-4">
                        <div className="text-slate-200">{u.email}</div>
                        {u.name && <div className="text-slate-600">{u.name}</div>}
                      </td>
                      <td className="py-2 pr-4 text-right text-slate-400">{u.usage_count}</td>
                      <td className="py-2 text-right text-slate-400">{u.saved_answers_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Detail panel */}
            {selectedUser && (
              <div className="rounded border border-slate-800 bg-slate-900 p-4">
                <div className="mb-3 flex items-start justify-between gap-2">
                  <div>
                    <p className="text-xs text-slate-200">{selectedUser.email}</p>
                    {selectedUser.name && (
                      <p className="text-xs text-slate-600">{selectedUser.name}</p>
                    )}
                  </div>
                  <button
                    onClick={() => setSelectedUser(null)}
                    className="text-slate-600 hover:text-slate-400"
                  >
                    ✕
                  </button>
                </div>

                <p className="mb-3 text-[11px] text-slate-500">
                  {selectedUser.usage_count} queries · {selectedUser.saved_answers.length} saved
                </p>

                {/* Recent queries */}
                {selectedUser.query_history.length > 0 && (
                  <div className="mb-4">
                    <p className="mb-1.5 text-[11px] uppercase tracking-widest text-slate-600">Recent queries</p>
                    <ul className="space-y-1">
                      {[...selectedUser.query_history].reverse().slice(0, 8).map((q, i) => (
                        <li key={i} className="truncate text-[11px] text-slate-400">
                          <span className="mr-1 text-slate-700">·</span>{q}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Saved answers */}
                {selectedUser.saved_answers.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-[11px] uppercase tracking-widest text-slate-600">Saved answers</p>
                    <ul className="space-y-2">
                      {[...selectedUser.saved_answers].reverse().slice(0, 5).map((s, i) => (
                        <li key={i} className="text-[11px]">
                          <div className="truncate text-slate-300">{s.query}</div>
                          <div className="mt-0.5 flex gap-2 text-slate-600">
                            {s.mode && <span>{s.mode.replace(/_/g, " ")}</span>}
                            {s.confidence != null && (
                              <span>{Math.round(s.confidence * 100)}% conf</span>
                            )}
                            <span>{new Date(s.saved_at).toLocaleDateString()}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Activity tab ───────────────────────────────────────────────────── */}
        {tab === "activity" && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-left text-slate-500">
                  <th className="pb-2 pr-6 font-normal">Email</th>
                  <th className="pb-2 font-normal">Query</th>
                </tr>
              </thead>
              <tbody>
                {activity.length === 0 && (
                  <tr>
                    <td colSpan={2} className="py-4 text-slate-600">No activity yet.</td>
                  </tr>
                )}
                {activity.map((a, i) => (
                  <tr key={i} className="border-b border-slate-800/40">
                    <td className="py-2 pr-6 text-slate-500">{a.email}</td>
                    <td className="py-2 text-slate-300">{a.query}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Failures tab ───────────────────────────────────────────────────── */}
        {tab === "failures" && (
          failures.length === 0 ? (
            <p className="text-xs text-slate-600">
              No failures recorded since last restart.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-normal">Time</th>
                    <th className="pb-2 pr-4 font-normal">Request ID</th>
                    <th className="pb-2 pr-4 font-normal">Mode</th>
                    <th className="pb-2 pr-4 font-normal">Reason</th>
                    <th className="pb-2 pr-4 font-normal">Provider</th>
                    <th className="pb-2 font-normal">Query</th>
                  </tr>
                </thead>
                <tbody>
                  {failures.map((f, i) => (
                    <tr key={i} className="border-b border-slate-800/40">
                      <td className="py-2 pr-4 text-slate-600">
                        {new Date(f.timestamp).toLocaleTimeString()}
                      </td>
                      <td className="py-2 pr-4">
                        <span className="select-all text-slate-500">{f.request_id}</span>
                      </td>
                      <td className="py-2 pr-4">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] ${
                          f.mode === "fallback"
                            ? "bg-rose-900/50 text-rose-300"
                            : "bg-amber-900/50 text-amber-300"
                        }`}>
                          {f.mode}
                        </span>
                      </td>
                      <td className="py-2 pr-4 text-slate-400">{f.fallback_reason}</td>
                      <td className="py-2 pr-4 text-slate-500">{f.provider_used}</td>
                      <td className="max-w-xs truncate py-2 text-slate-300">{f.query}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}

        {/* ── Discussions tab ────────────────────────────────────────────────── */}
        {tab === "discussions" && (
          discussions.length === 0 ? (
            <p className="text-xs text-slate-600">No moderated submissions yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-left text-slate-500">
                    <th className="pb-2 pr-4 font-normal">Time</th>
                    <th className="pb-2 pr-4 font-normal">User</th>
                    <th className="pb-2 pr-4 font-normal">Validation</th>
                    <th className="pb-2 pr-4 font-normal">Action</th>
                    <th className="pb-2 pr-4 font-normal">Comment</th>
                    <th className="pb-2 font-normal">Query</th>
                  </tr>
                </thead>
                <tbody>
                  {discussions.map((d, i) => (
                    <tr key={i} className="border-b border-slate-800/40">
                      <td className="py-2 pr-4 text-slate-600">
                        {new Date(d.created_at).toLocaleString()}
                      </td>
                      <td className="py-2 pr-4 text-slate-400">{d.user_email}</td>
                      <td className="py-2 pr-4 text-slate-300">
                        {d.validation} ({Math.round((d.confidence ?? 0) * 100)}%)
                      </td>
                      <td className="py-2 pr-4 text-slate-400">{d.action}</td>
                      <td className="max-w-xs truncate py-2 pr-4 text-slate-300">{d.comment}</td>
                      <td className="max-w-xs truncate py-2 text-slate-400">{d.query}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}

        {/* ── Health tab ─────────────────────────────────────────────────────── */}
        {tab === "health" && (
          <div className="space-y-4">
            <p className="text-[11px] uppercase tracking-widest text-slate-600">LLM Providers</p>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-left text-slate-500">
                  <th className="pb-2 pr-4 font-normal">Provider</th>
                  <th className="pb-2 pr-4 text-right font-normal">OK</th>
                  <th className="pb-2 pr-4 text-right font-normal">Fail</th>
                  <th className="pb-2 pr-4 text-right font-normal">Rate</th>
                  <th className="pb-2 pr-4 text-right font-normal">OK ms</th>
                  <th className="pb-2 text-right font-normal">Fail ms</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(providers).map(([name, m]) => {
                  const rate = m.success_rate != null
                    ? `${Math.round(m.success_rate * 100)}%`
                    : "—";
                  const rateColor = m.success_rate == null
                    ? "text-slate-600"
                    : m.success_rate >= 0.9
                      ? "text-emerald-400"
                      : m.success_rate >= 0.5
                        ? "text-amber-400"
                        : "text-rose-400";
                  return (
                    <tr key={name} className="border-b border-slate-800/40">
                      <td className="py-2 pr-4 text-slate-300">{name}</td>
                      <td className="py-2 pr-4 text-right text-emerald-400">{m.success}</td>
                      <td className="py-2 pr-4 text-right text-rose-400">{m.failure}</td>
                      <td className={`py-2 pr-4 text-right font-semibold ${rateColor}`}>{rate}</td>
                      <td className="py-2 pr-4 text-right text-slate-400">
                        {m.last_latency_ms > 0 ? `${m.last_latency_ms}ms` : "—"}
                      </td>
                      <td className="py-2 text-right text-slate-600">
                        {m.last_fail_latency_ms > 0 ? `${m.last_fail_latency_ms}ms` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
