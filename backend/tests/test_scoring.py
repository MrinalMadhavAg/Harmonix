"""Match scoring and weight configuration."""
from __future__ import annotations

from app.core.commodities import BEARING, GATE_VALVE
from app.core.scoring import match_score
from app.core.weights import DEFAULT_WEIGHTS, get_weights


def A(value):
    return {"value": value, "source": str(value), "method": "rule", "confidence": 0.99}


def rec(**attrs):
    return {"attributes": {k: A(v) for k, v in attrs.items()}}


IDENTICAL = dict(
    item_type="GATE VALVE", size="DN150", material="CARBON STEEL",
    pressure_class="CL150", end_connection="FLANGED", standard="API 600",
)


class TestScoreRange:
    def test_score_is_clipped_to_unit_interval(self):
        for sem, lex in [(-5.0, -5.0), (5.0, 5.0), (0.5, 0.5)]:
            ms = match_score(rec(**IDENTICAL), rec(**IDENTICAL), sem, lex, GATE_VALVE)
            assert 0.0 <= ms.score <= 1.0
            assert 0.0 <= ms.semantic <= 1.0
            assert 0.0 <= ms.lexical <= 1.0

    def test_identical_records_score_high(self):
        ms = match_score(rec(**IDENTICAL), rec(**IDENTICAL), 0.98, 0.95, GATE_VALVE)
        assert ms.score > 0.9
        assert ms.attribute_agreement > 0.9


class TestMismatchDominance:
    def test_safety_critical_mismatch_outweighs_many_agreements(self):
        """The core requirement: one disqualifying attribute must not be
        drowned out by everything else matching."""
        same = match_score(rec(**IDENTICAL), rec(**IDENTICAL), 0.98, 0.95, GATE_VALVE)
        differing = match_score(
            rec(**IDENTICAL),
            rec(**{**IDENTICAL, "pressure_class": "CL300"}),
            0.98, 0.95, GATE_VALVE,
        )
        assert differing.score < same.score
        assert same.score - differing.score > 0.1

    def test_critical_mismatch_costs_more_than_a_non_critical_one(self):
        critical = match_score(
            rec(**IDENTICAL), rec(**{**IDENTICAL, "material": "STAINLESS STEEL 316"}),
            0.95, 0.9, GATE_VALVE,
        )
        incidental = match_score(
            rec(**IDENTICAL), rec(**{**IDENTICAL, "standard": "BS 1868"}),
            0.95, 0.9, GATE_VALVE,
        )
        assert critical.score < incidental.score

    def test_scorer_contains_no_safety_logic(self):
        """A blocked pair still receives its honest similarity score; refusing
        the merge is the safety layer's job, not the scorer's."""
        ms = match_score(
            rec(**IDENTICAL), rec(**{**IDENTICAL, "pressure_class": "CL300"}),
            0.98, 0.95, GATE_VALVE,
        )
        assert ms.score > 0.5


class TestUnknownHandling:
    def test_unknown_attributes_do_not_count_as_mismatches(self):
        partial = {k: v for k, v in IDENTICAL.items() if k in ("item_type", "size", "material")}
        with_unknowns = match_score(rec(**IDENTICAL), rec(**partial), 0.9, 0.85, GATE_VALVE)
        with_conflict = match_score(
            rec(**IDENTICAL), rec(**{**partial, "material": "STAINLESS STEEL 316"}),
            0.9, 0.85, GATE_VALVE,
        )
        assert with_unknowns.score > with_conflict.score

    def test_thin_evidence_pulls_agreement_toward_neutral(self):
        full = match_score(rec(**IDENTICAL), rec(**IDENTICAL), 0.9, 0.9, GATE_VALVE)
        thin = match_score(
            rec(item_type="GATE VALVE"), rec(item_type="GATE VALVE"), 0.9, 0.9, GATE_VALVE
        )
        assert thin.coverage < full.coverage
        assert thin.attribute_agreement < full.attribute_agreement

    def test_no_shared_attributes_yields_neutral_agreement(self):
        ms = match_score({"attributes": {}}, {"attributes": {}}, 0.5, 0.5, GATE_VALVE)
        assert ms.attribute_agreement == 0.5
        assert ms.coverage == 0.0


class TestExplanation:
    def test_breakdown_is_complete_and_serialisable(self):
        ms = match_score(rec(**IDENTICAL), rec(**IDENTICAL), 0.98, 0.95, GATE_VALVE)
        d = ms.to_dict()
        assert set(d) >= {
            "score", "semantic", "lexical", "attribute_agreement",
            "coverage", "weights", "comparisons", "counts",
        }
        assert abs(sum(d["weights"].values()) - 1.0) < 1e-6
        for c in d["comparisons"]:
            assert set(c) >= {"key", "label", "state", "safety_critical", "weight"}
            assert c["state"] in ("MATCH", "MISMATCH", "UNKNOWN")

    def test_safety_critical_fields_are_listed_first(self):
        ms = match_score(rec(**IDENTICAL), rec(**IDENTICAL), 0.9, 0.9, GATE_VALVE)
        flags = [c["safety_critical"] for c in ms.comparisons]
        assert flags == sorted(flags, reverse=True)

    def test_reported_weights_reproduce_the_score(self):
        ms = match_score(rec(**IDENTICAL), rec(**IDENTICAL), 0.9, 0.8, GATE_VALVE)
        w = ms.weights
        expected = (
            w["semantic"] * ms.semantic
            + w["lexical"] * ms.lexical
            + w["attributes"] * ms.attribute_agreement
        )
        assert abs(expected - ms.score) < 1e-6


class TestCommoditySpecificWeights:
    def test_each_commodity_has_its_own_weights(self):
        assert get_weights(GATE_VALVE).attribute_weights != get_weights(BEARING).attribute_weights

    def test_material_dominates_for_valves_but_not_bearings(self):
        assert get_weights(GATE_VALVE).weight_for("material") >= 1.0
        assert get_weights(BEARING).weight_for("designation") >= 1.0

    def test_components_are_normalised_to_one(self):
        for w in DEFAULT_WEIGHTS.values():
            assert abs(sum(w.normalized_components()) - 1.0) < 1e-9

    def test_unknown_commodity_falls_back_without_raising(self):
        w = get_weights("not-a-commodity")
        assert sum(w.normalized_components()) > 0
