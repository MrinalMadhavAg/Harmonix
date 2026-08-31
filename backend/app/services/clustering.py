"""Graph clustering and cluster validation.

Connected components are a CANDIDATE grouping, never the answer. Similarity
edges are not transitive with respect to identity:

    A--B strong, B--C strong, A--C contradictory

would put A, B and C in one component and produce a golden record asserting
something no source actually says. So every component is re-examined against
the safety-critical fields directly, and split where the members disagree.

Members that leave a safety-critical field unstated are never absorbed into a
group that states it -- silence is not consent. They are emitted separately
with INSUFFICIENT_EVIDENCE and a proposed candidate for a human to confirm.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx

from app.core.attributes import value_of
from app.core.comparison import distinct_values
from app.core.safety import applicable_critical_fields, label_for


@dataclass
class ValidatedCluster:
    members: list[dict]
    commodity: str | None
    # Members that could not be confirmed into this cluster.
    incomplete: list[dict] = field(default_factory=list)
    split_reason: str | None = None


@dataclass
class ClusterValidationReport:
    clusters: list[ValidatedCluster]
    splits: list[dict] = field(default_factory=list)
    incomplete_assignments: list[dict] = field(default_factory=list)


def build_graph(record_ids: list[int], edges: list[tuple[int, int, float]]) -> nx.Graph:
    g = nx.Graph()
    g.add_nodes_from(record_ids)
    for a, b, score in edges:
        g.add_edge(a, b, weight=score)
    return g


def connected_components(g: nx.Graph) -> list[list[int]]:
    return [sorted(c) for c in nx.connected_components(g)]


def _signature(record: dict, fields: list[str]) -> tuple | None:
    """Tuple of stated safety-critical values, or None if any is missing."""
    sig = []
    for key in fields:
        v = value_of(record.get("attributes"), key)
        if v is None:
            return None
        sig.append(str(v).strip().upper() if not isinstance(v, (int, float)) else float(v))
    return tuple(sig)


def validate_cluster(
    members: list[dict], commodity: str | None, enforce_safety: bool = True
) -> ClusterValidationReport:
    """Split one candidate cluster into internally consistent sub-clusters.

    `enforce_safety=False` skips validation entirely and returns the component
    as-is. Validation applies the same safety-critical field logic as the edge
    gate, so leaving it on while the gate is off would silently re-impose the
    constraint the operator just switched off -- and the safety demonstration
    would show no difference.
    """
    if len(members) <= 1 or not enforce_safety:
        return ClusterValidationReport(
            clusters=[ValidatedCluster(members=members, commodity=commodity)]
        )

    attrs = [m.get("attributes") for m in members]
    fields = applicable_critical_fields(commodity, attrs[0], attrs[1] if len(attrs) > 1 else None)

    # Which safety-critical fields actually carry conflicting values here?
    contradictions: list[dict] = []
    for key in fields:
        vals = distinct_values([value_of(m.get("attributes"), key) for m in members])
        if len(vals) > 1:
            contradictions.append(
                {"field": key, "label": label_for(key), "values": [str(v) for v in vals]}
            )

    complete: list[dict] = []
    incomplete: list[dict] = []
    for m in members:
        (complete if _signature(m, fields) is not None else incomplete).append(m)

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for m in complete:
        groups[_signature(m, fields)].append(m)

    clusters: list[ValidatedCluster] = []
    splits: list[dict] = []
    incomplete_assignments: list[dict] = []

    if groups:
        ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), min(int(x["id"]) for x in kv[1])))
        for sig, group in ordered:
            clusters.append(
                ValidatedCluster(
                    members=group,
                    commodity=commodity,
                    split_reason=(
                        f"Safety-critical signature {dict(zip(fields, sig))}"
                        if len(ordered) > 1 else None
                    ),
                )
            )
        if len(ordered) > 1:
            splits.append(
                {
                    "reason": "Contradictory safety-critical values within candidate cluster",
                    "contradictions": contradictions,
                    "resulting_groups": [
                        {"size": len(g), "record_ids": [int(m["id"]) for m in g]}
                        for _s, g in ordered
                    ],
                }
            )

    # Every incomplete member becomes its own cluster. It keeps a pointer to
    # the largest consistent group as a *proposal*, not a merge.
    largest = clusters[0].members if clusters else []
    for m in incomplete:
        missing = [
            label_for(k) for k in fields
            if value_of(m.get("attributes"), k) is None
        ]
        clusters.append(ValidatedCluster(members=[m], commodity=commodity))
        incomplete_assignments.append(
            {
                "record_id": int(m["id"]),
                "missing_fields": missing,
                "proposed_group_record_ids": [int(x["id"]) for x in largest],
            }
        )

    if not clusters:
        clusters = [ValidatedCluster(members=members, commodity=commodity)]

    return ClusterValidationReport(
        clusters=clusters, splits=splits, incomplete_assignments=incomplete_assignments
    )
