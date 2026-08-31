"""Ingestion: raw description in, indexed material record out.

    validate -> normalize -> extract attributes -> embed -> persist -> reindex

Persistence is transactional per batch: a file that fails validation half-way
leaves no partial batch behind.
"""
from __future__ import annotations

import io
import logging
import uuid
from dataclasses import dataclass, field

from psycopg.types.json import Jsonb

from app.core.attributes import extract_attributes
from app.core.commodities import UNKNOWN_COMMODITY, UNSPSC_BY_COMMODITY, detect_commodity, is_known
from app.core.normalization import normalize
from app.db.session import get_conn, transaction
from app.ml import embeddings
from app.ml.hydration import hydrate_indexes

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"cpse_org", "legacy_code", "description"}
_ALIASES = {
    "cpse": "cpse_org", "organisation": "cpse_org", "organization": "cpse_org",
    "org": "cpse_org", "cpse_code": "cpse_org",
    "material_code": "legacy_code", "code": "legacy_code", "item_code": "legacy_code",
    "material_description": "description", "desc": "description",
    "item_description": "description", "raw_description": "description",
    "commodity": "commodity_type", "category": "commodity_type",
    "qty": "quantity", "stock": "quantity",
    "unit": "uom", "unit_of_measure": "uom",
    "value": "unit_value_inr", "rate": "unit_value_inr",
}


@dataclass
class IngestRow:
    cpse_org: str
    legacy_code: str
    description: str
    commodity_type: str | None = None
    quantity: int | None = None
    uom: str | None = None
    unit_value_inr: float | None = None


@dataclass
class IngestReport:
    job_id: str
    received: int = 0
    inserted: int = 0
    skipped_duplicates: int = 0
    unknown_commodity: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    inserted_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id, "received": self.received, "inserted": self.inserted,
            "skipped_duplicates": self.skipped_duplicates,
            "unknown_commodity": self.unknown_commodity,
            "errors": self.errors, "warnings": self.warnings,
        }


class IngestValidationError(ValueError):
    """Raised for a file the user can fix -- surfaced as HTTP 422."""


def parse_tabular(content: bytes, filename: str) -> list[IngestRow]:
    """Parse a CSV or Excel upload into validated rows."""
    import pandas as pd

    name = (filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    except Exception as exc:  # noqa: BLE001 - reported to the user verbatim
        raise IngestValidationError(f"Could not parse '{filename}': {exc}") from exc

    if df.empty:
        raise IngestValidationError("The uploaded file contains no data rows.")

    df.columns = [
        _ALIASES.get(str(c).strip().lower().replace(" ", "_"), str(c).strip().lower().replace(" ", "_"))
        for c in df.columns
    ]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise IngestValidationError(
            f"Missing required column(s): {', '.join(sorted(missing))}. "
            f"Found: {', '.join(df.columns)}"
        )

    rows: list[IngestRow] = []
    problems: list[str] = []
    for i, rec in enumerate(df.to_dict("records"), start=2):  # row 1 is the header
        cpse = str(rec.get("cpse_org") or "").strip().upper()
        code = str(rec.get("legacy_code") or "").strip()
        desc = str(rec.get("description") or "").strip()
        if not cpse or not code or not desc:
            problems.append(f"Row {i}: cpse_org, legacy_code and description are all required.")
            continue

        commodity = str(rec.get("commodity_type") or "").strip().lower() or None
        if commodity and not is_known(commodity):
            commodity = None

        def _num(key, cast):
            v = rec.get(key)
            if v in (None, "", "nan"):
                return None
            try:
                return cast(float(v))
            except (TypeError, ValueError):
                return None

        rows.append(
            IngestRow(
                cpse_org=cpse, legacy_code=code, description=desc,
                commodity_type=commodity,
                quantity=_num("quantity", int),
                uom=(str(rec.get("uom") or "").strip().upper() or None),
                unit_value_inr=_num("unit_value_inr", float),
            )
        )

    if not rows:
        raise IngestValidationError(
            "No valid rows found. " + (" ".join(problems[:5]) if problems else "")
        )
    return rows


def ingest_rows(
    rows: list[IngestRow], source_batch: str | None = None, reindex: bool = True
) -> IngestReport:
    """Normalize, extract, embed and persist a batch of records."""
    job_id = f"ing_{uuid.uuid4().hex[:12]}"
    batch = source_batch or job_id
    report = IngestReport(job_id=job_id, received=len(rows))

    # De-duplicate within the batch itself before touching the database.
    seen: set[tuple[str, str]] = set()
    unique: list[IngestRow] = []
    for r in rows:
        key = (r.cpse_org, r.legacy_code)
        if key in seen:
            report.skipped_duplicates += 1
            report.warnings.append(
                f"{r.cpse_org} / {r.legacy_code}: duplicate within the uploaded file, kept the first."
            )
            continue
        seen.add(key)
        unique.append(r)

    existing: set[tuple[str, str]] = set()
    if unique:
        # Two-array unnest pairs the columns explicitly. Two separate unnest()
        # calls in a select list rely on lockstep expansion, which is easy to
        # misread and easy to break.
        with get_conn() as conn:
            existing = {
                (r["cpse_org"], r["legacy_code"])
                for r in conn.execute(
                    """
                    SELECT cpse_org, legacy_code FROM raw_records
                    WHERE (cpse_org, legacy_code) IN (
                        SELECT org, code FROM unnest(%s::text[], %s::text[]) AS t(org, code)
                    )
                    """,
                    ([r.cpse_org for r in unique], [r.legacy_code for r in unique]),
                ).fetchall()
            }

    to_insert = []
    for r in unique:
        if (r.cpse_org, r.legacy_code) in existing:
            report.skipped_duplicates += 1
            report.warnings.append(
                f"{r.cpse_org} / {r.legacy_code}: already present, left unchanged."
            )
            continue
        to_insert.append(r)

    if not to_insert:
        return report

    prepared = []
    for r in to_insert:
        commodity = r.commodity_type or detect_commodity(r.description)
        if commodity == UNKNOWN_COMMODITY:
            report.unknown_commodity += 1
            report.warnings.append(
                f"{r.cpse_org} / {r.legacy_code}: commodity type could not be determined; "
                "the record is stored but will not be auto-matched."
            )
            commodity = None

        norm = normalize(r.description, commodity)
        attrs = extract_attributes(norm.text, commodity)
        prepared.append((r, commodity, norm.text, attrs))

    vectors = embeddings.embed([p[2] for p in prepared])

    with transaction() as conn:
        for (r, commodity, norm_text, attrs), vec in zip(prepared, vectors):
            row = conn.execute(
                """
                INSERT INTO raw_records
                    (cpse_org, legacy_code, raw_description, normalized_description,
                     attributes, unspsc_class, commodity_type, source_batch, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cpse_org, legacy_code) DO NOTHING
                RETURNING id
                """,
                (
                    r.cpse_org, r.legacy_code, r.description, norm_text,
                    Jsonb(attrs), UNSPSC_BY_COMMODITY.get(commodity or ""),
                    commodity, batch, vec,
                ),
            ).fetchone()
            if row is None:
                report.skipped_duplicates += 1
                continue
            rid = int(row["id"])
            report.inserted += 1
            report.inserted_ids.append(rid)

            if r.quantity is not None:
                conn.execute(
                    """
                    INSERT INTO demo_inventory (record_id, quantity, uom, unit_value_inr)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (record_id) DO UPDATE
                        SET quantity = EXCLUDED.quantity,
                            uom = EXCLUDED.uom,
                            unit_value_inr = EXCLUDED.unit_value_inr
                    """,
                    (rid, r.quantity, r.uom or "NOS", r.unit_value_inr or 0.0),
                )

    if reindex:
        hydrate_indexes()

    log.info("Ingest %s: %d inserted, %d skipped", job_id, report.inserted, report.skipped_duplicates)
    return report
