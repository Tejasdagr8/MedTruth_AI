# MedTruth AI

A medical question-answering system that only answers from peer-reviewed sources and tells you exactly how confident it is and why.

I built this because existing AI medical tools either refuse to say anything useful (liability-driven hedging) or answer everything confidently from sources you'd never cite in a clinical setting. Neither is helpful. MedTruth tries a different approach: retrieve only from trusted journals, score each source's evidence quality explicitly, generate a grounded answer with inline citations, and be transparent when the evidence isn't good enough to answer.

---

## The main idea

Every response goes through:

1. **Retrieval** from PubMed, Europe PMC, WHO, and Cochrane — concurrently, with deduplication
2. **Source validation** — hard-reject anything not matching a trusted DOI prefix, ISSN, or journal registry
3. **MEDEVA scoring** — a composite evidence-quality score (study design × impact factor × recency × citations × sample size)
4. **RAG generation** — Claude with a strict system prompt: answer only from the provided context, cite every claim, or say "INSUFFICIENT_EVIDENCE"
5. **Hallucination check** — DeBERTa NLI entailment on each generated claim vs source passages
6. **Risk flagging** — pattern-matched banners for dosage, drug interactions, pediatric, pregnancy, oncology, and emergency queries

If evidence quality is too low, the system returns a rejection rather than a low-confidence answer. In medicine, "I don't know" is more useful than a confident hallucination.

---

## MEDEVA score

The scoring formula assigns each retrieved document a 0–1 quality score:

```
MEDEVA(doc) =
  evidence_level  × 0.40    # study design hierarchy (RCT > cohort > case report)
  + impact_factor × 0.20    # journal IF normalized against 80 (Nature Medicine ceiling)
  + recency       × 0.15    # exponential decay, 5-year half-life
  + citations     × 0.15    # log-normalized citation count
  + sample_size   × 0.10    # log-normalized sample size
  + aha_bonus               # +0.04 for AHA journals
```

A 2023 double-blind RCT in NEJM scores around 0.88. A 2015 case report in an unknown journal scores around 0.22. The confidence thresholds are: HIGH ≥ 0.70, MEDIUM ≥ 0.55, LOW < 0.55.

The weights came from iterating against a test set of queries with known ground-truth evidence. They're not theoretically derived — they're empirically tuned to make the output ranking match what a clinician would prioritize.

---

## Trusted sources

Retrieval is limited to six source families. Nothing else passes the validation gate.

| Source | How |
|---|---|
| PubMed / MEDLINE | NCBI E-utilities (optional API key for higher rate limits) |
| BMJ | Europe PMC |
| The Lancet | Europe PMC |
| Nature Medicine | Europe PMC |
| WHO / CDC | WHO IRIS OAI-PMH |
| Cochrane Reviews | Europe PMC, filtered to Cochrane ISSN |
| AHA Journals | PubMed / Europe PMC, validated by DOI prefix `10.1161` |

Documents are validated by at least one of: PMID (confirms MEDLINE indexing), DOI publisher prefix, ISSN registry, or journal name regex. Wikipedia, WebMD, Healthline, Reddit, and similar domains are hard-rejected regardless of other signals.

---

## Response modes

The system has four possible output modes:

| Mode | When | What you get |
|---|---|---|
| `evidence_based` | Evidence found + LLM available | Answer with inline citations and confidence |
| `evidence_only` | Evidence found + LLM unavailable | Extractive summary from source abstracts |
| `general_explanation` | No strong evidence match | Safe educational answer, no citations |
| `fallback` | Real failure | Minimal response with explicit reason |

The mode is always returned in the response so the frontend can show an appropriate banner. There's no mode that silently degrades.

---

## Project structure

```
src/
  config/           # AHA journal registry (12 journals, ISSNs, IFs)
  retrieval/        # API clients for PubMed, Europe PMC, WHO, Cochrane
  validation/       # Source trust gate — DOI, ISSN, journal name, block list
  ranking/          # MEDEVA scoring engine
  vector_store/     # ChromaDB + BioBERT embeddings for hybrid search
  rag/              # Claude grounded generation chain, citation anchoring
  hallucination/    # DeBERTa NLI entailment check
  features/         # Contradiction detection, risk flagging, plain language rewrite
  db/               # MongoDB user store with in-memory fallback
  mcp/              # LLM Lab agent (experimental, separate from main pipeline)

api/
  routes/           # FastAPI endpoints: query, validate, explain, user, admin, llm_lab

frontend/
  app/              # Next.js 14 app router pages
  components/       # UI components (confidence badge, citation panel, risk banners)
```

---

## Getting started

Prerequisites: Python 3.11+, Node.js 20+, at least one LLM API key.

```bash
git clone https://github.com/Tejasdagr8/MedTruth_AI.git
cd MedTruth_AI

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Set ANTHROPIC_API_KEY (or GROQ_API_KEY / GEMINI_API_KEY as fallbacks)
# Optional: MONGO_URI for persistent user data (in-memory fallback if not set)

python -m uvicorn api.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend && npm install && npm run dev
```

Open `http://localhost:3001`. API docs at `http://localhost:8000/docs`.

Debug panel (mode + provider health): `http://localhost:3001/?debug=1`

Quick test:

```bash
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Does aspirin reduce mortality in acute myocardial infarction?"}' \
  | python3 -m json.tool
```

---

## Running tests

```bash
pytest tests/ -v
# or with coverage:
pytest tests/ --cov=src --cov-report=term-missing
```

47 tests across 5 modules (MEDEVA scoring, source validation, AHA registry, risk flagging, citation anchoring). All should pass.

---

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Primary LLM |
| `GROQ_API_KEY` | — | Fallback LLM |
| `GEMINI_API_KEY` | — | Fallback LLM |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | |
| `NCBI_API_KEY` | — | Raises PubMed rate limit 3→10 req/s |
| `MONGO_URI` | — | Without this, user data is in-memory only |
| `MONGO_DB` | `medtruth_ai` | |
| `ADMIN_SECRET` | — | Required for `/api/v1/admin/*`; panel disabled if unset |
| `ALLOWED_ORIGINS` | localhost:3000/3001 | Comma-separated list for CORS in production |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | |
| `NEXTAUTH_URL` | — | Required in production |
| `NEXTAUTH_SECRET` | — | Required in production |
| `GOOGLE_CLIENT_ID/SECRET` | — | If using Google OAuth |

---

## Docker

```bash
docker-compose up --build
```

Backend on :8000, frontend on :3000. ChromaDB data persists in a named volume (`chroma_data`).

---

## Deployment

Backend on Render, frontend on Vercel. See [DEPLOYMENT.md](DEPLOYMENT.md) for the full checklist.

One important note for Render: pin `PYTHON_VERSION=3.11.11` in your environment variables. Python 3.14 images have tokenizer build issues that break the sentence-transformers install.

---

## LLM Lab

There's a separate experimental interface at `/llm-lab` that uses a lighter agent loop (plan → PubMed search → synthesis) without the full MEDEVA pipeline. It's useful for exploring how the tool-calling behavior works and comparing outputs to the main pipeline. The responses include a trace of every step so you can see exactly what the agent did.

The Lab intentionally doesn't share infrastructure with the main query pipeline — it's a sandbox.

---

## Admin panel

Available at `/admin` in the frontend. Requires `X-Admin-Key: <ADMIN_SECRET>` on every request. Shows user activity, saved discussions, pipeline failures, and LLM provider health.

The auth is a shared secret — fine for a single-operator tool but not suitable for multi-tenant use.

---

## Known limitations / honest caveats

- Sample size extraction from abstracts is regex-based and often misses values, so most docs use the 0.10 floor for that component. The MEDEVA score is still useful because evidence level and impact factor carry 60% of the weight.
- The risk flagging is pattern-matched and has false positives (e.g., "stroke recovery" triggers the emergency banner). The alternatives considered (NER-based classifier) add latency and complexity for marginal improvement.
- The in-memory user store doesn't survive process restarts. On Render's free tier, this means query history is ephemeral unless you configure MongoDB Atlas.
- "general_explanation" mode answers without citing specific papers. It's not hallucinating — it's drawing on background medical knowledge — but it should be treated differently from an evidence-based answer. The UI makes this explicit.

---

## Disclaimer

For research and educational purposes. Not a substitute for professional medical advice. All outputs should be reviewed by a qualified clinician before being applied to patient care.
