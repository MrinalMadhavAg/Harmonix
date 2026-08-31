"""Three-state comparison semantics.

UNKNOWN is neither MATCH nor MISMATCH. Every consumer shares this module, so
these tests pin the contract the whole system depends on.
"""
from __future__ import annotations

import pytest

from app.core.comparison import (
    AttrState,
    compare_attributes,
    compare_values,
    distinct_values,
)
from app.core.commodities import BEARING, GATE_VALVE


def A(value, confidence=0.99):
    return {"value": value, "source": str(value), "method": "rule", "confidence": confidence}


class TestThreeStates:
    def test_equal_values_match(self):
        assert compare_values("material", "SS316", "SS316").state is AttrState.MATCH

    def test_different_values_mismatch(self):
        assert compare_values("material", "SS316", "SS304").state is AttrState.MISMATCH

    @pytest.mark.parametrize("a,b", [(None, "SS316"), ("SS316", None), (None, None)])
    def test_missing_value_is_unknown_not_mismatch(self, a, b):
        c = compare_values("material", a, b)
        assert c.state is AttrState.UNKNOWN
        assert c.state is not AttrState.MISMATCH
        assert c.state is not AttrState.MATCH

    def test_unknown_explains_which_side_is_missing(self):
        assert "right side" in compare_values("material", "SS316", None).detail
        assert "left side" in compare_values("material", None, "SS316").detail

    def test_case_and_whitespace_insensitive(self):
        assert compare_values("material", " ss316 ", "SS316").state is AttrState.MATCH

    def test_316_vs_316l_is_a_mismatch(self):
        c = compare_values("material", "STAINLESS STEEL 316", "STAINLESS STEEL 316L")
        assert c.state is AttrState.MISMATCH


class TestNumericComparison:
    def test_equal_numerics_match(self):
        assert compare_values("bore_mm", 25.0, 25).state is AttrState.MATCH

    def test_different_bore_is_a_mismatch(self):
        c = compare_values("bore_mm", 25.0, 30.0)
        assert c.state is AttrState.MISMATCH
        assert "25 vs 30" in c.detail

    def test_tolerance_is_tight(self):
        assert compare_values("bore_mm", 25.0, 25.5).state is AttrState.MISMATCH

    def test_numeric_strings_are_compared_as_numbers(self):
        assert compare_values("cross_section_sqmm", "95", 95.0).state is AttrState.MATCH


class TestStandardEquivalence:
    def test_high_confidence_equivalence_is_a_match(self):
        c = compare_values("pressure_class", "PN20", "CL150", GATE_VALVE)
        assert c.state is AttrState.MATCH
        assert c.equivalence_confidence >= 0.85

    def test_low_confidence_equivalence_stays_a_mismatch(self):
        c = compare_values("pressure_class", "PN16", "CL150", GATE_VALVE)
        assert c.state is AttrState.MISMATCH
        assert 0 < c.equivalence_confidence < 0.85
        assert "related notations" in c.detail

    def test_unrelated_classes_are_a_plain_mismatch(self):
        c = compare_values("pressure_class", "CL150", "CL300", GATE_VALVE)
        assert c.state is AttrState.MISMATCH
        assert c.equivalence_confidence == 0.0

    def test_equivalence_does_not_apply_outside_its_commodity(self):
        assert compare_values("pressure_class", "PN20", "CL150", BEARING).state is AttrState.MISMATCH


class TestHierarchicalTerms:
    def test_broader_item_type_matches_narrower(self):
        c = compare_values("item_type", "BALL BEARING", "DEEP GROOVE BALL BEARING")
        assert c.state is AttrState.MATCH
        assert "broader term" in c.detail

    def test_unrelated_item_types_still_mismatch(self):
        assert compare_values("item_type", "HEXAGON NUT", "WASHER").state is AttrState.MISMATCH

    def test_hierarchy_does_not_apply_to_grades(self):
        # "STAINLESS STEEL" is a word-subset of "STAINLESS STEEL 316" but a
        # grade is not a broader/narrower term -- it changes the material.
        assert compare_values(
            "material", "STAINLESS STEEL", "STAINLESS STEEL 316"
        ).state is AttrState.MISMATCH


class TestComparisonSet:
    def test_counts_and_key_listing(self):
        a = {"material": A("SS316"), "size": A("DN150"), "pressure_class": A("CL150")}
        b = {"material": A("SS316"), "size": A("DN100")}
        cs = compare_attributes(a, b, GATE_VALVE, keys=["material", "size", "pressure_class"])
        assert cs.counts() == {"MATCH": 1, "MISMATCH": 1, "UNKNOWN": 1}
        assert cs.mismatched_keys() == ["size"]
        assert cs.unknown_keys() == ["pressure_class"]

    def test_empty_attribute_bags_are_all_unknown(self):
        cs = compare_attributes({}, {}, GATE_VALVE, keys=["material", "size"])
        assert cs.counts()["UNKNOWN"] == 2


class TestDistinctValues:
    def test_nulls_are_ignored_not_counted_as_a_value(self):
        assert distinct_values(["CL150", None, "CL150"]) == ["CL150"]

    def test_contradiction_is_detected(self):
        assert len(distinct_values(["CL150", "CL300", None])) == 2

    def test_case_normalised(self):
        assert distinct_values(["cl150", "CL150"]) == ["CL150"]
