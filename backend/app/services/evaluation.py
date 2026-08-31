"""Evaluation against the hidden synthetic ground truth.

Definitions used throughout -- every reported number means exactly this:

  Pair       An unordered pair of source records of the SAME commodity. Only
             same-commodity pairs are considered, because retrieval never
             proposes a cross-commodity link.
  Positive   Ground truth: both records derive from the same canonical item.
  Predicted  The system placed both records under the same NMI.

  Precision  predicted-same that really are same / all predicted-same
  Recall     predicted-same that really are same / all truly-same
  F1         harmonic mean of the two

  Recall@K   share of truly-same pairs where hybrid retrieval put the partner
             in the candidate list at all. This upper-bounds the achievable
             recall -- no scorer can recover a pair retrieval never proposed.

  Hard negative  A pair from two DIFFERENT canonicals that belong to the same
             confusable group (CL150 vs CL300, SS316 vs SS316L, 25 mm vs
             30 mm bore). Reported separately, because performance on
             random negatives is not informative.
"""
from __future__ import annotations

import itertools
import logging
from collections import defaultdict

from psycopg.types.json import Jsonb

from app.config import get_settings
from app.db.session import get_conn
from app.ml.indexes import store
from app.seed.catalog import hard_negative_groups

log = logging.getLogger(__name__)


def _load_labelled() -> list[dict]:
    with get_conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                """
                SELECT r.id, r.commodity_type, r.normalized_description,
                       g.canonical_id, c.nmi
                FROM raw_records r
                JOIN ground_truth g ON g.record_id = r.id
                LEFT JOIN crosswalk c ON c.record_id = r.id
                ORDER BY r.id
                """
            ).fetchall()
        ]


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
    }


def candidate_recall_at_k(records: list[dict], k: int) -> dict:
    """Share of truly-same pairs that hybrid retrieval surfaces at all."""
    by_canonical: dict[str, list[int]] = defaultdict(list)
    for r in records:
        by_canonical[r["canonical_id"]].append(int(r["id"]))

    truly_same = {
        (min(a, b), max(a, b))
        for ids in by_canonical.values()
        for a, b in itertools.combinations(ids, 2)
    }
    if not truly_same:
        return {"k": k, "pairs": 0, "recall_at_k": 0.0}

    retrieved: set[tuple[int, int]] = set()
    for r in records:
        rid = int(r["id"])
        stored = store.get_record(rid)
        if stored is None:
            continue
        cands = store.search(
            commodity=r["commodity_type"],
            query_text=r["normalized_description"] or "",
            query_embedding=stored.get("embedding"),
            k=k,
            exclude_record_id=rid,
        )
        for c in cands:
            retrieved.add((min(rid, c.record_id), max(rid, c.record_id)))

    hits = len(truly_same & retrieved)
    return {
        "k": k,
        "pairs": len(truly_same),
        "retrieved": hits,
        "recall_at_k": round(hits / len(truly_same), 4),
    }


def evaluate(persist: bool = True, job_id: str | None = None) -> dict:
    records = _load_labelled()
    if not records:
        return {"error": "No ground-truth-labelled records found. Seed the database first."}

    s = get_settings()

    canon_of = {int(r["id"]): r["canonical_id"] for r in records}
    nmi_of = {int(r["id"]): r["nmi"] for r in records}
    commodity_of = {int(r["id"]): r["commodity_type"] for r in records}

    canon_to_group: dict[str, str] = {}
    for group, canonicals in hard_negative_groups().items():
        for c in canonicals:
            canon_to_group[c] = group

    overall = {"tp": 0, "fp": 0, "fn": 0}
    hard = {"tp": 0, "fp": 0, "fn": 0}
    per_commodity: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    false_merges: list[dict] = []
    missed: list[dict] = []

    ids = [int(r["id"]) for r in records]
    for a, b in itertools.combinations(ids, 2):
        if commodity_of[a] != commodity_of[b]:
            continue

        same_truth = canon_of[a] == canon_of[b]
        same_pred = nmi_of[a] is not None and nmi_of[a] == nmi_of[b]

        is_hard_negative = (
            not same_truth
            and canon_to_group.get(canon_of[a]) is not None
            and canon_to_group.get(canon_of[a]) == canon_to_group.get(canon_of[b])
        )

        bucket = "tp" if (same_truth and same_pred) else (
            "fp" if (not same_truth and same_pred) else (
                "fn" if (same_truth and not same_pred) else None
            )
        )
        if bucket is None:
            continue

        overall[bucket] += 1
        per_commodity[commodity_of[a]][bucket] += 1
        if is_hard_negative or same_truth:
            # The hard-negative slice scores the confusable population only:
            # its true pairs and its deliberately-similar false pairs.
            if is_hard_negative or canon_to_group.get(canon_of[a]) is not None:
                hard[bucket] += 1

        if bucket == "fp":
            false_merges.append(
                {"record_a": a, "record_b": b, "nmi": nmi_of[a],
                 "canonical_a": canon_of[a], "canonical_b": canon_of[b],
                 "hard_negative": is_hard_negative}
            )
        elif bucket == "fn" and len(missed) < 40:
            missed.append(
                {"record_a": a, "record_b": b, "canonical": canon_of[a],
                 "nmi_a": nmi_of[a], "nmi_b": nmi_of[b]}
            )

    metrics = {
        "definitions": {
            "pair": "unordered pair of source records of the same commodity",
            "positive": "both records derive from the same canonical material",
            "predicted": "both records were assigned the same NMI",
            "hard_negative": "different canonicals within the same deliberately-confusable group",
        },
        "records": len(records),
        "overall": _prf(overall["tp"], overall["fp"], overall["fn"]),
        "hard_negative_slice": _prf(hard["tp"], hard["fp"], hard["fn"]),
        "per_commodity": {
            c: _prf(v["tp"], v["fp"], v["fn"]) for c, v in sorted(per_commodity.items())
        },
        "candidate_recall": candidate_recall_at_k(records, s.candidate_k),
        "unsafe_merges": len([f for f in false_merges if f["hard_negative"]]),
        "false_merge_examples": false_merges[:20],
        "missed_pair_examples": missed[:20],
        "config": {
            "match_threshold": s.match_threshold,
            "candidate_k": s.candidate_k,
        },
    }

    if persist:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO evaluation_runs (job_id, metrics) VALUES (%s, %s)",
                (job_id, Jsonb(metrics)),
            )
            conn.commit()

    return metrics
