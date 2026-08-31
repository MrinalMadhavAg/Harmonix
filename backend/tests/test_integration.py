"""Integration tests: real PostgreSQL, real embedding model.

Skipped automatically when no database is reachable, so the unit suite still
runs anywhere. Inside the stack:

    docker compose exec ml-service python -m pytest tests/ -m integration -v

These cover the things a unit test cannot: transactional integrity, startup
hydration after a restart, and whether review decisions actually survive.
"""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.integration


def _database_available() -> bool:
    try:
        import psycopg

        from app.config import get_settings

        with psycopg.connect(get_settings().database_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 - availability probe
        return False


pytest.importorskip("psycopg")
if not _database_available():
    pytest.skip(
        "No PostgreSQL reachable at DATABASE_URL; integration tests skipped.",
        allow_module_level=True,
    )


@pytest.fixture(scope="module", autouse=True)
def app_state():
    from app.core import weights
    from app.db.schema import bootstrap_schema
    from app.db.session import init_pool
    from app.ml import embeddings
    from app.ml.hydration import hydrate_indexes

    init_pool()
    bootstrap_schema(embeddings.dimension())
    weights.seed_defaults()

    from app.seed.seeder import database_is_empty, seed_database

    if database_is_empty():
        seed_database()
    hydrate_indexes()

    from app.db.session import get_conn

    with get_conn() as conn:
        n = conn.execute("SELECT count(*) AS n FROM golden_records").fetchone()["n"]
    if int(n) == 0:
        from app.services.harmonization import run_harmonization

        run_harmonization()
    yield


class TestSchemaAndSeed:
    def test_core_tables_exist(self):
        from app.db.session import get_conn

        expected = {
            "raw_records", "golden_records", "golden_record_audit", "crosswalk",
            "steward_decisions", "review_queue_items", "harmonization_job_logs",
            "safety_blocks", "governance_overrides", "commodity_weights",
            "ground_truth", "evaluation_runs", "demo_inventory", "transfer_requests",
        }
        with get_conn() as conn:
            actual = {
                r["table_name"]
                for r in conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public'"
                ).fetchall()
            }
        assert expected <= actual, expected - actual

    def test_embedding_dimension_matches_the_live_model(self):
        from app.db.session import get_conn
        from app.ml import embeddings

        with get_conn() as conn:
            row = conn.execute(
                "SELECT a.atttypmod AS typmod FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "WHERE c.relname='raw_records' AND a.attname='embedding' "
                "AND a.attisdropped = false"
            ).fetchone()
        assert row is not None
        assert row["typmod"] == embeddings.dimension()

    def test_every_record_has_an_embedding(self):
        from app.db.session import get_conn

        with get_conn() as conn:
            n = conn.execute(
                "SELECT count(*) AS n FROM raw_records WHERE embedding IS NULL"
            ).fetchone()["n"]
        assert int(n) == 0

    def test_ground_truth_is_populated_but_separate(self):
        from app.db.session import get_conn

        with get_conn() as conn:
            gt = int(conn.execute("SELECT count(*) AS n FROM ground_truth").fetchone()["n"])
            raw = int(conn.execute("SELECT count(*) AS n FROM raw_records").fetchone()["n"])
        assert gt > 0
        assert gt <= raw


class TestStartupHydration:
    def test_indexes_rebuild_from_the_database_alone(self):
        """Simulates a backend restart: drop all in-memory state, rehydrate."""
        from app.db.session import get_conn
        from app.ml.hydration import hydrate_indexes
        from app.ml.indexes import IndexStore, store

        with get_conn() as conn:
            expected = int(conn.execute("SELECT count(*) AS n FROM raw_records").fetchone()["n"])

        # Wipe the singleton's contents the way a process restart would.
        store.__init__()  # type: ignore[misc]
        assert not store.ready

        result = hydrate_indexes()
        assert store.ready
        assert result["total_records"] == expected
        assert result["partitions"]
        assert all(n > 0 for n in result["partitions"].values())

    def test_retrieval_works_immediately_after_hydration(self):
        from app.db.session import get_conn
        from app.ml.indexes import store

        with get_conn() as conn:
            row = conn.execute(
                "SELECT id, commodity_type, normalized_description FROM raw_records "
                "WHERE commodity_type = 'gate_valve' LIMIT 1"
            ).fetchone()
        rec = store.get_record(int(row["id"]))
        assert rec is not None
        results = store.search(
            commodity=row["commodity_type"],
            query_text=row["normalized_description"],
            query_embedding=rec["embedding"],
            k=10,
            exclude_record_id=int(row["id"]),
        )
        assert results


class TestTransactionSafety:
    def test_a_failed_persist_leaves_no_partial_state(self):
        """A mid-transaction failure must roll the whole unit of work back."""
        from psycopg.types.json import Jsonb

        from app.db.session import get_conn, transaction

        with get_conn() as conn:
            before = int(conn.execute("SELECT count(*) AS n FROM golden_records").fetchone()["n"])

        nmi = f"NMI-TX{uuid.uuid4().hex[:4].upper()}"
        with pytest.raises(Exception):
            with transaction() as conn:
                conn.execute(
                    "INSERT INTO golden_records "
                    "(nmi, standardized_description, attributes) VALUES (%s, %s, %s)",
                    (nmi, "ROLLBACK PROBE", Jsonb({})),
                )
                # Violates the crosswalk FK: no such raw_record.
                conn.execute(
                    "INSERT INTO crosswalk (nmi, record_id, cpse_org, legacy_code) "
                    "VALUES (%s, %s, %s, %s)",
                    (nmi, -12345, "NOPE", "NOPE"),
                )

        with get_conn() as conn:
            after = int(conn.execute("SELECT count(*) AS n FROM golden_records").fetchone()["n"])
            orphan = conn.execute(
                "SELECT 1 FROM golden_records WHERE nmi = %s", (nmi,)
            ).fetchone()

        assert after == before
        assert orphan is None, "the golden record survived a failed transaction"

    def test_harmonization_leaves_no_dangling_crosswalk(self):
        from app.db.session import get_conn

        with get_conn() as conn:
            dangling = int(
                conn.execute(
                    "SELECT count(*) AS n FROM crosswalk c "
                    "LEFT JOIN golden_records g ON g.nmi = c.nmi WHERE g.nmi IS NULL"
                ).fetchone()["n"]
            )
            orphan_records = int(
                conn.execute(
                    "SELECT count(*) AS n FROM crosswalk c "
                    "LEFT JOIN raw_records r ON r.id = c.record_id WHERE r.id IS NULL"
                ).fetchone()["n"]
            )
        assert dangling == 0
        assert orphan_records == 0

    def test_every_source_code_survives_harmonization(self):
        """After a run, no source code is left without a crosswalk entry.

        Harmonization is run here rather than relied on from a previous test,
        so this asserts the invariant itself instead of whatever state the
        suite happened to leave behind.
        """
        from app.db.session import get_conn
        from app.services.harmonization import run_harmonization

        run_harmonization()

        with get_conn() as conn:
            missing = int(
                conn.execute(
                    "SELECT count(*) AS n FROM raw_records r "
                    "LEFT JOIN crosswalk c ON c.record_id = r.id WHERE c.id IS NULL"
                ).fetchone()["n"]
            )
        assert missing == 0, f"{missing} source codes have no crosswalk entry"


class TestReviewQueuePersistence:
    def test_decisions_survive_a_rerun_of_the_pipeline(self):
        from app.db.session import get_conn
        from app.services import review
        from app.services.harmonization import run_harmonization

        queue = review.list_review_items(status="OPEN", limit=1)
        if not queue["items"]:
            pytest.skip("No open review items in this dataset.")
        item = queue["items"][0]
        if not item["candidate_nmi"]:
            pytest.skip("Selected review item has no candidate NMI to approve.")

        review.decide(
            item_id=item["id"], decision="APPROVE",
            steward="test.steward", reason="integration test",
        )

        with get_conn() as conn:
            row = conn.execute(
                "SELECT status, reviewer FROM review_queue_items WHERE id = %s",
                (item["id"],),
            ).fetchone()
        assert row["status"] == "APPROVED"
        assert row["reviewer"] == "test.steward"

        # A full re-run rebuilds the derived tables but must not discard a
        # human decision.
        run_harmonization()
        with get_conn() as conn:
            row = conn.execute(
                "SELECT status FROM review_queue_items WHERE record_id = %s",
                (item["record_id"],),
            ).fetchone()
        assert row["status"] == "APPROVED"

    def test_a_steward_decision_is_written_to_the_audit_log(self):
        from app.db.session import get_conn

        with get_conn() as conn:
            n = int(
                conn.execute(
                    "SELECT count(*) AS n FROM steward_decisions WHERE steward = 'test.steward'"
                ).fetchone()["n"]
            )
        assert n >= 1


class TestNmiValidation:
    def test_approving_an_unknown_nmi_is_refused(self):
        from app.services import review
        from app.services.governance import NmiNotFound

        queue = review.list_review_items(status="OPEN", limit=1)
        if not queue["items"]:
            pytest.skip("No open review items.")
        with pytest.raises(NmiNotFound):
            review.decide(
                item_id=queue["items"][0]["id"], decision="APPROVE",
                override_nmi="NMI-999999",
            )

    def test_an_override_referencing_an_unknown_nmi_is_refused(self):
        from app.services.governance import NmiNotFound, record_override

        with pytest.raises(NmiNotFound):
            record_override(
                description="TEST MATERIAL", commodity_type="gate_valve",
                decision="USE_EXISTING", suggested_nmi="NMI-999999",
                suggested_score=0.9, new_legacy_code=None, cpse_org="BHEL",
                justification=None,
            )

    def test_no_invalid_crosswalk_reference_was_created(self):
        from app.db.session import get_conn

        with get_conn() as conn:
            bad = int(
                conn.execute(
                    "SELECT count(*) AS n FROM crosswalk WHERE nmi NOT IN "
                    "(SELECT nmi FROM golden_records)"
                ).fetchone()["n"]
            )
        assert bad == 0


class TestGovernanceGate:
    def test_a_known_material_is_recognised_as_existing(self):
        from app.db.session import get_conn
        from app.services.governance import check_new_material

        with get_conn() as conn:
            row = conn.execute(
                "SELECT g.standardized_description, g.commodity_type FROM golden_records g "
                "WHERE g.member_count > 1 AND g.commodity_type = 'gate_valve' LIMIT 1"
            ).fetchone()
        if row is None:
            pytest.skip("No multi-source gate valve identity available.")

        result = check_new_material(row["standardized_description"], row["commodity_type"])
        assert result["candidates"]
        assert result["recommendation"] in ("USE_EXISTING", "REVIEW")
        assert result["candidates"][0]["score"] > 0.5

    def test_the_gate_never_hard_rejects(self):
        from app.services.governance import check_new_material

        result = check_new_material(
            "GATE VALVE 6 INCH CARBON STEEL CLASS 150 FLANGED", "gate_valve"
        )
        assert "recommendation" in result
        assert result["recommendation"] != "REJECT"

    def test_an_unrelated_material_is_advised_as_new(self):
        from app.services.governance import check_new_material

        result = check_new_material(
            "PRESSURE GAUGE 100MM DIAL 0-16 BAR BOTTOM ENTRY", None
        )
        assert result["recommendation"] in ("CREATE_NEW", "REVIEW")

    def test_an_override_is_persisted(self):
        from app.db.session import get_conn
        from app.services.governance import record_override

        record_override(
            description="INTEGRATION TEST MATERIAL", commodity_type="gate_valve",
            decision="CREATE_NEW_ANYWAY", suggested_nmi=None, suggested_score=None,
            new_legacy_code="TEST-0001", cpse_org="BHEL",
            justification="integration test", actor="test.user",
        )
        with get_conn() as conn:
            n = int(
                conn.execute(
                    "SELECT count(*) AS n FROM governance_overrides WHERE actor='test.user'"
                ).fetchone()["n"]
            )
        assert n >= 1


class TestIngestionRoundTrip:
    """Ingestion inserts records; harmonization is what gives them an identity.

    The /ingest/upload endpoint runs both in one request, so a user never sees
    the intermediate state. These tests call ingest_rows directly, so they
    re-harmonize afterwards to model the same flow -- otherwise they leave
    records with no crosswalk entry and break the invariant that
    TestTransactionSafety asserts.
    """

    @pytest.fixture(scope="class", autouse=True)
    def reharmonize_after(self):
        yield
        from app.services.harmonization import run_harmonization

        run_harmonization()

    def test_uploading_a_new_record_indexes_it(self):
        from app.ml.indexes import store
        from app.services.ingestion import IngestRow, ingest_rows

        code = f"IT-{uuid.uuid4().hex[:8].upper()}"
        report = ingest_rows(
            [
                IngestRow(
                    cpse_org="TESTCO", legacy_code=code,
                    description="GATE VALVE 6 INCH CARBON STEEL CLASS 150 FLANGED",
                    commodity_type="gate_valve", quantity=5, uom="NOS",
                )
            ],
            source_batch="integration-test",
        )
        assert report.inserted == 1
        rid = report.inserted_ids[0]
        assert store.get_record(rid) is not None

    def test_reingesting_the_same_code_is_skipped_not_duplicated(self):
        from app.services.ingestion import IngestRow, ingest_rows

        code = f"IT-{uuid.uuid4().hex[:8].upper()}"
        row = IngestRow(
            cpse_org="TESTCO", legacy_code=code,
            description="GATE VALVE 6 INCH CARBON STEEL CLASS 150 FLANGED",
            commodity_type="gate_valve",
        )
        first = ingest_rows([row], source_batch="dup-test")
        second = ingest_rows([row], source_batch="dup-test")
        assert first.inserted == 1
        assert second.inserted == 0
        assert second.skipped_duplicates == 1

    def test_the_same_code_from_two_cpses_is_allowed(self):
        from app.services.ingestion import IngestRow, ingest_rows

        code = f"SHARED-{uuid.uuid4().hex[:6].upper()}"
        report = ingest_rows(
            [
                IngestRow("TESTCO", code, "GATE VALVE DN150 CS CL150", "gate_valve"),
                IngestRow("OTHERCO", code, "GATE VALVE DN150 CS CL150", "gate_valve"),
            ],
            source_batch="shared-code-test",
        )
        assert report.inserted == 2


class TestEvaluation:
    def test_evaluation_produces_defined_metrics(self):
        from app.services.evaluation import evaluate

        m = evaluate(persist=True)
        assert "error" not in m
        for key in ("precision", "recall", "f1"):
            assert 0.0 <= m["overall"][key] <= 1.0
        assert m["candidate_recall"]["recall_at_k"] > 0.5
        assert "definitions" in m

    def test_no_hard_negative_was_merged(self):
        from app.services.evaluation import evaluate

        m = evaluate(persist=False)
        assert m["unsafe_merges"] == 0, m["false_merge_examples"]
