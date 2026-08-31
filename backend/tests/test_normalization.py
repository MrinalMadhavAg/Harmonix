"""Normalization regression tests.

The headline case is the greedy-MM bug: a generic `(\\d+)\\s*MM` rule that
rewrites dimensions into commodity-specific terminology corrupts meaning.
`150MM` is a nominal bore on a valve, a bore diameter on a bearing, and part
of a cross-section on a cable. No rule may reinterpret it based on the
presence of "MM" alone.
"""
from __future__ import annotations

import pytest

from app.core.commodities import (
    BEARING,
    ELECTRICAL_CABLE,
    FASTENER,
    GATE_VALVE,
    PIPE,
    detect_commodity,
)
from app.core.normalization import expand_abbreviations, normalize, normalize_text


class TestGreedyMillimetreRegression:
    def test_150mm_on_valve_becomes_nominal_bore(self):
        assert normalize_text("150MM GATE VALVE", GATE_VALVE) == "DN150 GATE VALVE"

    def test_150mm_on_pipe_becomes_nominal_bore(self):
        assert "DN150" in normalize_text("150MM PIPE SCH40", PIPE)

    @pytest.mark.parametrize("commodity", [BEARING, ELECTRICAL_CABLE, FASTENER])
    def test_150mm_is_untouched_on_non_bore_commodities(self, commodity):
        out = normalize_text("150MM COMPONENT", commodity)
        assert "150MM" in out
        assert "DN" not in out

    def test_bearing_bore_never_becomes_inch_or_bore_terminology(self):
        """The specific corruption to prevent: 150MM -> '0.5 INCHMM BORE'."""
        out = normalize_text("BEARING 6205 BORE 150MM", BEARING)
        assert "INCH" not in out
        assert "DN" not in out
        assert "150MM" in out

    def test_mm_value_that_is_not_a_nominal_size_is_left_alone(self):
        # 137 is not a DN size, so converting it would be an invention.
        out = normalize_text("GATE VALVE 137 MM STEM", GATE_VALVE)
        assert "137 MM" in out
        assert "DN137" not in out

    def test_unknown_commodity_gets_no_dimensional_rewriting(self):
        out = normalize_text("150 MM SOMETHING", None)
        assert "150 MM" in out
        assert "DN150" not in out


class TestDimensionalEquivalence:
    @pytest.mark.parametrize(
        "text",
        [
            '6" GATE VALVE', "6 IN GATE VALVE", "6 INCH GATE VALVE",
            "150 MM GATE VALVE", "150MM GATE VALVE", "DN150 GATE VALVE",
            "150 NB GATE VALVE", "DN 150 GATE VALVE",
        ],
    )
    def test_all_notations_converge_on_dn150(self, text):
        assert "DN150" in normalize_text(text, GATE_VALVE)

    @pytest.mark.parametrize(
        "text,expected",
        [
            ('1/2" PIPE', "DN15"), ('3/4" PIPE', "DN20"), ('1" PIPE', "DN25"),
            ('1-1/2" PIPE', "DN40"), ('2" PIPE', "DN50"), ('4" PIPE', "DN100"),
            ('8" PIPE', "DN200"), ('12" PIPE', "DN300"),
        ],
    )
    def test_fractional_and_whole_inches(self, text, expected):
        assert expected in normalize_text(text, PIPE)

    def test_nb_is_millimetres_not_inches(self):
        # "150 NB" must map to DN150, never through the inch table.
        assert "DN150" in normalize_text("150 NB PIPE", PIPE)
        assert "DN15" not in normalize_text("150 NB PIPE", PIPE).replace("DN150", "")


class TestStandardEquivalenceIsNotSubstituted:
    def test_pn20_is_not_rewritten_to_cl150(self):
        out = normalize_text("GATE VALVE DN150 PN20", GATE_VALVE)
        assert "PN20" in out
        assert "CL150" not in out

    def test_cl150_is_not_rewritten_to_pn20(self):
        out = normalize_text("GATE VALVE DN150 CL150", GATE_VALVE)
        assert "CL150" in out
        assert "PN20" not in out


class TestAbbreviationExpansion:
    @pytest.mark.parametrize(
        "abbrev,expanded",
        [("VLV", "VALVE"), ("GT", "GATE"), ("CS", "CARBON STEEL"),
         ("SS", "STAINLESS STEEL"), ("FLGD", "FLANGED"), ("SMLS", "SEAMLESS")],
    )
    def test_whole_word_expansion(self, abbrev, expanded):
        out, _ = expand_abbreviations(f"X {abbrev} Y", GATE_VALVE)
        assert expanded in out

    def test_expansion_does_not_corrupt_unrelated_tokens(self):
        """SS316 is one token; the SS rule must not split it apart."""
        out = normalize_text("GATE VALVE SS316 DN150", GATE_VALVE)
        assert "SS316" in out
        assert "STAINLESS STEEL316" not in out

    def test_cs_inside_a_longer_token_is_untouched(self):
        out = normalize_text("PIPE CSX100 FITTING", PIPE)
        assert "CSX100" in out

    def test_commodity_scoped_abbreviation_does_not_leak(self):
        # "C" means CORE on a cable and nothing on a valve.
        assert "CORE" in normalize_text("CABLE 3 C X 95 SQ MM", ELECTRICAL_CABLE)
        assert "CORE" not in normalize_text("GATE VALVE C DN150", GATE_VALVE)

    def test_v_slash_v_resolves_to_valve(self):
        assert "VALVE" in normalize_text("GATE V/V 6 INCH", GATE_VALVE)


class TestCommodityDetection:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("GATE VALVE 6 INCH CS", GATE_VALVE),
            ("GATE, VALVE, 6 IN, CS", GATE_VALVE),      # comma-delimited ERP text
            ("GATE V/V 6 INCH CL150", GATE_VALVE),      # slash notation
            ("gate valev 6 inch cl150", GATE_VALVE),    # typo, fuzzy fallback
            ("SEAMLESS PIPE DN150 SCH40", PIPE),
            ("DGBB 6205 BORE 25MM", BEARING),
            ("XLPE CABLE 3 CORE 95 SQ MM 1.1KV", ELECTRICAL_CABLE),
            ("HEXAGON HEAD BOLT M16 X 100 8.8", FASTENER),
        ],
    )
    def test_detection(self, text, expected):
        assert detect_commodity(text) == expected

    def test_unrecognised_text_returns_unknown_not_a_default(self):
        assert detect_commodity("MISCELLANEOUS CONSUMABLE ITEM") == "unknown"

    def test_empty_input(self):
        assert detect_commodity("") == "unknown"


class TestNormalizationHousekeeping:
    def test_none_input_is_safe(self):
        assert normalize(None).text == ""

    def test_trace_records_applied_rules(self):
        result = normalize('6" GATE VALVE CS', GATE_VALVE)
        assert any("dim:inch" in t for t in result.trace)
        assert any("abbrev:CS" in t for t in result.trace)

    def test_whitespace_and_punctuation_collapse(self):
        assert normalize_text("GATE   VALVE,,,  DN150", GATE_VALVE) == "GATE VALVE DN150"
