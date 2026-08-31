"""Cluster validation and golden-record survivorship.

The scenario this file exists for:

    A--B strong, B--C strong, A--C contradictory

Connected components would emit one cluster. That must not become one golden
record.
"""
from __future__ import annotations

from app.core.commodities import GATE_VALVE
from app.services.clustering import build_graph, connected_components, validate_cluster
from app.services.survivorship import build_description, build_golden_record, survive_attributes


def A(value, confidence=0.99):
    return {"value": value, "source": str(value), "method": "rule", "confidence": confidence}


def record(rid, material="CARBON STEEL", pressure="CL150", size="DN150", **extra):
    attrs = {"item_type": A("GATE VALVE"), "size": A(size)}
    if material is not None:
        attrs["material"] = A(material)
    if pressure is not None:
        attrs["pressure_class"] = A(pressure)
    attrs.update({k: A(v) for k, v in extra.items()})
    return {"id": rid, "cpse_org": f"CPSE{rid}", "legacy_code": f"CODE{rid}",
            "commodity_type": GATE_VALVE, "attributes": attrs}


class TestGraph:
    def test_connected_components(self):
        g = build_graph([1, 2, 3, 4], [(1, 2, 0.9), (2, 3, 0.85)])
        comps = connected_components(g)
        assert sorted(comps, key=len) == [[4], [1, 2, 3]]

    def test_isolated_records_are_their_own_component(self):
        assert connected_components(build_graph([1, 2, 3], [])) == [[1], [2], [3]]


class TestClusterSplitting:
    def test_contradictory_cluster_is_split(self):
        """A=CL150, B=CL150, C=CL300 must not become one golden record."""
        members = [record(1), record(2), record(3, pressure="CL300")]
        report = validate_cluster(members, GATE_VALVE)

        assert len(report.clusters) == 2
        sizes = sorted(len(c.members) for c in report.clusters)
        assert sizes == [1, 2]
        assert report.splits
        fields = {c["field"] for c in report.splits[0]["contradictions"]}
        assert "pressure_class" in fields

    def test_split_groups_contain_the_right_members(self):
        members = [record(1), record(2), record(3, pressure="CL300")]
        report = validate_cluster(members, GATE_VALVE)
        groups = {tuple(sorted(int(m["id"]) for m in c.members)) for c in report.clusters}
        assert groups == {(1, 2), (3,)}

    def test_three_way_contradiction_splits_three_ways(self):
        members = [record(1, pressure="CL150"), record(2, pressure="CL300"),
                   record(3, pressure="CL600")]
        report = validate_cluster(members, GATE_VALVE)
        assert len(report.clusters) == 3

    def test_material_contradiction_splits(self):
        members = [
            record(1, material="STAINLESS STEEL 316"),
            record(2, material="STAINLESS STEEL 316"),
            record(3, material="STAINLESS STEEL 316L"),
        ]
        report = validate_cluster(members, GATE_VALVE)
        assert len(report.clusters) == 2


class TestIncompleteMembers:
    def test_unknown_member_is_not_absorbed(self):
        """A=CL150, B=CL150, C=UNKNOWN. C must not silently become CL150."""
        members = [record(1), record(2), record(3, pressure=None)]
        report = validate_cluster(members, GATE_VALVE)

        confirmed = [c for c in report.clusters if len(c.members) > 1]
        assert len(confirmed) == 1
        assert {int(m["id"]) for m in confirmed[0].members} == {1, 2}

        singles = [c for c in report.clusters if len(c.members) == 1]
        assert [int(c.members[0]["id"]) for c in singles] == [3]

    def test_incomplete_member_records_what_was_missing(self):
        members = [record(1), record(2), record(3, pressure=None)]
        report = validate_cluster(members, GATE_VALVE)
        assert len(report.incomplete_assignments) == 1
        assignment = report.incomplete_assignments[0]
        assert assignment["record_id"] == 3
        assert "Pressure Class" in assignment["missing_fields"]
        assert assignment["proposed_group_record_ids"] == [1, 2]

    def test_all_members_incomplete_produces_no_false_merge(self):
        members = [record(1, pressure=None), record(2, pressure=None)]
        report = validate_cluster(members, GATE_VALVE)
        assert all(len(c.members) == 1 for c in report.clusters)

    def test_consistent_cluster_is_left_intact(self):
        members = [record(1), record(2), record(3)]
        report = validate_cluster(members, GATE_VALVE)
        assert len(report.clusters) == 1
        assert len(report.clusters[0].members) == 3
        assert not report.splits

    def test_singleton_cluster(self):
        report = validate_cluster([record(1)], GATE_VALVE)
        assert len(report.clusters) == 1


class TestSurvivorship:
    def test_majority_value_wins_over_a_typo(self):
        members = [record(1), record(2), record(3, material="CARBQN STEEL")]
        attrs = survive_attributes(members, GATE_VALVE)
        assert attrs["material"]["value"] == "CARBON STEEL"
        assert attrs["material"]["agreement"] == "2/3"

    def test_agreement_ratio_and_confidence_are_recorded(self):
        members = [record(1), record(2), record(3), record(4, material="MILD STEEL")]
        attrs = survive_attributes(members, GATE_VALVE)
        assert attrs["material"]["agreement"] == "3/4"
        assert attrs["material"]["agreement_ratio"] == 0.75
        assert 0 < attrs["material"]["confidence"] <= 1

    def test_contested_values_are_retained_for_the_reviewer(self):
        members = [record(1), record(2), record(3, material="MILD STEEL")]
        attrs = survive_attributes(members, GATE_VALVE)
        assert attrs["material"]["contested_values"] == ["MILD STEEL"]

    def test_unanimous_attribute_has_no_contested_values(self):
        attrs = survive_attributes([record(1), record(2)], GATE_VALVE)
        assert attrs["material"]["contested_values"] is None
        assert attrs["material"]["agreement_ratio"] == 1.0

    def test_absent_attributes_are_not_invented(self):
        attrs = survive_attributes(
            [record(1, pressure=None), record(2, pressure=None)], GATE_VALVE
        )
        assert "pressure_class" not in attrs

    def test_a_value_stated_by_only_one_member_still_survives(self):
        attrs = survive_attributes(
            [record(1, standard="API 600"), record(2)], GATE_VALVE
        )
        assert attrs["standard"]["value"] == "API 600"
        assert attrs["standard"]["agreement"] == "1/1"

    def test_survivorship_is_not_most_complete_record_selection(self):
        """The fullest record's minority value must still lose the vote."""
        members = [
            record(1, material="CARBON STEEL"),
            record(2, material="CARBON STEEL"),
            record(3, material="MILD STEEL", end_connection="FLANGED",
                   standard="API 600", oem="KSB"),
        ]
        attrs = survive_attributes(members, GATE_VALVE)
        assert attrs["material"]["value"] == "CARBON STEEL"

    def test_ties_break_deterministically(self):
        members = [record(1, material="CARBON STEEL"), record(2, material="MILD STEEL")]
        first = survive_attributes(members, GATE_VALVE)["material"]["value"]
        second = survive_attributes(list(reversed(members)), GATE_VALVE)["material"]["value"]
        assert first == second

    def test_source_records_are_recorded(self):
        attrs = survive_attributes([record(1), record(2)], GATE_VALVE)
        assert attrs["material"]["source_record_ids"] == [1, 2]


class TestGoldenRecord:
    def test_description_is_generated_from_surviving_attributes(self):
        gr = build_golden_record("NMI-000001", [record(1), record(2)], GATE_VALVE)
        assert gr["nmi"] == "NMI-000001"
        assert gr["member_count"] == 2
        assert "GATE VALVE" in gr["standardized_description"]
        assert "DN150" in gr["standardized_description"]
        assert "CL150" in gr["standardized_description"]
        assert gr["unspsc_class"]

    def test_description_omits_attributes_nobody_stated(self):
        desc = build_description(
            survive_attributes([record(1, pressure=None)], GATE_VALVE), GATE_VALVE
        )
        assert "CL150" not in desc
        assert "GATE VALVE" in desc

    def test_empty_attributes_do_not_crash(self):
        assert build_description({}, GATE_VALVE) == "UNSPECIFIED MATERIAL"
