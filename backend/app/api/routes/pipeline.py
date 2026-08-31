from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.session import get_conn
from app.ml.hydration import hydrate_indexes
from app.ml.indexes import store
from app.services.evaluation import evaluate
from app.services.harmonization import run_harmonization

log = logging.getLogger(__name__)
router = APIRouter(tags=["pipeline"])


class HarmonizeRequest(BaseModel):
    enforce_safety: bool = Field(
        True,
        description=(
            "When false, safety-critical mismatches no longer prevent a merge. "
            "Used to demonstrate what the safety layer is preventing."
        ),
    )
    threshold: float | None = Field(None, ge=0.0, le=1.0)


@router.post("/harmonize")
def harmonize(req: HarmonizeRequest):
    """Re-run the full pipeline over every stored record."""
    result = run_harmonization(enforce_safety=req.enforce_safety, threshold=req.threshold)
    return {
        "job_id": result.job_id,
        "duration_seconds": round(result.duration_s, 2),
        "stats": result.stats,
    }


@router.post("/seed")
def seed(force: bool = Query(False, description="Delete existing records and reseed.")):
    from app.seed.seeder import seed_database

    result = seed_database(force=force)
    if result.get("seeded"):
        harmonized = run_harmonization()
        result["harmonization"] = harmonized.stats
        result["job_id"] = harmonized.job_id
    return result


@router.post("/reindex")
def reindex():
    """Rebuild BM25 and the commodity-partitioned FAISS indexes from PostgreSQL."""
    return hydrate_indexes()


@router.get("/index-status")
def index_status():
    return store.stats()


@router.get("/jobs")
def list_jobs(limit: int = Query(20, ge=1, le=100)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM harmonization_job_logs ORDER BY started_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM harmonization_job_logs WHERE job_id = %s", (job_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return dict(row)


@router.post("/evaluate")
def run_evaluation():
    """Score the pipeline against the hidden synthetic ground truth."""
    metrics = evaluate(persist=True)
    if "error" in metrics:
        raise HTTPException(status_code=409, detail=metrics["error"])
    return metrics


@router.get("/evaluate/latest")
def latest_evaluation():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM evaluation_runs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No evaluation has been run yet. POST /evaluate to produce one.",
        )
    return dict(row)


@router.get("/safety-blocks")
def list_safety_blocks(limit: int = Query(50, ge=1, le=200)):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.*, ra.raw_description AS description_a, ra.cpse_org AS cpse_a,
                   ra.legacy_code AS code_a,
                   rb.raw_description AS description_b, rb.cpse_org AS cpse_b,
                   rb.legacy_code AS code_b
            FROM safety_blocks s
            JOIN raw_records ra ON ra.id = s.record_a
            JOIN raw_records rb ON rb.id = s.record_b
            ORDER BY s.score DESC, s.id LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}
