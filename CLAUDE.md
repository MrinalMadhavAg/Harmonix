# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the whole stack (postgres + ml-service + web)
docker compose up --build

# Backend tests — unit + pipeline, no database or model download needed
docker compose exec ml-service python -m pytest tests/ -q

# Integration tests — require live PostgreSQL and the embedding model
docker compose exec ml-service python -m pytest tests/ -m integration -v

# A single test
docker compose exec ml-service python -m pytest tests/test_safety.py::TestBlock::test_316_vs_316l_blocks -v

# Frontend
cd frontend && npm run build      # production build
cd frontend && npx tsc --noEmit   # typecheck only
cd frontend && npm run dev        # dev server on :3000
```

The backend unit suite runs outside Docker with only `pytest numpy networkx
faiss-cpu rank-bm25 pandas psycopg[binary,pool] pgvector pydantic-settings`
installed — `sentence-transformers` is not needed (see `tests/harness.py`).

Re-run the pipeline after changing any matching rule: `POST /harmonize`, or
the **Run pipeline** button on `/harmonization`.

## Architecture

Three services: `postgres` (pgvector), `ml-service` (FastAPI), `web` (Next.js).
The browser only ever calls its own origin — `next.config.js` rewrites
`/api/*` to the FastAPI service, so there is no CORS in the container network.

### The layering that matters

```
app/core/       pure logic, no I/O — normalization, attributes, comparison, scoring, safety, weights
app/ml/         embeddings, commodity-partitioned FAISS + BM25, startup hydration
app/services/   orchestration — harmonization, clustering, survivorship, review, governance, evaluation
app/db/         schema bootstrap, pooled connections, transactions
app/api/routes/ thin HTTP layer
```

`app/core/` imports nothing from `app/db/` or `app/services/`. That is what
makes the whole matching stack testable without a database.

### Invariants — breaking these breaks the product

**PostgreSQL is the source of truth.** FAISS and BM25 are derived and rebuilt
from it at startup (`app/ml/hydration.py`). Never make `/seed` the only path to
a working system; a restart must recover on its own.

**One comparison implementation.** `app/core/comparison.py` owns the
`MATCH` / `MISMATCH` / `UNKNOWN` three-state model. `UNKNOWN` is neither a
match nor a mismatch. Do not re-implement this logic in scoring, safety,
clustering or the UI — import it.

**Safety is separate from scoring.** `scoring.py` must contain no safety logic;
`safety.py` must contain no scoring. A blocked pair still gets its honest
similarity score. If you find yourself capping a score to prevent a merge, the
change belongs in the safety layer.

**The safety toggle must cause a real re-run.** `enforce_safety=False` disables
both the edge gate *and* cluster validation (they apply the same
safety-critical logic). Leaving validation on would silently re-impose the
constraint the operator just switched off.

**Connected components are not clusters.** Every component is re-validated
against the safety-critical fields and split where members disagree
(`app/services/clustering.py`). A member missing a safety-critical value is
never absorbed into a group that states it.

**Normalization is commodity-scoped.** `150MM` is a nominal bore on a valve, a
bore diameter on a bearing, and part of a cross-section on a cable. There is no
global `(\d+)\s*MM` rule and there must never be one. See the regression tests
in `tests/test_normalization.py::TestGreedyMillimetreRegression`.

**Material grades are never collapsed.** SS316 and SS316L are different alloys.
The regex guards in `app/core/attributes.py::_MATERIAL_RULES` are load-bearing;
`316L` is matched before `316`, and `316` carries `(?!\s?L\b)`.

**Every attribute carries provenance** — `{value, source, method, confidence}`.
Never store a bare value. `method` is `rule`, `derived` (inferred from a
standard, e.g. bearing bore from an ISO designation) or `llm`.

**Standard equivalences are soft.** `PN20`/`CL150` live in
`app/core/standards.py` with a confidence and applicable commodity. They are
never substituted into a description and cannot override a safety block.

**Persistence is one transaction.** `_persist` in
`app/services/harmonization.py` replaces golden records, crosswalk, review
queue and safety blocks together or not at all. Human decisions
(`APPROVED`/`REJECTED`) are read before the wipe and carried across.

**No hardcoded NMIs.** Any NMI a request references is validated against
`golden_records` before use (`governance.nmi_exists`). The frontend always
uses the NMI the backend returned.

**One uvicorn worker** (`app/run.py`). The indexes are per-process memory.

### Embedding dimension

Read from the loaded model at runtime and used to size the pgvector column
(`app/db/schema.py::bootstrap_schema`). Never hardcode it. The
`get_embedding_dimension` / `get_sentence_embedding_dimension` accessor was
renamed in sentence-transformers 6.x; `app/ml/embeddings.py` handles both.

`register_vector` looks the `vector` type up at connection time, so
`wait_for_db()` creates the extension *before* the pool opens.

### Ground truth

`ground_truth` maps `record_id → canonical_id` and is written only by the
seeder and read only by `app/services/evaluation.py`. Nothing in the matching
path may read it.

## Frontend conventions

- Charts go inside `<ChartFrame>`, which mounts after hydration. Recharts
  measures the DOM, so rendering it during SSR produces a hydration mismatch.
- Dates render through `lib/format.ts` with a fixed locale and UTC. Bare
  `toLocaleString()` differs between server and client.
- React keys use database ids, never `cpse + legacy_code` — that pair is unique
  per CPSE but the same code string can legitimately appear under two CPSEs.
- `MatchExplanation` is the one explanation component; reuse it rather than
  showing a bare confidence number anywhere.
- Every table needs loading, empty and error states. `components/ui/primitives.tsx`
  has them.

## Adding a commodity

1. `app/core/commodities.py` — constant, label, UNSPSC code, detection patterns
2. `app/core/attributes.py` — extractor + `ATTRIBUTE_SCHEMA` entry
3. `app/core/safety.py` — `SAFETY_CRITICAL_FIELDS` entry
4. `app/core/weights.py` — `DEFAULT_WEIGHTS` entry
5. `app/core/normalization.py` — only if it needs dimensional rules
6. `app/seed/catalog.py` — canonicals, templates, and at least one hard negative
7. Tests in `tests/test_attributes.py` and `tests/test_safety.py`
8. `frontend/lib/format.ts` — `COMMODITY_LABEL` entry

## Data honesty

Stock quantities are illustrative demo inventory and are labelled as such in
the UI. Transfer requests are a demonstration and perform no real transaction.
Do not present synthetic figures as real CPSE data.
