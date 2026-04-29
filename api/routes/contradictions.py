"""
/contradictions endpoint — detect conflicting conclusions across a list of documents.
Accepts pre-retrieved docs or triggers a fresh retrieval for a query.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from api.dependencies import (
    get_cochrane_client,
    get_europepmc_client,
    get_pubmed_client,
    get_who_client,
)
from src.features.contradiction_detector import detect_contradictions
from src.ranking.medeva_scorer import rank_documents
from src.validation.source_validator import filter_trusted_docs

router = APIRouter()


class ContradictionRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=500)
    top_k: int = Field(default=10, ge=2, le=20)


class ContradictionResponse(BaseModel):
    query: str
    contradictions_found: int
    pairs: list[dict]
    total_docs_analyzed: int


@router.post("/contradictions", response_model=ContradictionResponse)
async def contradictions_endpoint(
    request: ContradictionRequest,
    pubmed=Depends(get_pubmed_client),
    europepmc=Depends(get_europepmc_client),
    who=Depends(get_who_client),
    cochrane=Depends(get_cochrane_client),
):
    results = await asyncio.gather(
        pubmed.retrieve(request.query),
        europepmc.retrieve(request.query),
        cochrane.retrieve(request.query),
        return_exceptions=True,
    )

    all_docs = []
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Retrieval source failed in /contradictions: %s", result)
            continue
        for item in result:
            all_docs.append(item.to_retrieval_doc())

    trusted_docs, _ = filter_trusted_docs(all_docs)
    ranked_docs = rank_documents(trusted_docs)[: request.top_k]
    pairs = detect_contradictions(ranked_docs)

    return ContradictionResponse(
        query=request.query,
        contradictions_found=len(pairs),
        pairs=[p.to_dict() for p in pairs],
        total_docs_analyzed=len(ranked_docs),
    )
