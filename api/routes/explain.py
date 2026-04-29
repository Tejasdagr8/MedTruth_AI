"""
/explain endpoint — translate a technical medical answer to plain language.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.features.plain_language import translate_to_plain_language

router = APIRouter()


class ExplainRequest(BaseModel):
    technical_answer: str = Field(..., min_length=10, max_length=4000)


class ExplainResponse(BaseModel):
    plain_language_answer: str


@router.post("/explain", response_model=ExplainResponse)
def explain_endpoint(request: ExplainRequest):
    try:
        plain = translate_to_plain_language(request.technical_answer)
        return ExplainResponse(plain_language_answer=plain)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")
