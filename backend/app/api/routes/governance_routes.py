from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.services import governance

router = APIRouter(tags=["governance"])


class CheckRequest(BaseModel):
    description: str = Field(..., min_length=2)
    commodity_type: str | None = None


class OverrideRequest(BaseModel):
    description: str
    commodity_type: str | None = None
    decision: str = Field(..., description="CREATE_NEW_ANYWAY, USE_EXISTING or CANCELLED")
    suggested_nmi: str | None = None
    suggested_score: float | None = None
    new_legacy_code: str | None = None
    cpse_org: str | None = None
    justification: str | None = None
    actor: str = "demo.user"


@router.post("/check-new-material")
def check_new_material(req: CheckRequest):
    """Governance gate. Advises, never hard-rejects."""
    return governance.check_new_material(req.description, req.commodity_type)


@router.post("/governance/override")
def override(req: OverrideRequest):
    return governance.record_override(
        description=req.description, commodity_type=req.commodity_type,
        decision=req.decision, suggested_nmi=req.suggested_nmi,
        suggested_score=req.suggested_score, new_legacy_code=req.new_legacy_code,
        cpse_org=req.cpse_org, justification=req.justification, actor=req.actor,
    )


@router.get("/governance/overrides")
def list_overrides(limit: int = Query(50, ge=1, le=200)):
    return {"items": governance.list_overrides(limit=limit)}
