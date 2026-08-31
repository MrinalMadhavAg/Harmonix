"""Persistent review queue.

State lives in `review_queue_items`, never in a process-local dict, so a
backend restart does not silently discard a steward's work. Approving or
rejecting also writes a `steward_decisions` row, which is the audit trail and
the training data a future learned scorer would use.
"""
from __future__ import annotations

import logging

from psycopg.types.json import Jsonb

from app.core.attributes import schema_for, value_of
from app.core.comparison import compare_attributes
from app.core.safety import critical_fields, evaluate_pair
from app.db.session import get_conn, transaction
from app.services.governance import NmiNotFound, nmi_exists

log = logging.getLogger(__name__)

OPEN_STATUSES = ("NEEDS_REVIEW", "INSUFFICIENT_EVIDENCE", "BLOCKED")
DECIDED_STATUSES = ("APPROVED", "REJECTED")
ALL_STATUSES = ("AUTO_MATCHED", *OPEN_STATUSES, *DECIDED_STATUSES)


def list_review_items(
    *, status: str | None = None, cpse: str | None = None,
    limit: int = 50, offset: int = 0,
) -> dict:
    where, params = [], []
    if status and status.upper() != "ALL":
        if status.upper() == "OPEN":
            where.append("q.status = ANY(%s)")
            params.append(list(OPEN_STATUSES))
        else:
            where.append("q.status = %s")
            params.append(status.upper())
    if cpse:
        where.append("r.cpse_org = %s")
        params.append(cpse)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT count(*) AS n FROM review_queue_items q "
            f"JOIN raw_records r ON r.id = q.record_id{clause}",
            params,
        ).fetchone()["n"]

        rows = conn.execute(
            f"""
            SELECT q.id, q.record_id, q.candidate_nmi, q.candidate_record_id, q.score,
                   q.reason, q.blocked_field, q.status, q.reviewer, q.created_at,
                   q.reviewed_at,
                   r.cpse_org, r.legacy_code, r.raw_description, r.commodity_type,
                   g.standardized_description AS candidate_description
            FROM review_queue_items q
            JOIN raw_records r ON r.id = q.record_id
            LEFT JOIN golden_records g ON g.nmi = q.candidate_nmi
            {clause}
            ORDER BY
                CASE q.status WHEN 'BLOCKED' THEN 0 WHEN 'NEEDS_REVIEW' THEN 1
                              WHEN 'INSUFFICIENT_EVIDENCE' THEN 2 ELSE 3 END,
                q.score DESC NULLS LAST, q.id
            LIMIT %s OFFSET %s
            """,
            [*params, limit, offset],
        ).fetchall()

        counts = {
            r["status"]: int(r["n"])
            for r in conn.execute(
                "SELECT status, count(*) AS n FROM review_queue_items GROUP BY status"
            ).fetchall()
        }

    return {
        "total": int(total), "limit": limit, "offset": offset,
        "items": [dict(r) for r in rows],
        "counts": {s: counts.get(s, 0) for s in ALL_STATUSES},
    }


def get_review_item(item_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT q.*, r.cpse_org, r.legacy_code, r.raw_description,
                   r.normalized_description, r.attributes, r.commodity_type,
                   g.standardized_description AS candidate_description,
                   g.attributes AS candidate_attributes
            FROM review_queue_items q
            JOIN raw_records r ON r.id = q.record_id
            LEFT JOIN golden_records g ON g.nmi = q.candidate_nmi
            WHERE q.id = %s
            """,
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        item = dict(row)

        candidate = None
        if item.get("candidate_record_id"):
            cand = conn.execute(
                """
                SELECT r.id, r.cpse_org, r.legacy_code, r.raw_description,
                       r.normalized_description, r.attributes, c.nmi
                FROM raw_records r LEFT JOIN crosswalk c ON c.record_id = r.id
                WHERE r.id = %s
                """,
                (item["candidate_record_id"],),
            ).fetchone()
            candidate = dict(cand) if cand else None
        item["candidate_record"] = candidate

    # Recompute the evidence live so the UI never shows a stale explanation.
    commodity = item.get("commodity_type")
    other_attrs = (candidate or {}).get("attributes") if candidate else item.get("candidate_attributes")
    keys = [k for k, _ in schema_for(commodity)]
    cs = compare_attributes(item.get("attributes"), other_attrs, commodity, keys=keys)
    verdict = evaluate_pair(item.get("attributes"), other_attrs, commodity)

    labels = dict(schema_for(commodity))
    critical = set(critical_fields(commodity))
    item["evidence_table"] = [
        {
            **c.to_dict(),
            "label": labels.get(c.key, c.key.replace("_", " ").title()),
            "safety_critical": c.key in critical,
        }
        for c in cs.results.values()
    ]
    item["safety"] = verdict.to_dict()
    return item


def decide(
    *, item_id: int, decision: str, steward: str = "demo.steward",
    reason: str | None = None, override_nmi: str | None = None,
) -> dict:
    """Approve or reject a review item, optionally redirecting the NMI."""
    decision = (decision or "").upper()
    if decision not in ("APPROVE", "REJECT"):
        raise ValueError("decision must be APPROVE or REJECT.")

    if override_nmi and not nmi_exists(override_nmi):
        raise NmiNotFound(f"{override_nmi} is not a known National Material Identifier.")

    with transaction() as conn:
        item = conn.execute(
            "SELECT * FROM review_queue_items WHERE id = %s FOR UPDATE", (item_id,)
        ).fetchone()
        if item is None:
            raise LookupError(f"Review item {item_id} not found.")

        target_nmi = override_nmi or item["candidate_nmi"]
        new_status = "APPROVED" if decision == "APPROVE" else "REJECTED"

        if decision == "APPROVE":
            if not target_nmi:
                raise ValueError(
                    "This item has no candidate NMI to approve. Supply override_nmi."
                )
            if not conn.execute(
                "SELECT 1 FROM golden_records WHERE nmi = %s", (target_nmi,)
            ).fetchone():
                raise NmiNotFound(f"{target_nmi} is not a known National Material Identifier.")

            rec = conn.execute(
                "SELECT * FROM raw_records WHERE id = %s", (item["record_id"],)
            ).fetchone()

            previous = conn.execute(
                "SELECT nmi FROM crosswalk WHERE record_id = %s", (item["record_id"],)
            ).fetchone()
            previous_nmi = previous["nmi"] if previous else None

            conn.execute(
                """
                INSERT INTO crosswalk
                    (nmi, record_id, cpse_org, legacy_code, match_score,
                     relationship, status, evidence)
                VALUES (%s, %s, %s, %s, %s, 'STEWARD_CONFIRMED', 'ACTIVE', %s)
                ON CONFLICT (record_id) DO UPDATE SET
                    nmi = EXCLUDED.nmi,
                    match_score = EXCLUDED.match_score,
                    relationship = EXCLUDED.relationship,
                    evidence = EXCLUDED.evidence
                """,
                (
                    target_nmi, item["record_id"], rec["cpse_org"], rec["legacy_code"],
                    item["score"],
                    Jsonb({"approved_by": steward, "previous_nmi": previous_nmi,
                           "reason": reason}),
                ),
            )

            conn.execute(
                """
                UPDATE golden_records SET
                    member_count = (SELECT count(*) FROM crosswalk WHERE nmi = golden_records.nmi),
                    updated_at = now()
                WHERE nmi = ANY(%s)
                """,
                ([n for n in {target_nmi, previous_nmi} if n],),
            )

            # A golden record that just lost its last member is dead weight.
            conn.execute(
                """
                DELETE FROM golden_records g
                WHERE g.member_count = 0
                  AND NOT EXISTS (SELECT 1 FROM crosswalk c WHERE c.nmi = g.nmi)
                """
            )

            conn.execute(
                """
                INSERT INTO golden_record_audit
                    (nmi, changed_field, old_value, new_value, changed_by, reason)
                VALUES (%s, 'crosswalk_member', %s, %s, %s, %s)
                """,
                (
                    target_nmi, previous_nmi,
                    f"{rec['cpse_org']}/{rec['legacy_code']}", steward,
                    reason or "Approved from review queue",
                ),
            )

        conn.execute(
            """
            UPDATE review_queue_items
            SET status = %s, reviewer = %s, reviewed_at = now(),
                candidate_nmi = COALESCE(%s, candidate_nmi)
            WHERE id = %s
            """,
            (new_status, steward, override_nmi, item_id),
        )

        conn.execute(
            """
            INSERT INTO steward_decisions
                (record_a, record_b, ai_score, features, human_decision, steward, reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                item["record_id"], item["candidate_record_id"], item["score"],
                Jsonb(dict(item["evidence"] or {})), new_status, steward, reason,
            ),
        )

    log.info("Review item %s %s by %s", item_id, new_status, steward)
    return {"id": item_id, "status": new_status, "nmi": override_nmi or None}


def steward_decision_log(limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                """
                SELECT s.*, r.cpse_org, r.legacy_code, r.raw_description
                FROM steward_decisions s
                LEFT JOIN raw_records r ON r.id = s.record_a
                ORDER BY s.decided_at DESC LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]


def attribute_evidence_matrix(nmi: str) -> dict | None:
    """Per-attribute comparison across every CPSE in a cluster, vs the golden record."""
    with get_conn() as conn:
        gr = conn.execute("SELECT * FROM golden_records WHERE nmi = %s", (nmi,)).fetchone()
        if gr is None:
            return None
        members = conn.execute(
            """
            SELECT r.id, r.cpse_org, r.legacy_code, r.attributes, r.raw_description
            FROM crosswalk c JOIN raw_records r ON r.id = c.record_id
            WHERE c.nmi = %s ORDER BY r.cpse_org, r.legacy_code
            """,
            (nmi,),
        ).fetchall()

    commodity = gr["commodity_type"]
    critical = set(critical_fields(commodity))
    golden_attrs = gr["attributes"] or {}

    rows = []
    for key, label in schema_for(commodity):
        cells = []
        for m in members:
            own = value_of(m["attributes"], key)
            golden = value_of(golden_attrs, key)
            state = (
                "UNKNOWN" if own is None
                else ("MATCH" if str(own).upper() == str(golden).upper() else "MISMATCH")
            )
            cells.append(
                {
                    "record_id": int(m["id"]), "cpse_org": m["cpse_org"],
                    "legacy_code": m["legacy_code"],
                    "value": own, "state": state,
                }
            )
        g = golden_attrs.get(key) if isinstance(golden_attrs.get(key), dict) else None
        rows.append(
            {
                "key": key, "label": label,
                "safety_critical": key in critical,
                "cells": cells,
                "golden": {
                    "value": g.get("value") if g else None,
                    "confidence": g.get("confidence") if g else None,
                    "agreement": g.get("agreement") if g else None,
                    "contested_values": g.get("contested_values") if g else None,
                },
            }
        )

    return {
        "nmi": nmi,
        "commodity_type": commodity,
        "cpses": [{"record_id": int(m["id"]), "cpse_org": m["cpse_org"],
                   "legacy_code": m["legacy_code"],
                   "raw_description": m["raw_description"]} for m in members],
        "rows": rows,
    }
