"""The one and only attribute comparison implementation.

Three states, and the distinction between them is the whole point:

    MATCH     both sides state a value and the values agree
    MISMATCH  both sides state a value and the values conflict
    UNKNOWN   at least one side does not state a value

UNKNOWN is *not* a mismatch (absence of evidence is not evidence of
difference) and it is *not* a match (we may not invent agreement). Every
consumer -- scoring, safety, clustering, survivorship, the evidence UI and
the review queue -- imports from here so the three-state semantics cannot
drift apart between layers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from app.core.attributes import value_of
from app.core.standards import describe_equivalence, equivalence_confidence

# Attributes compared as pressure notations, where PN/CL equivalence applies.
_EQUIVALENCE_KEYS = {"pressure_class"}

# Attributes where one description may legitimately be a broader term for the
# other: "BALL BEARING" does not contradict "DEEP GROOVE BALL BEARING", and a
# record that says "ZINC" is not in conflict with one that says "ZINC PLATED".
# Treated as a match at reduced strength, never as a mismatch. Deliberately
# NOT applied to grades or ratings, where a missing qualifier changes the
# part (SS316 vs SS316L).
_HIERARCHICAL_KEYS = {"item_type", "finish", "manufacture"}

# Numeric attributes and their absolute tolerance. Tolerances are tight on
# purpose: a 25 mm bore and a 30 mm bore are different bearings.
_NUMERIC_TOLERANCE = {
    "bore_mm": 0.01,
    "outer_diameter_mm": 0.01,
    "width_mm": 0.01,
    "cross_section_sqmm": 0.01,
    "length_mm": 0.01,
    "cores": 0.0,
}

# Confidence at or above which a cross-notation equivalence is accepted as a
# genuine MATCH rather than a softened mismatch.
EQUIVALENCE_MATCH_FLOOR = 0.85

_WS = re.compile(r"\s+")


class AttrState(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"


@dataclass
class Comparison:
    key: str
    state: AttrState
    value_a: object | None
    value_b: object | None
    detail: str = ""
    # Set when the two sides used different notations for a related standard.
    equivalence_confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "state": self.state.value,
            "value_a": self.value_a,
            "value_b": self.value_b,
            "detail": self.detail,
            "equivalence_confidence": round(self.equivalence_confidence, 3),
        }


@dataclass
class ComparisonSet:
    commodity: str | None
    results: dict[str, Comparison] = field(default_factory=dict)

    def state(self, key: str) -> AttrState:
        c = self.results.get(key)
        return c.state if c else AttrState.UNKNOWN

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in AttrState}
        for c in self.results.values():
            out[c.state.value] += 1
        return out

    def mismatched_keys(self) -> list[str]:
        return [k for k, c in self.results.items() if c.state is AttrState.MISMATCH]

    def unknown_keys(self) -> list[str]:
        return [k for k, c in self.results.items() if c.state is AttrState.UNKNOWN]

    def to_list(self) -> list[dict]:
        return [c.to_dict() for c in self.results.values()]


def _canon(v: object) -> object:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    s = _WS.sub(" ", str(v)).strip().upper()
    return s or None


def _numeric(v: object) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def compare_values(
    key: str, raw_a: object | None, raw_b: object | None, commodity: str | None = None
) -> Comparison:
    a, b = _canon(raw_a), _canon(raw_b)

    if a is None or b is None:
        missing = (
            "both sides" if a is None and b is None
            else ("left side" if a is None else "right side")
        )
        return Comparison(key, AttrState.UNKNOWN, raw_a, raw_b, f"Not specified on {missing}")

    if key in _NUMERIC_TOLERANCE:
        na, nb = _numeric(a), _numeric(b)
        if na is not None and nb is not None:
            tol = _NUMERIC_TOLERANCE[key]
            if abs(na - nb) <= tol:
                return Comparison(key, AttrState.MATCH, raw_a, raw_b, "Values agree")
            return Comparison(
                key, AttrState.MISMATCH, raw_a, raw_b, f"{na:g} vs {nb:g}"
            )

    if a == b:
        return Comparison(key, AttrState.MATCH, raw_a, raw_b, "Exact match")

    if key in _HIERARCHICAL_KEYS:
        wa, wb = set(str(a).split()), set(str(b).split())
        if wa and wb and (wa < wb or wb < wa):
            broader, narrower = (a, b) if wa < wb else (b, a)
            return Comparison(
                key, AttrState.MATCH, raw_a, raw_b,
                f"'{broader}' is a broader term for '{narrower}'",
            )

    if key in _EQUIVALENCE_KEYS:
        conf = equivalence_confidence(str(a), str(b), commodity)
        if conf >= EQUIVALENCE_MATCH_FLOOR:
            eq = describe_equivalence(str(a), str(b), commodity)
            return Comparison(
                key,
                AttrState.MATCH,
                raw_a,
                raw_b,
                f"Equivalent notation ({eq.context if eq else 'standard equivalence'})",
                equivalence_confidence=conf,
            )
        if conf > 0.0:
            # Related but not confidently interchangeable. Still a mismatch --
            # the safety layer must not be talked out of a block by a weak
            # cross-standard analogy -- but the reviewer is told why.
            return Comparison(
                key,
                AttrState.MISMATCH,
                raw_a,
                raw_b,
                f"{a} vs {b} (related notations, equivalence confidence {conf:.2f} "
                f"below {EQUIVALENCE_MATCH_FLOOR:.2f})",
                equivalence_confidence=conf,
            )

    return Comparison(key, AttrState.MISMATCH, raw_a, raw_b, f"{a} vs {b}")


def compare_attributes(
    attrs_a: dict | None,
    attrs_b: dict | None,
    commodity: str | None,
    keys: list[str] | None = None,
) -> ComparisonSet:
    """Compare two attribute bags over the union of their keys."""
    attrs_a = attrs_a or {}
    attrs_b = attrs_b or {}
    if keys is None:
        keys = sorted(set(attrs_a) | set(attrs_b))

    cs = ComparisonSet(commodity=commodity)
    for key in keys:
        cs.results[key] = compare_values(
            key, value_of(attrs_a, key), value_of(attrs_b, key), commodity
        )
    return cs


def distinct_values(values: list[object]) -> list[object]:
    """Distinct non-null canonical values, order preserved."""
    seen: list[object] = []
    for v in values:
        c = _canon(v)
        if c is None:
            continue
        if c not in seen:
            seen.append(c)
    return seen
