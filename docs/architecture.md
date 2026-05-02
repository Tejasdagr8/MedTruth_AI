# System architecture

High-level overview of how a query flows through the system.

---

## Request lifecycle

```
POST /api/v1/query
       │
       ▼
  Cache check (60s TTL, keyed by query hash)
  → Cache hit: return immediately
       │
       ▼
  Query expansion
  Broad queries (≤6 tokens, no medical terms) get
  "mechanism of action clinical uses effectiveness safety" appended.
  This improves retrieval recall without affecting the LLM prompt.
       │
       ▼
  Async retrieval  ─── asyncio.gather() across all four clients
  │  PubMedClient      NCBI E-utilities (esearch + efetch, XML)
  │  EuropePMCClient   REST API — BMJ, Lancet, Nature Medicine
  │  WHOClient         WHO IRIS OAI-PMH
  │  CochraneClient    Europe PMC filtered to Cochrane ISSN
  └──────────────────────────────────────────────────
  Results deduplicated by document ID. Any client that
  times out or errors is skipped silently — the others continue.
       │
       ▼
  Source validation gate
  Each doc checked against: blocked domain → ISSN → PMID → DOI prefix → journal name → source tag
  TRUSTED docs pass. REJECTED/UNVERIFIABLE docs are dropped.
  is_aha flag and trust_tier stamped into metadata here.
       │
       ▼
  MEDEVA ranking
  Each trusted doc scored on 5 signals (evidence level, impact factor,
  recency, citation count, sample size) + AHA authority bonus.
  Sorted descending. Top-K selected for context window.
       │
       ▼
  ChromaDB upsert + hybrid search
  Fresh docs embedded with BioBERT and upserted into ChromaDB.
  Repeated queries benefit from cached embeddings.
  Hybrid score = 0.6 × semantic_similarity + 0.4 × medeva_total
       │
       ▼
  LangGraph pipeline
  ├── Contradiction detection (pairwise topic/conclusion similarity)
  ├── Hallucination check setup
  └── Confidence computation
       │
       ▼
  RAG generation (Claude)
  Strict system prompt: answer ONLY from [SOURCE n] blocks.
  Model either produces a cited answer or INSUFFICIENT_EVIDENCE:.
  Context window is MEDEVA-ranked top-K docs, truncated to ~24K chars.
       │
       ▼
  Post-generation checks
  ├── NLI entailment — DeBERTa-v3 claim-vs-source check
  │   Claims below threshold get [⚠ Some uncertainty in evidence] prefix
  ├── Citation anchoring — map [n] markers to bibliography entries
  └── Confidence tone prefix added based on final score
       │
       ▼
  Risk flagging
  Pattern-matched against query + answer text.
  Returns RiskFlag list with category, level, banner_color.
       │
       ▼
  Response assembled
  ~25 fields: answer, citations, confidence, mode, risk_flags,
  contradictions, hallucination_check, source stats, provider trace.
```

Total p50 latency under normal conditions: ~3–5s (dominated by PubMed + LLM calls).

---

## Component map

```
api/
  main.py              FastAPI app, CORS, correlation ID + timing middleware
  dependencies.py      Singleton injectors (one instance of each client per process)
  failure_log.py       In-memory + Mongo failure event log
  routes/
    query.py           Main pipeline orchestration, cache, metrics
    validate.py        Standalone source trust check
    explain.py         Plain language rewrite (second LLM call)
    contradictions.py  Standalone contradiction scan
    user.py            Profile sync, history, saved answers
    discuss.py         Comment validation + moderated submission
    llm_lab.py         Experimental agent endpoint
    admin.py           Operator dashboard (guarded by ADMIN_SECRET)

src/
  config/
    trusted_journals.py  AHA registry: 12 journals, ISSNs, IFs, DOI prefix

  retrieval/
    pubmed_client.py        NCBI E-utilities XML parsing
    europepmc_client.py     Europe PMC REST
    who_cochrane_client.py  WHO IRIS + Cochrane
    query_refiner.py        LLM-assisted query expansion (single call)
    domain_classifier.py    Detects whether query is medical
    intent_filter.py        Broad vs specific query detection
    relevance_filter.py     Post-retrieval relevance scoring

  validation/
    source_validator.py  Multi-signal trust gate (see decisions.md for ordering rationale)

  ranking/
    medeva_scorer.py     MEDEVA formula, confidence aggregation, rejection threshold

  vector_store/
    chroma_store.py      BioBERT embeddings, hybrid search, upsert

  rag/
    rag_chain.py         Main generation class, fallback to extractive summary
    citation_anchor.py   [n] marker mapping and bibliography formatting
    grounding.py         Sentence-level grounding filter (pre-NLI quick check)
    graph_pipeline.py    LangGraph nodes for contradiction + confidence

  hallucination/
    entailment_checker.py  DeBERTa-v3 NLI, keyword-overlap fallback

  features/
    contradiction_detector.py  BioBERT cosine similarity on topics + conclusions
    risk_flagging.py           Pattern rules, 7 categories
    plain_language.py          Claude 8th-grade rewrite, citation marker preservation

  llm/
    fallback_client.py   Provider waterfall: Anthropic → Groq → Gemini → Ollama
                         Retry with exponential backoff, provider stickiness,
                         attempt tracing. Single function: generate_text_with_fallback()

  db/
    user_store.py  MongoDB + in-memory fallback, rate-limited reconnect

  mcp/
    agent.py   LabAgent — plan/validate/execute/synthesize loop
    tools.py   pubmed_search tool with 5-min result cache
```

---

## LLM provider waterfall

The system tries providers in order until one succeeds:

```
Anthropic (Claude)
    ↓ fails / times out
Groq (OpenAI-compatible endpoint)
    ↓ fails / times out
Gemini
    ↓ fails / times out
Ollama (local, optional)
    ↓ fails
Exception raised → evidence_only mode
```

Provider stickiness: the last successful provider is tried first on the next request.
This avoids re-trying a provider that's been failing and improves steady-state latency.

Retry configuration: `LLM_PROVIDER_MAX_RETRIES=2`, `LLM_PROVIDER_RETRY_BACKOFF_SECONDS=0.4`.

---

## Modes and degradation

```
Evidence retrieved?
    No  → fallback (reason: retrieval_empty)
    Yes →
        MEDEVA confidence ≥ threshold?
            No  → fallback (reason: low_confidence_evidence)
            Yes →
                LLM call succeeds?
                    No  → evidence_only (reason: provider_error_after_evidence)
                    Yes →
                        Model returns INSUFFICIENT_EVIDENCE:?
                            Yes → fallback (reason: insufficient_evidence_marker)
                            No  → evidence_based ✓
```

Every path that isn't `evidence_based` sets `fallback_reason` in the response so
the frontend and logs can distinguish them. There's also `provider_attempts` (list of
"provider:attemptN" strings) for debugging provider-level failures.

---

## ChromaDB hybrid search

Documents are embedded with BioBERT and stored in a persistent ChromaDB collection
(`CHROMA_PERSIST_DIR`, defaults to `./data/chroma_db`).

Hybrid search score:

```
hybrid = (1 - w) × semantic_similarity + w × medeva_total    where w = 0.4
```

The weight `w = 0.4` was chosen to prevent semantic similarity from completely
dominating when a highly-relevant older paper has lower MEDEVA than a less relevant
newer one. At w=0.4, MEDEVA quality has real influence without overriding topical
relevance entirely.

Fresh documents from each API call are upserted before search, so the first query on
a topic is slower (API + embed + index) and subsequent queries are faster (cache hit +
local embed lookup).

---

## LLM Lab vs main pipeline

The Lab (`/llm-lab`) is intentionally separate from the main query pipeline:

| | Main pipeline | LLM Lab |
|---|---|---|
| Source validation | Yes — hard trust gate | No — PubMed trusted by default |
| MEDEVA scoring | Yes | No |
| BioBERT embeddings | Yes | No |
| Contradiction detection | Yes | No |
| NLI entailment | Yes | No |
| Response mode | 4 modes | `success` / `partial` / `failed` |
| LLM calls | 1 (generation) | 2 (planning + synthesis) |

The Lab uses a plan → validate → execute → synthesize loop with its own safety
hardening (allowed-tools whitelist, step caps, claim grounding post-pass).

---

## Observability

- `GET /api/v1/health/modes` — request counts, cache hit rate, mode distribution, error signals
- `GET /api/v1/health/providers` — per-provider success/failure counts and last latency
- `GET /api/v1/admin/failures` — last 100 pipeline failures with request ID and reason
- `X-Request-ID` header on every response for log correlation
- `X-Process-Time-Ms` header on every response

The debug overlay (`?debug=1` on the frontend) shows mode and provider health panels.

---

## Frontend pages

```
/              Main query UI — answer, citations, confidence badge, risk banners,
               contradiction alerts, MEDEVA breakdown table, discussion threads

/profile       Query history, saved answers (search + filter), usage stats

/llm-lab       Experimental agent interface — query, step trace, architecture notes

/admin         Operator panel — users, activity, discussions, failures, provider health
```

Auth: NextAuth (Google). User identity is passed to the backend as `X-User-Email`.
The backend doesn't do auth itself — it trusts the header (which is set by the
Next.js session middleware, not user-supplied input).
