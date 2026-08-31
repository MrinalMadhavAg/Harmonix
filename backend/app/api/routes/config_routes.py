from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core import weights
from app.core.commodities import COMMODITIES, COMMODITY_LABELS
from app.core.safety import SAFETY_CRITICAL_FIELDS, label_for
from app.core.standards import all_equivalences

router = APIRouter(tags=["configuration"])


class WeightsUpdate(BaseModel):
    semantic: float = Field(..., ge=0.0, le=1.0)
    lexical: float = Field(..., ge=0.0, le=1.0)
    attributes: float = Field(..., ge=0.0, le=1.0)
    attribute_weights: dict[str, float] = Field(default_factory=dict)


@router.get("/config/weights")
def get_weights():
    return {
        "items": [
            {
                **w.to_dict(),
                "label": COMMODITY_LABELS.get(w.commodity_type, w.commodity_type),
                "safety_critical_fields": [
                    {"key": k, "label": label_for(k)}
                    for k in SAFETY_CRITICAL_FIELDS.get(w.commodity_type, [])
                ],
            }
            for w in weights.all_weights()
        ],
        "note": (
            "Component weights are normalized to sum to 1 at scoring time. "
            "Attribute weights are relative within a commodity."
        ),
    }


@router.put("/config/weights/{commodity}")
def update_weights(commodity: str, body: WeightsUpdate):
    if commodity not in COMMODITIES:
        raise HTTPException(status_code=404, detail=f"Unknown commodity '{commodity}'.")
    if body.semantic + body.lexical + body.attributes <= 0:
        raise HTTPException(
            status_code=400,
            detail="At least one of semantic, lexical or attributes must be greater than zero.",
        )
    for key, val in body.attribute_weights.items():
        if not 0.0 <= float(val) <= 2.0:
            raise HTTPException(
                status_code=400,
                detail=f"Attribute weight for '{key}' must be between 0 and 2.",
            )

    updated = weights.set_weights(
        weights.CommodityWeights(
            commodity_type=commodity,
            semantic=body.semantic, lexical=body.lexical, attributes=body.attributes,
            attribute_weights={k: float(v) for k, v in body.attribute_weights.items()},
        )
    )
    return {
        "updated": updated.to_dict(),
        "note": "Run POST /harmonize to apply the new weights to the catalogue.",
    }


@router.post("/config/weights/{commodity}/reset")
def reset_weights(commodity: str):
    if commodity not in COMMODITIES:
        raise HTTPException(status_code=404, detail=f"Unknown commodity '{commodity}'.")
    default = weights.DEFAULT_WEIGHTS[commodity]
    return {"updated": weights.set_weights(default).to_dict()}


@router.get("/config/safety")
def safety_config():
    return {
        "items": [
            {
                "commodity_type": c,
                "label": COMMODITY_LABELS[c],
                "fields": [{"key": k, "label": label_for(k)} for k in fields],
            }
            for c, fields in SAFETY_CRITICAL_FIELDS.items()
        ],
        "verdicts": {
            "PASS": "Every safety-critical field is stated on both records and agrees.",
            "BLOCK": "At least one safety-critical field is confirmed to differ.",
            "INSUFFICIENT_EVIDENCE": (
                "A safety-critical field is unstated on one or both records. "
                "Routed to review rather than assumed equal."
            ),
        },
    }


@router.get("/config/standards")
def standards():
    return {
        "equivalences": all_equivalences(),
        "note": (
            "These relationships are used as a soft scoring signal only. They are never "
            "substituted into a description, and they cannot override a safety block."
        ),
    }


@router.get("/config/settings")
def runtime_settings():
    s = get_settings()
    return {
        "match_threshold": s.match_threshold,
        "review_floor": s.review_floor,
        "candidate_k": s.candidate_k,
        "embedding_model": s.embedding_model,
        "auto_seed": s.auto_seed,
    }
