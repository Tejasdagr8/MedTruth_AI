"""
Europe PMC client — covers BMJ, The Lancet, Nature Medicine, and more.
Uses the Europe PMC REST API (free, no key required).
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

EUROPEPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

TRUSTED_SOURCE_IDS = {
    "BMJ",
    "LANCET",
    "NATURE",
    "COCHRANE",
}

TRUSTED_JOURNAL_SUBSTRINGS = [
    "bmj",
    "british medical journal",
    "lancet",
    "nature medicine",
    "cochrane",
    "annals of internal medicine",
    "jama",
    "plos medicine",
    "new england journal",
]


@dataclass
class EuropePMCArticle:
    pmid: Optional[str]
    pmcid: Optional[str]
    doi: Optional[str]
    title: str
    abstract: str
    journal: str
    pub_year: int
    authors: list[str]
    source: str = "europepmc"
    study_type: str = "expert_opinion"
    citation_count: int = 0
    mesh_terms: list[str] = field(default_factory=list)

    def to_retrieval_doc(self) -> dict:
        doc_id = f"pmid:{self.pmid}" if self.pmid else f"doi:{self.doi}" if self.doi else f"pmcid:{self.pmcid}"
        return {
            "id": doc_id,
            "text": f"{self.title}\n\n{self.abstract}",
            "metadata": {
                "pmid": self.pmid,
                "pmcid": self.pmcid,
                "doi": self.doi,
                "title": self.title,
                "journal": self.journal,
                "pub_year": self.pub_year,
                "study_type": self.study_type,
                "citation_count": self.citation_count,
                "source": self.source,
                "authors": self.authors,
            },
        }


def _infer_study_type_from_title_abstract(title: str, abstract: str) -> str:
    text = (title + " " + abstract).lower()
    if any(kw in text for kw in ["systematic review", "meta-analysis", "meta analysis"]):
        return "systematic_review_meta_analysis"
    if any(kw in text for kw in ["randomized controlled trial", "randomised controlled trial", "rct", "double-blind", "double blind"]):
        return "rct_double_blind"
    if any(kw in text for kw in ["randomized", "randomised", "placebo"]):
        return "rct_single_blind"
    if any(kw in text for kw in ["cohort study", "prospective study", "prospective cohort"]):
        return "cohort_study_prospective"
    if any(kw in text for kw in ["retrospective", "medical records"]):
        return "cohort_study_retrospective"
    if any(kw in text for kw in ["case-control", "case control"]):
        return "case_control"
    if any(kw in text for kw in ["cross-sectional", "cross sectional", "survey"]):
        return "cross_sectional"
    if any(kw in text for kw in ["case report", "case series"]):
        return "case_report_series"
    return "expert_opinion"


def _is_trusted_journal(journal_name: str) -> bool:
    j = journal_name.lower()
    return any(t in j for t in TRUSTED_JOURNAL_SUBSTRINGS)


def _parse_result(hit: dict) -> Optional[EuropePMCArticle]:
    try:
        title = hit.get("title", "").strip()
        abstract = hit.get("abstractText", "").strip()
        if not title or not abstract:
            return None

        journal = hit.get("journalTitle", "").strip()
        if not _is_trusted_journal(journal):
            return None

        pub_year_str = hit.get("pubYear", "2000")
        try:
            pub_year = int(pub_year_str)
        except ValueError:
            pub_year = 2000

        pmid = hit.get("pmid")
        pmcid = hit.get("pmcid")
        doi = hit.get("doi")
        citation_count = int(hit.get("citedByCount", 0))

        author_list = hit.get("authorList", {}).get("author", [])
        authors = [
            f"{a.get('lastName', '')} {a.get('firstName', '')}".strip()
            for a in author_list
            if a.get("lastName")
        ]

        study_type = _infer_study_type_from_title_abstract(title, abstract)

        return EuropePMCArticle(
            pmid=pmid,
            pmcid=pmcid,
            doi=doi,
            title=title,
            abstract=abstract,
            journal=journal,
            pub_year=pub_year,
            authors=authors,
            study_type=study_type,
            citation_count=citation_count,
        )
    except Exception:
        logger.warning("Failed to parse EuropePMC result", exc_info=True)
        return None


class EuropePMCClient:
    def __init__(self, max_results: int = 10):
        self.max_results = max_results
        self._client = httpx.AsyncClient(timeout=30.0)

    async def retrieve(
        self,
        query: str,
        expanded_terms: list[str] | None = None,
    ) -> list[EuropePMCArticle]:
        """
        Search Europe PMC for trusted-journal articles matching query.

        When expanded_terms are provided (from the query refiner), a second
        query variant is attempted and its unique results are merged.
        Total results are capped at self.max_results.
        """
        journal_filter = (
            'JOURNAL:"BMJ" OR JOURNAL:"The Lancet" OR JOURNAL:"Lancet" '
            'OR JOURNAL:"Nature Medicine" OR JOURNAL:"Cochrane Database"'
        )

        async def _run_query(q: str) -> list[EuropePMCArticle]:
            full_query = f"({q}) AND ({journal_filter}) AND HAS_ABSTRACT:Y"
            params = {
                "query": full_query,
                "format": "json",
                "pageSize": self.max_results,
                "resultType": "core",
                "sort": "CITED desc",
            }
            try:
                resp = await self._client.get(EUROPEPMC_SEARCH, params=params)
                resp.raise_for_status()
                hits = resp.json().get("resultList", {}).get("result", [])
                parsed: list[EuropePMCArticle] = []
                for hit in hits:
                    article = _parse_result(hit)
                    if article:
                        parsed.append(article)
                return parsed
            except Exception:
                logger.warning(
                    "EuropePMC retrieval failed for query variant: %s", q, exc_info=True
                )
                return []

        original_results = await _run_query(query)
        expanded_results: list[EuropePMCArticle] = []
        if expanded_terms:
            joined = " OR ".join(f'"{t}"' for t in expanded_terms[:3])
            expanded_results = await _run_query(f"({query}) AND ({joined})")

        # Merge with original-first priority. Expanded bucket is capped to <= 50%.
        seen_ids: set[str] = set()
        original_bucket: list[EuropePMCArticle] = []
        for article in original_results:
            dedup_key = article.pmid or article.doi or article.pmcid or article.title
            if dedup_key and dedup_key not in seen_ids:
                seen_ids.add(dedup_key)
                original_bucket.append(article)
            if len(original_bucket) >= self.max_results:
                break

        expanded_bucket: list[EuropePMCArticle] = []
        expanded_cap = max(0, self.max_results // 2)
        for article in expanded_results:
            dedup_key = article.pmid or article.doi or article.pmcid or article.title
            if dedup_key and dedup_key not in seen_ids:
                seen_ids.add(dedup_key)
                expanded_bucket.append(article)
            if len(expanded_bucket) >= expanded_cap:
                break

        merged = list(original_bucket)
        remaining = max(0, self.max_results - len(merged))
        if remaining > 0:
            merged.extend(expanded_bucket[:remaining])
        return merged[: self.max_results]

    async def close(self):
        await self._client.aclose()
