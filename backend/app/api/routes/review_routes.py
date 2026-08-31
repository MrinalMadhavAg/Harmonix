from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import review

router = APIRouter(tags=["review"])


class DecisionRequest(BaseModel):
    decision: str = Field(..., description="APPROVE or REJECT")
    steward: str = "demo.steward"
    reason: str | None = None
    override_nmi: str | None = Field(
        None, description="Redirect the record to a different NMI. Must already exist."
    )


@router.get("/review-queue")
def list_items(
    status: str | None = None,
    cpse: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return review.list_review_items(status=status, cpse=cpse, limit=limit, offset=offset)


@router.get("/review-queue/{item_id}")
def get_item(item_id: int):
    item = review.get_review_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Review item {item_id} not found.")
    return item


@router.post("/review-queue/{item_id}/decide")
def decide(item_id: int, req: DecisionRequest):
    return review.decide(
        item_id=item_id, decision=req.decision, steward=req.steward,
        reason=req.reason, override_nmi=req.override_nmi,
    )


@router.get("/steward-decisions")
def decisions(limit: int = Query(100, ge=1, le=500)):
    return {"items": review.steward_decision_log(limit=limit)}


@router.get("/evidence/{nmi}")
def evidence_matrix(nmi: str):
    data = review.attribute_evidence_matrix(nmi)
    if data is None:
        raise HTTPException(
            status_code=404, detail=f"{nmi} is not a known National Material Identifier."
        )
    return data
