"""Attribute extraction, with particular attention to material grades.

SS316 and SS316L are different alloys. Reading a "316L" as "316" -- or
inferring "316L" because the digits 316 appear -- would let the safety layer
approve a merge it should refuse.
"""
from __future__ import annotations

import pytest

from app.core.attributes import extract_attributes, extract_material, value_of
from app.core.commodities import BEARING, ELECTRICAL_CABLE, FASTENER, GATE_VALVE, PIPE
from app.core.normalization import normalize_text


def norm_extract(text: str, commodity: str) -> dict:
    return extract_attributes(normalize_text(text, commodity), commodity)


class TestMaterialGradeSafety:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("STAINLESS STEEL 316", "STAINLESS STEEL 316"),
            ("STAINLESS STEEL 316L", "STAINLESS STEEL 316L"),
            ("SS316", "STAINLESS STEEL 316"),
            ("SS316L", "STAINLESS STEEL 316L"),
            ("SS 316", "STAINLESS STEEL 316"),
            ("SS 316L", "STAINLESS STEEL 316L"),
            ("AISI 316", "STAINLESS STEEL 316"),
            ("AISI 316L", "STAINLESS STEEL 316L"),
            ("SS304", "STAINLESS STEEL 304"),
            ("SS304L", "STAINLESS STEEL 304L"),
            ("AISI 304", "STAINLESS STEEL 304"),
        ],
    )
    def test_grades_are_preserved_exactly(self, text, expected):
        attrs = norm_extract(f"GATE VALVE DN150 {text} CL150", GATE_VALVE)
        assert value_of(attrs, "material") == expected

    def test_316l_is_never_collapsed_to_316(self):
        attrs = norm_extract("GATE VALVE DN150 SS316L CL150", GATE_VALVE)
        assert value_of(attrs, "material") == "STAINLESS STEEL 316L"
        assert value_of(attrs, "material") != "STAINLESS STEEL 316"

    def test_316_is_never_inflated_to_316l(self):
        attrs = norm_extract("GATE VALVE DN150 SS316 CL150", GATE_VALVE)
        assert value_of(attrs, "material") == "STAINLESS STEEL 316"

    def test_316_followed_by_unrelated_l_word_is_still_316(self):
        # "316 LONG" must not be read as 316L.
        assert extract_material("SS316 LONG PATTERN")["value"] == "STAINLESS STEEL 316"

    @pytest.mark.parametrize(
        "text,expected",
        [("A216 WCB", "CARBON STEEL"), ("WCB", "CARBON STEEL"),
         ("ASTM A106", "CARBON STEEL"), ("CF8M", "STAINLESS STEEL 316"),
         ("CF3M", "STAINLESS STEEL 316L")],
    )
    def test_foundry_and_astm_designations(self, text, expected):
        assert extract_material(text)["value"] == expected

    def test_ungraded_stainless_has_lower_confidence(self):
        graded = extract_material("SS316")
        ungraded = extract_material("STAINLESS STEEL BODY")
        assert ungraded["value"] == "STAINLESS STEEL"
        assert ungraded["confidence"] < graded["confidence"]


class TestProvenance:
    def test_every_attribute_carries_full_provenance(self):
        attrs = norm_extract("GATE VALVE 6 INCH SS316 CLASS 150 FLANGED API 600", GATE_VALVE)
        assert attrs
        for key, a in attrs.items():
            assert set(a) >= {"value", "source", "method", "confidence"}, key
            assert a["method"] in ("rule", "derived", "llm"), key
            assert 0.0 <= a["confidence"] <= 1.0, key
            assert isinstance(a["source"], str) and a["source"], key

    def test_derived_values_are_marked_as_derived(self):
        attrs = norm_extract("BALL BEARING 6205 OPEN", BEARING)
        assert attrs["bore_mm"]["method"] == "derived"
        assert "6205" in attrs["bore_mm"]["source"]


class TestGateValve:
    def test_full_extraction(self):
        attrs = norm_extract("GATE VALVE 6 INCH CARBON STEEL CLASS 150 FLANGED API 600", GATE_VALVE)
        assert value_of(attrs, "size") == "DN150"
        assert value_of(attrs, "material") == "CARBON STEEL"
        assert value_of(attrs, "pressure_class") == "CL150"
        assert value_of(attrs, "end_connection") == "FLANGED"
        assert value_of(attrs, "standard") == "API 600"

    @pytest.mark.parametrize(
        "text", ["CLASS 150", "CL150", "CL 150", "150#", "#150", "ANSI 150"]
    )
    def test_pressure_class_notations(self, text):
        attrs = norm_extract(f"GATE VALVE DN150 CS {text}", GATE_VALVE)
        assert value_of(attrs, "pressure_class") == "CL150"

    def test_nominal_bore_is_not_read_as_a_pressure_class(self):
        # DN150 must not become CL150.
        attrs = norm_extract("GATE VALVE DN150 CARBON STEEL FLANGED", GATE_VALVE)
        assert value_of(attrs, "pressure_class") is None

    def test_pn_notation_is_kept_as_pn(self):
        attrs = norm_extract("GATE VALVE DN150 CS PN20", GATE_VALVE)
        assert value_of(attrs, "pressure_class") == "PN20"


class TestPipe:
    def test_schedule_and_size(self):
        attrs = norm_extract("SEAMLESS PIPE 6 INCH SCH 40 CARBON STEEL ASTM A106", PIPE)
        assert value_of(attrs, "size") == "DN150"
        assert value_of(attrs, "schedule") == "SCH40"
        assert value_of(attrs, "manufacture") == "SEAMLESS"

    def test_schedule_is_not_confused_with_nominal_size(self):
        attrs = norm_extract("PIPE DN150 SCH 80 CS", PIPE)
        assert value_of(attrs, "size") == "DN150"
        assert value_of(attrs, "schedule") == "SCH80"


class TestBearing:
    @pytest.mark.parametrize(
        "designation,bore",
        [("6205", 25.0), ("6206", 30.0), ("6204", 20.0), ("6305", 25.0),
         ("22220", 100.0), ("NU210", 50.0), ("6200", 10.0), ("6202", 15.0)],
    )
    def test_iso_bore_derivation(self, designation, bore):
        attrs = norm_extract(f"BALL BEARING {designation} OPEN", BEARING)
        assert value_of(attrs, "bore_mm") == bore

    def test_explicit_bore_overrides_derivation(self):
        attrs = norm_extract("BEARING 6205 BORE 25 MM OD 52 MM", BEARING)
        assert value_of(attrs, "bore_mm") == 25.0
        assert value_of(attrs, "outer_diameter_mm") == 52.0

    def test_keyword_first_measurements(self):
        attrs = norm_extract("BRG 6205 OPEN ID 25MM OD 52MM W 15MM", BEARING)
        assert value_of(attrs, "bore_mm") == 25.0
        assert value_of(attrs, "outer_diameter_mm") == 52.0
        assert value_of(attrs, "width_mm") == 15.0

    def test_value_first_measurements(self):
        attrs = norm_extract("DGBB 6205 25MM BORE 52MM OD OPEN", BEARING)
        assert value_of(attrs, "bore_mm") == 25.0
        assert value_of(attrs, "outer_diameter_mm") == 52.0

    def test_truncated_measurement_yields_unknown_not_a_wrong_value(self):
        """'OD 52' has lost its unit; reporting the bore as the OD is worse than nothing."""
        attrs = norm_extract("DEEP GROOVE BALL BEARING 6205 BORE 25 MM OD 52", BEARING)
        assert value_of(attrs, "bore_mm") == 25.0
        assert value_of(attrs, "outer_diameter_mm") is None

    def test_seal_type(self):
        assert value_of(norm_extract("BALL BEARING 6205-2RS SEALED", BEARING), "seal_type") == "2RS"
        assert value_of(norm_extract("BALL BEARING 6205 OPEN", BEARING), "seal_type") == "OPEN"


class TestCable:
    def test_full_extraction(self):
        attrs = norm_extract(
            "XLPE CABLE 3 CORE 95 SQ MM ALUMINIUM ARMOURED 1.1KV", ELECTRICAL_CABLE
        )
        assert value_of(attrs, "cores") == 3
        assert value_of(attrs, "cross_section_sqmm") == 95.0
        assert value_of(attrs, "voltage_grade") == "1.1KV"
        assert value_of(attrs, "conductor_material") == "ALUMINIUM"
        assert value_of(attrs, "insulation") == "XLPE"
        assert value_of(attrs, "armour") == "ARMOURED"

    def test_jammed_cores_and_cross_section(self):
        """'2CX2.5 MM2' must not read the cross-section as 5."""
        attrs = norm_extract("2CX2.5 MM2 COPPER PVC 1.1KV CABLE", ELECTRICAL_CABLE)
        assert value_of(attrs, "cores") == 2
        assert value_of(attrs, "cross_section_sqmm") == 2.5

    def test_lt_voltage_designation(self):
        attrs = norm_extract(
            "XLPE CABLE 3 CORE 95 SQ MM AL ARMOURED 650/1100 V", ELECTRICAL_CABLE
        )
        assert value_of(attrs, "voltage_grade") == "1.1KV"

    def test_implausible_derived_voltage_is_rejected(self):
        """OCR damage ('650/11100 V') must not yield a confident fictional grade."""
        attrs = norm_extract("XLPE CABLE 3 CORE 95 MM2 AL ARMOURED 11100 V", ELECTRICAL_CABLE)
        assert value_of(attrs, "voltage_grade") is None

    def test_al_expands_only_in_cable_context(self):
        assert value_of(
            norm_extract("CABLE 3 CORE 95 SQ MM AL XLPE 1.1KV", ELECTRICAL_CABLE),
            "conductor_material",
        ) == "ALUMINIUM"


class TestFastener:
    def test_full_extraction(self):
        attrs = norm_extract(
            "HEXAGON HEAD BOLT M16 X 100 GRADE 8.8 ZINC PLATED IS 1364", FASTENER
        )
        assert value_of(attrs, "item_type") == "HEXAGON HEAD BOLT"
        assert value_of(attrs, "thread_size") == "M16"
        assert value_of(attrs, "length_mm") == 100.0
        assert value_of(attrs, "property_class") == "8.8"
        assert value_of(attrs, "finish") == "ZINC PLATED"

    def test_tight_thread_notation(self):
        attrs = norm_extract("HEX BOLT M16X100 8.8 ZN PLTD", FASTENER)
        assert value_of(attrs, "thread_size") == "M16"
        assert value_of(attrs, "length_mm") == 100.0

    def test_stainless_property_class(self):
        attrs = norm_extract("HEXAGON HEAD BOLT M16 X 100 A4-80 SS316", FASTENER)
        assert value_of(attrs, "property_class") == "A4-80"

    def test_standard_number_is_not_read_as_a_thread(self):
        attrs = norm_extract("HEXAGON HEAD BOLT M16 X 100 8.8 IS 1364", FASTENER)
        assert value_of(attrs, "thread_size") == "M16"


class TestUnknownCommodity:
    def test_unknown_commodity_yields_no_attributes(self):
        assert extract_attributes("SOMETHING UNCLASSIFIABLE", None) == {}
        assert extract_attributes("SOMETHING UNCLASSIFIABLE", "unknown") == {}
