"""Commodity-specific scoring weights.

There is deliberately no global attribute-weight dictionary: `material`
dominates a valve match but is near-irrelevant for a bearing, where the
designation and bore carry the identity. Defaults live here; the database
holds any operator overrides so a change survives restart and can be made
from the Settings screen without a redeploy.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.commodities import (
    BEARING,
    COMMODITIES,
    ELECTRICAL_CABLE,
    FASTENER,
    GATE_VALVE,
    PIPE,
)

log = logging.getLogger(__name__)


@dataclass
class CommodityWeights:
    commodity_type: str
    semantic: float
    lexical: float
    attributes: float
    attribute_weights: dict[str, float] = field(default_factory=dict)

    def normalized_components(self) -> tuple[float, float, float]:
        total = self.semantic + self.lexical + self.attributes
        if total <= 0:
            return (0.34, 0.16, 0.50)
        return (self.semantic / total, self.lexical / total, self.attributes / total)

    def weight_for(self, key: str) -> float:
        return self.attribute_weights.get(key, 0.25)

    def to_dict(self) -> dict:
        return {
            "commodity_type": self.commodity_type,
            "semantic": self.semantic,
            "lexical": self.lexical,
            "attributes": self.attributes,
            "attribute_weights": self.attribute_weights,
        }


DEFAULT_WEIGHTS: dict[str, CommodityWeights] = {
    GATE_VALVE: CommodityWeights(
        GATE_VALVE, semantic=0.35, lexical=0.15, attributes=0.50,
        attribute_weights={
            "item_type": 1.00, "size": 0.90, "material": 1.00,
            "pressure_class": 1.00, "end_connection": 0.40,
            "standard": 0.30, "oem": 0.10,
        },
    ),
    PIPE: CommodityWeights(
        PIPE, semantic=0.35, lexical=0.15, attributes=0.50,
        attribute_weights={
            "item_type": 1.00, "size": 0.90, "material": 1.00,
            "schedule": 1.00, "manufacture": 0.30,
            "standard": 0.40, "oem": 0.10,
        },
    ),
    BEARING: CommodityWeights(
        BEARING, semantic=0.25, lexical=0.25, attributes=0.50,
        attribute_weights={
            "item_type": 0.60, "designation": 1.00, "bore_mm": 1.00,
            "outer_diameter_mm": 0.90, "width_mm": 0.60,
            "seal_type": 0.70, "oem": 0.15,
        },
    ),
    ELECTRICAL_CABLE: CommodityWeights(
        ELECTRICAL_CABLE, semantic=0.30, lexical=0.15, attributes=0.55,
        attribute_weights={
            "item_type": 0.50, "cores": 1.00, "cross_section_sqmm": 1.00,
            "voltage_grade": 1.00, "conductor_material": 1.00,
            "insulation": 0.60, "armour": 0.40, "oem": 0.10,
        },
    ),
    FASTENER: CommodityWeights(
        FASTENER, semantic=0.30, lexical=0.20, attributes=0.50,
        attribute_weights={
            "item_type": 0.80, "thread_size": 1.00, "length_mm": 0.90,
            "property_class": 1.00, "material": 0.70,
            "finish": 0.30, "standard": 0.30, "oem": 0.10,
        },
    ),
}

_FALLBACK = CommodityWeights("unknown", 0.45, 0.25, 0.30, {})

_cache: dict[str, CommodityWeights] = {}


def seed_defaults() -> None:
    """Insert defaults for any commodity not yet present in the database."""
    from app.db.session import get_conn
    from psycopg.types.json import Jsonb

    with get_conn() as conn:
        for c in COMMODITIES:
            w = DEFAULT_WEIGHTS[c]
            conn.execute(
                """
                INSERT INTO commodity_weights
                    (commodity_type, semantic, lexical, attributes, attribute_weights)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (commodity_type) DO NOTHING
                """,
                (c, w.semantic, w.lexical, w.attributes, Jsonb(w.attribute_weights)),
            )
        conn.commit()
    refresh_cache()


def refresh_cache() -> None:
    from app.db.session import get_conn

    _cache.clear()
    try:
        with get_conn() as conn:
            for row in conn.execute("SELECT * FROM commodity_weights").fetchall():
                _cache[row["commodity_type"]] = CommodityWeights(
                    commodity_type=row["commodity_type"],
                    semantic=row["semantic"],
                    lexical=row["lexical"],
                    attributes=row["attributes"],
                    attribute_weights=dict(row["attribute_weights"] or {}),
                )
    except Exception as exc:  # noqa: BLE001 - fall back to code defaults
        log.warning("Could not load commodity weights, using defaults: %s", exc)


def get_weights(commodity: str | None) -> CommodityWeights:
    if not commodity:
        return _FALLBACK
    if commodity in _cache:
        return _cache[commodity]
    return DEFAULT_WEIGHTS.get(commodity, _FALLBACK)


def set_weights(w: CommodityWeights) -> CommodityWeights:
    from app.db.session import get_conn
    from psycopg.types.json import Jsonb

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO commodity_weights
                (commodity_type, semantic, lexical, attributes, attribute_weights, updated_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (commodity_type) DO UPDATE SET
                semantic = EXCLUDED.semantic,
                lexical = EXCLUDED.lexical,
                attributes = EXCLUDED.attributes,
                attribute_weights = EXCLUDED.attribute_weights,
                updated_at = now()
            """,
            (w.commodity_type, w.semantic, w.lexical, w.attributes, Jsonb(w.attribute_weights)),
        )
        conn.commit()
    refresh_cache()
    return get_weights(w.commodity_type)


def all_weights() -> list[CommodityWeights]:
    if not _cache:
        refresh_cache()
    return [get_weights(c) for c in COMMODITIES]
