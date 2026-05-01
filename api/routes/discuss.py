"""
Controlled discussion endpoints.

Comments are tied to a specific sentence or citation within an answer.
Every comment is validated by AI before being surfaced.

POST /discuss/validate  — validate a single comment and return classification
POST /discuss/submit    — validate + persist a moderated submission
"""

import re

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from src.interaction.controlled_discussion import validate_comment
from src.db.user_store import UserStore

router = APIRouter()
store = UserStore()
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ValidateCommentRequest(BaseModel):
    comment: str = Field(..., min_length=5, max_length=1000)
    answer: str = Field(..., min_length=10, max_length=8000)
    evidence_titles: list[str] = Field(default_factory=list, max_length=10)
    # Optional anchors — at least one should be provided for structured comments
    anchor_sentence: str | None = Field(default=None, max_length=600)
    anchor_citation_title: str | None = Field(default=None, max_length=200)


class SubmitCommentRequest(ValidateCommentRequest):
    query: str = Field(..., min_length=5, max_length=500)
    answer_id: str | None = Field(default=None, max_length=128)


@router.post("/discuss/validate")
def validate_comment_endpoint(request: ValidateCommentRequest):
    """
    Validate and classify a user comment against the answer evidence.

    Returns:
      type: VALID | QUESTION | MISINFORMATION
      confidence: 0.0–1.0
      reason: why this classification was assigned
      suggested_action: approved | held_for_review | blocked | converted_to_query
      query_suggestion: rephrased search query (only when type=QUESTION)
      action: resolved action label
    """
    result = validate_comment(
        comment=request.comment,
        answer=request.answer,
        evidence_titles=request.evidence_titles,
        anchor_sentence=request.anchor_sentence,
        anchor_citation_title=request.anchor_citation_title,
    )
    return result.to_dict()


@router.post("/discuss/submit")
def submit_comment_endpoint(
    request: SubmitCommentRequest,
    x_user_email: str | None = Header(default=None),
):
    if not x_user_email or not EMAIL_REGEX.match(x_user_email):
        raise HTTPException(status_code=401, detail="Missing or invalid X-User-Email header")

    validation = validate_comment(
        comment=request.comment,
        answer=request.answer,
        evidence_titles=request.evidence_titles,
        anchor_sentence=request.anchor_sentence,
        anchor_citation_title=request.anchor_citation_title,
    ).to_dict()

    payload = {
        "user_email": x_user_email.lower(),
        "query": request.query,
        "answer_id": request.answer_id,
        "comment": request.comment,
        "validation": validation["type"],
        "confidence": validation["confidence"],
        "action": validation["action"],
        "reason": validation.get("reason"),
        "suggested_action": validation.get("suggested_action"),
        "query_suggestion": validation.get("query_suggestion"),
        "anchor_sentence": request.anchor_sentence,
        "anchor_citation_title": request.anchor_citation_title,
    }
    stored = store.save_discussion(payload)
    return {"status": "submitted", "submission": stored, "validation": validation}
