# Harmonix — AI-Driven Standardization & Harmonization of Material Codes Across CPSEs

Smart India Hackathon 2026 · Enterprise prototype

Independent CPSEs each maintain their own material master. The same 6-inch
carbon steel gate valve is `10023841` at BHEL, `MAT-GV-0284` at IOCL and
`400000918273` at NTPC. Harmonix does **not** try to replace or merge those
codes. It establishes a neutral **National Material Identifier (NMI)** above
them and maintains the crosswalk between the two.

```
BHEL   10023841       ─┐
IOCL   MAT-GV-0284    ─┼──▶  NMI-000001   GATE VALVE, DN150, CARBON STEEL, CL150
NTPC   400000918273   ─┘
```

Every CPSE keeps its own code. The crosswalk is the product.

---

## Running it

```bash
docker compose up --build
```

That is the whole procedure. No manual database initialization, no migration
step, no seed command.

| Service | URL |
|---|---|
| Web application | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs (OpenAPI) | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| PostgreSQL | localhost:5433 (`harmonix` / `harmonix`) |

The first build downloads PyTorch and the sentence-transformer, so expect
**5–12 minutes**. The model is baked into the image, so the container needs no
network at runtime. On first boot the backend seeds the synthetic catalogue and
runs the pipeline before reporting healthy; `web` waits for that.

### What happens on startup

```
wait for PostgreSQL  ──▶  create pgvector extension
                     ──▶  load embedding model, read its dimension
                     ──▶  bootstrap schema (vector column sized to the model)
                     ──▶  hydrate BM25 + per-commodity FAISS from PostgreSQL
                     ──▶  seed + harmonize if the database is empty
                     ──▶  ready
```

PostgreSQL is the source of truth. FAISS and BM25 are derived structures
rebuilt from it on every start, so **a restart needs no `/seed` call** and the
review queue, crosswalk and audit trail all survive.

---

## Tests

```bash
# Unit + pipeline suite: no database, no model download
docker compose exec ml-service python -m pytest tests/ -q

# Integration suite: real PostgreSQL and real embedding model
docker compose exec ml-service python -m pytest tests/ -m integration -v

# Frontend production build
docker compose exec web npm run build
```

The unit suite also runs on a bare checkout with only `pytest`, `numpy`,
`networkx`, `faiss-cpu`, `rank-bm25` and `pandas` installed.

---

## Architecture

```
Next.js (app router)
      │  /api/* rewrite
      ▼
FastAPI
      ├── app/core/       normalization · attributes · comparison · scoring · safety · weights
      ├── app/ml/         embeddings · commodity-partitioned FAISS + BM25 · hydration
      ├── app/services/   harmonization · clustering · survivorship · review · governance · evaluation
      └── app/db/         schema bootstrap · pooled connections · transactions
      ▼
PostgreSQL + pgvector      (source of truth)
```

### The pipeline

```
raw description
   ─▶ normalize                commodity-aware; dimensional canonicalization only
                               where the equivalence is genuinely deterministic
   ─▶ extract attributes       deterministic rules, every value carries provenance
   ─▶ embed                    dimension read from the live model, never hardcoded
   ─▶ retrieve                 BM25 top-k UNION FAISS top-k, constrained to the
                               commodity partition (not filtered afterwards)
   ─▶ score                    semantic + lexical + weighted attribute agreement
   ─▶ safety gate              PASS / BLOCK / INSUFFICIENT_EVIDENCE
   ─▶ graph                    edge iff score ≥ threshold AND gate passes
   ─▶ connected components     candidate clusters
   ─▶ cluster validation       split on contradictory safety-critical values
   ─▶ survivorship             majority value per attribute, with agreement ratio
   ─▶ persist                  golden records + crosswalk + review queue, ONE transaction
```

### Design decisions worth knowing

**Similarity is not identity.** On this dataset the sentence encoder rates a
CL150 vs CL300 gate valve pair at **0.981** cosine and an SS316 vs SS316L pair
at **0.989** — *higher* than genuine matches (0.69–0.96). Semantic similarity
alone would merge exactly the pairs that must never merge. Attribute agreement
and the safety gate, not the encoder, carry the decision.

**Three states, everywhere.** Attribute comparison yields `MATCH`, `MISMATCH`
or `UNKNOWN`. `UNKNOWN` is not a mismatch (absence of evidence is not evidence
of difference) and not a match (agreement is not invented). One module
(`app/core/comparison.py`) implements this; scoring, safety, clustering,
survivorship, the review queue and the evidence UI all import it.

**Safety is a separate layer.** `scoring.py` contains no safety logic and
`safety.py` contains no scoring. A blocked pair still receives its honest
similarity score; the gate decides whether that score is permitted to act.

**Connected components are not enough.** A–B strong, B–C strong, A–C
contradictory yields one component and must not yield one golden record. Every
component is re-checked against the safety-critical fields and split where its
members disagree. A member that leaves a safety-critical field unstated is
never absorbed into a group that states it.

**Standard equivalences are soft.** `PN20 → CL150` is never substituted into a
description. It lives in `app/core/standards.py` with an explicit confidence
and applicable commodity, is used only as a scoring signal, and cannot override
a safety block.

**One uvicorn worker.** FAISS and BM25 are in-process memory. With N workers
each holds an independent copy and a write served by worker 1 is invisible to
worker 2. At this data scale one worker is ample and removes a whole class of
"works on refresh, fails on refresh" bugs. See `app/run.py`.

---

## The safety demonstration

`Harmonization → Enforce safety constraints` re-runs the entire pipeline. The
results are recomputed, not pre-recorded.

| | Safety enforced | Safety disabled |
|---|---|---|
| Pair precision | **1.0000** | 0.1394 |
| Pair recall | 0.7483 | 1.0000 |
| F1 | **0.8560** | 0.2447 |
| Golden records | 62 | 11 |
| Unsafe merges | **0** | **621** |

With the gate off, 168 source codes collapse into 11 identities: carbon steel
valves merge with SS316L valves, CL150 with CL300, 25 mm bores with 30 mm.

---

## Evaluation

Measured against a hidden ground truth stored in a separate table that the
matching pipeline never reads.

- **Pair** — two source records of the same commodity.
- **Positive** — both derive from the same canonical material.
- **Predicted** — both were assigned the same NMI.
- **Hard negative** — two *different* canonicals from the same deliberately
  confusable group (CL150/CL300, SS316/SS316L, 25 mm/30 mm bore, 1.1 kV/3.3 kV,
  SCH40/SCH80, 8.8/10.9).

| Metric | Value |
|---|---|
| Precision | 1.0000 |
| Recall | 0.7483 |
| F1 | 0.8560 |
| Hard-negative slice F1 | 0.8765 |
| Candidate Recall@30 | 0.9966 |
| Unsafe merges | 0 |

Recall is capped by design, not by the matcher: retrieval finds 99.7% of true
pairs, and the misses are records that omit a safety-critical attribute. Those
go to the review queue rather than being merged on an assumption. A threshold
sweep from 0.20 to 0.80 leaves precision at 1.000 throughout — precision here
is held by the safety layer, not by the threshold.

Run it yourself from **Reports → Run evaluation**, or `POST /evaluate`.

---

## Synthetic dataset

38 canonical materials across five commodities (gate valve, pipe, bearing,
electrical cable, fastener), each with 3–6 CPSE variants — 168 records across
five CPSEs, each using a genuinely different code format.

Variants carry realistic damage: abbreviations (`GT VLV`), token reordering,
typos, OCR corruption (`GATE VALEV`, `2OMM`), unit differences (`6"` / `6 IN` /
`150 MM` / `DN150` / `150 NB`), notation differences (`CL150` / `150#` /
`ANSI 150`), missing attributes, OEM codes and inconsistent capitalization.

Hard negatives are deliberate: 14 canonical pairs differ in exactly one
safety-critical attribute and must never merge.

Stock quantities are **illustrative demo inventory**, labelled as such
wherever they appear. Nothing in this system performs a real procurement,
financial or ERP transaction.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://harmonix:harmonix@postgres:5432/harmonix` | Source of truth |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Baked into the image |
| `MATCH_THRESHOLD` | `0.58` | Unsupervised merge confidence |
| `REVIEW_FLOOR` | `0.42` | Below this a pair is not worth a reviewer's time |
| `CANDIDATE_K` | `30` | Retrieval depth per channel |
| `AUTO_SEED` | `true` | Seed on first boot when the database is empty |
| `UVICORN_WORKERS` | `1` | See "One uvicorn worker" above |

Per-commodity scoring weights are stored in PostgreSQL and editable from
**Settings**.
