"""End-to-end pipeline tests over the synthetic catalogue.

Runs the real retrieval (FAISS partitions + BM25), the real scorer, the real
safety gate, real cluster validation and real survivorship. No database and
no model download -- see tests/harness.py for the substituted embedder and
what that substitution does and does not cover.

The quality assertions are deliberately loose floors. They exist to catch a
regression that breaks matching, not to pin exact numbers that legitimately
move when a rule is improved.
"""
from __future__ import annotations

import pytest

from app.services import harmonization as harm
from app.services.harmonization import compute_harmonization
from tests.harness import build_corpus, candidate_recall, pair_metrics


@pytest.fixture(scope="module")
def corpus():
    records, truth, store = build_corpus()
    # compute_harmonization reads the module-level index singleton.
    original = harm.store
    harm.store = store
    yield records, truth, store
    harm.store = original


@pytest.fixture(scope="module")
def enforced(corpus):
    records, truth, store = corpus
    plan = compute_harmonization(records, enforce_safety=True, job_id="test-safe")
    return records, truth, store, plan


class TestCorpus:
    def test_corpus_size_and_partitioning(self, corpus):
        records, truth, store = corpus
        assert 120 <= len(records) <= 260
        stats = store.stats()
        assert stats["ready"]
        assert stats["total_records"] == len(records)
        # Each commodity gets its own FAISS/BM25 partition.
        assert set(stats["partitions"]) == {
            "gate_valve", "pipe", "bearing", "electrical_cable", "fastener"
        }
        assert all(n > 0 for n in stats["partitions"].values())

    def test_legacy_codes_are_unique_per_cpse(self, corpus):
        records, _, _ = corpus
        pairs = [(r["cpse_org"], r["legacy_code"]) for r in records]
        assert len(pairs) == len(set(pairs))

    def test_cpses_use_different_code_formats(self, corpus):
        records, _, _ = corpus
        by_org: dict[str, str] = {}
        for r in records:
            by_org.setdefault(r["cpse_org"], r["legacy_code"])
        assert len(by_org) >= 4
        # No two CPSEs should share a code shape.
        shapes = {org: "".join("9" if c.isdigit() else ("A" if c.isalpha() else c))
                  for org, code in by_org.items() for c in [code]}
        shapes = {
            org: "".join("9" if ch.isdigit() else ("A" if ch.isalpha() else ch) for ch in code)
            for org, code in by_org.items()
        }
        assert len(set(shapes.values())) == len(shapes)


class TestRetrieval:
    def test_candidate_recall_is_high(self, corpus):
        records, truth, store = corpus
        r = candidate_recall(records, truth, store, k=30)
        # Retrieval sets the ceiling on achievable recall; it must not be
        # the bottleneck.
        assert r["recall_at_k"] >= 0.95, r

    def test_retrieval_never_crosses_commodities(self, corpus):
        records, _, store = corpus
        by_id = {int(r["id"]): r for r in records}
        for r in records[:40]:
            for c in store.search(
                commodity=r["commodity_type"],
                query_text=r["normalized_description"],
                query_embedding=r["embedding"],
                k=30,
                exclude_record_id=int(r["id"]),
            ):
                assert by_id[c.record_id]["commodity_type"] == r["commodity_type"]

    def test_search_on_empty_partition_returns_nothing(self, corpus):
        _, _, store = corpus
        assert store.search("no-such-commodity", "anything", None, k=10) == []


class TestSafetyEnforced:
    def test_no_unsafe_merges(self, enforced):
        records, truth, _, plan = enforced
        m = pair_metrics(records, truth, plan.nmi_by_record)
        assert m["unsafe_merges"] == 0, m["unsafe_examples"]

    def test_precision_is_perfect_on_the_synthetic_set(self, enforced):
        records, truth, _, plan = enforced
        m = pair_metrics(records, truth, plan.nmi_by_record)
        assert m["overall"]["precision"] == 1.0, m["overall"]

    def test_recall_floor(self, enforced):
        records, truth, _, plan = enforced
        m = pair_metrics(records, truth, plan.nmi_by_record)
        assert m["overall"]["recall"] >= 0.60, m["overall"]

    def test_safety_blocks_are_recorded_with_their_field(self, enforced):
        *_, plan = enforced
        assert plan.blocked_pairs
        for p in plan.blocked_pairs:
            assert p.blocked_field
            assert p.safety_detail["blocked_values"]
            assert p.safety_reason

    def test_every_record_receives_an_nmi(self, enforced):
        records, _, _, plan = enforced
        assert set(plan.nmi_by_record) == {int(r["id"]) for r in records}

    def test_crosswalk_preserves_every_legacy_code(self, enforced):
        """No source code may disappear because of harmonization."""
        records, _, _, plan = enforced
        source = {(r["cpse_org"], r["legacy_code"]) for r in records}
        walked = {(c["cpse_org"], c["legacy_code"]) for c in plan.crosswalk_rows}
        assert walked == source

    def test_every_record_gets_exactly_one_review_row(self, enforced):
        records, _, _, plan = enforced
        ids = [r["record_id"] for r in plan.review_rows]
        assert sorted(ids) == sorted(int(r["id"]) for r in records)

    def test_golden_record_member_counts_match_the_crosswalk(self, enforced):
        *_, plan = enforced
        from collections import Counter

        counted = Counter(c["nmi"] for c in plan.crosswalk_rows)
        for g in plan.golden_records:
            assert g["member_count"] == counted[g["nmi"]]

    def test_golden_records_carry_survivorship_evidence(self, enforced):
        *_, plan = enforced
        multi = [g for g in plan.golden_records if g["member_count"] > 1]
        assert multi, "expected at least one multi-source golden record"
        for g in multi[:10]:
            for a in g["attributes"].values():
                assert "agreement" in a and "confidence" in a
                assert a["method"] == "survivorship"

    def test_multiple_cpses_are_actually_harmonized(self, enforced):
        """The whole point: different CPSEs' codes reaching one identity."""
        *_, plan = enforced
        by_nmi: dict[str, set[str]] = {}
        for c in plan.crosswalk_rows:
            by_nmi.setdefault(c["nmi"], set()).add(c["cpse_org"])
        cross = [n for n, orgs in by_nmi.items() if len(orgs) > 1]
        assert len(cross) >= 20, f"only {len(cross)} identities span multiple CPSEs"

    def test_nmi_ids_are_well_formed_and_unique(self, enforced):
        *_, plan = enforced
        nmis = [g["nmi"] for g in plan.golden_records]
        assert len(nmis) == len(set(nmis))
        for n in nmis:
            assert n.startswith("NMI-") and n[4:].isdigit() and len(n) == 10


class TestSafetyDisabledDemonstration:
    """The live toggle must produce a genuinely different, worse result."""

    def test_disabling_safety_causes_real_unsafe_merges(self, corpus):
        records, truth, _ = corpus
        plan = compute_harmonization(records, enforce_safety=False, job_id="test-unsafe")
        m = pair_metrics(records, truth, plan.nmi_by_record)
        assert m["unsafe_merges"] > 0, "the safety demonstration would show nothing"
        assert m["overall"]["precision"] < 0.9

    def test_enforcement_changes_the_outcome(self, corpus, enforced):
        records, truth, _ = corpus
        *_, safe_plan = enforced
        unsafe_plan = compute_harmonization(records, enforce_safety=False, job_id="t")

        safe = pair_metrics(records, truth, safe_plan.nmi_by_record)
        unsafe = pair_metrics(records, truth, unsafe_plan.nmi_by_record)

        assert safe["unsafe_merges"] == 0
        assert unsafe["unsafe_merges"] > safe["unsafe_merges"]
        assert safe["overall"]["precision"] > unsafe["overall"]["precision"]
        # Without the gate, distinct materials collapse into fewer identities.
        assert unsafe_plan.stats["golden_records"] < safe_plan.stats["golden_records"]
        assert safe_plan.stats["blocked_pairs"] > 0
        assert unsafe_plan.stats["blocked_pairs"] == 0


class TestDeterminism:
    def test_two_runs_produce_identical_assignments(self, corpus):
        records, _, _ = corpus
        a = compute_harmonization(records, enforce_safety=True, job_id="det-a")
        b = compute_harmonization(records, enforce_safety=True, job_id="det-b")
        assert a.nmi_by_record == b.nmi_by_record
        assert [g["nmi"] for g in a.golden_records] == [g["nmi"] for g in b.golden_records]
        assert [g["standardized_description"] for g in a.golden_records] == [
            g["standardized_description"] for g in b.golden_records
        ]


class TestEmptyAndDegenerateInputs:
    def test_empty_record_set(self):
        plan = compute_harmonization([], job_id="empty")
        assert plan.stats["records"] == 0
        assert plan.golden_records == []
        assert plan.crosswalk_rows == []

    def test_single_record_becomes_its_own_identity(self, corpus):
        records, _, _ = corpus
        plan = compute_harmonization([records[0]], enforce_safety=True, job_id="one")
        assert len(plan.golden_records) == 1
        assert plan.golden_records[0]["member_count"] == 1
        assert plan.crosswalk_rows[0]["relationship"] == "SINGLETON"

    def test_records_with_unknown_commodity_do_not_crash(self, corpus):
        """An unclassifiable record is still stored and still gets an identity."""
        from app.ml.indexes import IndexStore

        records, _, _ = corpus
        orphan = {**records[0], "id": 999999, "commodity_type": None, "attributes": {}}

        # Hydrate a store containing it, so the pipeline reads its stored
        # embedding rather than reaching for the model.
        store = IndexStore()
        store.rebuild([orphan])
        original = harm.store
        harm.store = store
        try:
            plan = compute_harmonization([orphan], enforce_safety=True, job_id="orphan")
        finally:
            harm.store = original

        assert len(plan.golden_records) == 1
        assert 999999 in plan.nmi_by_record
        # No safety envelope is defined for an unknown commodity, so it can
        # never be auto-merged into anything.
        assert plan.golden_records[0]["member_count"] == 1
