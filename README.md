# MedTruth AI

> **Evidence-grounded medical intelligence. Every claim is sourced when possible. Every degraded path is explicit.**

MedTruth AI is a production-ready medical question-answering system that retrieves evidence exclusively from peer-reviewed, high-authority sources, scores each document using a custom evidence-quality algorithm (MEDEVA), and generates citation-anchored answers through a hallucination-resistant RAG pipeline. It is designed for medical researchers, clinical educators, and anyone who needs answers they can actually trust.

---

## Table of Contents

1. [Why MedTruth AI](#why-medtruth-ai)
2. [Core Innovation: MEDEVA Score](#core-innovation-medeva-score)
3. [Trusted Sources](#trusted-sources)
4. [System Architecture](#system-architecture)
5. [Feature Breakdown](#feature-breakdown)
6. [Project Structure](#project-structure)
7. [Tech Stack](#tech-stack)
8. [API Reference](#api-reference)
9. [Getting Started](#getting-started)
10. [Running Tests](#running-tests)
11. [Docker Deployment](#docker-deployment)
12. [Production Deployment (Vercel + Render)](#production-deployment-vercel--render)
13. [Environment Variables](#environment-variables)
14. [User data, discussions, and persistence](#user-data-discussions-and-persistence)
15. [LLM Lab (MCP-style agent)](#llm-lab-mcp-style-agent)
16. [Admin Panel](#admin-panel)
17. [Design Decisions](#design-decisions)
18. [Disclaimer](#disclaimer)

---

## Why MedTruth AI

Existing AI systems answer medical questions confidently — regardless of whether their sources are peer-reviewed journals, retracted papers, or blog posts. There is no distinction between a Cochrane systematic review and a wellness website. For clinical or research use, that gap is dangerous.

MedTruth AI is built on a different principle: **epistemic integrity**. It knows its own limits.

| Typical medical AI | MedTruth AI |
|--------------------|-------------|
| Sources any webpage it finds | Sources only from 6 trusted authority families |
| No source quality distinction | MEDEVA score ranks RCTs above case reports |
| Hides failure modes | Distinguishes evidence-based, evidence-only, general explanation, and fallback modes |
| No hallucination detection | NLI entailment check on every sentence |
| No conflict awareness | Detects contradictions between studies |
| One reading level | Expert and plain-language modes |

---

## Core Innovation: MEDEVA Score

**MEDEVA** (Medical Evidence Validity Assessment) is a composite scoring algorithm that assigns each retrieved document a quality score between 0.0 and 1.0. It is the engine behind every ranking and confidence decision in the system.

### Formula

```
MEDEVA(doc) =
    evidence_level_score  × 0.40
  + impact_factor_score   × 0.20
  + recency_score         × 0.15
  + citation_count_score  × 0.15
  + sample_size_score     × 0.10
  + authority_bonus             (AHA journals: +0.04)
```

### Evidence Level Hierarchy

Derived from the Oxford Centre for Evidence-Based Medicine (CEBM) levels:

| Study Design | Score |
|---|---|
| Systematic review / Meta-analysis | 1.00 |
| Double-blind RCT | 0.90 |
| Single-blind RCT | 0.80 |
| Prospective cohort | 0.65 |
| Retrospective cohort | 0.55 |
| Case-control | 0.45 |
| Cross-sectional | 0.35 |
| Case report / Series | 0.20 |
| Expert opinion / Editorial | 0.10 |

### Impact Factor Normalization

Impact factors are normalized against a ceiling of 80 (Nature Medicine's approximate IF), capped at 1.0. Examples:

| Journal | Raw IF (2023) | Normalized |
|---|---|---|
| Nature Medicine | ~80 | 1.00 |
| NEJM | ~79 | 0.99 |
| The Lancet | ~79 | 0.98 |
| JAMA | ~77 | 0.96 |
| BMJ | ~70 | 0.88 |
| Circulation (AHA) | ~38 | 0.47 |
| Cochrane Reviews | ~72 | 0.90 |

### Recency Score

Exponential decay with a 5-year half-life:

```
recency = 0.5 ^ (age_years / 5)
```

A 2023 paper scores ~1.0. A 2013 paper scores ~0.5. A 1993 paper scores ~0.05 (floor). This penalises outdated evidence without discarding it entirely — some foundational studies from decades ago remain authoritative.

### Confidence Thresholds

| Band | Score Range | Action |
|---|---|---|
| HIGH | ≥ 0.70 | Answer delivered with green badge |
| MEDIUM | 0.55 – 0.70 | Answer delivered with yellow warning |
| LOW | < 0.55 | System may return evidence-only or general explanation paths with explicit trust labels |

Low-confidence handling is explicit and mode-aware. The system avoids pretending certainty when generation or retrieval quality degrades.

### Runtime Response Modes

| Mode | Trigger | Behavior |
|---|---|---|
| `evidence_based` | Evidence retrieved + generation succeeds | Full answer with citations and confidence |
| `evidence_only` | Evidence retrieved + provider generation unavailable | Extractive evidence summary + citations, explicit AI-unavailable banner |
| `general_explanation` | No strong direct evidence match | Safe educational explanation, no fake citations |
| `fallback` | True failure path (provider/evidence constraints) | Minimal degraded response with explicit reason |

---

## Trusted Sources

MedTruth AI retrieves from exactly six source families. No other source can pass the validation gate.

| Source | Access Method | Authority Tier |
|---|---|---|
| **PubMed / MEDLINE** | NCBI E-utilities API (free, optional API key for higher rate limits) | 2 |
| **BMJ** | Europe PMC REST API | 2 |
| **The Lancet** | Europe PMC REST API | 2 |
| **Nature Medicine** | Europe PMC REST API | 2 |
| **WHO / CDC** | WHO IRIS OAI-PMH endpoint | 1 |
| **Cochrane Reviews** | Europe PMC, filtered to Cochrane Database ISSN | 1 |
| **AHA Journals** | PubMed / Europe PMC, validated by DOI prefix `10.1161` and ISSN | 2 |

### AHA Journal Registry

The system includes a complete registry of 12 American Heart Association journals with real ISSNs and normalized impact factors:

- Circulation (IF 37.8)
- Circulation Research (IF 20.1)
- Stroke (IF 10.2)
- Hypertension (IF 8.3)
- Arteriosclerosis, Thrombosis, and Vascular Biology (IF 10.4)
- Journal of the American Heart Association (IF 5.5)
- Circulation: Heart Failure, Arrhythmia & Electrophysiology, Cardiovascular Imaging, Cardiovascular Interventions, Cardiovascular Quality & Outcomes, Genomic & Precision Medicine

AHA documents receive a `+0.04` MEDEVA authority bonus and display a ♥ AHA badge in the UI.

### What is blocked

The validation gate hard-rejects any document matching blocked domain patterns:

```
wikipedia.org · webmd.com · healthline.com · reddit.com
quora.com · medium.com · blogspot.com · wordpress.com
news.*.com · mayoclinic.org/blogs
```

Validation is multi-signal: PMID (MEDLINE indexing), DOI publisher prefix (`10.XXXX`), ISSN registry, journal name pattern, and source tag are all checked independently.

---

## System Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                  Query Processing                        │
│  • Medical NER (scispaCy: diseases, drugs, genes)        │
│  • Intent classification                                  │
│  • MeSH term expansion                                   │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│           Concurrent Multi-Source Retrieval              │
│                                                          │
│   PubMed API ──┐                                         │
│  EuropePMC ────┤──► asyncio.gather() ──► raw_docs[]     │
│   WHO IRIS ────┤                                         │
│   Cochrane ────┘                                         │
│   ChromaDB (cached) ──► cached_docs[]                   │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│              Source Validation Gate                      │
│  • PMID check → confirms MEDLINE indexing                │
│  • DOI prefix check → 9 trusted publisher prefixes       │
│  • ISSN check → 40+ whitelisted journal ISSNs            │
│  • Journal name regex → 15+ pattern matches              │
│  • URL block list → 10 blocked domain patterns           │
│  • HARD REJECT if no trusted signal found                │
│  • Stamp is_aha=True for AHA-origin documents            │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│               MEDEVA Ranking Engine                      │
│  • Score each doc: 5 signals + AHA authority bonus       │
│  • Sort descending by MEDEVA total                       │
│  • Select top-K for context window                       │
│  • Compute query-weighted confidence score               │
│  • REJECT if confidence < 0.55                           │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│             ChromaDB Vector Store                        │
│  • BioBERT sentence embeddings (PubMed-trained)          │
│  • Upsert fresh docs (cache for future queries)          │
│  • Hybrid search: MEDEVA × semantic similarity           │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│           RAG Generation (Claude Sonnet)                 │
│  • Strict system prompt: answer ONLY from context        │
│  • Every claim must be tagged [n] inline                 │
│  • Model self-flags INSUFFICIENT_EVIDENCE if needed      │
│  • Citation post-processor maps [n] → bibliography       │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│           Hallucination Detection (NLI)                  │
│  • Extract atomic claims from generated text             │
│  • Run DeBERTa-v3 entailment: claim vs source passages   │
│  • Flag claims with entailment score < 0.60              │
│  • Prefix flagged sentences with [⚠️ UNVERIFIED]         │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│             Bonus Feature Layers                         │
│                                                          │
│  Risk Flagging ─── 7 categories (dosage, pregnancy,      │
│                    drug interaction, pediatric,           │
│                    surgical, oncology, emergency)         │
│                                                          │
│  Contradiction ─── BioBERT topic + conclusion            │
│  Detection         embedding clusters; MEDEVA-ranked     │
│                    precedence for conflicting studies     │
│                                                          │
│  Plain Language ── Claude rewrites at 8th-grade level    │
│  Mode              preserving all [n] citation markers   │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                Response to User                          │
│  • Answer with inline [n] citations                      │
│  • Confidence badge (HIGH / MEDIUM / LOW)                │
│  • MEDEVA breakdown table (collapsible)                  │
│  • Citation panel with PubMed links + AHA badges         │
│  • Risk banners (red / amber)                            │
│  • Contradiction alerts (expandable)                     │
│  • Evidence summary line                                 │
│  • Source stats (retrieved / trusted / rejected)         │
└─────────────────────────────────────────────────────────┘
```

---

## Feature Breakdown

### 1. Multi-Source Concurrent Retrieval

All four source clients (`PubMedClient`, `EuropePMCClient`, `WHOClient`, `CochraneClient`) run concurrently via `asyncio.gather()`. Each client fails gracefully — an unreachable endpoint skips, it does not crash the request. Results are deduplicated by document ID before ranking.

### 2. Source Validation Gate

Three-tier defence:

- **Hard block** — any URL matching a blocked domain pattern is immediately rejected, regardless of other signals
- **Hard trust** — a valid PMID proves MEDLINE indexing; a DOI prefix in the whitelist proves publisher trust; an ISSN in the registry proves journal identity
- **Soft trust** — journal name regex matching and source tag check

Every validated document has `is_aha`, `trust_tier`, and validation `reason` stamped into its metadata.

### 3. MEDEVA Scoring Engine

Implemented in [`src/ranking/medeva_scorer.py`](src/ranking/medeva_scorer.py). Study type is inferred from PubMed publication type tags (e.g. `"Randomized Controlled Trial"` → `rct_single_blind`) or from abstract keyword heuristics for Europe PMC results. Sample size is extracted from abstract text using regex patterns matching `n = X`, `X patients`, `X participants`.

### 4. ChromaDB Hybrid Search

BioBERT sentence embeddings (`pritamdeka/BioBERT-mnli-snli-scinli-scitail-mednli-stsb`) are stored in a persistent ChromaDB collection. Fresh documents retrieved from APIs are upserted into the store, so repeated queries benefit from cached embeddings. Hybrid search combines semantic cosine similarity with MEDEVA scores:

```
hybrid_score = (1 - w) × similarity + w × medeva_total   (w = 0.4)
```

### 5. Grounded Generation

The Claude system prompt contains hard constraints:

```
1. Answer ONLY using information from [SOURCE n] blocks.
2. Every factual claim MUST be followed by [n].
3. If the answer cannot be found: respond INSUFFICIENT_EVIDENCE.
4. NEVER introduce information not present in the sources.
5. If sources conflict, cite both and acknowledge the disagreement.
```

The model can self-trigger rejection by starting its response with `INSUFFICIENT_EVIDENCE:`. This is checked before the response reaches the user.

### 6. Hallucination Detection — NLI Entailment

Post-generation, every sentence in the answer is extracted as an atomic claim and tested for textual entailment against each source passage using a DeBERTa-v3 NLI model. Severe low-support claims are annotated with a softer marker (`[⚠️ Some uncertainty in evidence]`) using a dedicated threshold. A keyword overlap fallback activates if the NLI model is unavailable.

### 7. Contradiction Detection

Studies are compared pairwise using BioBERT embeddings of their full text (topic similarity) and extracted conclusions (conclusion similarity). A pair is a contradiction when:

```
topic_similarity ≥ 0.75  AND  conclusion_similarity < 0.45
contradiction_score = topic_similarity × (1 − conclusion_similarity)
```

Contradicting pairs are sorted by `contradiction_score` descending. The pair with the higher-MEDEVA study is labelled as the higher-evidence source in the UI.

### 8. Risk Flagging

Pattern matching across 7 clinical risk categories, evaluated against both the query and the generated answer:

| Category | Risk Level | Trigger Examples |
|---|---|---|
| Drug Dosage / Prescription | HIGH | "dose", "mg", "prescribe", "therapeutic range" |
| Drug Interactions | HIGH | "drug interaction", "contraindicated", "polypharmacy" |
| Pediatric Population | HIGH | "pediatric", "children", "infant", "neonatal" |
| Pregnancy / Obstetrics | HIGH | "pregnant", "fetal", "gestational", "lactation" |
| Oncology / Cancer | HIGH | "chemotherapy", "malignant", "immunotherapy" |
| Emergency / Critical Care | HIGH | "sepsis", "cardiac arrest", "CPR", "anaphylaxis" |
| Surgical / Procedural | MEDIUM | "surgery", "anesthesia", "post-op", "biopsy" |

### 9. Plain Language Mode

A second Claude call rewrites the expert answer at approximately 8th-grade reading level. Citation markers (`[1]`, `[2]`, etc.) are preserved exactly. Medical terms are replaced with plain equivalents. A post-processing check re-appends any markers that the model accidentally dropped.

### 10. Reliability Hardening (Week 2)

- Provider retries + exponential backoff (`LLM_PROVIDER_MAX_RETRIES`, `LLM_PROVIDER_RETRY_BACKOFF_SECONDS`)
- Provider stickiness (last successful provider is attempted first)
- Attempt tracing (`provider_attempts`) returned in degraded responses
- 60s mode stabilization cache for identical queries
- Backend confidence payload (`confidence_details`, `confidence_explanation`) to keep UI auditable
- Mode/provider observability endpoints:
  - `GET /api/v1/health/modes`
  - `GET /api/v1/health/providers`

### 11. Accounts, Saved Answers, and Profile

**Sign-in (end users)** — The Next.js app uses **NextAuth** with **Google OAuth** only (`signIn("google")` in the UI). Configure `NEXTAUTH_URL`, `NEXTAUTH_SECRET`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET` in `frontend/.env.local` (see [Environment Variables](#environment-variables)). After sign-in, the client calls `/api/v1/user/sync` and subsequent user routes with the **`X-User-Email`** header so the backend can attach history and saves to that identity.

**Where to click**

| Area | Route | Notes |
|------|--------|--------|
| Main MEDEVA Q&A | `/` | Evidence-grounded pipeline; header has theme toggle, **Admin** link, and **Sign in with Google** / **Sign out**. |
| Profile | `/profile` | Query history, saved answers, usage stats (requires sign-in for live data from the API). Linked from the sidebar on large screens. |
| How it works | `/how-it-works` | Product / pipeline explainer. |

Query history and manual saves are stored when Mongo is configured; otherwise the same APIs operate against an in-memory store (see [User data, discussions, and persistence](#user-data-discussions-and-persistence)). **`POST /api/v1/user/save`** returns **`503`** if the server has no working persistent store (so “save to profile” requires Mongo in production configurations that enforce persistence).

### 12. Discussions, Admin, and LLM Lab

- **Discussions** — Threaded comments under an answer can be validated (misinformation vs genuine questions) and **submitted** for persistence and admin review.
- **Admin** — Internal operator UI at **`/admin`** (header link on the home page). It is **not** tied to Google sign-in: you enter the shared **`ADMIN_SECRET`** once as **`X-Admin-Key`** in the admin page. Tabs call `GET /api/v1/admin/*` (see [Admin Panel](#admin-panel)).
- **LLM Lab** — Experimental agent at **`/llm-lab`** (prominent card in the **left sidebar** on `lg+` breakpoints; you can always open the URL directly). Uses `POST /api/v1/llm-lab/query` with tool traces and optional claim-to-context grounding (`[UNSUPPORTED]`-style tagging when claims drift from tool output). **No MEDEVA / trusted-source filter** — it is explicitly not the production clinical path.

---

## Project Structure

```
MedTruth_AI/
│
├── src/
│   ├── config/
│   │   └── trusted_journals.py        # AHA journal registry (12 journals, ISSNs, IF scores)
│   │
│   ├── retrieval/
│   │   ├── pubmed_client.py           # NCBI E-utilities: esearch + efetch, XML parsing
│   │   ├── europepmc_client.py        # Europe PMC REST: BMJ, Lancet, Nature Medicine
│   │   └── who_cochrane_client.py     # WHO IRIS + Cochrane via Europe PMC
│   │
│   ├── validation/
│   │   └── source_validator.py        # Multi-signal trust gate, block list, is_aha stamping
│   │
│   ├── ranking/
│   │   └── medeva_scorer.py           # MEDEVA formula, evidence hierarchy, confidence bands
│   │
│   ├── vector_store/
│   │   └── chroma_store.py            # ChromaDB + BioBERT, hybrid MEDEVA×similarity search
│   │
│   ├── rag/
│   │   ├── rag_chain.py               # Claude grounded generation, rejection gating
│   │   └── citation_anchor.py         # [n] marker mapping, bibliography builder
│   │
│   ├── hallucination/
│   │   └── entailment_checker.py      # DeBERTa NLI claim verification, fallback overlap
│   │
│   └── features/
│       ├── contradiction_detector.py  # BioBERT topic+conclusion clustering, MEDEVA precedence
│       ├── risk_flagging.py           # 7-category risk pattern matching, banner metadata
│       └── plain_language.py          # Claude 8th-grade rewriter, citation marker preservation
│   │
│   ├── db/
│   │   └── user_store.py              # Mongo + in-memory fallback: users, saves, discussions
│   │
│   └── mcp/
│       ├── agent.py                   # LLM Lab orchestration, grounding pass
│       └── tools.py                   # Tool definitions for lab agent
│
├── api/
│   ├── main.py                        # FastAPI app, CORS, process-time header, global error handler
│   ├── dependencies.py                # Singleton injectors for all clients
│   └── routes/
│       ├── query.py                   # POST /api/v1/query — full 10-step pipeline; health/modes, health/providers
│       ├── validate.py                # POST /api/v1/validate — source trust check
│       ├── explain.py                 # POST /api/v1/explain — plain language rewrite
│       ├── contradictions.py          # POST /api/v1/contradictions — standalone conflict scan
│       ├── user.py                    # User sync, history, save, storage-health
│       ├── discuss.py                 # POST /discuss/validate, /discuss/submit
│       ├── llm_lab.py                 # POST /llm-lab/query — experimental MCP-style agent
│       └── admin.py                   # Admin users, activity, discussions, failures, health
│
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx               # Main UI: query, evidence layout, auto-save, discussions
│       │   ├── profile/page.tsx       # Dashboard: history, saved filters, insights
│       │   ├── llm-lab/page.tsx       # Experimental MCP lab + architecture docs
│       │   ├── admin/page.tsx         # Admin: users, activity, discussions, health
│       │   ├── layout.tsx             # Root layout and metadata
│       │   └── globals.css            # Tailwind base + confidence/risk utility classes
│       ├── components/
│       │   ├── ConfidenceBadge.tsx    # GREEN/YELLOW/RED badge with MEDEVA % score
│       │   ├── RiskBanner.tsx         # Left-bordered alert panels per risk category
│       │   ├── CitationPanel.tsx      # Source cards with MEDEVA score, AHA badge, PubMed links
│       │   ├── ContradictionAlert.tsx # Expandable Study A vs B comparison panels
│       │   ├── MEDEVABreakdown.tsx    # Collapsible MEDEVA score table per source
│       │   └── ControlledDiscussion.tsx  # Discussion validate/submit UI
│       ├── lib/
│       │   └── api.ts                 # Typed fetch: query, user, discuss, llm-lab, admin
│       └── global.d.ts                # process.env declaration (resolves before npm install)
│
├── tests/
│   ├── test_aha_journals.py           # 22 tests: config, validator, MEDEVA (AHA-specific)
│   ├── test_source_validator.py       # 9 tests: trust signals, block list, filter
│   ├── test_medeva_scorer.py          # 6 tests: evidence hierarchy, recency, rank order
│   ├── test_risk_flagging.py          # 6 tests: all 7 risk categories
│   └── test_citation_anchor.py        # 4 tests: indexing, URLs, orphan cleanup, bibliography
│
├── Dockerfile.backend
├── frontend/Dockerfile.frontend
├── docker-compose.yml
├── render.yaml                        # Render web service (Python 3.11, build/start commands)
├── DEPLOYMENT.md                      # Vercel + Render env var checklist
├── requirements.txt
├── pytest.ini
├── ruff.toml
├── vercel.json                        # Monorepo root: build frontend/ for Vercel
├── package.json                       # Root stub so Vercel does not treat repo as Python-only
└── .env.example
```

---

## Tech Stack

### Backend

| Component | Technology | Version |
|---|---|---|
| API framework | FastAPI | 0.111.0 |
| ASGI server | Uvicorn | 0.29.0 |
| Data validation | Pydantic v2 | 2.7.1 |
| HTTP client | httpx (async) | 0.27.0 |
| LLM | Anthropic Claude Sonnet 4.6 | anthropic 0.28.0 |
| Embeddings | BioBERT (sentence-transformers) | 2.7.0 |
| NLI model | DeBERTa-v3-base-mnli | transformers 4.41.0 |
| Vector store | ChromaDB | 0.5.0 |
| ML runtime | PyTorch | 2.3.0 |
| NLP | spaCy + scispaCy | 3.7.4 |

### Frontend

| Component | Technology |
|---|---|
| Framework | Next.js 14 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS v3 |
| Component primitives | shadcn/ui pattern, lucide-react |
| State | React `useState` (client components) |

### External APIs

| Service | Endpoint | Auth |
|---|---|---|
| PubMed | `eutils.ncbi.nlm.nih.gov/entrez/eutils/` | Optional API key |
| Europe PMC | `ebi.ac.uk/europepmc/webservices/rest/search` | None |
| WHO IRIS | `extranet.who.int/iris/rest/discover` | None |
| CrossRef | `api.crossref.org/works` | None |

---

## API Reference

All endpoints are under `/api/v1`. Interactive docs at `http://localhost:8000/docs`.

---

### `POST /api/v1/query`

Main adaptive endpoint. Runs retrieval, validation, ranking, generation, safety checks, and returns one of the runtime modes (`evidence_based`, `evidence_only`, `general_explanation`, `fallback`).

**Request body:**

```json
{
  "query": "Does metformin reduce cardiovascular risk in type 2 diabetes?",
  "top_k": 8,
  "enable_entailment_check": true,
  "enable_contradiction_check": true
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | string | required | Medical question (5–500 chars) |
| `top_k` | int | 8 | Max sources to use for generation (1–20) |
| `enable_entailment_check` | bool | true | Run NLI hallucination detection |
| `enable_contradiction_check` | bool | true | Run contradiction detection |

**Response:**

```json
{
  "query": "Does metformin reduce cardiovascular risk in type 2 diabetes?",
  "answer": "Metformin has been shown to reduce cardiovascular mortality... [1][3]",
  "confidence": 0.81,
  "confidence_band": "HIGH",
  "rejected": false,
  "rejection_reason": null,
  "citations": [
    {
      "index": 1,
      "pmid": "9742977",
      "doi": "10.1016/S0140-6736(98)07019-6",
      "title": "Effect of intensive blood-glucose control with metformin...",
      "authors": ["UK Prospective Diabetes Study Group"],
      "journal": "The Lancet",
      "pub_year": 1998,
      "source": "pubmed",
      "medeva_total": 0.84,
      "confidence_band": "HIGH",
      "url": "https://pubmed.ncbi.nlm.nih.gov/9742977/",
      "is_aha": false
    }
  ],
  "bibliography": "[1] UK Prospective Diabetes Study Group. \"Effect of...\". The Lancet (1998).",
  "evidence_summary": "Evidence based on: 2 RCTs, 1 systematic review.",
  "risk_flags": [],
  "overall_risk": "NONE",
  "contradictions": [],
  "hallucination_check": {
    "hallucination_risk": "LOW",
    "hallucination_score": 0.0,
    "verified_count": 5,
    "unverified_count": 0,
    "unverified_claims": [],
    "safe_answer": "Metformin has been shown to..."
  },
  "sources_retrieved": 21,
  "sources_trusted": 18,
  "sources_rejected": 3,
  "mode": "evidence_based",
  "fallback_reason": null,
  "provider_used": "groq",
  "provider_attempts": ["groq:attempt1"],
  "confidence_details": {
    "retrieved": 21,
    "trusted": 18,
    "excluded": 3,
    "contradictions": 0,
    "low_support_claims": 0,
    "evidence_types": ["Meta-analysis", "RCT"]
  },
  "confidence_explanation": "Based on multiple high-quality studies with largely consistent findings."
}
```

**Evidence-only example** (evidence present, generation unavailable):

```json
{
  "mode": "evidence_only",
  "fallback_reason": "provider_error_after_evidence",
  "provider_used": "none",
  "provider_attempts": ["anthropic:attempt1", "anthropic:attempt2", "groq:attempt1", "groq:attempt2"],
  "answer": "Evidence-Based Summary ...",
  "citations": [{ "index": 1, "title": "..." }]
}
```

---

### `POST /api/v1/validate`

Check whether a given source is trusted before using it.

**Request:**

```json
{ "doi": "10.1161/CIRCULATIONAHA.123.056789" }
```

**Response:**

```json
{
  "status": "trusted",
  "reason": "DOI prefix 10.1161 belongs to trusted publisher",
  "trust_tier": 2,
  "trusted": true
}
```

---

### `POST /api/v1/explain`

Rewrite a technical medical answer in plain language (8th-grade level). All citation markers are preserved.

**Request:**

```json
{
  "technical_answer": "Metformin exhibits pleiotropic cardioprotective effects... [1][2]"
}
```

**Response:**

```json
{
  "plain_language_answer": "Metformin helps protect your heart in several ways... [1][2]"
}
```

---

### `POST /api/v1/contradictions`

Trigger a standalone contradiction scan for a query without generating an answer.

**Request:**

```json
{ "query": "hydroxychloroquine COVID-19 efficacy", "top_k": 10 }
```

**Response:**

```json
{
  "query": "hydroxychloroquine COVID-19 efficacy",
  "contradictions_found": 2,
  "total_docs_analyzed": 10,
  "pairs": [
    {
      "doc_a": { "index": 1, "title": "...", "conclusion": "...", "medeva_score": 0.72 },
      "doc_b": { "index": 3, "title": "...", "conclusion": "...", "medeva_score": 0.91 },
      "topic_similarity": 0.89,
      "conclusion_similarity": 0.21,
      "contradiction_score": 0.70,
      "higher_evidence_index": 3,
      "summary": "Study A (RCT, 2020, MEDEVA=0.72) and Study B (Meta-analysis, 2021, MEDEVA=0.91)..."
    }
  ]
}
```

---

### `GET /health`

```json
{
  "status": "ok",
  "service": "MedTruth AI",
  "trusted_sources": ["PubMed", "BMJ", "The Lancet", "Nature Medicine", "WHO", "CDC", "Cochrane Reviews"]
}
```

---

### `GET /api/v1/health/modes`

Operational mode distribution and error signals.

```json
{
  "requests": 120,
  "cache_hits": 34,
  "mode_counts": {
    "evidence_based": 74,
    "evidence_only": 18,
    "general_explanation": 20,
    "fallback": 8
  },
  "mode_percentages": {
    "evidence_based": 61.67,
    "evidence_only": 15.0,
    "general_explanation": 16.67,
    "fallback": 6.67
  },
  "error_signals": {
    "provider_error_count": 21,
    "retrieval_empty_count": 25
  }
}
```

---

### `GET /api/v1/health/providers`

Provider-level reliability snapshot.

```json
{
  "providers": {
    "anthropic": { "success": 3, "failure": 41, "last_latency_ms": 0.0 },
    "groq": { "success": 92, "failure": 8, "last_latency_ms": 834.2 },
    "gemini": { "success": 14, "failure": 12, "last_latency_ms": 1201.7 },
    "ollama": { "success": 0, "failure": 5, "last_latency_ms": 0.0 }
  }
}
```

---

### User & profile (`/api/v1/user/*`)

| Method | Path | Headers | Description |
|--------|------|---------|-------------|
| `POST` | `/api/v1/user/sync` | `X-User-Email`, JSON body `{ email, name?, image? }` | Upsert user profile |
| `GET` | `/api/v1/user/history` | `X-User-Email` | Full profile: `query_history`, `saved_answers`, `usage_count`, etc. |
| `POST` | `/api/v1/user/save` | `X-User-Email`, JSON `{ query, answer, confidence?, confidence_band?, mode?, citations_count? }` | Persist a saved answer. Returns **`503`** if persistent storage (Mongo) is not available — no silent in-memory save for this route. |
| `DELETE` | `/api/v1/user/saved/{answer_hash}` | `X-User-Email` | Remove one saved answer |
| `GET` | `/api/v1/user/storage-health` | — | `{ persistent_available, backend }` — `mongo` vs `memory_fallback` |

When MongoDB is unreachable, `UserStore` falls back to an **in-process** store (data survives only for the lifetime of that server process).

---

### Discussion & moderation (`/api/v1/discuss/*`)

| Method | Path | Headers | Description |
|--------|------|---------|-------------|
| `POST` | `/api/v1/discuss/validate` | — | Classify a comment (`VALID` / `QUESTION` / `MISINFORMATION`) against answer + evidence titles |
| `POST` | `/api/v1/discuss/submit` | `X-User-Email` | Validate **and** persist a moderated submission (linked query, anchors, validation payload) |

Submissions are stored for admin review when persistence is available; see [User data, discussions, and persistence](#user-data-discussions-and-persistence).

---

### LLM Lab (`/api/v1/llm-lab/*`)

| Method | Path | Description |
|--------|------|---------------|
| `POST` | `/api/v1/llm-lab/query` | Free-form experimental agent (not the main RAG pipeline). Rate-limited per IP. |

Response includes `answer`, `steps` (execution trace), `tools_used`, `plan`, `confidence`, `confidence_reason`, `total_duration_ms`, and `status`. See [LLM Lab (MCP-style agent)](#llm-lab-mcp-style-agent).

---

### Admin (`/api/v1/admin/*`)

All routes require header **`X-Admin-Key`** matching environment variable **`ADMIN_SECRET`**. If `ADMIN_SECRET` is unset, admin routes return **`503`**.

**Mongo vs no Mongo**

| Paths | When Mongo is down or not configured |
|--------|--------------------------------------|
| `/admin/users`, `/admin/user/{email}`, `/admin/activity`, `/admin/discussions` | Return **`503`** — admin must not show in-memory data as if it were the real database. |
| `/admin/failures`, `/admin/health` | Still work — failures use Mongo with in-memory fallback; health is provider metrics only. |

| Method | Path | Description |
|--------|------|---------------|
| `GET` | `/api/v1/admin/users` | Summary rows per user (**requires Mongo**) |
| `GET` | `/api/v1/admin/user/{email}` | Full user document (**requires Mongo**) |
| `GET` | `/api/v1/admin/activity` | Recent cross-user activity (**requires Mongo**) |
| `GET` | `/api/v1/admin/discussions` | Moderated discussion submissions (**requires Mongo**) |
| `GET` | `/api/v1/admin/failures` | Recent pipeline failure events |
| `GET` | `/api/v1/admin/health` | LLM provider metrics snapshot |

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- An Anthropic API key ([console.anthropic.com](https://console.anthropic.com))
- Optional: NCBI API key for higher PubMed rate limits ([ncbi.nlm.nih.gov/account](https://www.ncbi.nlm.nih.gov/account/))

### Local Setup

```bash
# 1. Clone the repository
git clone https://github.com/Tejasdagr8/MedTruth_AI.git
cd MedTruth_AI

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate       # macOS/Linux
.venv\Scripts\activate          # Windows

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Open .env and set at least one LLM key (e.g. ANTHROPIC_API_KEY).
# Optional: MONGO_URI + MONGO_DB for persistent users/saves/discussions.

# 5. Start the backend (use this venv's python — not a global conda base)
python -m uvicorn api.main:app --reload --port 8000

# 6. In a new terminal, set up and start the frontend
cd frontend
npm install
# Copy auth/API settings (NEXT_PUBLIC_API_URL, NextAuth, Google OAuth) — see Environment Variables
cp ../.env.example .env.local   # then edit .env.local with real values
npm run dev
```

Open [http://localhost:3001](http://localhost:3001) in your browser.

API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

Internal debug panel (mode/provider health) is available at:

`http://localhost:3001/?debug=1`

### First Query

Try this example in the UI or via curl:

```bash
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Does aspirin reduce mortality in acute myocardial infarction?"}' \
  | python3 -m json.tool
```

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run a specific module
pytest tests/test_medeva_scorer.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing
```

**Current status: 47/47 passing**

| Test file | Tests | What it covers |
|---|---|---|
| `test_aha_journals.py` | 22 | AHA config, ISSN registry, DOI validation, MEDEVA bonus |
| `test_source_validator.py` | 9 | Trust signals, block list, filter pipeline |
| `test_medeva_scorer.py` | 6 | Evidence hierarchy, recency decay, rank ordering |
| `test_risk_flagging.py` | 6 | All 7 risk categories, severity levels |
| `test_citation_anchor.py` | 4 | Citation indexing, URL generation, orphan cleanup |

---

## Docker Deployment

```bash
# Build and start all services
docker-compose up --build

# Rebuild only the backend after code changes
docker-compose up --build backend

# Run in detached mode
docker-compose up -d
```

Services:

| Service | Port | Description |
|---|---|---|
| `backend` | 8000 | FastAPI + all ML models |
| `frontend` | 3000 | Next.js production build |

ChromaDB data is persisted in a named volume `chroma_data` so your vector store survives container restarts.

---

## Production Deployment (Vercel + Render)

A split deployment keeps the heavy Python stack on Render and the Next.js app on Vercel. Step-by-step env var names, CORS, and custom domains are documented in [`DEPLOYMENT.md`](DEPLOYMENT.md).

**Summary**

| Layer | Platform | Notes |
|--------|----------|--------|
| Backend | [Render](https://render.com) | Uses root [`render.yaml`](render.yaml): `PYTHON_VERSION=3.11.11` (avoids Python 3.14 / tokenizer build issues), `pip install -r requirements.txt`, `uvicorn api.main:app --host 0.0.0.0 --port $PORT`, health check `GET /health`. |
| Frontend | [Vercel](https://vercel.com) | Set **Root Directory** to `frontend`. Point `NEXT_PUBLIC_API_URL` at your Render service URL with the `/api/v1` suffix. |
| Database | MongoDB Atlas (recommended) | Set `MONGO_URI` and `MONGO_DB` on Render. Without Mongo, the API still runs using an **in-memory** user store (ephemeral on free tier restarts). |
| CORS | `ALLOWED_ORIGINS` on Render | Comma-separated list of exact frontend origins (e.g. `https://your-app.vercel.app`). |

**Frontend (Vercel) env vars**

- `NEXT_PUBLIC_API_URL` — backend base including `/api/v1`
- `NEXTAUTH_URL` — canonical site URL (must match the browser URL users sign in from)
- `NEXTAUTH_SECRET` — random secret for session encryption
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — if using Google sign-in

**Backend (Render) env vars**

- At least one LLM provider key (same as local `.env`)
- `ALLOWED_ORIGINS` matching your Vercel deployment URL(s)
- `ADMIN_SECRET` — required for [admin API routes](#admin-panel) (`/api/v1/admin/*`)
- Optional: `MONGO_URI`, `MONGO_DB` for durable profiles, saved answers, and discussion submissions

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | No* | — | Anthropic API key |
| `GROQ_API_KEY` | No* | — | Groq API key (OpenAI-compatible endpoint) |
| `GEMINI_API_KEY` | No* | — | Gemini API key |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Groq model ID |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model ID |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Local Ollama endpoint |
| `OLLAMA_MODEL` | No | `llama3` | Local Ollama model |
| `LLM_PROVIDER_MAX_RETRIES` | No | `2` | Retry count per provider |
| `LLM_PROVIDER_RETRY_BACKOFF_SECONDS` | No | `0.4` | Base backoff seconds per retry |
| `NCBI_API_KEY` | No | — | Raises PubMed rate limit from 3 to 10 req/sec |
| `CLAUDE_MODEL` | No | `claude-sonnet-4-6` | Claude model ID to use |
| `PUBMED_MAX_RESULTS` | No | `8` | Max PubMed results per query |
| `EUROPEPMC_MAX_RESULTS` | No | `5` | Max Europe PMC results per query |
| `NLI_MODEL` | No | `microsoft/deberta-v3-base-mnli` | HuggingFace NLI model for entailment checking |
| `ENTAILMENT_THRESHOLD` | No | `0.60` | Claims below this score are flagged as unverified |
| `SEVERE_UNCERTAINTY_THRESHOLD` | No | `0.40` | Threshold for inline severe-uncertainty annotation |
| `CHROMA_PERSIST_DIR` | No | `./data/chroma_db` | ChromaDB persistence directory |
| `EMBEDDING_MODEL` | No | `pritamdeka/BioBERT-mnli-snli-scinli-scitail-mednli-stsb` | Sentence embedding model |
| `ALLOWED_ORIGINS` | No | *(empty → localhost defaults)* | If unset, CORS allows `http://localhost:3000`, `http://localhost:3001`, and `127.0.0.1` on those ports. In production, set an explicit comma-separated list |
| `NEXT_PUBLIC_API_URL` | No | `http://localhost:8000/api/v1` | Frontend API base URL (must end with `/api/v1` for this codebase) |
| `MONGO_URI` | No | — | MongoDB connection string (Atlas or self-hosted). If unset or unreachable, user data uses **in-memory** storage for that process |
| `MONGO_DB` | No | `medtruth_ai` | Database name when using Mongo |
| `ADMIN_SECRET` | No | — | Shared secret for `X-Admin-Key` on admin routes. If unset, admin endpoints return `503` |
| `PYTHON_VERSION` | Render only | — | Pin **3.11.x** in Render (see `render.yaml`); avoids broken builds on very new Python images |

**Next.js / auth (frontend only, typically Vercel)**

| Variable | Required | Description |
|---|---|---|
| `NEXTAUTH_URL` | Yes (prod) | Public URL of the site |
| `NEXTAUTH_SECRET` | Yes (prod) | Session signing secret |
| `GOOGLE_CLIENT_ID` | If using Google OAuth | Google Cloud OAuth client |
| `GOOGLE_CLIENT_SECRET` | If using Google OAuth | Google Cloud OAuth secret |

\* At least one generation provider (Anthropic/Groq/Gemini/Ollama) should be available for full explanation paths.

---

## User data, discussions, and persistence

**Profiles and history**

Signed-in users are identified by email (via NextAuth). The backend upserts a user document on `/api/v1/user/sync` and returns full state from `/api/v1/user/history` (query history, saved answers, usage counters). The main UI can auto-save answers after a successful query when the user is signed in.

**Mongo vs in-memory**

- With a working **`MONGO_URI`**, data is stored in MongoDB collections for users, saved answers, and discussions.
- Without Mongo (or when the server cannot connect), **`UserStore` falls back to an in-process dictionary** for reads and some paths. The API keeps responding for many routes, but **`POST /api/v1/user/save`** and the **admin user/activity/discussions** tabs require a working persistent store and return **`503`** when Mongo is unavailable (see [Admin Panel](#admin-panel)). Free-tier hosts may restart often, which clears in-memory data.

**Discussions**

The UI can validate a comment with `/api/v1/discuss/validate` and submit a moderated thread with `/api/v1/discuss/submit` (header `X-User-Email`). Submissions are persisted when Mongo is available and appear under **Admin → Discussions**.

**Health check for storage**

`GET /api/v1/user/storage-health` reports `persistent_available` and `backend` (`mongo` vs `memory_fallback`) so operators and the UI can surface whether data will survive a deploy.

---

## LLM Lab (MCP-style agent)

The **LLM Lab** lives at **`/llm-lab`** in the Next.js app. On wide layouts, open it from the **sidebar** (“LLM Lab · Experimental”); the route works the same if bookmarked. It is an experimental surface **separate** from the main MEDEVA RAG pipeline. It calls `POST /api/v1/llm-lab/query` (same `NEXT_PUBLIC_API_URL` base as the rest of the app) and shows:

**What “MCP-style” means (vs the real Model Context Protocol)**

The industry **Model Context Protocol (MCP)** is a wire protocol: hosts and servers exchange JSON-RPC messages (often over `stdio` or HTTP), advertise **tools/resources** with schemas, and let a client (for example an IDE) attach external context to an LLM. MedTruth does **not** ship an MCP server, stdio adapter, or Cursor/Claude-Desktop MCP config for this lab.

What we *do* have is **MCP-shaped behavior inside the API**: `src/mcp/` holds an in-process **tool-calling agent** (`LabAgent`) — the planner emits a JSON **plan** (steps), the runtime executes allowed tools (`pubmed_search`, then `analysis`), and the API returns a **trace** (`steps`, `tools_used`, `plan`, timings). That loop is why we call it **MCP-style**: same *interaction pattern* (model ↔ tools ↔ structured steps), different *transport* (plain FastAPI + Python, not the MCP spec).

- **Architecture** — how the lab agent differs from production query (tools, planning, no PubMed-first MEDEVA stack).
- **Tools & agents** — enumerated capabilities (retrieval-style tools, planning steps).
- **Trace** — `steps`, `tools_used`, `plan`, timings, and status from the API response.

The backend agent (`src/mcp/`) runs a lighter orchestration path with its own rate limiting. Answers may include a **grounding pass**: clinical claims in the draft are checked against provided context; unsupported fragments can be tagged (e.g. `[UNSUPPORTED]`) and confidence adjusted when violations are found. This is complementary to the main pipeline’s citation anchoring and NLI checks.

---

## Admin Panel

The admin UI lives at **`/admin`** on the frontend. The home page header includes an **Admin** link (same for local and deployed builds). It is backed by `GET /api/v1/admin/*` routes on the API.

**Authentication (operators, not Google users)**

This panel does **not** use NextAuth. Every admin API request must send:

```http
X-Admin-Key: <same value as ADMIN_SECRET on the server>
```

The `/admin` page prompts for that key once in the browser and attaches it to fetches. Set **`ADMIN_SECRET`** in the **backend** environment (local `.env`, Render dashboard, etc.). There is no lockout after failed attempts; invalid or missing keys receive **`401`**; if `ADMIN_SECRET` is unset, admin routes return **`503`**.

**Tabs**

- **Users** — list and drill into stored user documents (**Mongo required** — tab errors if persistence is unavailable).
- **Activity** — recent cross-user events (**Mongo required**).
- **Discussions** — moderated discussion submissions from `/discuss/submit` (**Mongo required**).
- **Failures** — pipeline failure log (Mongo if configured, else in-memory ring buffer on the server).
- **Health** — LLM provider metrics snapshot (no Mongo).

---

## Design Decisions

**Why refuse to answer instead of generating a low-confidence response?**
In every other domain, an uncertain AI answer is annoying. In medicine, it can directly harm someone. The rejection mechanism is not a limitation — it is the primary safety feature. A response that says "insufficient evidence" is always more useful than a confident hallucination.

**Why BioBERT for embeddings instead of OpenAI or a generic model?**
BioBERT is trained on PubMed abstracts and PMC full-text articles. Its token vocabulary and semantic space are calibrated for biomedical language. A generic embedding model will conflate "Stroke" (journal) with "stroke" (condition). BioBERT does not.

**Why is the DOI prefix checked by splitting on `/` and not `.`?**
The DOI format is `10.XXXX/suffix`. The publisher prefix is `10.XXXX` — everything before the first `/`. Splitting on `.` produces `10.XXXX/suffix-part` as the second token, which never matches a clean prefix. The original implementation had this bug; it was caught during smoke testing and corrected.

**Why is the AHA authority bonus only 0.04?**
The bonus is intentionally small. MEDEVA's primary discriminator is evidence level (weight 0.40). A case report from Circulation still scores lower than a meta-analysis from PLoS Medicine. The AHA bonus reflects editorial authority without overriding study design quality.

**Why does the system prompt tell Claude to say `INSUFFICIENT_EVIDENCE:` rather than just produce a low-quality answer?**
The model is better at recognising knowledge gaps than the retrieval pipeline is. This allows the model to self-trigger rejection for queries that retrieved documents but none of them actually addressed the question. It is a second line of defence after the MEDEVA confidence threshold.

---

## Disclaimer

MedTruth AI is built for research and educational purposes. It is not a substitute for professional medical advice, diagnosis, or treatment. All outputs should be reviewed by a qualified clinician before being applied to patient care.