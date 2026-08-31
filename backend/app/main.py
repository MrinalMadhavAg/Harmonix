"""FastAPI application: startup sequence, error handling, routing."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    config_routes,
    governance_routes,
    health,
    ingestion_routes,
    materials,
    pipeline,
    reports,
    review_routes,
)
from app.config import get_settings
from app.core import weights
from app.db.schema import bootstrap_schema
from app.db.session import close_pool, get_conn, init_pool, wait_for_db
from app.ml import embeddings
from app.ml.hydration import hydrate_indexes
from app.ml.indexes import store
from app.services.governance import NmiNotFound
from app.services.ingestion import IngestValidationError

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("harmonix")

STARTUP_STATE: dict = {"ready": False, "stage": "starting", "detail": {}}


def _startup() -> None:
    s = get_settings()

    STARTUP_STATE["stage"] = "waiting_for_database"
    wait_for_db()
    init_pool()

    STARTUP_STATE["stage"] = "loading_embedding_model"
    dim = embeddings.dimension()
    STARTUP_STATE["detail"]["embedding_dimension"] = dim
    STARTUP_STATE["detail"]["embedding_model"] = s.embedding_model

    STARTUP_STATE["stage"] = "bootstrapping_schema"
    bootstrap_schema(dim)
    weights.seed_defaults()

    STARTUP_STATE["stage"] = "hydrating_indexes"
    hydrate = hydrate_indexes()
    STARTUP_STATE["detail"]["hydration"] = hydrate

    with get_conn() as conn:
        raw_count = int(conn.execute("SELECT count(*) AS n FROM raw_records").fetchone()["n"])
        golden_count = int(conn.execute("SELECT count(*) AS n FROM golden_records").fetchone()["n"])

    if raw_count == 0 and s.auto_seed:
        # First boot: make the application demonstrable without a manual step.
        STARTUP_STATE["stage"] = "seeding"
        from app.seed.seeder import seed_database

        STARTUP_STATE["detail"]["seed"] = seed_database()
        raw_count = int(STARTUP_STATE["detail"]["seed"].get("records", 0))
        golden_count = 0

    if raw_count > 0 and golden_count == 0:
        # Records but no golden layer -- either a fresh seed or a previous run
        # that died before it committed. Rebuild it.
        STARTUP_STATE["stage"] = "harmonizing"
        from app.services.harmonization import run_harmonization

        result = run_harmonization()
        STARTUP_STATE["detail"]["harmonization"] = result.stats

    # Re-read the index state: seeding rehydrates, so the figures captured
    # before it ran describe an empty database and would misreport what the
    # service actually has loaded.
    STARTUP_STATE["detail"]["hydration"] = store.stats()

    STARTUP_STATE["stage"] = "ready"
    STARTUP_STATE["ready"] = True
    log.info("Startup complete: %s", STARTUP_STATE["detail"]["hydration"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _startup()
    except Exception as exc:  # noqa: BLE001 - surfaced via /health, never swallowed
        STARTUP_STATE["stage"] = "failed"
        STARTUP_STATE["error"] = f"{type(exc).__name__}: {exc}"
        log.exception("Startup failed")
        raise
    yield
    close_pool()


app = FastAPI(
    title="Harmonix -- CPSE Material Code Harmonization",
    description=(
        "Neutral National Material Identifier (NMI) layer and legacy-code crosswalk "
        "for Central Public Sector Enterprises."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://web:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Error handling: useful messages to the client, full detail to the log.
# ---------------------------------------------------------------------------

@app.exception_handler(IngestValidationError)
async def _ingest_error(request: Request, exc: IngestValidationError):
    return JSONResponse(status_code=422, content={"detail": str(exc), "type": "validation_error"})


@app.exception_handler(NmiNotFound)
async def _nmi_error(request: Request, exc: NmiNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc), "type": "nmi_not_found"})


@app.exception_handler(LookupError)
async def _lookup_error(request: Request, exc: LookupError):
    return JSONResponse(status_code=404, content={"detail": str(exc), "type": "not_found"})


@app.exception_handler(ValueError)
async def _value_error(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc), "type": "bad_request"})


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    # Stack traces belong in the log, not in a procurement officer's browser.
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal error occurred. The technical details have been logged.",
            "type": "internal_error",
            "reference": request.headers.get("x-request-id"),
        },
    )


app.include_router(health.router)
app.include_router(materials.router)
app.include_router(pipeline.router)
app.include_router(review_routes.router)
app.include_router(governance_routes.router)
app.include_router(ingestion_routes.router)
app.include_router(config_routes.router)
app.include_router(reports.router)
