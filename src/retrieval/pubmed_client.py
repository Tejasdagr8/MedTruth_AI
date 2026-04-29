"""
PubMed retrieval client using NCBI E-utilities API.
Searches abstracts and fetches full metadata including PMID, DOI, study type, journal.
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

TRUSTED_JOURNALS = {
    "bmj", "british medical journal",
    "the lancet", "lancet",
    "nature medicine",
    "jama", "journal of the american medical association",
    "new england journal of medicine", "nejm",
    "annals of internal medicine",
    "cochrane database of systematic reviews",
    "plos medicine",
    "the bmj",
}


@dataclass
class PubMedArticle:
    pmid: str
    title: str
    abstract: str
    authors: list[str]
    journal: str
    pub_year: int
    doi: Optional[str]
    study_type: str           # inferred from publication types
    citation_count: int = 0
    sample_size: Optional[int] = None
    mesh_terms: list[str] = field(default_factory=list)
    source: str = "pubmed"

    def to_retrieval_doc(self) -> dict:
        return {
            "id": f"pmid:{self.pmid}",
            "text": f"{self.title}\n\n{self.abstract}",
            "metadata": {
                "pmid": self.pmid,
                "title": self.title,
                "journal": self.journal,
                "pub_year": self.pub_year,
                "doi": self.doi,
                "study_type": self.study_type,
                "citation_count": self.citation_count,
                "sample_size": self.sample_size,
                "mesh_terms": self.mesh_terms,
                "source": self.source,
                "authors": self.authors,
            },
        }


_STUDY_TYPE_MAP = {
    "Randomized Controlled Trial": "rct_single_blind",
    "Meta-Analysis": "systematic_review_meta_analysis",
    "Systematic Review": "systematic_review_meta_analysis",
    "Clinical Trial, Phase III": "rct_single_blind",
    "Clinical Trial, Phase IV": "rct_single_blind",
    "Observational Study": "cohort_study_prospective",
    "Cohort Study": "cohort_study_prospective",
    "Case-Control Studies": "case_control",
    "Cross-Sectional Studies": "cross_sectional",
    "Case Reports": "case_report_series",
    "Review": "expert_opinion",
    "Editorial": "expert_opinion",
}


def _infer_study_type(pub_types: list[str]) -> str:
    for pt in pub_types:
        if pt in _STUDY_TYPE_MAP:
            return _STUDY_TYPE_MAP[pt]
    return "expert_opinion"


def _extract_sample_size(abstract: str) -> Optional[int]:
    import re
    patterns = [
        r"(?:n\s*=\s*|enrolled\s+|included\s+|recruited\s+)(\d{2,6})",
        r"(\d{2,6})\s+(?:patients|participants|subjects|individuals)",
    ]
    for pat in patterns:
        m = re.search(pat, abstract, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def _parse_article_xml(article_node: ET.Element) -> Optional[PubMedArticle]:
    try:
        pmid_el = article_node.find(".//PMID")
        pmid = pmid_el.text.strip() if pmid_el is not None else ""
        if not pmid:
            return None

        title_el = article_node.find(".//ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else ""

        abstract_parts = article_node.findall(".//AbstractText")
        abstract = " ".join("".join(p.itertext()) for p in abstract_parts).strip()

        journal_el = article_node.find(".//Journal/Title")
        journal = journal_el.text.strip().lower() if journal_el is not None else ""

        year_el = article_node.find(".//PubDate/Year")
        pub_year = int(year_el.text) if year_el is not None else 2000

        doi = None
        for id_el in article_node.findall(".//ArticleId"):
            if id_el.get("IdType") == "doi":
                doi = id_el.text.strip()

        pub_types = [
            pt.text.strip()
            for pt in article_node.findall(".//PublicationType")
            if pt.text
        ]
        study_type = _infer_study_type(pub_types)

        authors = []
        for author in article_node.findall(".//Author"):
            last = author.findtext("LastName", "")
            fore = author.findtext("ForeName", "")
            if last:
                authors.append(f"{last} {fore}".strip())

        mesh_terms = [
            mh.findtext("DescriptorName", "")
            for mh in article_node.findall(".//MeshHeading")
        ]

        sample_size = _extract_sample_size(abstract)

        return PubMedArticle(
            pmid=pmid,
            title=title,
            abstract=abstract,
            authors=authors,
            journal=journal,
            pub_year=pub_year,
            doi=doi,
            study_type=study_type,
            sample_size=sample_size,
            mesh_terms=[m for m in mesh_terms if m],
        )
    except Exception:
        logger.warning("Failed to parse PubMed article XML", exc_info=True)
        return None


class PubMedClient:
    def __init__(self, api_key: Optional[str] = None, max_results: int = 10):
        self.api_key = api_key
        self.max_results = max_results
        self._client = httpx.AsyncClient(timeout=30.0)

    def _base_params(self) -> dict:
        p = {"retmode": "json"}
        if self.api_key:
            p["api_key"] = self.api_key
        return p

    async def search(self, query: str, mesh_expand: bool = True) -> list[str]:
        """Return list of PMIDs matching the query."""
        params = {
            **self._base_params(),
            "db": "pubmed",
            "term": query,
            "retmax": self.max_results,
            "usehistory": "y",
            "sort": "relevance",
        }
        resp = await self._client.get(ESEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("esearchresult", {}).get("idlist", [])

    async def fetch_articles(self, pmids: list[str]) -> list[PubMedArticle]:
        """Fetch full article data for given PMIDs."""
        if not pmids:
            return []
        params = {
            **self._base_params(),
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "xml",
            "retmode": "xml",
        }
        resp = await self._client.get(EFETCH_URL, params=params)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        articles = []
        for article_node in root.findall(".//PubmedArticle"):
            article = _parse_article_xml(article_node)
            if article and article.abstract:
                articles.append(article)
        return articles

    async def retrieve(
        self,
        query: str,
        expanded_terms: list[str] | None = None,
    ) -> list[PubMedArticle]:
        """
        Full search + fetch pipeline.

        When expanded_terms are provided (from the query refiner), a second
        search incorporating those synonyms is run and its results are merged.
        Total PMIDs are capped at self.max_results to avoid API overload.
        """
        base_query = expand_query(query)
        original_results = await self.search(base_query)

        expanded_results: list[str] = []
        if expanded_terms:
            joined = " OR ".join(f'"{t}"' for t in expanded_terms[:4])
            expanded_query = f"({query}) AND ({joined})"
            expanded_results = await self.search(expanded_query)

        # Keep original query hits first, then append expanded hits.
        # Expanded hits are capped to <= 50% of final candidate pool.
        seen_pmids: set[str] = set()
        merged_pmids: list[str] = []
        original_bucket: list[str] = []
        for pmid in original_results:
            if pmid and pmid not in seen_pmids:
                seen_pmids.add(pmid)
                original_bucket.append(pmid)
            if len(original_bucket) >= self.max_results:
                break

        expanded_bucket: list[str] = []
        expanded_cap = max(0, self.max_results // 2)
        for pmid in expanded_results:
            if pmid and pmid not in seen_pmids:
                seen_pmids.add(pmid)
                expanded_bucket.append(pmid)
            if len(expanded_bucket) >= expanded_cap:
                break

        merged_pmids.extend(original_bucket)
        remaining = max(0, self.max_results - len(merged_pmids))
        if remaining > 0:
            merged_pmids.extend(expanded_bucket[:remaining])

        all_pmids = merged_pmids[: self.max_results]
        if not all_pmids:
            return []
        return await self.fetch_articles(all_pmids)

    async def close(self):
        await self._client.aclose()


def expand_query(query: str) -> str:
    q = query.lower()
    has_depression_intent = any(
        term in q for term in ["depression", "depressive", "major depressive disorder", "mdd"]
    )
    if has_depression_intent and ("cbt" in q or "cognitive behavioral therapy" in q or "therapy" in q):
        return (
            '(cognitive behavioral therapy OR CBT) AND '
            '("major depressive disorder" OR depression) AND '
            '(adult OR "general population")'
        )
    if "cbt" in q or "cognitive behavioral therapy" in q:
        return '(cognitive behavioral therapy OR CBT) AND (depression OR "major depressive disorder")'
    return query
