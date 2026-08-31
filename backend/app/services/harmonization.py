"""The harmonization pipeline.

    load records
        -> commodity-partitioned hybrid retrieval (BM25 UNION FAISS)
        -> pairwise scoring
        -> safety gate
        -> similarity graph
        -> connected components
        -> cluster validation (split on contradictory critical values)
        -> golden records via majority survivorship
        -> crosswalk + review queue
        -> ONE transaction

Persistence is a single unit of work. A failure part-way through leaves the
database exactly as it was rather than with golden records that no crosswalk
points at, or a crosswalk referencing NMIs that were never written.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from psycopg.types.json import Jsonb

from app.config import get_settings
from app.core.commodities import COMMODITIES
from app.core.safety import SafetyStatus, evaluate_pair
from app.core.scoring import MatchScore, match_score
from app.db.session import get_conn, transaction
from app.ml import embeddings
from app.ml.indexes import store
from app.services.clustering import build_graph, connected_components, validate_cluster
from app.services.survivorship import build_golden_record

log = logging.getLogger(__name__)

# Review queue statuses (see docs/ARCHITECTURE.md).
AUTO_MATCHED = "AUTO_MATCHED"
NEEDS_REVIEW = "NEEDS_REVIEW"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
BLOCKED = "BLOCKED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"


@dataclass
class PairResult:
    a: int
    b: int
    score: MatchScore
    safety_status: str
    blocked_field: str | None
    safety_reason: str
    safety_detail: dict


@dataclass
class HarmonizationResult:
    job_id: str
    stats: dict = field(default_factory=dict)
    duration_s: float = 0.0


@dataclass
class HarmonizationPlan:
    """Everything the pipeline decided, before anything is written.

    Separating the decision from the write makes the whole pipeline runnable
    against an in-memory index with no database, which is how the offline
    evaluation harness and the pipeline tests exercise it.
    """

    job_id: str
    golden_records: list[dict] = field(default_factory=list)
    crosswalk_rows: list[dict] = field(default_factory=list)
    review_rows: list[dict] = field(default_factory=list)
    blocked_pairs: list[PairResult] = field(default_factory=list)
    pairs: list[PairResult] = field(default_factory=list)
    splits: list[dict] = field(default_factory=list)
    incomplete: list[dict] = field(default_factory=list)
    nmi_by_record: dict[int, str] = field(default_factory=dict)
    stats: dict = field(default_factory=dict)


def _load_records() -> list[dict]:
    with get_conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                """
                SELECT id, cpse_org, legacy_code, raw_description, normalized_description,
                       attributes, unspsc_class, commodity_type
                FROM raw_records
                ORDER BY id
                """
            ).fetchall()
        ]


def _score_pairs(records: list[dict], enforce_safety: bool, k: int) -> list[PairResult]:
    """Generate and score candidate pairs, commodity by commodity."""
    by_id = {int(r["id"]): r for r in records}
    seen: set[tuple[int, int]] = set()
    results: list[PairResult] = []

    for rec in records:
        rid = int(rec["id"])
        commodity = rec.get("commodity_type")
        stored = store.get_record(rid)
        emb = stored.get("embedding") if stored else None
        if emb is None:
            emb = embeddings.embed_one(rec["normalized_description"] or rec["raw_description"])

        candidates = store.search(
            commodity=commodity,
            query_text=rec["normalized_description"] or "",
            query_embedding=emb,
            k=k,
            exclude_record_id=rid,
        )

        for cand in candidates:
            other = by_id.get(cand.record_id)
            if other is None:
                continue
            key = (min(rid, cand.record_id), max(rid, cand.record_id))
            if key in seen:
                continue
            seen.add(key)

            ms = match_score(rec, other, cand.semantic, cand.lexical, commodity)
            verdict = evaluate_pair(rec.get("attributes"), other.get("attributes"), commodity)

            results.append(
                PairResult(
                    a=key[0], b=key[1], score=ms,
                    safety_status=verdict.status.value,
                    blocked_field=verdict.blocked_field,
                    safety_reason=verdict.reason,
                    safety_detail=verdict.to_dict(),
                )
            )
    return results


def compute_harmonization(
    records: list[dict],
    enforce_safety: bool = True,
    threshold: float | None = None,
    review_floor: float | None = None,
    candidate_k: int | None = None,
    job_id: str = "offline",
) -> HarmonizationPlan:
    """Run the decision half of the pipeline. Touches no database."""
    s = get_settings()
    threshold = s.match_threshold if threshold is None else threshold
    review_floor = s.review_floor if review_floor is None else review_floor
    candidate_k = s.candidate_k if candidate_k is None else candidate_k

    plan = HarmonizationPlan(job_id=job_id)
    if not records:
        plan.stats = {"records": 0, "golden_records": 0}
        return plan

    by_id = {int(r["id"]): r for r in records}
    plan.pairs = _score_pairs(records, enforce_safety, candidate_k)

    edges: list[tuple[int, int, float]] = []
    review_band: list[PairResult] = []

    for p in plan.pairs:
        above = p.score.score >= threshold
        safe = p.safety_status == SafetyStatus.PASS.value

        if above and (safe or not enforce_safety):
            edges.append((p.a, p.b, p.score.score))
        elif above and p.safety_status == SafetyStatus.BLOCK.value:
            plan.blocked_pairs.append(p)
        elif above and p.safety_status == SafetyStatus.INSUFFICIENT_EVIDENCE.value:
            review_band.append(p)
        elif p.score.score >= review_floor:
            review_band.append(p)

    graph = build_graph([int(r["id"]) for r in records], edges)
    components = connected_components(graph)

    validated: list[tuple[list[dict], str | None]] = []
    for comp in components:
        members = [by_id[i] for i in comp]
        commodity = members[0].get("commodity_type")
        report = validate_cluster(members, commodity, enforce_safety=enforce_safety)
        plan.splits.extend(report.splits)
        plan.incomplete.extend(report.incomplete_assignments)
        for vc in report.clusters:
            if vc.members:
                validated.append((vc.members, vc.commodity))

    # Deterministic NMI assignment: commodity order, then lowest member id, so
    # a re-run over unchanged data produces the same identifiers.
    validated.sort(
        key=lambda t: (
            COMMODITIES.index(t[1]) if t[1] in COMMODITIES else 99,
            min(int(m["id"]) for m in t[0]),
        )
    )

    for idx, (members, commodity) in enumerate(validated, start=1):
        nmi = f"NMI-{idx:06d}"
        plan.golden_records.append(build_golden_record(nmi, members, commodity))

        for m in members:
            rid = int(m["id"])
            plan.nmi_by_record[rid] = nmi
            plan.crosswalk_rows.append(
                {
                    "nmi": nmi,
                    "record_id": rid,
                    "cpse_org": m["cpse_org"],
                    "legacy_code": m["legacy_code"],
                    "match_score": _best_internal_score(rid, members, plan.pairs),
                    "relationship": "SINGLETON" if len(members) == 1 else "EXACT",
                    "status": "ACTIVE",
                    "evidence": {
                        "cluster_size": len(members),
                        "member_record_ids": [int(x["id"]) for x in members],
                    },
                }
            )

    plan.review_rows = _build_review_rows(
        job_id=job_id,
        records=records,
        nmi_by_record=plan.nmi_by_record,
        pairs=plan.pairs,
        blocked_pairs=plan.blocked_pairs,
        review_band=review_band,
        threshold=threshold,
        enforce_safety=enforce_safety,
    )

    plan.stats = {
        "records": len(records),
        "candidate_pairs": len(plan.pairs),
        "edges": len(edges),
        "components": len(components),
        "golden_records": len(plan.golden_records),
        "clusters_split": len(plan.splits),
        "blocked_pairs": len(plan.blocked_pairs),
        "incomplete_members": len(plan.incomplete),
        "threshold": threshold,
        "enforce_safety": enforce_safety,
        "status_counts": _count_statuses(plan.review_rows),
    }
    return plan


def run_harmonization(
    enforce_safety: bool = True,
    threshold: float | None = None,
    job_id: str | None = None,
) -> HarmonizationResult:
    """Run the full pipeline and replace the derived tables atomically."""
    s = get_settings()
    threshold = s.match_threshold if threshold is None else threshold
    job_id = job_id or f"job_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO harmonization_job_logs (job_id, status, stage, params)
            VALUES (%s, 'RUNNING', 'loading', %s)
            ON CONFLICT (job_id) DO UPDATE SET status='RUNNING', stage='loading'
            """,
            (job_id, Jsonb({"enforce_safety": enforce_safety, "threshold": threshold})),
        )
        conn.commit()

    try:
        records = _load_records()
        if not records:
            with get_conn() as conn:
                conn.execute(
                    """
                    UPDATE harmonization_job_logs
                    SET status='SUCCEEDED', stage='complete', finished_at=now(),
                        stats=%s
                    WHERE job_id=%s
                    """,
                    (Jsonb({"records": 0, "golden_records": 0}), job_id),
                )
                conn.commit()
            return HarmonizationResult(job_id=job_id, stats={"records": 0, "golden_records": 0})

        plan = compute_harmonization(
            records,
            enforce_safety=enforce_safety,
            threshold=threshold,
            job_id=job_id,
        )

        _persist(
            job_id=job_id,
            golden_records=plan.golden_records,
            crosswalk_rows=plan.crosswalk_rows,
            review_rows=plan.review_rows,
            blocked_pairs=plan.blocked_pairs,
            stats=plan.stats,
            splits=plan.splits,
        )

        duration = time.perf_counter() - started
        log.info("Harmonization %s complete in %.2fs: %s", job_id, duration, plan.stats)
        return HarmonizationResult(job_id=job_id, stats=plan.stats, duration_s=duration)

    except Exception as exc:
        log.exception("Harmonization job %s failed", job_id)
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE harmonization_job_logs
                SET status='FAILED', error=%s, finished_at=now()
                WHERE job_id=%s
                """,
                (f"{type(exc).__name__}: {exc}", job_id),
            )
            conn.commit()
        raise


def _best_internal_score(rid: int, members: list[dict], pairs: list[PairResult]) -> float:
    ids = {int(m["id"]) for m in members}
    best = 0.0
    for p in pairs:
        if p.a == rid and p.b in ids:
            best = max(best, p.score.score)
        elif p.b == rid and p.a in ids:
            best = max(best, p.score.score)
    return round(best, 4) if best else (1.0 if len(members) == 1 else 0.0)


def _count_statuses(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


def _build_review_rows(
    *,
    job_id: str,
    records: list[dict],
    nmi_by_record: dict[int, str],
    pairs: list[PairResult],
    blocked_pairs: list[PairResult],
    review_band: list[PairResult],
    threshold: float,
    enforce_safety: bool,
) -> list[dict]:
    """One row per source record describing its harmonization outcome."""
    by_id = {int(r["id"]): r for r in records}

    best_blocked: dict[int, PairResult] = {}
    for p in blocked_pairs:
        for rid in (p.a, p.b):
            cur = best_blocked.get(rid)
            if cur is None or p.score.score > cur.score.score:
                best_blocked[rid] = p

    best_review: dict[int, PairResult] = {}
    for p in review_band:
        for rid in (p.a, p.b):
            cur = best_review.get(rid)
            if cur is None or p.score.score > cur.score.score:
                best_review[rid] = p

    cluster_size: dict[str, int] = {}
    for rid, nmi in nmi_by_record.items():
        cluster_size[nmi] = cluster_size.get(nmi, 0) + 1

    rows: list[dict] = []
    for rec in records:
        rid = int(rec["id"])
        nmi = nmi_by_record.get(rid)
        size = cluster_size.get(nmi or "", 1)

        if size > 1:
            other = best_review.get(rid)
            rows.append(
                {
                    "job_id": job_id, "record_id": rid, "candidate_nmi": nmi,
                    "candidate_record_id": None,
                    "score": _cluster_score(rid, pairs, nmi_by_record),
                    "reason": f"Harmonized with {size - 1} other CPSE record(s) into {nmi}.",
                    "blocked_field": None,
                    "evidence": {"cluster_size": size},
                    "status": AUTO_MATCHED,
                }
            )
            continue

        blocked = best_blocked.get(rid)
        if blocked is not None and enforce_safety:
            other_id = blocked.b if blocked.a == rid else blocked.a
            rows.append(
                {
                    "job_id": job_id, "record_id": rid,
                    "candidate_nmi": nmi_by_record.get(other_id),
                    "candidate_record_id": other_id,
                    "score": blocked.score.score,
                    "reason": blocked.safety_reason,
                    "blocked_field": blocked.blocked_field,
                    "evidence": {
                        "match": blocked.score.to_dict(),
                        "safety": blocked.safety_detail,
                        "candidate_description": by_id[other_id]["raw_description"],
                        "candidate_cpse": by_id[other_id]["cpse_org"],
                        "candidate_legacy_code": by_id[other_id]["legacy_code"],
                    },
                    "status": BLOCKED,
                }
            )
            continue

        near = best_review.get(rid)
        if near is not None:
            other_id = near.b if near.a == rid else near.a
            insufficient = near.safety_status == SafetyStatus.INSUFFICIENT_EVIDENCE.value
            rows.append(
                {
                    "job_id": job_id, "record_id": rid,
                    "candidate_nmi": nmi_by_record.get(other_id),
                    "candidate_record_id": other_id,
                    "score": near.score.score,
                    "reason": (
                        near.safety_reason if insufficient
                        else f"Similarity {near.score.score:.2f} is below the "
                             f"auto-merge threshold of {threshold:.2f}."
                    ),
                    "blocked_field": None,
                    "evidence": {
                        "match": near.score.to_dict(),
                        "safety": near.safety_detail,
                        "candidate_description": by_id[other_id]["raw_description"],
                        "candidate_cpse": by_id[other_id]["cpse_org"],
                        "candidate_legacy_code": by_id[other_id]["legacy_code"],
                    },
                    "status": INSUFFICIENT_EVIDENCE if insufficient else NEEDS_REVIEW,
                }
            )
            continue

        rows.append(
            {
                "job_id": job_id, "record_id": rid, "candidate_nmi": nmi,
                "candidate_record_id": None, "score": 1.0,
                "reason": "No duplicate candidates found in any other CPSE.",
                "blocked_field": None, "evidence": {"cluster_size": 1},
                "status": AUTO_MATCHED,
            }
        )
    return rows


def _cluster_score(rid: int, pairs: list[PairResult], nmi_by_record: dict[int, str]) -> float:
    nmi = nmi_by_record.get(rid)
    best = 0.0
    for p in pairs:
        other = p.b if p.a == rid else (p.a if p.b == rid else None)
        if other is None:
            continue
        if nmi_by_record.get(other) == nmi:
            best = max(best, p.score.score)
    return round(best, 4)


def _persist(
    *,
    job_id: str,
    golden_records: list[dict],
    crosswalk_rows: list[dict],
    review_rows: list[dict],
    blocked_pairs: list[PairResult],
    stats: dict,
    splits: list[dict],
) -> None:
    """Replace all derived tables in a single transaction."""
    with transaction() as conn:
        # Human decisions are preserved across re-runs; everything else derived
        # is rebuilt from scratch.
        decided = {
            int(r["record_id"]): r
            for r in conn.execute(
                """
                SELECT record_id, status, reviewer, reviewed_at, candidate_nmi
                FROM review_queue_items
                WHERE status IN (%s, %s)
                """,
                (APPROVED, REJECTED),
            ).fetchall()
        }

        conn.execute("DELETE FROM review_queue_items")
        conn.execute("DELETE FROM safety_blocks WHERE job_id IS DISTINCT FROM %s", (job_id,))
        conn.execute("DELETE FROM crosswalk")
        conn.execute("DELETE FROM golden_records")

        for gr in golden_records:
            conn.execute(
                """
                INSERT INTO golden_records
                    (nmi, version, standardized_description, unspsc_class,
                     commodity_type, attributes, member_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    gr["nmi"], gr["version"], gr["standardized_description"],
                    gr["unspsc_class"], gr["commodity_type"],
                    Jsonb(gr["attributes"]), gr["member_count"],
                ),
            )

        for cw in crosswalk_rows:
            conn.execute(
                """
                INSERT INTO crosswalk
                    (nmi, record_id, cpse_org, legacy_code, match_score,
                     relationship, status, evidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    cw["nmi"], cw["record_id"], cw["cpse_org"], cw["legacy_code"],
                    cw["match_score"], cw["relationship"], cw["status"],
                    Jsonb(cw["evidence"]),
                ),
            )

        for rv in review_rows:
            prior = decided.get(rv["record_id"])
            status = prior["status"] if prior else rv["status"]
            reviewer = prior["reviewer"] if prior else None
            reviewed_at = prior["reviewed_at"] if prior else None
            conn.execute(
                """
                INSERT INTO review_queue_items
                    (job_id, record_id, candidate_nmi, candidate_record_id, score,
                     reason, blocked_field, evidence, status, reviewer, reviewed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    rv["job_id"], rv["record_id"], rv["candidate_nmi"],
                    rv["candidate_record_id"], rv["score"], rv["reason"],
                    rv["blocked_field"], Jsonb(rv["evidence"]), status,
                    reviewer, reviewed_at,
                ),
            )

        for p in blocked_pairs:
            d = p.safety_detail
            vals = d.get("blocked_values") or [None, None]
            conn.execute(
                """
                INSERT INTO safety_blocks
                    (job_id, record_a, record_b, commodity_type, blocked_field,
                     value_a, value_b, score)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job_id, p.a, p.b, d.get("commodity"), p.blocked_field,
                    str(vals[0]), str(vals[1]), p.score.score,
                ),
            )

        conn.execute(
            """
            UPDATE harmonization_job_logs
            SET status='SUCCEEDED', stage='complete', stats=%s, finished_at=now()
            WHERE job_id=%s
            """,
            (Jsonb({**stats, "splits": splits[:50]}), job_id),
        )
