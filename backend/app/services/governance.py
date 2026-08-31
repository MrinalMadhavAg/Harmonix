"""Governance gate: check a proposed new material against existing NMIs.

The gate never hard-rejects. A CPSE has legitimate reasons to create a code
the system thinks is a duplicate, and a system that blocks them simply gets
worked around. Instead it shows what already exists, makes the duplication
visible, and records the override so the pattern is auditable later.
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.core.attributes import extract_attributes
from app.core.commodities import UNKNOWN_COMMODITY, detect_commodity, is_known
from app.core.normalization import normalize
from app.core.safety import evaluate_pair
from app.core.scoring import match_score
from app.db.session import get_conn, transaction
from app.ml import embeddings
from app.ml.indexes import store

log = logging.getLogger(__name__)


class NmiNotFound(ValueError):
    pass


def nmi_exists(nmi: str) -> bool:
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM golden_records WHERE nmi = %s", (nmi,)
        ).fetchone() is not None


def check_new_material(description: str, commodity_type: str | None = None, top_n: int = 5) -> dict:
    """Score a proposed description against the existing catalogue."""
    s = get_settings()
    description = (description or "").strip()
    if not description:
        raise ValueError("A material description is required.")

    commodity = commodity_type if is_known(commodity_type) else detect_commodity(description)
    commodity_detected = commodity_type is None or not is_known(commodity_type)

    if commodity == UNKNOWN_COMMODITY:
        return {
            "description": description,
            "commodity_type": None,
            "commodity_detected": True,
            "recommendation": "REVIEW",
            "message": (
                "The commodity type could not be determined from this description, so it "
                "cannot be compared against the existing catalogue. Select a commodity "
                "type explicitly or add more detail."
            ),
            "candidates": [],
        }

    norm = normalize(description, commodity)
    attrs = extract_attributes(norm.text, commodity)
    vec = embeddings.embed_one(norm.text)

    probe = {"attributes": attrs}
    candidates = store.search(
        commodity=commodity, query_text=norm.text, query_embedding=vec, k=s.candidate_k
    )

    with get_conn() as conn:
        rows = {
            int(r["record_id"]): dict(r)
            for r in conn.execute(
                """
                SELECT c.record_id, c.nmi, c.match_score, g.standardized_description,
                       g.member_count, g.attributes AS golden_attributes,
                       r.raw_description, r.cpse_org, r.legacy_code, r.attributes
                FROM crosswalk c
                JOIN golden_records g ON g.nmi = c.nmi
                JOIN raw_records r ON r.id = c.record_id
                WHERE c.record_id = ANY(%s)
                """,
                ([c.record_id for c in candidates] or [0],),
            ).fetchall()
        }

        cpse_counts = {}
        if rows:
            for r in conn.execute(
                """
                SELECT nmi, count(DISTINCT cpse_org) AS n FROM crosswalk
                WHERE nmi = ANY(%s) GROUP BY nmi
                """,
                ([r["nmi"] for r in rows.values()],),
            ).fetchall():
                cpse_counts[r["nmi"]] = int(r["n"])

    scored: list[dict] = []
    best_by_nmi: dict[str, dict] = {}
    for cand in candidates:
        row = rows.get(cand.record_id)
        if row is None:
            continue
        ms = match_score(probe, row, cand.semantic, cand.lexical, commodity)
        verdict = evaluate_pair(attrs, row["attributes"], commodity)
        entry = {
            "nmi": row["nmi"],
            "standardized_description": row["standardized_description"],
            "matched_record": {
                "record_id": cand.record_id,
                "cpse_org": row["cpse_org"],
                "legacy_code": row["legacy_code"],
                "raw_description": row["raw_description"],
            },
            "cpse_count": cpse_counts.get(row["nmi"], 1),
            "member_count": row["member_count"],
            "score": ms.score,
            "explanation": ms.to_dict(),
            "safety": verdict.to_dict(),
        }
        prior = best_by_nmi.get(row["nmi"])
        if prior is None or ms.score > prior["score"]:
            best_by_nmi[row["nmi"]] = entry

    scored = sorted(best_by_nmi.values(), key=lambda e: e["score"], reverse=True)[:top_n]

    top = scored[0] if scored else None
    if top and top["score"] >= s.match_threshold and top["safety"]["status"] == "PASS":
        recommendation = "USE_EXISTING"
        message = (
            f"This material closely matches {top['nmi']}, already represented across "
            f"{top['cpse_count']} CPSE(s). Would you still like to create a new material code?"
        )
    elif top and top["score"] >= s.match_threshold and top["safety"]["status"] == "BLOCK":
        recommendation = "CREATE_NEW"
        message = (
            f"{top['nmi']} is textually similar but differs on "
            f"{top['safety']['blocked_field_label']} "
            f"({top['safety']['blocked_values'][0]} vs {top['safety']['blocked_values'][1]}). "
            "This is a genuinely different material and warrants its own code."
        )
    elif top and top["score"] >= s.review_floor:
        recommendation = "REVIEW"
        message = (
            f"{top['nmi']} is a possible match at {top['score']:.0%} confidence but the "
            "evidence is not conclusive. A data steward should confirm before you proceed."
        )
    else:
        recommendation = "CREATE_NEW"
        message = "No comparable material found in the national catalogue. A new code is appropriate."

    return {
        "description": description,
        "normalized_description": norm.text,
        "commodity_type": commodity,
        "commodity_detected": commodity_detected,
        "extracted_attributes": attrs,
        "recommendation": recommendation,
        "message": message,
        "candidates": scored,
        "threshold": s.match_threshold,
    }


def record_override(
    *,
    description: str,
    commodity_type: str | None,
    decision: str,
    suggested_nmi: str | None,
    suggested_score: float | None,
    new_legacy_code: str | None,
    cpse_org: str | None,
    justification: str | None,
    actor: str = "demo.user",
) -> dict:
    """Persist a governance decision. Validates any NMI it references."""
    decision = (decision or "").upper()
    if decision not in ("CREATE_NEW_ANYWAY", "USE_EXISTING", "CANCELLED"):
        raise ValueError(
            "decision must be one of CREATE_NEW_ANYWAY, USE_EXISTING or CANCELLED."
        )

    # Never write a crosswalk reference to an NMI that does not exist.
    if suggested_nmi and not nmi_exists(suggested_nmi):
        raise NmiNotFound(f"{suggested_nmi} is not a known National Material Identifier.")

    if decision == "USE_EXISTING" and not suggested_nmi:
        raise ValueError("Adopting an existing identity requires the NMI to adopt.")

    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO governance_overrides
                (description, commodity_type, suggested_nmi, suggested_score, decision,
                 new_legacy_code, cpse_org, justification, actor)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (
                description, commodity_type, suggested_nmi, suggested_score, decision,
                new_legacy_code, cpse_org, justification, actor,
            ),
        ).fetchone()

        if suggested_nmi:
            conn.execute(
                """
                INSERT INTO golden_record_audit
                    (nmi, changed_field, old_value, new_value, changed_by, reason)
                VALUES (%s, 'governance_decision', NULL, %s, %s, %s)
                """,
                (
                    suggested_nmi, decision, actor,
                    justification or f"Governance gate decision for: {description[:200]}",
                ),
            )

    log.info("Governance override %s by %s (nmi=%s)", decision, actor, suggested_nmi)
    return {"id": int(row["id"]), "created_at": row["created_at"], "decision": decision}


def list_overrides(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM governance_overrides ORDER BY created_at DESC LIMIT %s",
                (limit,),
            ).fetchall()
        ]
