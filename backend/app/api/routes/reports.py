from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.session import get_conn, transaction
from app.services import queries
from app.services.governance import nmi_exists

router = APIRouter(tags=["reports"])


@router.get("/dashboard")
def dashboard():
    return queries.dashboard_summary()


@router.get("/reports/summary")
def summary():
    with get_conn() as conn:
        duplicates = conn.execute(
            """
            SELECT g.nmi, g.standardized_description, g.commodity_type, g.member_count,
                   count(DISTINCT c.cpse_org) AS cpse_count,
                   array_agg(DISTINCT c.cpse_org) AS cpses
            FROM golden_records g JOIN crosswalk c ON c.nmi = g.nmi
            WHERE g.member_count > 1
            GROUP BY g.nmi, g.standardized_description, g.commodity_type, g.member_count
            ORDER BY count(DISTINCT c.cpse_org) DESC, g.member_count DESC
            LIMIT 25
            """
        ).fetchall()

        confidence = conn.execute(
            """
            SELECT
              CASE
                WHEN match_score >= 0.9 THEN '0.90 - 1.00'
                WHEN match_score >= 0.8 THEN '0.80 - 0.89'
                WHEN match_score >= 0.7 THEN '0.70 - 0.79'
                WHEN match_score >= 0.6 THEN '0.60 - 0.69'
                ELSE 'below 0.60'
              END AS band,
              count(*) AS n
            FROM crosswalk WHERE match_score IS NOT NULL
            GROUP BY band ORDER BY band DESC
            """
        ).fetchall()

        commodity = conn.execute(
            """
            SELECT COALESCE(r.commodity_type,'unknown') AS commodity_type,
                   count(*) AS materials,
                   count(DISTINCT c.nmi) AS golden_records,
                   count(*) - count(DISTINCT c.nmi) AS codes_consolidated
            FROM raw_records r LEFT JOIN crosswalk c ON c.record_id = r.id
            GROUP BY 1 ORDER BY materials DESC
            """
        ).fetchall()

        cpse_matrix = conn.execute(
            """
            SELECT a.cpse_org AS cpse_a, b.cpse_org AS cpse_b,
                   count(DISTINCT a.nmi) AS shared_materials
            FROM crosswalk a JOIN crosswalk b
              ON a.nmi = b.nmi AND a.cpse_org < b.cpse_org
            GROUP BY a.cpse_org, b.cpse_org
            ORDER BY shared_materials DESC
            """
        ).fetchall()

    return {
        "duplicate_materials": [dict(r) for r in duplicates],
        "confidence_distribution": [dict(r) for r in confidence],
        "commodity_distribution": [dict(r) for r in commodity],
        "cpse_overlap": [dict(r) for r in cpse_matrix],
    }


@router.get("/reports/surplus")
def surplus(limit: int = Query(15, ge=1, le=50)):
    """Cross-CPSE holdings of the same NMI. Illustrative demo inventory only."""
    return {
        "disclaimer": (
            "Illustrative demo inventory. Quantities are synthetic and do not "
            "represent real CPSE stock."
        ),
        "items": queries.surplus_opportunities(limit=limit),
    }


class TransferRequest(BaseModel):
    nmi: str
    from_cpse: str
    to_cpse: str
    quantity: int
    note: str | None = None


@router.post("/transfers")
def create_transfer(req: TransferRequest):
    """Draft an illustrative inter-CPSE transfer. Not a procurement action."""
    if not nmi_exists(req.nmi):
        raise HTTPException(
            status_code=404, detail=f"{req.nmi} is not a known National Material Identifier."
        )
    if req.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero.")
    if req.from_cpse.upper() == req.to_cpse.upper():
        raise HTTPException(status_code=400, detail="Source and destination CPSE must differ.")

    with transaction() as conn:
        available = conn.execute(
            """
            SELECT COALESCE(sum(i.quantity), 0) AS q
            FROM crosswalk c JOIN demo_inventory i ON i.record_id = c.record_id
            WHERE c.nmi = %s AND c.cpse_org = %s
            """,
            (req.nmi, req.from_cpse.upper()),
        ).fetchone()["q"]
        if req.quantity > int(available):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{req.from_cpse.upper()} holds {int(available)} unit(s) of {req.nmi} "
                    f"in the demo inventory; cannot transfer {req.quantity}."
                ),
            )

        row = conn.execute(
            """
            INSERT INTO transfer_requests (nmi, from_cpse, to_cpse, quantity, note, status)
            VALUES (%s, %s, %s, %s, %s, 'DRAFT') RETURNING *
            """,
            (req.nmi, req.from_cpse.upper(), req.to_cpse.upper(), req.quantity, req.note),
        ).fetchone()

    return {
        "transfer": dict(row),
        "disclaimer": (
            "Demonstration / illustrative only. This does not initiate any real "
            "procurement, financial or ERP transaction."
        ),
    }


@router.get("/transfers")
def list_transfers(limit: int = Query(50, ge=1, le=200)):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT t.*, g.standardized_description
            FROM transfer_requests t
            LEFT JOIN golden_records g ON g.nmi = t.nmi
            ORDER BY t.created_at DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {
        "items": [dict(r) for r in rows],
        "disclaimer": "Demonstration / illustrative only.",
    }


@router.get("/audit")
def audit_log(limit: int = Query(100, ge=1, le=500)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM golden_record_audit ORDER BY changed_at DESC LIMIT %s", (limit,)
        ).fetchall()
    return {"items": [dict(r) for r in rows]}
