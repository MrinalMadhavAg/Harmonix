"""Load the synthetic CPSE dataset and record its hidden ground truth."""
from __future__ import annotations

import logging

from app.db.session import get_conn, transaction
from app.seed.catalog import generate_records
from app.services.ingestion import IngestRow, ingest_rows

log = logging.getLogger(__name__)


def database_is_empty() -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT count(*) AS n FROM raw_records").fetchone()
        return int(row["n"]) == 0


def seed_database(force: bool = False) -> dict:
    """Insert the synthetic dataset. Idempotent unless `force` is set."""
    if not force and not database_is_empty():
        with get_conn() as conn:
            n = conn.execute("SELECT count(*) AS n FROM raw_records").fetchone()["n"]
        return {"seeded": False, "reason": "database already contains records", "records": int(n)}

    if force:
        with transaction() as conn:
            # Cascades clear crosswalk, review items, ground truth and inventory.
            conn.execute("DELETE FROM golden_records")
            conn.execute("DELETE FROM raw_records")

    seeds = generate_records()
    rows = [
        IngestRow(
            cpse_org=s.cpse_org,
            legacy_code=s.legacy_code,
            description=s.raw_description,
            commodity_type=s.commodity_type,
            quantity=s.quantity,
            uom=s.uom,
            unit_value_inr=s.unit_value_inr,
        )
        for s in seeds
    ]

    report = ingest_rows(rows, source_batch="synthetic-seed", reindex=True)

    # Ground truth is written to its own table AFTER ingestion, keyed by the
    # database id. Nothing in the matching pipeline reads this table -- it
    # exists purely so evaluation has something to score against.
    with transaction() as conn:
        code_to_id = {
            (r["cpse_org"], r["legacy_code"]): int(r["id"])
            for r in conn.execute("SELECT id, cpse_org, legacy_code FROM raw_records").fetchall()
        }
        written = 0
        for s in seeds:
            rid = code_to_id.get((s.cpse_org, s.legacy_code))
            if rid is None:
                continue
            conn.execute(
                """
                INSERT INTO ground_truth (record_id, canonical_id) VALUES (%s, %s)
                ON CONFLICT (record_id) DO UPDATE SET canonical_id = EXCLUDED.canonical_id
                """,
                (rid, s.canonical_id),
            )
            written += 1

    log.info("Seeded %d records (%d ground-truth labels)", report.inserted, written)
    return {
        "seeded": True,
        "records": report.inserted,
        "ground_truth_labels": written,
        "warnings": report.warnings[:20],
    }
