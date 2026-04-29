"""
/validate endpoint — check if a given source/DOI/PMID is trusted.
"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src.validation.source_validator import ValidationStatus, validate_document

router = APIRouter()


class ValidateRequest(BaseModel):
    doi: Optional[str] = None
    pmid: Optional[str] = None
    journal: Optional[str] = None
    issn: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None


class ValidateResponse(BaseModel):
    status: str
    reason: str
    trust_tier: int
    trusted: bool


@router.post("/validate", response_model=ValidateResponse)
def validate_source(request: ValidateRequest):
    result = validate_document(
        source=request.source or "",
        journal=request.journal or "",
        doi=request.doi,
        pmid=request.pmid,
        issn=request.issn,
        url=request.url,
    )
    return ValidateResponse(
        status=result.status.value,
        reason=result.reason,
        trust_tier=result.trust_tier,
        trusted=result.status == ValidationStatus.TRUSTED,
    )
