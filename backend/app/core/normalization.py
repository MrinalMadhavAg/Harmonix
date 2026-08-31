"""Text normalization.

Three deliberately separated concerns:

  A. SAFE DIMENSIONAL NORMALIZATION -- only where the equivalence is
     genuinely deterministic *for that commodity*.
  B. STANDARD EQUIVALENCE -- e.g. PN20 vs CL150. NOT applied to the text.
     Kept in `standards.py` as a soft scoring feature.
  C. ABBREVIATION EXPANSION -- whole-word only.

The hazard this module exists to prevent: a generic `(\\d+)\\s*MM` rule that
rewrites dimensions into commodity-specific terminology. `150MM` means
nominal bore DN150 on a gate valve, a 150 mm bore on a bearing, and nothing
of the sort on a cable (where MM appears as SQ MM cross-section). A single
global rule corrupts meaning. See tests/test_normalization.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.commodities import (
    BEARING,
    ELECTRICAL_CABLE,
    FASTENER,
    GATE_VALVE,
    PIPE,
)

# --------------------------------------------------------------------------
# A. Dimensional canonicalization
# --------------------------------------------------------------------------

# NPS (inch) <-> DN (mm) nominal pipe sizes. This is a fixed standards table,
# not an approximation: DN150 *is* the designation for NPS 6.
NPS_TO_DN: dict[str, int] = {
    "0.125": 6, "0.25": 8, "0.375": 10, "0.5": 15, "0.75": 20,
    "1": 25, "1.25": 32, "1.5": 40, "2": 50, "2.5": 65,
    "3": 80, "3.5": 90, "4": 100, "5": 125, "6": 150,
    "8": 200, "10": 250, "12": 300, "14": 350, "16": 400,
    "18": 450, "20": 500, "22": 550, "24": 600, "28": 700,
    "30": 750, "32": 800, "36": 900, "40": 1000, "48": 1200,
}
# Fractional inch spellings seen in real ERP descriptions.
_FRACTIONS = {
    "1/8": "0.125", "1/4": "0.25", "3/8": "0.375", "1/2": "0.5",
    "3/4": "0.75", "1-1/4": "1.25", "1 1/4": "1.25", "1-1/2": "1.5",
    "1 1/2": "1.5", "2-1/2": "2.5", "2 1/2": "2.5", "3-1/2": "3.5",
}
VALID_DN = set(NPS_TO_DN.values())

# Only these commodities have a nominal-bore concept where inch/mm/DN are
# interchangeable designations of the same thing.
_DN_COMMODITIES = {GATE_VALVE, PIPE}


def _inch_to_dn(value: str) -> int | None:
    key = _FRACTIONS.get(value.strip(), value.strip())
    # Normalize "6.0" -> "6"
    try:
        f = float(key)
    except ValueError:
        return None
    key = str(int(f)) if f == int(f) else str(f)
    return NPS_TO_DN.get(key)


_INCH_PAT = re.compile(
    r"(?<![\w.])(\d+(?:[-\s]\d/\d)?(?:\.\d+)?|\d/\d)\s*(?:\"|''|INCH(?:ES)?|IN\b)",
    re.IGNORECASE,
)
_MM_PAT = re.compile(r"(?<![\w.])(\d{1,4})(?:\.0)?\s*MM\b", re.IGNORECASE)
# "150 NB" is a millimetre nominal-bore designation, not an inch one. Handled
# separately so it is never run through the inch->DN table.
_NB_PAT = re.compile(r"(?<![\w.])(\d{1,4})\s*(?:NB|NOMINAL\s+BORE)\b", re.IGNORECASE)
_DN_PAT = re.compile(r"\bDN\s*(\d{1,4})\b", re.IGNORECASE)


def canonicalize_dimensions(text: str, commodity: str | None) -> tuple[str, list[str]]:
    """Rewrite nominal-size notation to a single canonical DN token.

    Applied ONLY for commodities where inch/mm/DN genuinely denote the same
    nominal size. For every other commodity the text is returned untouched --
    a bearing's `25 MM` bore must never become `DN25`.
    """
    trace: list[str] = []
    if commodity not in _DN_COMMODITIES:
        return text, trace

    def _sub_inch(m: re.Match[str]) -> str:
        dn = _inch_to_dn(m.group(1))
        if dn is None:
            return m.group(0)
        trace.append(f"dim:inch:{m.group(0).strip()}->DN{dn}")
        return f"DN{dn}"

    def _sub_mm(m: re.Match[str]) -> str:
        val = int(m.group(1))
        # Only convert values that are actually nominal DN sizes. `SCH 40` or a
        # random `12 MM` on a valve body stays as written.
        if val not in VALID_DN:
            return m.group(0)
        trace.append(f"dim:mm:{m.group(0).strip()}->DN{val}")
        return f"DN{val}"

    def _sub_nb(m: re.Match[str]) -> str:
        val = int(m.group(1))
        if val not in VALID_DN:
            return m.group(0)
        trace.append(f"dim:nb:{m.group(0).strip()}->DN{val}")
        return f"DN{val}"

    def _sub_dn(m: re.Match[str]) -> str:
        return f"DN{int(m.group(1))}"

    out = _NB_PAT.sub(_sub_nb, text)
    out = _INCH_PAT.sub(_sub_inch, out)
    out = _MM_PAT.sub(_sub_mm, out)
    out = _DN_PAT.sub(_sub_dn, out)
    return out, trace


# --------------------------------------------------------------------------
# C. Abbreviation expansion (whole-word only)
# --------------------------------------------------------------------------

# NOTE: material *grades* (SS316, A106) are intentionally absent. Expanding
# them here would destroy the grade distinctions the safety layer depends on;
# grade handling lives in attributes.py.
ABBREVIATIONS: dict[str, str] = {
    "VLV": "VALVE", "VV": "VALVE", "V/V": "VALVE",
    "GT": "GATE", "GLB": "GLOBE", "CHK": "CHECK", "BFLY": "BUTTERFLY",
    "BALLV": "BALL VALVE",
    "SS": "STAINLESS STEEL", "STL": "STEEL", "CS": "CARBON STEEL",
    "MS": "MILD STEEL", "GI": "GALVANIZED IRON", "DI": "DUCTILE IRON",
    "CI": "CAST IRON", "CU": "COPPER", "ALU": "ALUMINIUM",
    "ALUM": "ALUMINIUM", "ALUMINUM": "ALUMINIUM",
    "FLGD": "FLANGED", "FLG": "FLANGE", "FLNG": "FLANGE",
    "SCRD": "SCREWED", "THRD": "THREADED", "THD": "THREADED",
    "BW": "BUTT WELD", "SW": "SOCKET WELD", "RF": "RAISED FACE",
    "SMLS": "SEAMLESS", "ERW": "ELECTRIC RESISTANCE WELDED",
    "BRG": "BEARING", "BB": "BALL BEARING",
    "DGBB": "DEEP GROOVE BALL BEARING", "SPH": "SPHERICAL",
    "CYL": "CYLINDRICAL", "RLR": "ROLLER",
    "CBL": "CABLE", "CDR": "CONDUCTOR", "COND": "CONDUCTOR",
    "ARMD": "ARMOURED", "ARM": "ARMOURED", "ARMORED": "ARMOURED",
    "UNARMD": "UNARMOURED", "UNARMORED": "UNARMOURED",
    "C": "CORE",  # only in cable context; guarded below
    "AL": "ALUMINIUM",  # cable context only
    "HEX": "HEXAGON", "HD": "HEAD", "SCR": "SCREW", "BLT": "BOLT",
    "WSHR": "WASHER", "PLTD": "PLATED", "ZN": "ZINC",
    "GALV": "GALVANIZED", "HDG": "HOT DIP GALVANIZED",
    "SCH": "SCHEDULE", "GR": "GRADE", "MTL": "MATERIAL",
    "ASSY": "ASSEMBLY", "QTY": "QUANTITY",
    "PRESS": "PRESSURE", "TEMP": "TEMPERATURE",
    "NOM": "NOMINAL", "DIA": "DIAMETER",
}

# Expansions that only make sense inside a specific commodity.
_COMMODITY_SCOPED = {
    "C": {ELECTRICAL_CABLE},
    "AL": {ELECTRICAL_CABLE},
    "CDR": {ELECTRICAL_CABLE},
    "COND": {ELECTRICAL_CABLE},
    "RLR": {BEARING},
    "SPH": {BEARING},
    "CYL": {BEARING},
    "HD": {FASTENER},
    "SCR": {FASTENER},
    "BLT": {FASTENER},
}

# Longest-first so multi-char keys win before their prefixes.
_ABBREV_PAT = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(ABBREVIATIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def expand_abbreviations(text: str, commodity: str | None) -> tuple[str, list[str]]:
    trace: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        key = m.group(1).upper()
        scope = _COMMODITY_SCOPED.get(key)
        if scope is not None and commodity not in scope:
            return m.group(0)
        expansion = ABBREVIATIONS[key]
        trace.append(f"abbrev:{key}->{expansion}")
        return expansion

    return _ABBREV_PAT.sub(_sub, text), trace


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

# Fractional inch sizes must be resolved BEFORE punctuation is flattened:
# stripping the slash first turns `1/2"` into `1 2"`, which then reads as a
# 2 inch (DN50) size. Only fractions immediately followed by an inch marker
# are touched, so unrelated slashes are unaffected.
_FRACTION_INCH_PAT = re.compile(
    r"(?<![\d.])(?:(\d+)[-\s]+)?(\d)\s*/\s*(\d)(?=\s*(?:\"|''|INCH(?:ES)?|IN\b))",
    re.IGNORECASE,
)

_PUNCT_TO_SPACE = re.compile(r"[,;:/\\|()\[\]{}]+")
_WS = re.compile(r"\s+")
_UNICODE_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "″": '"', "′": "'"})


@dataclass
class NormalizationResult:
    text: str
    trace: list[str] = field(default_factory=list)


def normalize(raw: str, commodity: str | None = None) -> NormalizationResult:
    """Produce the canonical description used for indexing and matching."""
    if raw is None:
        return NormalizationResult(text="", trace=[])

    trace: list[str] = []
    text = raw.translate(_UNICODE_QUOTES).upper().strip()

    # Slashes separate fields in ERP text ("GATE V/V" is handled by the
    # abbreviation table via the V/V key before this runs), so protect it.
    text = re.sub(r"\bV\s*/\s*V\b", "VALVE", text)

    def _fraction(m: re.Match[str]) -> str:
        whole = int(m.group(1)) if m.group(1) else 0
        num, den = int(m.group(2)), int(m.group(3))
        if den == 0:
            return m.group(0)
        value = whole + num / den
        trace.append(f"fraction:{m.group(0).strip()}->{value:g}")
        return f"{value:g}"

    text = _FRACTION_INCH_PAT.sub(_fraction, text)

    text = _PUNCT_TO_SPACE.sub(" ", text)
    text = _WS.sub(" ", text).strip()

    text, t1 = canonicalize_dimensions(text, commodity)
    trace.extend(t1)

    text, t2 = expand_abbreviations(text, commodity)
    trace.extend(t2)

    # Collapse the double spaces that expansions introduce.
    text = _WS.sub(" ", text).strip()
    return NormalizationResult(text=text, trace=trace)


def normalize_text(raw: str, commodity: str | None = None) -> str:
    return normalize(raw, commodity).text


def tokenize(text: str) -> list[str]:
    """Tokenizer shared by BM25 indexing and query time."""
    return [t for t in re.split(r"[^A-Z0-9.\-#]+", text.upper()) if t]
