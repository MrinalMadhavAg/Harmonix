"""Startup hydration of the derived indexes from PostgreSQL.

    application starts
        -> PostgreSQL becomes available
        -> stored material records are read back
        -> missing embeddings are regenerated and persisted
        -> BM25 corpus is rebuilt
        -> commodity-partitioned FAISS indexes are rebuilt
        -> application becomes ready

Zero records is a success, not a failure.
"""
from __future__ import annotations

import logging

from app.db.session import get_conn
from app.ml import embeddings
from app.ml.indexes import store

log = logging.getLogger(__name__)


def _backfill_missing_embeddings() -> int:
    """Generate and persist embeddings for rows that lack them."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, normalized_description, raw_description
            FROM raw_records
            WHERE embedding IS NULL
            ORDER BY id
            """
        ).fetchall()
        if not rows:
            return 0

        log.info("Backfilling embeddings for %d record(s)", len(rows))
        texts = [r["normalized_description"] or r["raw_description"] or "" for r in rows]
        vecs = embeddings.embed(texts)
        for row, vec in zip(rows, vecs):
            conn.execute(
                "UPDATE raw_records SET embedding = %s WHERE id = %s",
                (vec, row["id"]),
            )
        conn.commit()
        return len(rows)


def hydrate_indexes() -> dict:
    """Rebuild all in-memory retrieval structures from the database."""
    backfilled = _backfill_missing_embeddings()

    with get_conn() as conn:
        records = conn.execute(
            """
            SELECT id, cpse_org, legacy_code, raw_description, normalized_description,
                   attributes, unspsc_class, commodity_type, embedding, created_at
            FROM raw_records
            ORDER BY id
            """
        ).fetchall()

    if not records:
        store.mark_ready_empty()
        return {"records": 0, "backfilled": backfilled, **store.stats()}

    store.rebuild([dict(r) for r in records])
    return {"records": len(records), "backfilled": backfilled, **store.stats()}
