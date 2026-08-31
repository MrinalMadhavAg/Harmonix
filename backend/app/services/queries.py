"""Read-side queries backing the dashboard, materials and crosswalk screens."""
from __future__ import annotations

from typing import Any

from app.db.session import get_conn

_MATERIAL_SELECT = """
    SELECT r.id, r.cpse_org, r.legacy_code, r.raw_description, r.normalized_description,
           r.attributes, r.commodity_type, r.unspsc_class, r.created_at,
           c.nmi, c.match_score, c.relationship,
           q.status AS review_status, q.reason AS review_reason,
           q.blocked_field, q.score AS review_score,
           g.standardized_description
    FROM raw_records r
    LEFT JOIN crosswalk c ON c.record_id = r.id
    LEFT JOIN golden_records g ON g.nmi = c.nmi
    LEFT JOIN review_queue_items q ON q.record_id = r.id
"""


def list_materials(
    *,
    search: str | None = None,
    cpse: str | None = None,
    commodity: str | None = None,
    status: str | None = None,
    min_confidence: float | None = None,
    sort: str = "id",
    direction: str = "asc",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    where: list[str] = []
    params: list[Any] = []

    if search:
        where.append(
            "(r.raw_description ILIKE %s OR r.legacy_code ILIKE %s "
            "OR r.normalized_description ILIKE %s OR c.nmi ILIKE %s)"
        )
        like = f"%{search}%"
        params += [like, like, like, like]
    if cpse:
        where.append("r.cpse_org = %s")
        params.append(cpse)
    if commodity:
        where.append("r.commodity_type = %s")
        params.append(commodity)
    if status:
        where.append("q.status = %s")
        params.append(status)
    if min_confidence is not None:
        where.append("COALESCE(c.match_score, 0) >= %s")
        params.append(min_confidence)

    clause = (" WHERE " + " AND ".join(where)) if where else ""

    sort_map = {
        "id": "r.id", "code": "r.legacy_code", "cpse": "r.cpse_org",
        "description": "r.raw_description", "commodity": "r.commodity_type",
        "nmi": "c.nmi", "confidence": "c.match_score", "status": "q.status",
        "updated": "r.created_at",
    }
    order_col = sort_map.get(sort, "r.id")
    order_dir = "DESC" if str(direction).lower() == "desc" else "ASC"

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT count(*) AS n FROM raw_records r "
            f"LEFT JOIN crosswalk c ON c.record_id = r.id "
            f"LEFT JOIN review_queue_items q ON q.record_id = r.id{clause}",
            params,
        ).fetchone()["n"]

        rows = conn.execute(
            f"{_MATERIAL_SELECT}{clause} ORDER BY {order_col} {order_dir} NULLS LAST, r.id "
            f"LIMIT %s OFFSET %s",
            [*params, limit, offset],
        ).fetchall()

    return {"total": int(total), "limit": limit, "offset": offset,
            "items": [dict(r) for r in rows]}


def get_material(record_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(f"{_MATERIAL_SELECT} WHERE r.id = %s", (record_id,)).fetchone()
        if row is None:
            return None
        material = dict(row)

        inv = conn.execute(
            "SELECT quantity, uom, unit_value_inr FROM demo_inventory WHERE record_id = %s",
            (record_id,),
        ).fetchone()
        material["demo_inventory"] = dict(inv) if inv else None

        if material.get("nmi"):
            siblings = conn.execute(
                """
                SELECT r.id, r.cpse_org, r.legacy_code, r.raw_description,
                       c.match_score, c.relationship
                FROM crosswalk c JOIN raw_records r ON r.id = c.record_id
                WHERE c.nmi = %s AND c.record_id <> %s
                ORDER BY c.match_score DESC NULLS LAST, r.id
                """,
                (material["nmi"], record_id),
            ).fetchall()
            material["nmi_siblings"] = [dict(s) for s in siblings]
        else:
            material["nmi_siblings"] = []
    return material


def get_crosswalk(nmi: str) -> dict | None:
    with get_conn() as conn:
        gr = conn.execute("SELECT * FROM golden_records WHERE nmi = %s", (nmi,)).fetchone()
        if gr is None:
            return None

        members = conn.execute(
            """
            SELECT c.id AS crosswalk_id, c.record_id, c.cpse_org, c.legacy_code,
                   c.match_score, c.relationship, c.status, c.evidence,
                   r.raw_description, r.normalized_description, r.attributes,
                   r.commodity_type, r.created_at,
                   q.status AS review_status, q.reason AS review_reason
            FROM crosswalk c
            JOIN raw_records r ON r.id = c.record_id
            LEFT JOIN review_queue_items q ON q.record_id = c.record_id
            WHERE c.nmi = %s
            ORDER BY c.cpse_org, c.legacy_code
            """,
            (nmi,),
        ).fetchall()

        audit = conn.execute(
            "SELECT * FROM golden_record_audit WHERE nmi = %s ORDER BY changed_at DESC LIMIT 50",
            (nmi,),
        ).fetchall()

        inv = conn.execute(
            """
            SELECT c.cpse_org, SUM(i.quantity) AS quantity,
                   MIN(i.uom) AS uom, AVG(i.unit_value_inr) AS unit_value_inr
            FROM crosswalk c JOIN demo_inventory i ON i.record_id = c.record_id
            WHERE c.nmi = %s
            GROUP BY c.cpse_org ORDER BY c.cpse_org
            """,
            (nmi,),
        ).fetchall()

    return {
        "golden_record": dict(gr),
        "members": [dict(m) for m in members],
        "audit": [dict(a) for a in audit],
        "demo_inventory_by_cpse": [dict(i) for i in inv],
    }


def list_golden_records(
    *, search: str | None = None, commodity: str | None = None,
    limit: int = 50, offset: int = 0,
) -> dict:
    where, params = [], []
    if search:
        where.append("(g.nmi ILIKE %s OR g.standardized_description ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]
    if commodity:
        where.append("g.commodity_type = %s")
        params.append(commodity)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT count(*) AS n FROM golden_records g{clause}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            SELECT g.*, count(DISTINCT c.cpse_org) AS cpse_count
            FROM golden_records g
            LEFT JOIN crosswalk c ON c.nmi = g.nmi
            {clause}
            GROUP BY g.nmi
            ORDER BY count(DISTINCT c.cpse_org) DESC, g.nmi
            LIMIT %s OFFSET %s
            """,
            [*params, limit, offset],
        ).fetchall()
    return {"total": int(total), "limit": limit, "offset": offset,
            "items": [dict(r) for r in rows]}


def dashboard_summary() -> dict:
    with get_conn() as conn:
        totals = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM raw_records)                            AS total_materials,
              (SELECT count(*) FROM golden_records)                         AS golden_records,
              (SELECT count(*) FROM crosswalk)                              AS crosswalk_links,
              (SELECT count(*) FROM review_queue_items
                 WHERE status IN ('NEEDS_REVIEW','INSUFFICIENT_EVIDENCE'))  AS pending_review,
              (SELECT count(*) FROM review_queue_items WHERE status='BLOCKED') AS blocked_matches,
              (SELECT count(*) FROM review_queue_items WHERE status='APPROVED') AS approved,
              (SELECT count(*) FROM review_queue_items WHERE status='REJECTED') AS rejected,
              (SELECT count(*) FROM golden_records WHERE member_count > 1)  AS multi_source_records,
              (SELECT COALESCE(sum(member_count - 1), 0) FROM golden_records
                 WHERE member_count > 1)                                    AS duplicates_removed
            """
        ).fetchone()

        status_breakdown = conn.execute(
            "SELECT status, count(*) AS n FROM review_queue_items GROUP BY status ORDER BY n DESC"
        ).fetchall()

        commodity_breakdown = conn.execute(
            """
            SELECT COALESCE(r.commodity_type, 'unknown') AS commodity_type,
                   count(*) AS materials,
                   count(DISTINCT c.nmi) AS golden_records
            FROM raw_records r LEFT JOIN crosswalk c ON c.record_id = r.id
            GROUP BY 1 ORDER BY materials DESC
            """
        ).fetchall()

        cpse_overview = conn.execute(
            """
            SELECT r.cpse_org,
                   count(*) AS materials,
                   count(*) FILTER (WHERE q.status = 'AUTO_MATCHED')          AS harmonized,
                   count(*) FILTER (WHERE q.status IN ('NEEDS_REVIEW','INSUFFICIENT_EVIDENCE')) AS pending,
                   count(*) FILTER (WHERE q.status = 'BLOCKED')               AS blocked,
                   count(DISTINCT c.nmi)                                       AS distinct_nmis,
                   AVG(c.match_score)                                          AS avg_confidence
            FROM raw_records r
            LEFT JOIN crosswalk c ON c.record_id = r.id
            LEFT JOIN review_queue_items q ON q.record_id = r.id
            GROUP BY r.cpse_org ORDER BY materials DESC
            """
        ).fetchall()

        recent = conn.execute(
            """
            SELECT r.id, r.raw_description, r.cpse_org, r.legacy_code,
                   c.nmi, c.match_score, q.status, r.created_at
            FROM raw_records r
            LEFT JOIN crosswalk c ON c.record_id = r.id
            LEFT JOIN review_queue_items q ON q.record_id = r.id
            ORDER BY r.created_at DESC, r.id DESC LIMIT 12
            """
        ).fetchall()

        confidence_hist = conn.execute(
            """
            SELECT width_bucket(match_score, 0, 1, 10) AS bucket, count(*) AS n
            FROM crosswalk WHERE match_score IS NOT NULL
            GROUP BY bucket ORDER BY bucket
            """
        ).fetchall()

        last_job = conn.execute(
            "SELECT * FROM harmonization_job_logs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()

        blocked_fields = conn.execute(
            """
            SELECT blocked_field, count(*) AS n FROM safety_blocks
            WHERE blocked_field IS NOT NULL GROUP BY blocked_field ORDER BY n DESC
            """
        ).fetchall()

    return {
        "totals": dict(totals),
        "status_breakdown": [dict(r) for r in status_breakdown],
        "commodity_breakdown": [dict(r) for r in commodity_breakdown],
        "cpse_overview": [dict(r) for r in cpse_overview],
        "recent_activity": [dict(r) for r in recent],
        "confidence_histogram": [dict(r) for r in confidence_hist],
        "blocked_fields": [dict(r) for r in blocked_fields],
        "last_job": dict(last_job) if last_job else None,
    }


def cpse_detail(cpse: str) -> dict:
    with get_conn() as conn:
        summary = conn.execute(
            """
            SELECT r.cpse_org,
                   count(*) AS materials,
                   count(*) FILTER (WHERE q.status = 'AUTO_MATCHED') AS harmonized,
                   count(*) FILTER (WHERE q.status IN ('NEEDS_REVIEW','INSUFFICIENT_EVIDENCE')) AS pending,
                   count(*) FILTER (WHERE q.status = 'BLOCKED') AS blocked,
                   AVG(c.match_score) AS avg_confidence
            FROM raw_records r
            LEFT JOIN crosswalk c ON c.record_id = r.id
            LEFT JOIN review_queue_items q ON q.record_id = r.id
            WHERE r.cpse_org = %s GROUP BY r.cpse_org
            """,
            (cpse,),
        ).fetchone()
        if summary is None:
            return {}

        shared = conn.execute(
            """
            SELECT c.nmi, g.standardized_description,
                   count(DISTINCT c2.cpse_org) AS other_cpse_count,
                   array_agg(DISTINCT c2.cpse_org) AS other_cpses
            FROM crosswalk c
            JOIN golden_records g ON g.nmi = c.nmi
            JOIN crosswalk c2 ON c2.nmi = c.nmi AND c2.cpse_org <> c.cpse_org
            WHERE c.cpse_org = %s
            GROUP BY c.nmi, g.standardized_description
            ORDER BY other_cpse_count DESC, c.nmi LIMIT 25
            """,
            (cpse,),
        ).fetchall()
    return {"summary": dict(summary), "shared_materials": [dict(s) for s in shared]}


def surplus_opportunities(limit: int = 15) -> list[dict]:
    """NMIs stocked by more than one CPSE -- illustrative demo inventory only."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.nmi, g.standardized_description, g.commodity_type,
                   count(DISTINCT c.cpse_org) AS cpse_count,
                   sum(i.quantity) AS total_quantity,
                   MIN(i.uom) AS uom,
                   AVG(i.unit_value_inr) AS unit_value_inr,
                   json_agg(json_build_object(
                       'cpse_org', c.cpse_org, 'quantity', i.quantity,
                       'legacy_code', c.legacy_code) ORDER BY i.quantity DESC) AS holdings
            FROM crosswalk c
            JOIN golden_records g ON g.nmi = c.nmi
            JOIN demo_inventory i ON i.record_id = c.record_id
            GROUP BY c.nmi, g.standardized_description, g.commodity_type
            HAVING count(DISTINCT c.cpse_org) > 1
            ORDER BY count(DISTINCT c.cpse_org) DESC, sum(i.quantity) DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
