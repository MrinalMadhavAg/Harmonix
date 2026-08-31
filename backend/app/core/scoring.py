"""Match scoring.

Combines semantic similarity, normalized lexical similarity and weighted
attribute agreement into a single [0, 1] confidence, and returns the full
breakdown that produced it. Nothing downstream is allowed to display a
confidence without also being able to display this breakdown.

Contains NO safety logic. Safety is a separate gate (`safety.py`) applied
*after* scoring, so that turning safety off for the demo changes what the
system permits without changing what it believes.

The signature is kept narrow so this scorer can later be swapped for a
trained cross-encoder without touching its callers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.attributes import schema_for
from app.core.comparison import AttrState, ComparisonSet, compare_attributes
from app.core.safety import critical_fields
from app.core.weights import get_weights

# A confirmed difference must outweigh an equal-weight agreement, otherwise a
# pile of matching incidentals can drown out one disqualifying attribute.
MISMATCH_PENALTY_CRITICAL = 2.5
MISMATCH_PENALTY_STANDARD = 1.2

# When most attributes are UNKNOWN the agreement signal is thin, so it is
# pulled back toward neutral instead of being trusted at face value.
MIN_COVERAGE_TRUST = 0.40


@dataclass
class MatchScore:
    score: float
    semantic: float
    lexical: float
    attribute_agreement: float
    coverage: float
    weights: dict[str, float]
    comparisons: list[dict] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "semantic": round(self.semantic, 4),
            "lexical": round(self.lexical, 4),
            "attribute_agreement": round(self.attribute_agreement, 4),
            "coverage": round(self.coverage, 4),
            "weights": self.weights,
            "comparisons": self.comparisons,
            "counts": self.counts,
        }


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def attribute_agreement(cs: ComparisonSet, commodity: str | None) -> tuple[float, float]:
    """Weighted agreement in [0, 1] plus the evidence coverage in [0, 1]."""
    w = get_weights(commodity)
    critical = set(critical_fields(commodity))

    contrib = 0.0
    known_weight = 0.0
    total_weight = 0.0

    for key, c in cs.results.items():
        weight = w.weight_for(key)
        total_weight += weight
        if c.state is AttrState.MATCH:
            contrib += weight
            known_weight += weight
        elif c.state is AttrState.MISMATCH:
            penalty = MISMATCH_PENALTY_CRITICAL if key in critical else MISMATCH_PENALTY_STANDARD
            # A weak cross-notation relationship softens the penalty a little
            # but never erases it.
            penalty *= 1.0 - 0.3 * c.equivalence_confidence
            contrib -= weight * penalty
            known_weight += weight
        # UNKNOWN contributes nothing and does not count as evidence.

    if known_weight <= 0.0:
        return 0.5, 0.0

    raw = contrib / known_weight            # in [-penalty_max, 1]
    raw = max(-1.0, min(1.0, raw))
    agreement = (raw + 1.0) / 2.0           # in [0, 1]

    coverage = known_weight / total_weight if total_weight > 0 else 0.0
    trust = MIN_COVERAGE_TRUST + (1.0 - MIN_COVERAGE_TRUST) * coverage
    agreement = 0.5 + (agreement - 0.5) * trust

    return _clip01(agreement), _clip01(coverage)


def match_score(
    rec_a: dict,
    rec_b: dict,
    semantic_score: float,
    lexical_score: float,
    commodity_type: str | None,
) -> MatchScore:
    """Score a candidate pair.

    `rec_a` / `rec_b` are record dicts carrying at least `attributes`.
    `semantic_score` and `lexical_score` are expected pre-normalized to [0, 1].
    """
    keys = [k for k, _ in schema_for(commodity_type)]
    if not keys:
        keys = sorted(set(rec_a.get("attributes") or {}) | set(rec_b.get("attributes") or {}))

    cs = compare_attributes(
        rec_a.get("attributes"), rec_b.get("attributes"), commodity_type, keys=keys
    )
    agreement, coverage = attribute_agreement(cs, commodity_type)

    w = get_weights(commodity_type)
    ws, wl, wa = w.normalized_components()

    sem = _clip01(semantic_score)
    lex = _clip01(lexical_score)
    final = ws * sem + wl * lex + wa * agreement

    return MatchScore(
        score=_clip01(final),
        semantic=sem,
        lexical=lex,
        attribute_agreement=agreement,
        coverage=coverage,
        weights={"semantic": round(ws, 4), "lexical": round(wl, 4), "attributes": round(wa, 4)},
        comparisons=_labelled(cs, commodity_type),
        counts=cs.counts(),
    )


def _labelled(cs: ComparisonSet, commodity: str | None) -> list[dict]:
    labels = dict(schema_for(commodity))
    critical = set(critical_fields(commodity))
    w = get_weights(commodity)
    out = []
    for key, c in cs.results.items():
        d = c.to_dict()
        d["label"] = labels.get(key, key.replace("_", " ").title())
        d["safety_critical"] = key in critical
        d["weight"] = w.weight_for(key)
        out.append(d)
    # Safety-critical fields first, then by descending weight -- the order a
    # reviewer needs, not alphabetical.
    out.sort(key=lambda d: (not d["safety_critical"], -d["weight"], d["key"]))
    return out
