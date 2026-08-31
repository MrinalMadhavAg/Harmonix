from __future__ import annotations

import logging
import threading
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.harmonization import run_harmonization
from app.services.ingestion import IngestValidationError, ingest_rows, parse_tabular

log = logging.getLogger(__name__)
router = APIRouter(tags=["ingestion"])

MAX_UPLOAD_BYTES = 8 * 1024 * 1024

# Progress for in-flight uploads. Polled by the ingestion screen; deliberately
# in-memory because it is throwaway UI state -- the ingested RECORDS are in
# PostgreSQL, and a lost progress bar costs nothing.
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()

STAGES = [
    "Validating file",
    "Normalizing descriptions",
    "Extracting attributes and embeddings",
    "Matching and golden record generation",
]


def _set(job_id: str, **kwargs) -> None:
    with _LOCK:
        # The id is seeded here rather than passed by callers, which would
        # collide with the positional argument.
        _JOBS.setdefault(job_id, {"job_id": job_id}).update(kwargs)


@router.post("/ingest/upload")
async def upload(file: UploadFile = File(...)):
    """Upload a CSV or Excel export and run it through the full pipeline."""
    content = await file.read()
    if not content:
        raise IngestValidationError("The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise IngestValidationError(
            f"File is {len(content) / 1e6:.1f} MB; the limit is {MAX_UPLOAD_BYTES / 1e6:.0f} MB."
        )

    job_id = f"upl_{uuid.uuid4().hex[:12]}"
    _set(job_id, filename=file.filename, status="RUNNING",
         stage=STAGES[0], step=1, total_steps=len(STAGES))

    try:
        rows = parse_tabular(content, file.filename or "upload.csv")
        _set(job_id, stage=STAGES[1], step=2, received=len(rows))

        _set(job_id, stage=STAGES[2], step=3)
        report = ingest_rows(rows, source_batch=file.filename, reindex=True)

        _set(job_id, stage=STAGES[3], step=4)
        harmonized = run_harmonization()

        _set(job_id, status="SUCCEEDED", stage="Complete", step=4,
             report=report.to_dict(), harmonization=harmonized.stats)
        return {
            "job_id": job_id,
            "report": report.to_dict(),
            "harmonization": harmonized.stats,
        }
    except IngestValidationError as exc:
        _set(job_id, status="FAILED", error=str(exc))
        raise
    except Exception as exc:  # noqa: BLE001 - recorded then re-raised
        _set(job_id, status="FAILED", error=f"{type(exc).__name__}: {exc}")
        log.exception("Ingestion job %s failed", job_id)
        raise


@router.get("/ingest/jobs/{job_id}")
def job_status(job_id: str):
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Upload job {job_id} not found.")
    return job


@router.get("/ingest/template")
def template():
    """The expected upload format, and the aliases accepted for each column."""
    return {
        "required_columns": ["cpse_org", "legacy_code", "description"],
        "optional_columns": ["commodity_type", "quantity", "uom", "unit_value_inr"],
        "accepted_aliases": {
            "cpse_org": ["cpse", "org", "organisation", "organization", "cpse_code"],
            "legacy_code": ["material_code", "code", "item_code"],
            "description": ["material_description", "item_description", "desc", "raw_description"],
            "commodity_type": ["commodity", "category"],
            "quantity": ["qty", "stock"],
            "uom": ["unit", "unit_of_measure"],
            "unit_value_inr": ["value", "rate"],
        },
        "example_csv": (
            "cpse_org,legacy_code,description,commodity_type,quantity,uom\n"
            "BHEL,10023841,\"GATE VALVE 6 INCH CS CLASS 150 FLANGED\",gate_valve,12,NOS\n"
            "IOCL,MAT-GV-0284,\"GT VLV DN150 CARBON STEEL CL150 FLGD\",gate_valve,7,NOS\n"
        ),
        "notes": [
            "commodity_type is optional; it is inferred from the description when omitted.",
            "A record whose commodity cannot be determined is stored but not auto-matched.",
            "(cpse_org, legacy_code) must be unique; existing records are left unchanged.",
            "quantity/uom/unit_value_inr populate the illustrative demo inventory only.",
        ],
    }
