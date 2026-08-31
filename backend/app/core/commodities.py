"""Commodity vocabulary and lightweight commodity detection.

The commodity type is load-bearing: it selects the FAISS partition, the
normalization rules, the attribute extractors, the scoring weights and the
safety-critical field list. Getting it wrong is worse than leaving it
UNKNOWN, so detection is conservative and rule-based.
"""
from __future__ import annotations

import re

GATE_VALVE = "gate_valve"
PIPE = "pipe"
BEARING = "bearing"
ELECTRICAL_CABLE = "electrical_cable"
FASTENER = "fastener"
UNKNOWN_COMMODITY = "unknown"

COMMODITIES = [GATE_VALVE, PIPE, BEARING, ELECTRICAL_CABLE, FASTENER]

COMMODITY_LABELS = {
    GATE_VALVE: "Gate Valve",
    PIPE: "Pipe",
    BEARING: "Bearing",
    ELECTRICAL_CABLE: "Electrical Cable",
    FASTENER: "Fastener",
    UNKNOWN_COMMODITY: "Unknown",
}

# UNSPSC segment/class codes used for the standardized identity.
UNSPSC_BY_COMMODITY = {
    GATE_VALVE: "40141607",
    PIPE: "40174300",
    BEARING: "31171500",
    ELECTRICAL_CABLE: "26121600",
    FASTENER: "31161500",
}

# Ordered: the first commodity whose signature matches wins. Valve patterns are
# checked before pipe because "6 IN CS GATE VALVE" contains pipe-like tokens.
_DETECTION_RULES: list[tuple[str, list[str]]] = [
    (
        GATE_VALVE,
        [
            r"\bGATE\s*VALVE\b",
            r"\bGT\s*VLV\b",
            r"\bGATE\s*V/?V\b",
            r"\bVALVE\s*,?\s*GATE\b",
            r"\bGT\s*VALVE\b",
            r"\bGATE\s*VLV\b",
        ],
    ),
    (
        BEARING,
        [
            r"\bBEARING\b",
            r"\bBRG\b",
            r"\bDGBB\b",
            r"\bBALL\s*BRG\b",
            r"\b6[23]\d{2}(-?2RS|-?ZZ)?\b",
            r"\bNU\s?\d{3,4}\b",
            r"\b2[23]\d{3}\b",
        ],
    ),
    (
        ELECTRICAL_CABLE,
        [
            r"\bCABLE\b",
            r"\bCBL\b",
            r"\bXLPE\b",
            r"\bSQ\.?\s?MM\b",
            r"\bCORE\b.*\b(KV|VOLT)\b",
            r"\bARMOU?RED\b",
        ],
    ),
    (
        FASTENER,
        [
            r"\b(HEX|HEXAGON)\s*(HEAD)?\s*(BOLT|SCREW|NUT)\b",
            r"\bBOLT\b",
            r"\bNUT\b",
            r"\bWASHER\b",
            r"\bWSHR\b",
            r"\bSTUD\b",
            r"\bSCREW\b",
            r"\bM\d{1,2}\s*[Xx]\s*\d{2,3}\b",
        ],
    ),
    (
        PIPE,
        [
            r"\bPIPE\b",
            r"\bTUBE\b",
            r"\bSEAMLESS\b",
            r"\bSMLS\b",
            r"\bERW\b",
            r"\bSCH\s?\d{2,3}\b",
            r"\bSCHEDULE\s?\d{2,3}\b",
        ],
    ),
]

_COMPILED = [
    (commodity, [re.compile(p, re.IGNORECASE) for p in pats])
    for commodity, pats in _DETECTION_RULES
]


_PUNCT = re.compile(r"[,;:/\\|()\[\]{}.]+")
_WS = re.compile(r"\s+")

# Fuzzy fallback vocabulary: OCR and typing errors routinely mangle the head
# noun ("GATE VALEV", "BEARlNG"). Only the item-type words are fuzzed, and
# only at edit distance 1, so this cannot pull an unrelated item into a
# commodity.
_FUZZY_TERMS: list[tuple[str, str]] = [
    ("VALVE", GATE_VALVE), ("BEARING", BEARING), ("CABLE", ELECTRICAL_CABLE),
    ("PIPE", PIPE), ("BOLT", FASTENER), ("WASHER", FASTENER), ("SCREW", FASTENER),
]


def _within_edit_distance_1(a: str, b: str) -> bool:
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if a == b:
        return True
    if la == lb:  # one substitution or one transposition
        diffs = [i for i in range(la) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        if len(diffs) == 2 and diffs[1] == diffs[0] + 1:
            i, j = diffs
            return a[i] == b[j] and a[j] == b[i]
        return False
    # one insertion / deletion
    longer, shorter = (a, b) if la > lb else (b, a)
    for i in range(len(longer)):
        if longer[:i] + longer[i + 1:] == shorter:
            return True
    return False


def _fuzzy_detect(cleaned: str) -> str:
    tokens = [t for t in cleaned.split() if len(t) >= 4 and t.isalpha()]
    for token in tokens:
        for term, commodity in _FUZZY_TERMS:
            if _within_edit_distance_1(token, term):
                # A fuzzy "VALVE" only implies a gate valve if GATE is nearby.
                if commodity is GATE_VALVE and "GATE" not in cleaned and not any(
                    _within_edit_distance_1(t, "GATE") for t in tokens
                ):
                    continue
                return commodity
    return UNKNOWN_COMMODITY


def detect_commodity(text: str) -> str:
    """Best-effort commodity classification from free text.

    Returns UNKNOWN_COMMODITY when nothing matches -- callers must treat that
    as "route to review", never as a default commodity.
    """
    if not text:
        return UNKNOWN_COMMODITY

    # ERP descriptions are comma- and slash-delimited ("GATE, VALVE, 6 IN"),
    # so punctuation is flattened before the signature patterns run. "V/V" is
    # resolved first -- flattening its slash would otherwise leave "V V".
    upper = re.sub(r"\bV\s*/\s*V\b", "VALVE", text.upper())
    cleaned = _WS.sub(" ", _PUNCT.sub(" ", upper)).strip()

    for commodity, patterns in _COMPILED:
        for pat in patterns:
            if pat.search(cleaned):
                return commodity

    return _fuzzy_detect(cleaned)


def is_known(commodity: str | None) -> bool:
    return commodity in COMMODITIES
