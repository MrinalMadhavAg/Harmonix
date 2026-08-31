"""Safety constraint engine.

Kept strictly separate from `scoring.py`. The scorer answers "how similar are
these two descriptions"; this module answers "is it permissible to declare
them the same material". A 0.95 semantic similarity between a CL150 and a
CL300 gate valve is *correct* -- the descriptions really are nearly
identical -- and it must still be refused.

Verdicts:

    PASS                  every safety-critical field is stated and agrees
    BLOCK                 at least one safety-critical field confirmed to differ
    INSUFFICIENT_EVIDENCE at least one safety-critical field is UNKNOWN,
                          and none of them mismatch

INSUFFICIENT_EVIDENCE never auto-merges. It routes to human review.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.core.commodities import (
    BEARING,
    ELECTRICAL_CABLE,
    FASTENER,
    GATE_VALVE,
    PIPE,
)
from app.core.comparison import AttrState, ComparisonSet, compare_attributes


class SafetyStatus(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


# Fields where a confirmed difference makes two items non-interchangeable in
# service. These are the fields a procurement officer would be held
# responsible for if a wrong part reached a plant.
SAFETY_CRITICAL_FIELDS: dict[str, list[str]] = {
    GATE_VALVE: ["material", "pressure_class", "size"],
    PIPE: ["material", "schedule", "size"],
    # `outer_diameter_mm` is deliberately absent: a bearing's OD is fixed by
    # its designation (a 6205 is always 52 mm OD), which is already critical
    # here. Listing both adds no safety and turns every terse-but-unambiguous
    # record ("BALL BEARING 6205 OPEN") into a review item.
    BEARING: ["designation", "bore_mm", "seal_type"],
    ELECTRICAL_CABLE: [
        "voltage_grade", "conductor_material", "cross_section_sqmm", "cores",
    ],
    FASTENER: ["thread_size", "property_class", "length_mm"],
}

# Fields that only apply to some members of a commodity. A hexagon nut has no
# length, so demanding one would send every nut pair to review forever.
_CONDITIONAL_FIELDS: dict[tuple[str, str], set[str]] = {
    (FASTENER, "length_mm"): {"HEXAGON HEAD BOLT", "STUD BOLT", "BOLT", "SCREW", "STUD"},
}

FIELD_LABELS = {
    "material": "Material", "pressure_class": "Pressure Class", "size": "Size",
    "schedule": "Schedule", "designation": "Designation", "bore_mm": "Bore (mm)",
    "outer_diameter_mm": "Outer Dia (mm)", "seal_type": "Seal Type",
    "voltage_grade": "Voltage Grade", "conductor_material": "Conductor",
    "cross_section_sqmm": "Cross Section (sq mm)", "cores": "Cores",
    "thread_size": "Thread Size", "property_class": "Property Class",
    "length_mm": "Length (mm)",
}


def critical_fields(commodity: str | None) -> list[str]:
    return SAFETY_CRITICAL_FIELDS.get(commodity or "", [])


def applicable_critical_fields(
    commodity: str | None, attrs_a: dict | None, attrs_b: dict | None
) -> list[str]:
    """Critical fields, minus those that do not apply to this kind of item."""
    from app.core.attributes import value_of

    fields = critical_fields(commodity)
    if not fields:
        return fields

    out = []
    for key in fields:
        applies_to = _CONDITIONAL_FIELDS.get((commodity or "", key))
        if applies_to is not None:
            types = {
                str(value_of(attrs_a, "item_type") or "").upper(),
                str(value_of(attrs_b, "item_type") or "").upper(),
            }
            # Applicable if either side is a kind of item that has this field.
            if not any(t in applies_to for t in types if t):
                continue
        out.append(key)
    return out


def label_for(field_key: str) -> str:
    return FIELD_LABELS.get(field_key, field_key.replace("_", " ").title())


@dataclass
class SafetyVerdict:
    status: SafetyStatus
    commodity: str | None
    blocked_field: str | None = None
    blocked_values: tuple[object, object] | None = None
    reason: str = ""
    critical_comparisons: list[dict] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)

    @property
    def allows_merge(self) -> bool:
        return self.status is SafetyStatus.PASS

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "commodity": self.commodity,
            "blocked_field": self.blocked_field,
            "blocked_field_label": label_for(self.blocked_field) if self.blocked_field else None,
            "blocked_values": list(self.blocked_values) if self.blocked_values else None,
            "reason": self.reason,
            "critical_comparisons": self.critical_comparisons,
            "unknown_fields": self.unknown_fields,
        }


def evaluate_pair(
    attrs_a: dict | None,
    attrs_b: dict | None,
    commodity: str | None,
    precomputed: ComparisonSet | None = None,
) -> SafetyVerdict:
    """Decide whether two records may be linked."""
    if not critical_fields(commodity):
        # An unrecognised commodity has no defined safety envelope, so we
        # cannot assert the pair is safe. Refuse to auto-merge.
        return SafetyVerdict(
            status=SafetyStatus.INSUFFICIENT_EVIDENCE,
            commodity=commodity,
            reason="No safety-critical field set is defined for this commodity type.",
        )

    fields = applicable_critical_fields(commodity, attrs_a, attrs_b)

    cs = precomputed or compare_attributes(attrs_a, attrs_b, commodity, keys=fields)

    critical = []
    for key in fields:
        c = cs.results.get(key)
        if c is None:
            from app.core.attributes import value_of
            from app.core.comparison import compare_values

            c = compare_values(key, value_of(attrs_a, key), value_of(attrs_b, key), commodity)
        d = c.to_dict()
        d["label"] = label_for(key)
        critical.append(d)

    mismatches = [c for c in critical if c["state"] == AttrState.MISMATCH.value]
    if mismatches:
        first = mismatches[0]
        return SafetyVerdict(
            status=SafetyStatus.BLOCK,
            commodity=commodity,
            blocked_field=first["key"],
            blocked_values=(first["value_a"], first["value_b"]),
            reason=(
                f"{first['label']} differs: {first['value_a']} vs {first['value_b']}. "
                "Safety-critical attributes must agree before two codes can share an NMI."
            ),
            critical_comparisons=critical,
        )

    unknowns = [c["key"] for c in critical if c["state"] == AttrState.UNKNOWN.value]
    if unknowns:
        labels = ", ".join(label_for(k) for k in unknowns)
        return SafetyVerdict(
            status=SafetyStatus.INSUFFICIENT_EVIDENCE,
            commodity=commodity,
            reason=(
                f"Safety-critical attribute(s) not specified on one or both records: {labels}. "
                "Routed for human confirmation rather than assumed equal."
            ),
            critical_comparisons=critical,
            unknown_fields=unknowns,
        )

    return SafetyVerdict(
        status=SafetyStatus.PASS,
        commodity=commodity,
        reason="All safety-critical attributes are stated and agree.",
        critical_comparisons=critical,
    )


def validate_cluster_attribute(
    values: list[object], key: str
) -> tuple[bool, list[object]]:
    """Are all stated values of `key` across a cluster consistent?

    Returns (is_consistent, distinct_stated_values). Null/absent values are
    ignored rather than treated as agreement.
    """
    from app.core.comparison import distinct_values

    distinct = distinct_values(values)
    return (len(distinct) <= 1, distinct)
