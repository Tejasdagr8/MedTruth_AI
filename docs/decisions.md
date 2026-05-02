# Architecture decisions

Decisions I made while building this, and why. Written mostly so future-me doesn't
have to reverse-engineer them from the code.

---

## Why reject instead of hedging

The first version of the system would always return *some* answer, just with a low
confidence badge. I noticed during testing that low-confidence answers were often
wrong in subtle ways — they'd cite studies that were adjacent to the question, not
actually relevant. The problem isn't the confidence display, it's that a bad answer
with a yellow badge is still a bad answer.

The explicit rejection mechanism (either MEDEVA confidence < threshold, or the model
self-triggers `INSUFFICIENT_EVIDENCE:`) was added after thinking about who actually
reads these outputs. A researcher sees a low-confidence answer and probably treats
it as a starting point, not a conclusion. A non-expert sees the same thing and might
not know what "MEDIUM confidence" actually means in terms of clinical reliability.

Refusing to answer is unambiguous. It forces the user to reformulate the question or
consult a different resource, which is the right outcome when evidence is weak.

---

## MEDEVA weights

The 40/20/15/15/10 split isn't from a paper — it's empirically tuned. I built a small
test set of ~50 medical questions where I knew what the best evidence was (landmark
RCTs, Cochrane reviews) and iterated the weights until the top-ranked documents
matched what a clinician would want to see.

Evidence level gets 40% because that's the core insight: a well-designed small study
beats a large badly-designed one. Impact factor gets 20% rather than more because
I didn't want journal prestige to override study design — a case report in Nature is
still a case report.

The AHA authority bonus (+0.04) is deliberately tiny. It's there to break ties in
cardiovascular queries where two docs with similar MEDEVA scores come from different
sources, not to promote AHA content overall.

---

## Why BioBERT for embeddings

I tested three options: `text-embedding-ada-002` (OpenAI), a generic sentence
transformer (`all-MiniLM-L6`), and `pritamdeka/BioBERT-mnli-snli-scinli-scitail-mednli-stsb`.

The generic model conflated clinical terms with general language — "Stroke" (the journal)
matched weakly against stroke-related queries because the model's representation of
"stroke" was dominated by the general English meaning. BioBERT's token vocabulary and
pretraining corpus are specifically PubMed + PMC, so biomedical terminology is embedded
in the right space.

I didn't use OpenAI embeddings because: (a) API latency adds up when embedding many
documents at query time, (b) it's an external dependency that costs money per request,
and (c) the BioBERT model runs locally and was better on biomedical similarity anyway.

---

## Source validation ordering

The validation check order matters for correctness and performance:

1. **Blocked domain check** first — hard exit, no further work needed
2. **ISSN** — most reliable signal, direct registry lookup
3. **PMID** — strong signal (MEDLINE indexing criteria), regex format check only
4. **DOI prefix** — publisher-level trust, one string operation
5. **Journal name regex** — fallback, prone to false positives
6. **Source tag** — weakest, last resort

I tried doing PMID before ISSN initially. The problem: many documents from Europe PMC
have a PMID but no ISSN in their metadata. If we stop at PMID, we never stamp `is_aha`
correctly for AHA-origin docs. The ISSN check both validates and stamps `is_aha` in
one step, so it should come first.

One bug I caught during testing: the DOI prefix extraction was originally splitting on
`.` instead of `/`. DOIs look like `10.1161/CIRCULATIONAHA.123`, so splitting on `.`
gives `["10", "1161/CIRCULATIONAHA", "123"]` — the prefix `10.1161` never appears as
an element. Splitting on `/` gives `["10.1161", "CIRCULATIONAHA.123"]` which works.
The fix is in `_check_doi`.

---

## Why four response modes

I went through a few design iterations here:

**Option A**: Single response type with varying confidence badges.  
Problem: silently degrades. The user can't tell if a low-confidence badge means
"we found weak studies" vs "the LLM provider was down and we returned a fallback."

**Option B**: Binary answer/reject.  
Problem: too coarse. When evidence exists but the LLM call fails, the user gets
nothing even though there's good information to show them.

**Option C (current)**: Explicit modes.  
`evidence_based`, `evidence_only`, `general_explanation`, `fallback` — each
maps to a specific situation and the frontend renders them differently. The mode
field is always in the response so there's no ambiguity about what happened.

The `general_explanation` mode is the one I'm least happy with. It answers without
citing specific papers, which is a weaker guarantee than the other modes. But for
educational questions with no good direct evidence match, returning nothing is worse
than a clearly-labeled explanation. The UI shows a different banner for this mode.

---

## MongoDB + in-memory fallback

I added the in-memory fallback after realising Render's free tier restarts frequently
and doesn't keep sidecar services running reliably. The fallback lets the API keep
responding during Mongo outages without throwing 500s everywhere.

The tradeoff: data doesn't survive process restarts in fallback mode. For a research
tool, that's acceptable — query history and saved answers are convenience features,
not core functionality. If you need persistence, point `MONGO_URI` at Atlas (free tier
is fine for this volume).

The reconnect rate-limiting (`_CONNECT_RETRY_TTL = 10.0`) is important. Without it,
every request during a Mongo outage pays a 1.5s `serverSelectionTimeoutMS` penalty,
which effectively kills the API. With it, reconnect attempts are bounded to once per
10 seconds.

---

## LLM Lab isolation

The Lab agent (`src/mcp/`) deliberately doesn't share infrastructure with the main
query pipeline. It doesn't run MEDEVA scoring, source validation, or BioBERT embeddings.

The reason is experimental flexibility. The Lab exists to explore how LLM tool-calling
behaves with medical queries, not to produce production-quality answers. If I coupled
it to the main pipeline, every change to the pipeline would need to be compatible with
the Lab's use cases, and every Lab experiment would need to be safe for production use.
Keeping them isolated means they can evolve independently.

The safety hardening in the Lab (ALLOWED_TOOLS, step caps, output validation,
claim grounding) was added after observing the raw planner behavior. Without it: the
planner occasionally emitted tools that didn't exist, produced empty synthesis steps,
and made claims with no study citations. The hardening is defensive rather than clever.

---

## Why the system prompt is repetitive

The RAG system prompt has multiple redundant instructions ("ONLY", "MUST", "NEVER",
"answer ONLY from the provided context"). This isn't accident or bad writing.

Early testing showed Claude occasionally supplementing answers with training-data
knowledge that wasn't in the retrieved context. The answers were often correct-sounding
but couldn't be cited — which defeats the entire purpose. Adding more explicit
prohibition language (even when it's logically redundant) reduced this significantly.

The repetition is load-bearing. Don't trim it for style.

---

## What I'd change if starting over

**The risk flagging system** would be a lightweight multi-label classifier rather than
regex patterns. The current approach produces false positives on queries like "stroke
recovery" (triggers the emergency banner) and fails on queries with negations. The
classifier approach adds ~50ms of latency but would be much more precise. Didn't do it
because the false-positive rate is low enough to be a minor UX annoyance, not a
reliability issue.

**The extractive summary fallback** in `evidence_only` mode needs work. The current
implementation looks for sentences containing specific keywords ("reduce", "improve",
"effective") which is crude. A proper extractive summarizer (even a simple one based
on sentence importance scores) would be better.

**Activity timestamps** in the user store — query history just stores the query string,
not when it was submitted. The admin panel activity tab shows queries in "recent per
user" order rather than "globally recent" order. This was a deliberate simplification
that I'd undo now.
