"""PostgreSQL connection pool and transaction helpers."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app.config import get_settings

log = logging.getLogger(__name__)

_pool: "psycopg_pool.ConnectionPool | None" = None  # noqa: F821


def _configure(conn: psycopg.Connection) -> None:
    """Register the pgvector adapters on each pooled connection.

    Tolerant of the type being absent: `wait_for_db` creates the extension
    before the pool opens, but a connection established against a database
    where it is somehow missing should still be usable for everything else
    rather than failing the whole pool.
    """
    try:
        register_vector(conn)
    except Exception as exc:  # noqa: BLE001 - degraded, not fatal
        log.warning("pgvector adapters not registered on this connection: %s", exc)


def wait_for_db() -> None:
    """Block until PostgreSQL accepts connections, and ensure pgvector exists.

    The extension must be created BEFORE the pool opens: `register_vector`
    looks the `vector` type up at connection time, so on a brand-new database
    every pooled connection would otherwise be configured against a type that
    does not yet exist.
    """
    s = get_settings()
    last: Exception | None = None
    for attempt in range(1, s.db_connect_retries + 1):
        try:
            with psycopg.connect(s.database_url, connect_timeout=5) as conn:
                conn.execute("SELECT 1")
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit()
            log.info("PostgreSQL reachable after %d attempt(s); pgvector present", attempt)
            return
        except Exception as exc:  # noqa: BLE001 - retried, then re-raised
            last = exc
            log.warning(
                "PostgreSQL not ready (attempt %d/%d): %s",
                attempt,
                s.db_connect_retries,
                exc,
            )
            time.sleep(s.db_connect_delay_s)
    raise RuntimeError(f"PostgreSQL unreachable after {s.db_connect_retries} attempts") from last


def init_pool() -> None:
    global _pool
    from psycopg_pool import ConnectionPool

    if _pool is not None:
        return
    s = get_settings()
    _pool = ConnectionPool(
        s.database_url,
        min_size=1,
        max_size=8,
        configure=_configure,
        kwargs={"row_factory": dict_row},
        open=True,
    )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Autocommit-per-statement connection for reads and single writes."""
    if _pool is None:
        init_pool()
    assert _pool is not None
    with _pool.connection() as conn:
        yield conn


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """Explicit unit of work.

    Everything inside commits together or not at all. psycopg3 opens a
    transaction on the first statement and `pool.connection()` commits on
    clean exit / rolls back on exception, so a raised error here leaves the
    database exactly as it was.
    """
    if _pool is None:
        init_pool()
    assert _pool is not None
    with _pool.connection() as conn:
        with conn.transaction():
            yield conn
