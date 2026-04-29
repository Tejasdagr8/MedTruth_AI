"""
WHO IRIS and Cochrane retrieval clients.
WHO uses IRIS OAI-PMH / REST search.
Cochrane uses Europe PMC filtered to Cochrane Database of Systematic Reviews.
"""

from dataclasses import dataclass, field
from typing import Optional

import httpx

WHO_SEARCH_URL = "https://extranet.who.int/iris/rest/discover"
COCHRANE_PMC_QUERY = 'JOURNAL:"Cochrane Database of Systematic Reviews"'


@dataclass
class WHODocument:
    handle: str
    title: str
    abstract: str
    pub_year: int
    authors: list[str]
    source: str = "who"
    study_type: str = "expert_opinion"
    doi: Optional[str] = None
    citation_count: int = 0

    def to_retrieval_doc(self) -> dict:
        return {
            "id": f"who:{self.handle}",
            "text": f"{self.title}\n\n{self.abstract}",
            "metadata": {
                "handle": self.handle,
                "title": self.title,
                "pub_year": self.pub_year,
                "study_type": self.study_type,
                "source": self.source,
                "doi": self.doi,
                "authors": self.authors,
                "citation_count": self.citation_count,
            },
        }


@dataclass
class CochraneReview:
    pmid: Optional[str]
    doi: Optional[str]
    title: str
    abstract: str
    pub_year: int
    authors: list[str]
    citation_count: int = 0
    source: str = "cochrane"
    study_type: str = "systematic_review_meta_analysis"

    def to_retrieval_doc(self) -> dict:
        doc_id = f"pmid:{self.pmid}" if self.pmid else f"doi:{self.doi}"
        return {
            "id": doc_id,
            "text": f"{self.title}\n\n{self.abstract}",
            "metadata": {
                "pmid": self.pmid,
                "doi": self.doi,
                "title": self.title,
                "pub_year": self.pub_year,
                "study_type": self.study_type,
                "source": self.source,
                "authors": self.authors,
                "citation_count": self.citation_count,
                "journal": "Cochrane Database of Systematic Reviews",
            },
        }


class WHOClient:
    def __init__(self, max_results: int = 5):
        self.max_results = max_results
        self._client = httpx.AsyncClient(timeout=30.0)

    async def retrieve(self, query: str) -> list[WHODocument]:
        """Search WHO IRIS for policy documents and guidelines."""
        try:
            params = {
                "query": query,
                "rpp": self.max_results,
                "start": 0,
                "scope": "/",
                "expand": "metadata",
            }
            resp = await self._client.get(WHO_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            docs = []
            for item in data.get("discoverySearchResult", {}).get("discoverySearchResultItem", []):
                metadata = {
                    m["key"]: m["value"]
                    for m in item.get("metadata", [])
                    if "value" in m
                }
                title = metadata.get("dc.title", "").strip()
                abstract = metadata.get("dc.description.abstract", "").strip()
                if not title or not abstract:
                    continue
                handle = item.get("handle", "")
                year_str = metadata.get("dc.date.issued", "2000")[:4]
                try:
                    pub_year = int(year_str)
                except ValueError:
                    pub_year = 2000
                authors_raw = metadata.get("dc.contributor.author", "")
                authors = [a.strip() for a in authors_raw.split(";") if a.strip()]
                doi = metadata.get("dc.identifier.doi")
                docs.append(WHODocument(
                    handle=handle,
                    title=title,
                    abstract=abstract,
                    pub_year=pub_year,
                    authors=authors,
                    doi=doi,
                ))
            return docs
        except Exception:
            # WHO IRIS API can be unreliable; fail gracefully
            return []

    async def close(self):
        await self._client.aclose()


class CochraneClient:
    """Fetches Cochrane systematic reviews via Europe PMC."""

    def __init__(self, max_results: int = 5):
        self.max_results = max_results
        self._client = httpx.AsyncClient(timeout=30.0)
        self._base = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    async def retrieve(self, query: str) -> list[CochraneReview]:
        full_query = (
            f'({query}) AND JOURNAL:"Cochrane Database of Systematic Reviews" '
            f"AND HAS_ABSTRACT:Y"
        )
        params = {
            "query": full_query,
            "format": "json",
            "pageSize": self.max_results,
            "resultType": "core",
            "sort": "CITED desc",
        }
        try:
            resp = await self._client.get(self._base, params=params)
            resp.raise_for_status()
            hits = resp.json().get("resultList", {}).get("result", [])
            reviews = []
            for hit in hits:
                title = hit.get("title", "").strip()
                abstract = hit.get("abstractText", "").strip()
                if not title or not abstract:
                    continue
                year_str = hit.get("pubYear", "2000")
                try:
                    pub_year = int(year_str)
                except ValueError:
                    pub_year = 2000
                author_list = hit.get("authorList", {}).get("author", [])
                authors = [
                    f"{a.get('lastName', '')} {a.get('firstName', '')}".strip()
                    for a in author_list
                    if a.get("lastName")
                ]
                reviews.append(CochraneReview(
                    pmid=hit.get("pmid"),
                    doi=hit.get("doi"),
                    title=title,
                    abstract=abstract,
                    pub_year=pub_year,
                    authors=authors,
                    citation_count=int(hit.get("citedByCount", 0)),
                ))
            return reviews
        except Exception:
            return []

    async def close(self):
        await self._client.aclose()
