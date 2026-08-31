"""Safety constraint engine.

These are the tests that matter most: they encode the promise that the system
will not merge two materials that a plant engineer would consider different.
"""
from __future__ import annotations

import pytest

from app.core.commodities import BEARING, ELECTRICAL_CABLE, FASTENER, GATE_VALVE, PIPE
from app.core.safety import (
    SafetyStatus,
    applicable_critical_fields,
    critical_fields,
    evaluate_pair,
)


def A(value):
    return {"value": value, "source": str(value), "method": "rule", "confidence": 0.99}


def valve(material="CARBON STEEL", pressure="CL150", size="DN150", **extra):
    out = {"item_type": A("GATE VALVE"), "size": A(size)}
    if material is not None:
        out["material"] = A(material)
    if pressure is not None:
        out["pressure_class"] = A(pressure)
    out.update({k: A(v) for k, v in extra.items()})
    return out


class TestPass:
    def test_identical_valves_pass(self):
        v = evaluate_pair(valve(), valve(), GATE_VALVE)
        assert v.status is SafetyStatus.PASS
        assert v.allows_merge

    def test_differing_non_critical_field_still_passes(self):
        a = valve(end_connection="FLANGED", oem="KSB")
        b = valve(end_connection="FLANGED", oem="AUDCO")
        assert evaluate_pair(a, b, GATE_VALVE).status is SafetyStatus.PASS

    def test_equivalent_pressure_notation_passes(self):
        a, b = valve(pressure="CL150"), valve(pressure="PN20")
        assert evaluate_pair(a, b, GATE_VALVE).status is SafetyStatus.PASS


class TestBlock:
    def test_pressure_class_mismatch_blocks(self):
        v = evaluate_pair(valve(pressure="CL150"), valve(pressure="CL300"), GATE_VALVE)
        assert v.status is SafetyStatus.BLOCK
        assert v.blocked_field == "pressure_class"
        assert not v.allows_merge
        assert "CL150" in v.reason and "CL300" in v.reason

    def test_material_mismatch_blocks(self):
        v = evaluate_pair(
            valve(material="STAINLESS STEEL 304"),
            valve(material="STAINLESS STEEL 316"),
            GATE_VALVE,
        )
        assert v.status is SafetyStatus.BLOCK
        assert v.blocked_field == "material"

    def test_316_vs_316l_blocks(self):
        v = evaluate_pair(
            valve(material="STAINLESS STEEL 316"),
            valve(material="STAINLESS STEEL 316L"),
            GATE_VALVE,
        )
        assert v.status is SafetyStatus.BLOCK
        assert v.blocked_field == "material"

    def test_size_mismatch_blocks(self):
        v = evaluate_pair(valve(size="DN100"), valve(size="DN150"), GATE_VALVE)
        assert v.status is SafetyStatus.BLOCK
        assert v.blocked_field == "size"

    def test_bearing_bore_mismatch_blocks(self):
        a = {"designation": A("6205"), "bore_mm": A(25.0), "seal_type": A("OPEN")}
        b = {"designation": A("6206"), "bore_mm": A(30.0), "seal_type": A("OPEN")}
        v = evaluate_pair(a, b, BEARING)
        assert v.status is SafetyStatus.BLOCK

    def test_bearing_seal_type_mismatch_blocks(self):
        a = {"designation": A("6205"), "bore_mm": A(25.0), "seal_type": A("OPEN")}
        b = {"designation": A("6205"), "bore_mm": A(25.0), "seal_type": A("2RS")}
        v = evaluate_pair(a, b, BEARING)
        assert v.status is SafetyStatus.BLOCK
        assert v.blocked_field == "seal_type"

    def test_cable_voltage_grade_mismatch_blocks(self):
        base = {"cores": A(3), "cross_section_sqmm": A(95.0),
                "conductor_material": A("ALUMINIUM")}
        a = {**base, "voltage_grade": A("1.1KV")}
        b = {**base, "voltage_grade": A("3.3KV")}
        v = evaluate_pair(a, b, ELECTRICAL_CABLE)
        assert v.status is SafetyStatus.BLOCK
        assert v.blocked_field == "voltage_grade"

    def test_cable_conductor_material_mismatch_blocks(self):
        base = {"cores": A(3), "cross_section_sqmm": A(95.0), "voltage_grade": A("1.1KV")}
        a = {**base, "conductor_material": A("ALUMINIUM")}
        b = {**base, "conductor_material": A("COPPER")}
        assert evaluate_pair(a, b, ELECTRICAL_CABLE).blocked_field == "conductor_material"

    def test_fastener_property_class_mismatch_blocks(self):
        a = {"item_type": A("HEXAGON HEAD BOLT"), "thread_size": A("M16"),
             "length_mm": A(100.0), "property_class": A("8.8")}
        b = {**a, "property_class": A("10.9")}
        assert evaluate_pair(a, b, FASTENER).blocked_field == "property_class"

    def test_pipe_schedule_mismatch_blocks(self):
        a = {"size": A("DN150"), "material": A("CARBON STEEL"), "schedule": A("SCH40")}
        b = {**a, "schedule": A("SCH80")}
        assert evaluate_pair(a, b, PIPE).blocked_field == "schedule"

    def test_weak_standard_equivalence_cannot_talk_the_gate_out_of_a_block(self):
        v = evaluate_pair(valve(pressure="PN16"), valve(pressure="CL150"), GATE_VALVE)
        assert v.status is SafetyStatus.BLOCK


class TestInsufficientEvidence:
    def test_missing_critical_field_on_one_side(self):
        v = evaluate_pair(valve(pressure=None), valve(pressure="CL150"), GATE_VALVE)
        assert v.status is SafetyStatus.INSUFFICIENT_EVIDENCE
        assert "pressure_class" in v.unknown_fields
        assert not v.allows_merge

    def test_missing_on_both_sides_is_still_not_a_pass(self):
        v = evaluate_pair(valve(pressure=None), valve(pressure=None), GATE_VALVE)
        assert v.status is SafetyStatus.INSUFFICIENT_EVIDENCE

    def test_a_confirmed_mismatch_outranks_a_missing_field(self):
        """One field unknown, another confirmed different -> BLOCK, not INSUFFICIENT."""
        a = valve(material="STAINLESS STEEL 316", pressure=None)
        b = valve(material="STAINLESS STEEL 304", pressure="CL150")
        v = evaluate_pair(a, b, GATE_VALVE)
        assert v.status is SafetyStatus.BLOCK
        assert v.blocked_field == "material"

    def test_unknown_commodity_cannot_be_declared_safe(self):
        v = evaluate_pair({"x": A(1)}, {"x": A(1)}, None)
        assert v.status is SafetyStatus.INSUFFICIENT_EVIDENCE
        assert not v.allows_merge


class TestConditionalFields:
    def test_length_is_critical_for_bolts(self):
        assert "length_mm" in applicable_critical_fields(
            FASTENER, {"item_type": A("HEXAGON HEAD BOLT")}, {"item_type": A("HEXAGON HEAD BOLT")}
        )

    def test_length_does_not_apply_to_nuts(self):
        assert "length_mm" not in applicable_critical_fields(
            FASTENER, {"item_type": A("HEXAGON NUT")}, {"item_type": A("HEXAGON NUT")}
        )

    def test_two_identical_nuts_pass_despite_having_no_length(self):
        a = {"item_type": A("HEXAGON NUT"), "thread_size": A("M16"), "property_class": A("8.8")}
        assert evaluate_pair(a, dict(a), FASTENER).status is SafetyStatus.PASS


class TestConfiguration:
    @pytest.mark.parametrize(
        "commodity", [GATE_VALVE, PIPE, BEARING, ELECTRICAL_CABLE, FASTENER]
    )
    def test_every_commodity_declares_critical_fields(self, commodity):
        assert critical_fields(commodity)

    def test_verdict_serialises_for_the_ui(self):
        d = evaluate_pair(valve(pressure="CL150"), valve(pressure="CL300"), GATE_VALVE).to_dict()
        assert d["status"] == "BLOCK"
        assert d["blocked_field_label"] == "Pressure Class"
        assert d["blocked_values"] == ["CL150", "CL300"]
        assert any(c["state"] == "MISMATCH" for c in d["critical_comparisons"])
