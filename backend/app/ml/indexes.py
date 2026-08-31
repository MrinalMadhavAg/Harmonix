"""In-memory retrieval indexes, hydrated from PostgreSQL.

PostgreSQL is the source of truth. FAISS and BM25 are derived structures that
are rebuilt from it at startup, so the application is fully operational after
a restart without anyone calling /seed.

FAISS is partitioned BY COMMODITY. Retrieval is constrained at the index
level rather than by post-filtering a global top-k: a global search for a
6" gate valve returns 6" pipes and 6" flanges, and filtering those out
afterwards silently shrinks the candidate list to almost nothing. Partitioned
retrieval gives each commodity its own honest top-k.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

import numpy as np

from app.core.normalization import tokenize

log = logging.getLogger(__name__)


@dataclass
class Candidate:
    record_id: int
    semantic: float
    lexical: float
    source: str  # "faiss", "bm25" or "both"


@dataclass
class _Partition:
    commodity: str
    record_ids: list[int] = field(default_factory=list)
    faiss_index: object | None = None
    bm25: object | None = None
    corpus: list[list[str]] = field(default_factory=list)


class IndexStore:
    """Thread-safe container for the derived retrieval structures."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._partitions: dict[str, _Partition] = {}
        self._records: dict[int, dict] = {}
        self._ready = False
        self._hydrated_at: str | None = None

    # -- state ------------------------------------------------------------
    @property
    def ready(self) -> bool:
        return self._ready

    def stats(self) -> dict:
        with self._lock:
            return {
                "ready": self._ready,
                "hydrated_at": self._hydrated_at,
                "total_records": len(self._records),
                "partitions": {
                    c: len(p.record_ids) for c, p in sorted(self._partitions.items())
                },
            }

    def get_record(self, record_id: int) -> dict | None:
        return self._records.get(record_id)

    def all_records(self) -> list[dict]:
        with self._lock:
            return list(self._records.values())

    def records_for(self, commodity: str) -> list[dict]:
        with self._lock:
            p = self._partitions.get(commodity)
            if not p:
                return []
            return [self._records[i] for i in p.record_ids if i in self._records]

    # -- construction -----------------------------------------------------
    def rebuild(self, records: list[dict]) -> None:
        """Replace the whole index set from a list of DB rows."""
        import faiss

        with self._lock:
            self._records = {int(r["id"]): r for r in records}
            partitions: dict[str, _Partition] = {}

            by_commodity: dict[str, list[dict]] = {}
            for r in records:
                c = r.get("commodity_type") or "unknown"
                by_commodity.setdefault(c, []).append(r)

            for commodity, rows in by_commodity.items():
                p = _Partition(commodity=commodity)
                vectors: list[np.ndarray] = []
                for r in rows:
                    emb = r.get("embedding")
                    if emb is None:
                        continue
                    p.record_ids.append(int(r["id"]))
                    vectors.append(np.asarray(emb, dtype="float32"))
                    p.corpus.append(tokenize(r.get("normalized_description") or ""))

                if vectors:
                    mat = np.vstack(vectors).astype("float32")
                    # Vectors are already L2-normalized, so inner product is cosine.
                    index = faiss.IndexFlatIP(mat.shape[1])
                    index.add(mat)
                    p.faiss_index = index

                if p.corpus:
                    from rank_bm25 import BM25Okapi

                    p.bm25 = BM25Okapi(p.corpus)

                partitions[commodity] = p

            self._partitions = partitions
            self._ready = True
            from datetime import datetime, timezone

            self._hydrated_at = datetime.now(timezone.utc).isoformat()

        log.info("Indexes rebuilt: %s", self.stats())

    def mark_ready_empty(self) -> None:
        """An empty database is a valid state -- startup must still succeed."""
        with self._lock:
            self._records = {}
            self._partitions = {}
            self._ready = True
            from datetime import datetime, timezone

            self._hydrated_at = datetime.now(timezone.utc).isoformat()
        log.info("Indexes hydrated with zero records (empty database).")

    # -- retrieval --------------------------------------------------------
    def search(
        self,
        commodity: str | None,
        query_text: str,
        query_embedding: np.ndarray | None,
        k: int = 30,
        exclude_record_id: int | None = None,
    ) -> list[Candidate]:
        """Hybrid candidate generation: BM25 top-k UNION FAISS top-k.

        Both channels are constrained to the commodity partition. Returns at
        most ~2k candidates, each carrying its semantic and lexical score.
        """
        with self._lock:
            p = self._partitions.get(commodity or "unknown")
            if p is None or not p.record_ids:
                return []

            n = len(p.record_ids)
            take = min(k, n)

            faiss_hits: dict[int, float] = {}
            if query_embedding is not None and p.faiss_index is not None:
                q = np.asarray(query_embedding, dtype="float32").reshape(1, -1)
                scores, idxs = p.faiss_index.search(q, take)
                for score, idx in zip(scores[0], idxs[0]):
                    if idx < 0:
                        continue
                    rid = p.record_ids[int(idx)]
                    # Cosine on normalized sentence embeddings; negatives mean
                    # "unrelated", which is a 0 for our purposes.
                    faiss_hits[rid] = max(0.0, float(score))

            bm25_hits: dict[int, float] = {}
            if p.bm25 is not None:
                tokens = tokenize(query_text)
                if tokens:
                    raw = np.asarray(p.bm25.get_scores(tokens), dtype="float32")
                    if raw.size:
                        top = np.argsort(-raw)[:take]
                        # BM25 is unbounded; normalize against the best score in
                        # this result set so the value is comparable to cosine.
                        peak = float(raw[top[0]]) if raw[top[0]] > 0 else 0.0
                        for idx in top:
                            score = float(raw[int(idx)])
                            if score <= 0:
                                continue
                            rid = p.record_ids[int(idx)]
                            bm25_hits[rid] = score / peak if peak > 0 else 0.0

            out: list[Candidate] = []
            for rid in set(faiss_hits) | set(bm25_hits):
                if exclude_record_id is not None and rid == exclude_record_id:
                    continue
                sem = faiss_hits.get(rid)
                lex = bm25_hits.get(rid)
                if sem is not None and lex is not None:
                    src = "both"
                elif sem is not None:
                    src = "faiss"
                else:
                    src = "bm25"
                out.append(
                    Candidate(
                        record_id=rid,
                        semantic=sem if sem is not None else 0.0,
                        lexical=lex if lex is not None else 0.0,
                        source=src,
                    )
                )

            out.sort(key=lambda c: (c.semantic + c.lexical), reverse=True)
            return out

    def score_pair_lexical(self, commodity: str | None, query_text: str, record_id: int) -> float:
        """Lexical score for one specific pair (used when scoring known pairs)."""
        with self._lock:
            p = self._partitions.get(commodity or "unknown")
            if p is None or p.bm25 is None or record_id not in p.record_ids:
                return 0.0
            tokens = tokenize(query_text)
            if not tokens:
                return 0.0
            raw = np.asarray(p.bm25.get_scores(tokens), dtype="float32")
            if not raw.size:
                return 0.0
            peak = float(raw.max())
            pos = p.record_ids.index(record_id)
            return float(raw[pos]) / peak if peak > 0 else 0.0


# Process-wide singleton. Safe because the service runs one uvicorn worker;
# see app/run.py for why.
store = IndexStore()
