const API_BASE = process.env.NEXT_PUBLIC_API_URL!;

export interface Citation {
  index: number;
  pmid: string | null;
  doi: string | null;
  title: string;
  authors: string[];
  journal: string;
  pub_year: number;
  source: string;
  medeva_total: number | null;
  confidence_band: string | null;
  url: string;
  is_aha: boolean;
}

export interface RiskFlag {
  level: "HIGH" | "MEDIUM" | "LOW";
  category: string;
  message: string;
  banner_color: string;
}

export interface ContradictionPair {
  doc_a: { index: number; title: string; conclusion: string; medeva_score: number };
  doc_b: { index: number; title: string; conclusion: string; medeva_score: number };
  topic_similarity: number;
  conclusion_similarity: number;
  contradiction_score: number;
  higher_evidence_index: number;
  summary: string;
}

export interface HallucinationCheck {
  hallucination_risk: "LOW" | "MEDIUM" | "HIGH";
  hallucination_score: number;
  verified_count: number;
  unverified_count: number;
  unverified_claims: { claim: string; entailment_score: number }[];
  safe_answer: string;
}

export interface SelectionRationale {
  why_selected: Array<{
    title: string;
    study_type: string;
    journal: string;
    pub_year: number | string;
    medeva_score: number;
    confidence_band: string;
    reason: string;
  }>;
  why_excluded: string[];
  filter_summary: string;
}

export interface QueryResponse {
  query: string;
  domain: string;
  answer: string;
  confidence: number;
  confidence_band: "HIGH" | "MEDIUM" | "LOW";
  rejected: boolean;
  rejection_reason: string | null;
  citations: Citation[];
  bibliography: string;
  evidence_summary: string;
  risk_flags: RiskFlag[];
  overall_risk: string;
  contradictions: ContradictionPair[];
  hallucination_check: HallucinationCheck | null;
  sources_retrieved: number;
  sources_trusted: number;
  sources_rejected: number;
  mode?: "evidence_based" | "general_explanation" | "evidence_only" | "fallback";
  fallback_reason?: string | null;
  provider_used?: string;
  provider_attempts?: string[];
  confidence_details?: {
    retrieved: number;
    trusted: number;
    excluded: number;
    contradictions: number;
    low_support_claims: number;
    evidence_types: string[];
    // Enhanced fields (Task 3+4)
    contradiction_flag?: boolean;
    contradiction_summary?: string;
    study_agreement?: "mixed" | "consistent";
    evidence_diversity?: number;
  };
  confidence_explanation?: string;
  // Task 1: Related questions
  related_questions?: string[];
  // Task 3: Selection rationale
  selection_rationale?: SelectionRationale;
  // Populated client-side from X-Request-ID response header; not sent by the backend JSON body.
  request_id?: string;
}

export interface SavedAnswer {
  query: string;
  answer: string;
  answer_hash: string;
  saved_at: string;
  confidence?: number;
  confidence_band?: string;
  mode?: string;
  citations_count?: number;
}

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  image: string | null;
  created_at: string;
  usage_count: number;
  query_history: string[];
  saved_answers: SavedAnswer[];
  most_searched_condition: string | null;
}

export interface CommentValidation {
  type: "VALID" | "QUESTION" | "MISINFORMATION";
  confidence: number;
  reason: string;
  suggested_action: string;
  query_suggestion: string | null;
  action: "approved" | "held_for_review" | "blocked" | "converted_to_query";
}

export interface ModesHealth {
  requests: number;
  cache_hits: number;
  mode_counts: {
    evidence_based: number;
    evidence_only: number;
    general_explanation: number;
    fallback: number;
  };
  mode_percentages: {
    evidence_based: number;
    evidence_only: number;
    general_explanation: number;
    fallback: number;
  };
  error_signals: {
    provider_error_count: number;
    retrieval_empty_count: number;
  };
}

export interface ProvidersHealth {
  providers: Record<
    string,
    {
      success: number;
      failure: number;
      last_latency_ms: number;
    }
  >;
}

export async function queryMedTruth(
  query: string,
  topK = 8,
  enableEntailment = true,
  enableContradictions = true,
  userEmail?: string
): Promise<QueryResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (userEmail) headers["X-User-Email"] = userEmail;
  const res = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      query,
      top_k: topK,
      enable_entailment_check: enableEntailment,
      enable_contradiction_check: enableContradictions,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Request failed");
  }
  const data = (await res.json()) as QueryResponse;
  data.request_id = res.headers.get("X-Request-ID") ?? undefined;
  return data;
}

export async function explainAnswer(payload: { query: string; answer: string }): Promise<string> {
  const res = await fetch(`${API_BASE}/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ technical_answer: payload.answer }),
  });
  if (!res.ok) throw new Error("Explanation failed");
  const data = await res.json();
  return data.plain_language_answer;
}

export async function validateSource(params: {
  doi?: string;
  pmid?: string;
  journal?: string;
  url?: string;
}) {
  const res = await fetch(`${API_BASE}/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`Validation request failed: ${res.status}`);
  return res.json();
}

function userHeaders(email: string) {
  return {
    "Content-Type": "application/json",
    "X-User-Email": email,
  };
}

export async function syncUser(payload: { email: string; name?: string | null; image?: string | null }) {
  const res = await fetch(`${API_BASE}/user/sync`, {
    method: "POST",
    headers: userHeaders(payload.email),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to sync user");
  return res.json() as Promise<UserProfile>;
}

export async function getUserHistory(email: string) {
  const res = await fetch(`${API_BASE}/user/history`, {
    method: "GET",
    headers: userHeaders(email),
  });
  if (!res.ok) throw new Error("Failed to load history");
  return res.json() as Promise<UserProfile>;
}

export async function saveAnswer(
  email: string,
  payload: {
    query: string;
    answer: string;
    confidence?: number;
    confidence_band?: string;
    mode?: string;
    citations_count?: number;
  }
) {
  const res = await fetch(`${API_BASE}/user/save`, {
    method: "POST",
    headers: userHeaders(email),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to save answer");
  return res.json() as Promise<{ status: string }>;
}

export async function deleteSavedAnswer(email: string, answerHash: string) {
  const res = await fetch(`${API_BASE}/user/saved/${answerHash}`, {
    method: "DELETE",
    headers: userHeaders(email),
  });
  if (!res.ok) throw new Error("Failed to delete saved answer");
  return res.json() as Promise<{ status: string }>;
}

export async function validateComment(payload: {
  comment: string;
  answer: string;
  evidence_titles?: string[];
  anchor_sentence?: string | null;
  anchor_citation_title?: string | null;
}): Promise<CommentValidation> {
  const res = await fetch(`${API_BASE}/discuss/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Moderation failed");
  return res.json();
}

export async function getModesHealth(): Promise<ModesHealth> {
  const res = await fetch(`${API_BASE}/health/modes`, { method: "GET" });
  if (!res.ok) throw new Error("Failed to load mode health");
  return res.json();
}

export async function getProvidersHealth(): Promise<ProvidersHealth> {
  const res = await fetch(`${API_BASE}/health/providers`, { method: "GET" });
  if (!res.ok) throw new Error("Failed to load provider health");
  return res.json();
}
