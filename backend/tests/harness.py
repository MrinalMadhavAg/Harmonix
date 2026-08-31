"""Offline pipeline harness: the real pipeline, no PostgreSQL.

Builds the genuine `IndexStore` (real FAISS partitions, real BM25) over the
synthetic catalogue and runs the real `compute_harmonization`. The only
substituted component is the sentence-transformer, replaced by a
deterministic hashing vectorizer -- see `stub_embed`.

This lets scoring, retrieval, the safety gate, cluster validation and
survivorship be exercised end to end in CI without a database or a model
download. The transformer itself is exercised in the Docker integration path.
"""
from __future__ import annotations

import hashlib
import itertools
from collections import defaultdict

import numpy as np

from app.core.attributes import extract_attributes
from app.core.normalization import normalize_text, tokenize
from app.ml.indexes import IndexStore
from app.seed.catalog import generate_records, hard_negative_groups

EMBED_DIM = 256


def stub_embed(texts: list[str]) -> np.ndarray:
    """Deterministic hashed token/bigram vectorizer standing in for the model.

    Not a language model: it captures lexical overlap, not meaning. It is
    adequate for exercising the FAISS path and the scoring arithmetic, and it
    makes the offline metrics a conservative floor -- the real sentence
    encoder recovers paraphrases this cannot.
    """
    out = np.zeros((len(texts), EMBED_DIM), dtype="float32")
    for i, text in enumerate(texts):
        tokens = tokenize(text or "")
        features = list(tokens) + [
            f"{a}~{b}" for a, b in zip(tokens, tokens[1:])
        ]
        for f in features:
            h = hashlib.blake2b(f.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "big") % EMBED_DIM
            sign = 1.0 if h[4] % 2 == 0 else -1.0
            out[i, idx] += sign
        norm = float(np.linalg.norm(out[i]))
        if norm > 0:
            out[i] /= norm
    return out


def build_corpus(seed: int = 20260101) -> tuple[list[dict], dict[int, str], IndexStore]:
    """Return (records, ground_truth_by_record_id, hydrated index store)."""
    seeds = generate_records(seed=seed)

    records: list[dict] = []
    truth: dict[int, str] = {}
    for i, s in enumerate(seeds, start=1):
        norm = normalize_text(s.raw_description, s.commodity_type)
        records.append(
            {
                "id": i,
                "cpse_org": s.cpse_org,
                "legacy_code": s.legacy_code,
                "raw_description": s.raw_description,
                "normalized_description": norm,
                "attributes": extract_attributes(norm, s.commodity_type),
                "commodity_type": s.commodity_type,
                "unspsc_class": None,
            }
        )
        truth[i] = s.canonical_id

    vectors = stub_embed([r["normalized_description"] for r in records])
    for r, v in zip(records, vectors):
        r["embedding"] = v

    store = IndexStore()
    store.rebuild(records)
    return records, truth, store


def pair_metrics(
    records: list[dict], truth: dict[int, str], nmi_by_record: dict[int, str]
) -> dict:
    """Precision/recall/F1 over same-commodity pairs, plus the hard-negative slice.

    A pair is two records of the same commodity. It is a positive when both
    derive from the same canonical material, and predicted-positive when both
    were assigned the same NMI.
    """
    canon_to_group: dict[str, str] = {}
    for group, canonicals in hard_negative_groups().items():
        for c in canonicals:
            canon_to_group[c] = group

    commodity = {int(r["id"]): r["commodity_type"] for r in records}
    ids = sorted(commodity)

    overall = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    hard = {"tp": 0, "fp": 0, "fn": 0}
    unsafe: list[tuple[int, int, str, str]] = []

    for a, b in itertools.combinations(ids, 2):
        if commodity[a] != commodity[b]:
            continue
        same_truth = truth[a] == truth[b]
        same_pred = (
            nmi_by_record.get(a) is not None and nmi_by_record.get(a) == nmi_by_record.get(b)
        )
        is_hard_negative = (
            not same_truth
            and canon_to_group.get(truth[a]) is not None
            and canon_to_group.get(truth[a]) == canon_to_group.get(truth[b])
        )

        if same_truth and same_pred:
            key = "tp"
        elif not same_truth and same_pred:
            key = "fp"
        elif same_truth and not same_pred:
            key = "fn"
        else:
            key = "tn"

        overall[key] += 1
        if canon_to_group.get(truth[a]) is not None and key != "tn":
            hard[key] += 1
        if key == "fp" and is_hard_negative:
            unsafe.append((a, b, truth[a], truth[b]))

    def prf(d: dict) -> dict:
        p = d["tp"] / (d["tp"] + d["fp"]) if (d["tp"] + d["fp"]) else 0.0
        r = d["tp"] / (d["tp"] + d["fn"]) if (d["tp"] + d["fn"]) else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        return {**d, "precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4)}

    return {
        "overall": prf(overall),
        "hard_negative_slice": prf(hard),
        "unsafe_merges": len(unsafe),
        "unsafe_examples": unsafe[:10],
    }


def candidate_recall(
    records: list[dict], truth: dict[int, str], store: IndexStore, k: int
) -> dict:
    by_canonical: dict[str, list[int]] = defaultdict(list)
    for r in records:
        by_canonical[truth[int(r["id"])]].append(int(r["id"]))

    truly_same = {
        (min(a, b), max(a, b))
        for ids in by_canonical.values()
        for a, b in itertools.combinations(ids, 2)
    }
    retrieved: set[tuple[int, int]] = set()
    for r in records:
        rid = int(r["id"])
        for c in store.search(
            commodity=r["commodity_type"],
            query_text=r["normalized_description"],
            query_embedding=r["embedding"],
            k=k,
            exclude_record_id=rid,
        ):
            retrieved.add((min(rid, c.record_id), max(rid, c.record_id)))

    hits = len(truly_same & retrieved)
    return {
        "k": k,
        "pairs": len(truly_same),
        "retrieved": hits,
        "recall_at_k": round(hits / len(truly_same), 4) if truly_same else 0.0,
    }
