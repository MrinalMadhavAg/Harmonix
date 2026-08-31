"""Idempotent schema bootstrap.

Runs on every application start. Deliberately NOT placed in
docker-entrypoint-initdb.d, because that only executes on a brand-new
volume -- a schema change would then silently not apply to an existing
developer database.
"""
from __future__ import annotations

import logging

from app.db.session import get_conn

log = logging.getLogger(__name__)

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS raw_records (
    id                      BIGSERIAL PRIMARY KEY,
    cpse_org                TEXT NOT NULL,
    legacy_code             TEXT NOT NULL,
    raw_description         TEXT NOT NULL,
    normalized_description  TEXT NOT NULL DEFAULT '',
    attributes              JSONB NOT NULL DEFAULT '{}'::jsonb,
    unspsc_class            TEXT,
    commodity_type          TEXT,
    source_batch            TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A CPSE's own code is unique within that CPSE. Two CPSEs may legitimately
-- reuse the same string, so the constraint is on the pair.
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_records_org_code
    ON raw_records (cpse_org, legacy_code);
CREATE INDEX IF NOT EXISTS ix_raw_records_commodity ON raw_records (commodity_type);

CREATE TABLE IF NOT EXISTS golden_records (
    nmi                     TEXT PRIMARY KEY,
    version                 INTEGER NOT NULL DEFAULT 1,
    standardized_description TEXT NOT NULL,
    unspsc_class            TEXT,
    commodity_type          TEXT,
    attributes              JSONB NOT NULL DEFAULT '{}'::jsonb,
    member_count            INTEGER NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS golden_record_audit (
    id            BIGSERIAL PRIMARY KEY,
    nmi           TEXT NOT NULL,
    changed_field TEXT NOT NULL,
    old_value     TEXT,
    new_value     TEXT,
    changed_by    TEXT NOT NULL DEFAULT 'system',
    reason        TEXT,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_gr_audit_nmi ON golden_record_audit (nmi);

CREATE TABLE IF NOT EXISTS crosswalk (
    id           BIGSERIAL PRIMARY KEY,
    nmi          TEXT NOT NULL REFERENCES golden_records (nmi) ON DELETE CASCADE,
    record_id    BIGINT REFERENCES raw_records (id) ON DELETE CASCADE,
    cpse_org     TEXT NOT NULL,
    legacy_code  TEXT NOT NULL,
    match_score  DOUBLE PRECISION NOT NULL DEFAULT 0,
    relationship TEXT NOT NULL DEFAULT 'EXACT',
    status       TEXT NOT NULL DEFAULT 'ACTIVE',
    evidence     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_crosswalk_record ON crosswalk (record_id);
CREATE INDEX IF NOT EXISTS ix_crosswalk_nmi ON crosswalk (nmi);

CREATE TABLE IF NOT EXISTS steward_decisions (
    id             BIGSERIAL PRIMARY KEY,
    record_a       BIGINT NOT NULL,
    record_b       BIGINT,
    ai_score       DOUBLE PRECISION,
    features       JSONB NOT NULL DEFAULT '{}'::jsonb,
    human_decision TEXT NOT NULL,
    steward        TEXT NOT NULL DEFAULT 'demo.steward',
    reason         TEXT,
    decided_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS review_queue_items (
    id             BIGSERIAL PRIMARY KEY,
    job_id         TEXT,
    record_id      BIGINT NOT NULL REFERENCES raw_records (id) ON DELETE CASCADE,
    candidate_nmi  TEXT,
    candidate_record_id BIGINT,
    score          DOUBLE PRECISION,
    reason         TEXT NOT NULL,
    blocked_field  TEXT,
    evidence       JSONB NOT NULL DEFAULT '{}'::jsonb,
    status         TEXT NOT NULL,
    reviewer       TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at    TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_review_record ON review_queue_items (record_id);
CREATE INDEX IF NOT EXISTS ix_review_status ON review_queue_items (status);

CREATE TABLE IF NOT EXISTS harmonization_job_logs (
    job_id        TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    stage         TEXT,
    params        JSONB NOT NULL DEFAULT '{}'::jsonb,
    stats         JSONB NOT NULL DEFAULT '{}'::jsonb,
    error         TEXT,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS safety_blocks (
    id            BIGSERIAL PRIMARY KEY,
    job_id        TEXT,
    record_a      BIGINT NOT NULL,
    record_b      BIGINT NOT NULL,
    commodity_type TEXT,
    blocked_field TEXT NOT NULL,
    value_a       TEXT,
    value_b       TEXT,
    score         DOUBLE PRECISION,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_safety_blocks_job ON safety_blocks (job_id);

CREATE TABLE IF NOT EXISTS governance_overrides (
    id            BIGSERIAL PRIMARY KEY,
    description   TEXT NOT NULL,
    commodity_type TEXT,
    suggested_nmi TEXT,
    suggested_score DOUBLE PRECISION,
    decision      TEXT NOT NULL,
    new_legacy_code TEXT,
    cpse_org      TEXT,
    justification TEXT,
    actor         TEXT NOT NULL DEFAULT 'demo.user',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS commodity_weights (
    commodity_type TEXT PRIMARY KEY,
    semantic       DOUBLE PRECISION NOT NULL,
    lexical        DOUBLE PRECISION NOT NULL,
    attributes     DOUBLE PRECISION NOT NULL,
    attribute_weights JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Evaluation-only. The matching pipeline must never read this table.
CREATE TABLE IF NOT EXISTS ground_truth (
    record_id    BIGINT PRIMARY KEY REFERENCES raw_records (id) ON DELETE CASCADE,
    canonical_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ground_truth_canonical ON ground_truth (canonical_id);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id          BIGSERIAL PRIMARY KEY,
    job_id      TEXT,
    metrics     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Illustrative demo inventory. Explicitly NOT real CPSE stock data.
CREATE TABLE IF NOT EXISTS demo_inventory (
    record_id  BIGINT PRIMARY KEY REFERENCES raw_records (id) ON DELETE CASCADE,
    quantity   INTEGER NOT NULL DEFAULT 0,
    uom        TEXT NOT NULL DEFAULT 'NOS',
    unit_value_inr DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transfer_requests (
    id            BIGSERIAL PRIMARY KEY,
    nmi           TEXT NOT NULL,
    from_cpse     TEXT NOT NULL,
    to_cpse       TEXT NOT NULL,
    quantity      INTEGER NOT NULL,
    note          TEXT,
    status        TEXT NOT NULL DEFAULT 'DRAFT',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _statements(ddl: str) -> list[str]:
    """Split the DDL into individual statements.

    psycopg3 only accepts multiple statements in one execute() under the
    simple query protocol, and only when no parameters are bound. Splitting
    explicitly keeps this working regardless of driver behaviour, and makes a
    failure point at the statement that actually broke. Safe here because no
    statement contains a semicolon inside a literal.
    """
    return [s.strip() for s in ddl.split(";") if s.strip()]


def bootstrap_schema(embedding_dim: int) -> None:
    """Create tables and ensure the vector column matches the live model dim."""
    with get_conn() as conn:
        for statement in _statements(DDL):
            conn.execute(statement)
        conn.commit()

        row = conn.execute(
            """
            SELECT a.atttypmod AS typmod
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relname = 'raw_records' AND a.attname = 'embedding'
              AND a.attisdropped = false
            """
        ).fetchone()

        if row is None:
            log.info("Adding embedding vector(%d) column", embedding_dim)
            conn.execute(
                f"ALTER TABLE raw_records ADD COLUMN embedding vector({embedding_dim})"
            )
            conn.commit()
        else:
            # pgvector stores the declared dimension directly in atttypmod.
            existing_dim = row["typmod"]
            if existing_dim != embedding_dim:
                log.warning(
                    "Embedding dim changed (%s -> %s); dropping stored vectors so "
                    "they are regenerated with the current model.",
                    existing_dim,
                    embedding_dim,
                )
                conn.execute("ALTER TABLE raw_records DROP COLUMN embedding")
                conn.execute(
                    f"ALTER TABLE raw_records ADD COLUMN embedding vector({embedding_dim})"
                )
                conn.commit()

    log.info("Schema bootstrap complete (embedding_dim=%d)", embedding_dim)
