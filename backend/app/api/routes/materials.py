from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.core.attributes import extract_attributes, schema_for
from app.core.commodities import COMMODITIES, COMMODITY_LABELS
from app.core.safety import evaluate_pair
from app.core.scoring import match_score
from app.db.session import get_conn
from app.ml import embeddings
from app.ml.indexes import store
from app.services import queries
from app.services.review import attribute_evidence_matrix

router = APIRouter(tags=["materials"])


@router.get("/materials")
def list_materials(
    search: str | None = None,
    cpse: str | None = None,
    commodity: str | None = None,
    status: str | None = None,
    min_confidence: float | None = Query(None, ge=0, le=1),
    sort: str = "id",
    direction: str = "asc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return queries.list_materials(
        search=search, cpse=cpse, commodity=commodity, status=status,
        min_confidence=min_confidence, sort=sort, direction=direction,
        limit=limit, offset=offset,
    )


@router.get("/materials/{record_id}")
def get_material(record_id: int):
    material = queries.get_material(record_id)
    if material is None:
        raise HTTPException(status_code=404, detail=f"Material {record_id} not found.")
    material["attribute_schema"] = [
        {"key": k, "label": label} for k, label in schema_for(material.get("commodity_type"))
    ]
    return material


@router.get("/materials/{record_id}/candidates")
def material_candidates(record_id: int, k: int = Query(10, ge=1, le=50)):
    """Ranked candidate matches for one record, each with its full explanation."""
    s = get_settings()
    with get_conn() as conn:
        rec = conn.execute(
            """
            SELECT r.*, c.nmi FROM raw_records r
            LEFT JOIN crosswalk c ON c.record_id = r.id WHERE r.id = %s
            """,
            (record_id,),
        ).fetchone()
        if rec is None:
            raise HTTPException(status_code=404, detail=f"Material {record_id} not found.")
        rec = dict(rec)

    stored = store.get_record(record_id)
    emb = stored.get("embedding") if stored else embeddings.embed_one(
        rec["normalized_description"] or rec["raw_description"]
    )

    cands = store.search(
        commodity=rec.get("commodity_type"),
        query_text=rec.get("normalized_description") or "",
        query_embedding=emb,
        k=max(k * 3, s.candidate_k),
        exclude_record_id=record_id,
    )
    if not cands:
        return {"record_id": record_id, "candidates": [], "threshold": s.match_threshold}

    with get_conn() as conn:
        others = {
            int(r["id"]): dict(r)
            for r in conn.execute(
                """
                SELECT r.id, r.cpse_org, r.legacy_code, r.raw_description,
                       r.normalized_description, r.attributes, r.commodity_type,
                       c.nmi, g.standardized_description
                FROM raw_records r
                LEFT JOIN crosswalk c ON c.record_id = r.id
                LEFT JOIN golden_records g ON g.nmi = c.nmi
                WHERE r.id = ANY(%s)
                """,
                ([c.record_id for c in cands],),
            ).fetchall()
        }

    out = []
    for c in cands:
        other = others.get(c.record_id)
        if other is None:
            continue
        ms = match_score(rec, other, c.semantic, c.lexical, rec.get("commodity_type"))
        verdict = evaluate_pair(rec.get("attributes"), other.get("attributes"),
                                rec.get("commodity_type"))
        out.append(
            {
                "record_id": c.record_id,
                "nmi": other.get("nmi"),
                "cpse_org": other["cpse_org"],
                "legacy_code": other["legacy_code"],
                "raw_description": other["raw_description"],
                "standardized_description": other.get("standardized_description"),
                "retrieval_source": c.source,
                "score": ms.score,
                "explanation": ms.to_dict(),
                "safety": verdict.to_dict(),
                "would_merge": ms.score >= s.match_threshold and verdict.allows_merge,
            }
        )

    out.sort(key=lambda e: e["score"], reverse=True)
    for i, e in enumerate(out[:k], start=1):
        e["rank"] = i
    return {"record_id": record_id, "candidates": out[:k], "threshold": s.match_threshold}


@router.get("/crosswalk/{nmi}")
def get_crosswalk(nmi: str):
    data = queries.get_crosswalk(nmi)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"{nmi} is not a known National Material Identifier.",
        )
    data["evidence_matrix"] = attribute_evidence_matrix(nmi)
    return data


@router.get("/golden-records")
def list_golden_records(
    search: str | None = None,
    commodity: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return queries.list_golden_records(
        search=search, commodity=commodity, limit=limit, offset=offset
    )


@router.get("/cpses")
def list_cpses():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.cpse_org,
                   count(*) AS materials,
                   count(*) FILTER (WHERE q.status = 'AUTO_MATCHED') AS harmonized,
                   count(*) FILTER (WHERE q.status IN ('NEEDS_REVIEW','INSUFFICIENT_EVIDENCE')) AS pending,
                   count(*) FILTER (WHERE q.status = 'BLOCKED') AS blocked,
                   count(DISTINCT c.nmi) AS distinct_nmis,
                   AVG(c.match_score) AS avg_confidence
            FROM raw_records r
            LEFT JOIN crosswalk c ON c.record_id = r.id
            LEFT JOIN review_queue_items q ON q.record_id = r.id
            GROUP BY r.cpse_org ORDER BY materials DESC
            """
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/cpses/{cpse}")
def get_cpse(cpse: str):
    data = queries.cpse_detail(cpse.upper())
    if not data:
        raise HTTPException(status_code=404, detail=f"CPSE '{cpse}' has no records.")
    return data


@router.get("/commodities")
def list_commodities():
    with get_conn() as conn:
        counts = {
            r["commodity_type"]: int(r["n"])
            for r in conn.execute(
                "SELECT commodity_type, count(*) AS n FROM raw_records "
                "WHERE commodity_type IS NOT NULL GROUP BY commodity_type"
            ).fetchall()
        }
    return {
        "items": [
            {
                "key": c,
                "label": COMMODITY_LABELS[c],
                "materials": counts.get(c, 0),
                "attributes": [{"key": k, "label": lbl} for k, lbl in schema_for(c)],
            }
            for c in COMMODITIES
        ]
    }


@router.post("/normalize-preview")
def normalize_preview(payload: dict):
    """Inspect the normalization and extraction of an arbitrary description."""
    from app.core.commodities import detect_commodity, is_known
    from app.core.normalization import normalize

    text = (payload or {}).get("description", "")
    if not text:
        raise ValueError("A 'description' field is required.")
    commodity = (payload or {}).get("commodity_type")
    if not is_known(commodity):
        commodity = detect_commodity(text)

    result = normalize(text, commodity if commodity != "unknown" else None)
    attrs = extract_attributes(result.text, commodity)
    return {
        "raw_description": text,
        "commodity_type": commodity,
        "normalized_description": result.text,
        "normalization_trace": result.trace,
        "attributes": attrs,
    }
