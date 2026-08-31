"""Golden record construction from a validated cluster.

Survivorship is by MAJORITY VALUE per attribute, not by picking the "most
complete" record. Choosing a single winning record would import that record's
individual errors wholesale; majority voting per field lets a typo in one
source be outvoted by the others while still recording how strong the
agreement was.

Every surviving attribute stores value, confidence and the agreement ratio,
so a reviewer can see that `material = SS316` rests on 3 of 4 sources rather
than on an unexplained assertion.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from app.core.attributes import schema_for, value_of
from app.core.commodities import UNSPSC_BY_COMMODITY

# Order in which attributes appear in a generated standardized description.
_DESCRIPTION_ORDER: dict[str, list[str]] = {
    "gate_valve": ["item_type", "size", "material", "pressure_class", "end_connection", "standard"],
    "pipe": ["item_type", "size", "material", "schedule", "manufacture", "standard"],
    "bearing": ["item_type", "designation", "bore_mm", "outer_diameter_mm", "width_mm", "seal_type"],
    "electrical_cable": [
        "item_type", "cores", "cross_section_sqmm", "conductor_material",
        "insulation", "voltage_grade", "armour",
    ],
    "fastener": ["item_type", "thread_size", "length_mm", "property_class", "material", "finish", "standard"],
}

_UNIT_SUFFIX = {
    "bore_mm": " MM BORE", "outer_diameter_mm": " MM OD", "width_mm": " MM WIDTH",
    "cross_section_sqmm": " SQ MM", "length_mm": " MM LONG",
}
_UNIT_PREFIX = {"cores": "", "designation": ""}


def _canon(v: object) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip().upper()


def survive_attributes(members: list[dict], commodity: str | None) -> dict:
    """Majority-vote each attribute across the cluster members."""
    keys = [k for k, _ in schema_for(commodity)]
    if not keys:
        seen: set[str] = set()
        for m in members:
            seen |= set(m.get("attributes") or {})
        keys = sorted(seen)

    out: dict = {}
    for key in keys:
        votes: list[tuple[str, object, float, int]] = []  # canon, raw, confidence, record_id
        for m in members:
            raw = value_of(m.get("attributes"), key)
            if raw is None:
                continue
            a = (m.get("attributes") or {}).get(key)
            conf = float(a.get("confidence", 0.8)) if isinstance(a, dict) else 0.8
            votes.append((_canon(raw), raw, conf, int(m["id"])))

        if not votes:
            continue

        tally = Counter(v[0] for v in votes)
        # Ties break toward the value carrying the higher total extraction
        # confidence, then lexically, so the result is deterministic.
        conf_by_value: dict[str, float] = defaultdict(float)
        for canon, _raw, conf, _rid in votes:
            conf_by_value[canon] += conf
        winner = max(tally, key=lambda v: (tally[v], conf_by_value[v], v))

        supporters = [v for v in votes if v[0] == winner]
        agreement_ratio = len(supporters) / len(votes)
        mean_conf = sum(v[2] for v in supporters) / len(supporters)

        out[key] = {
            "value": supporters[0][1],
            # Confidence is the extraction confidence tempered by how much of
            # the cluster actually agreed.
            "confidence": round(mean_conf * (0.6 + 0.4 * agreement_ratio), 4),
            "agreement": f"{len(supporters)}/{len(votes)}",
            "agreement_ratio": round(agreement_ratio, 4),
            "method": "survivorship",
            "source_record_ids": [v[3] for v in supporters],
            "contested_values": sorted(set(v[0] for v in votes if v[0] != winner)) or None,
        }
    return out


def build_description(attributes: dict, commodity: str | None) -> str:
    """Render a clean, canonical description from the surviving attributes."""
    order = _DESCRIPTION_ORDER.get(commodity or "", [k for k, _ in schema_for(commodity)])
    parts: list[str] = []
    for key in order:
        a = attributes.get(key)
        if not isinstance(a, dict) or a.get("value") is None:
            continue
        val = a["value"]
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        text = str(val).upper()
        if key == "cores":
            text = f"{text} CORE"
        elif key in _UNIT_SUFFIX:
            text = f"{text}{_UNIT_SUFFIX[key]}"
        parts.append(text)
    return ", ".join(parts) if parts else "UNSPECIFIED MATERIAL"


def build_golden_record(nmi: str, members: list[dict], commodity: str | None) -> dict:
    attributes = survive_attributes(members, commodity)
    return {
        "nmi": nmi,
        "version": 1,
        "standardized_description": build_description(attributes, commodity),
        "unspsc_class": UNSPSC_BY_COMMODITY.get(commodity or ""),
        "commodity_type": commodity,
        "attributes": attributes,
        "member_count": len(members),
    }
