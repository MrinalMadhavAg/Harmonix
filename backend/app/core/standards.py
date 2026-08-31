"""Standard-equivalence knowledge base.

PN20 and CL150 are *related* pressure designations, not interchangeable
strings. Rewriting `PN20 -> CL150` inside a description would erase a real
engineering distinction and make the golden record lie about the source
data. So the knowledge lives here, carries an explicit confidence and an
applicable commodity, and is consumed only as a SOFT scoring feature -- it
can nudge a score upward, it can never turn a MISMATCH into a MATCH.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.commodities import GATE_VALVE, PIPE


@dataclass(frozen=True)
class Equivalence:
    source: str
    target: str
    confidence: float
    commodities: frozenset[str]
    context: str


# ASME B16.5 pressure classes vs ISO/EN PN ratings. The pairing is standard
# practice but is temperature- and material-dependent, hence < 1.0 confidence.
PRESSURE_EQUIVALENCES: list[Equivalence] = [
    Equivalence("PN20", "CL150", 0.90, frozenset({GATE_VALVE, PIPE}), "ASME B16.5 / ISO 7005 nominal pairing"),
    Equivalence("PN50", "CL300", 0.90, frozenset({GATE_VALVE, PIPE}), "ASME B16.5 / ISO 7005 nominal pairing"),
    Equivalence("PN68", "CL400", 0.85, frozenset({GATE_VALVE, PIPE}), "ASME B16.5 / ISO 7005 nominal pairing"),
    Equivalence("PN100", "CL600", 0.90, frozenset({GATE_VALVE, PIPE}), "ASME B16.5 / ISO 7005 nominal pairing"),
    Equivalence("PN150", "CL900", 0.85, frozenset({GATE_VALVE, PIPE}), "ASME B16.5 / ISO 7005 nominal pairing"),
    Equivalence("PN250", "CL1500", 0.85, frozenset({GATE_VALVE, PIPE}), "ASME B16.5 / ISO 7005 nominal pairing"),
    Equivalence("PN420", "CL2500", 0.85, frozenset({GATE_VALVE, PIPE}), "ASME B16.5 / ISO 7005 nominal pairing"),
    # Common European ratings that procurement teams treat as near-equivalents.
    Equivalence("PN16", "CL150", 0.60, frozenset({GATE_VALVE, PIPE}), "Approximate; PN16 is lower rated than CL150"),
    Equivalence("PN40", "CL300", 0.60, frozenset({GATE_VALVE, PIPE}), "Approximate; PN40 is lower rated than CL300"),
]

_INDEX: dict[tuple[str, str], Equivalence] = {}
for _eq in PRESSURE_EQUIVALENCES:
    _INDEX[(_eq.source, _eq.target)] = _eq
    _INDEX[(_eq.target, _eq.source)] = _eq


def equivalence_confidence(a: str, b: str, commodity: str | None) -> float:
    """Return the soft-equivalence confidence for two notations, else 0.0."""
    if not a or not b:
        return 0.0
    a, b = a.upper().replace(" ", ""), b.upper().replace(" ", "")
    if a == b:
        return 1.0
    eq = _INDEX.get((a, b))
    if eq is None:
        return 0.0
    if commodity is not None and commodity not in eq.commodities:
        return 0.0
    return eq.confidence


def describe_equivalence(a: str, b: str, commodity: str | None) -> Equivalence | None:
    a, b = (a or "").upper().replace(" ", ""), (b or "").upper().replace(" ", "")
    eq = _INDEX.get((a, b))
    if eq is None:
        return None
    if commodity is not None and commodity not in eq.commodities:
        return None
    return eq


def all_equivalences() -> list[dict]:
    return [
        {
            "source": e.source,
            "target": e.target,
            "confidence": e.confidence,
            "commodities": sorted(e.commodities),
            "context": e.context,
        }
        for e in PRESSURE_EQUIVALENCES
    ]
