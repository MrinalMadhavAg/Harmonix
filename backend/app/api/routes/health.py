from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.session import get_conn
from app.ml.indexes import store

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    """200 when the database is reachable and the indexes are hydrated."""
    from app.main import STARTUP_STATE

    db_ok, db_error = True, None
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001 - reported in the payload
        db_ok, db_error = False, f"{type(exc).__name__}: {exc}"

    payload = {
        "status": "healthy" if (db_ok and store.ready) else "degraded",
        "database": {"connected": db_ok, "error": db_error},
        "indexes": store.stats(),
        "startup": {"stage": STARTUP_STATE.get("stage"), "ready": STARTUP_STATE.get("ready")},
    }
    return JSONResponse(status_code=200 if (db_ok and store.ready) else 503, content=payload)


@router.get("/")
def root():
    return {
        "service": "Harmonix",
        "description": "AI-driven standardization and harmonization of material codes across CPSEs",
        "docs": "/docs",
        "health": "/health",
    }
