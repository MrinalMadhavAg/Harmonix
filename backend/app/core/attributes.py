"""Deterministic, commodity-scoped attribute extraction.

Every extracted attribute carries provenance:

    {"value": ..., "source": <substring that produced it>,
     "method": "rule" | "derived" | "llm", "confidence": float}

A bare ``{"material": "SS316"}`` is never produced -- without provenance an
attribute cannot be defended to a procurement officer, and the whole point
of this system is that its decisions are defensible.

Extraction is rule-based and runs with no external service. An LLM extractor
may be plugged in behind ``LLMExtractor`` but the demo never depends on it.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Protocol

from app.core.commodities import (
    BEARING,
    ELECTRICAL_CABLE,
    FASTENER,
    GATE_VALVE,
    PIPE,
)

Attribute = dict[str, Any]
Attributes = dict[str, Attribute]


def attr(value: Any, source: str, method: str = "rule", confidence: float = 0.99) -> Attribute:
    return {
        "value": value,
        "source": source.strip(),
        "method": method,
        "confidence": round(float(confidence), 4),
    }


def value_of(attributes: Attributes | None, key: str) -> Any | None:
    """Read an attribute value, tolerating legacy bare-value shapes."""
    if not attributes:
        return None
    a = attributes.get(key)
    if a is None:
        return None
    if isinstance(a, dict):
        return a.get("value")
    return a


# ==========================================================================
# Material grades -- the highest-risk extraction in the system.
# ==========================================================================
#
# Ordering is significant and the patterns are mutually exclusive by
# construction: `316` carries a negative lookahead for a trailing `L` so that
# SS316L can never be read as SS316. 316 and 316L are different alloys with
# different weldability and corrosion behaviour; collapsing them is exactly
# the class of error this project exists to prevent.

_MATERIAL_RULES: list[tuple[str, str]] = [
    # The `L` suffix is matched as `\s?L\b`: it may be written 316L or 316 L,
    # but "SS316 LONG PATTERN" is not an L grade. Correspondingly the plain
    # grades carry `(?!\s?L\b)` -- a guard of `(?!\s*L)` would reject SS316
    # whenever any word starting with L happened to follow it.
    ("STAINLESS STEEL 316L", r"\b(?:SS|AISI|ASTM|UNS|TYPE|GRADE|STAINLESS\s+STEEL)?[\s\-]*316\s?L\b"),
    ("STAINLESS STEEL 316L", r"\bS31603\b|\bF316L\b|\bCF3M\b"),
    ("STAINLESS STEEL 316", r"\b(?:SS|AISI|ASTM|UNS|TYPE|GRADE|STAINLESS\s+STEEL)[\s\-]*316\b(?!\s?L\b)"),
    ("STAINLESS STEEL 316", r"\bS31600\b|\bF316\b(?!L)|\bCF8M\b"),
    ("STAINLESS STEEL 304L", r"\b(?:SS|AISI|ASTM|UNS|TYPE|GRADE|STAINLESS\s+STEEL)?[\s\-]*304\s?L\b"),
    ("STAINLESS STEEL 304L", r"\bS30403\b|\bF304L\b|\bCF3\b"),
    ("STAINLESS STEEL 304", r"\b(?:SS|AISI|ASTM|UNS|TYPE|GRADE|STAINLESS\s+STEEL)[\s\-]*304\b(?!\s?L\b)"),
    ("STAINLESS STEEL 304", r"\bS30400\b|\bF304\b(?!L)|\bCF8\b"),
    ("STAINLESS STEEL 321", r"\b(?:SS|AISI|TYPE)?[\s\-]*321\b"),
    ("DUPLEX STAINLESS STEEL 2205", r"\b2205\b|\bS31803\b|\bS32205\b"),
    ("ALLOY STEEL A182 F11", r"\bF11\b|\bA182\s*F11\b"),
    ("ALLOY STEEL A182 F22", r"\bF22\b|\bA182\s*F22\b"),
    ("ALLOY STEEL A193 B7", r"\bA193\s*(?:GRADE\s*)?B7\b|\bB7\b"),
    ("CARBON STEEL", r"\bCARBON\s+STEEL\b|\bA216\s*(?:GRADE\s*)?WCB\b|\bWCB\b|\bA105\b|\bA106\b|\bA53\b|\bASTM\s*A106\b"),
    ("CAST IRON", r"\bCAST\s+IRON\b"),
    ("DUCTILE IRON", r"\bDUCTILE\s+IRON\b|\bSG\s+IRON\b"),
    ("GALVANIZED IRON", r"\bGALVANIZED\s+IRON\b"),
    ("MILD STEEL", r"\bMILD\s+STEEL\b"),
    ("BRONZE", r"\bBRONZE\b|\bGUNMETAL\b"),
    ("BRASS", r"\bBRASS\b"),
    ("ALUMINIUM", r"\bALUMINIUM\b"),
    ("COPPER", r"\bCOPPER\b"),
    # Bare `STAINLESS STEEL` with no grade -- deliberately last and lower
    # confidence, because an ungraded stainless claim is weak evidence.
    ("STAINLESS STEEL", r"\bSTAINLESS\s+STEEL\b"),
]
_MATERIAL_COMPILED = [(name, re.compile(p, re.IGNORECASE)) for name, p in _MATERIAL_RULES]


def extract_material(text: str) -> Attribute | None:
    for name, pat in _MATERIAL_COMPILED:
        m = pat.search(text)
        if m:
            # An ungraded stainless mention is genuinely less informative.
            conf = 0.70 if name == "STAINLESS STEEL" else 0.98
            return attr(name, m.group(0), "rule", conf)
    return None


# ==========================================================================
# Shared extractors
# ==========================================================================

_DN_PAT = re.compile(r"\bDN\s*(\d{1,4})\b", re.IGNORECASE)
_OEM_NAMES = [
    "KSB", "AUDCO", "LEADER", "BDK", "IVC", "FOURESS", "MICROFINISH",
    "SKF", "FAG", "NTN", "NSK", "TIMKEN", "KOYO", "SCHAEFFLER",
    "POLYCAB", "HAVELLS", "KEI", "FINOLEX", "RR KABEL", "GLOSTER",
    "JINDAL", "TATA", "MAHARASHTRA SEAMLESS", "ISMT",
    "UNBRAKO", "SUNDRAM", "TVS", "APL APOLLO",
]
_OEM_PAT = re.compile(r"\b(" + "|".join(re.escape(n) for n in _OEM_NAMES) + r")\b", re.IGNORECASE)
_OEM_PARTNO_PAT = re.compile(r"\b(?:PN|P/N|PART|OEM|MAKE)[\s:#-]*([A-Z0-9][A-Z0-9\-/]{3,})\b", re.IGNORECASE)


def _extract_oem(text: str) -> Attribute | None:
    m = _OEM_PAT.search(text)
    if m:
        return attr(m.group(1).upper(), m.group(0), "rule", 0.95)
    m = _OEM_PARTNO_PAT.search(text)
    if m:
        return attr(m.group(1).upper(), m.group(0), "rule", 0.70)
    return None


def _extract_dn(text: str) -> Attribute | None:
    m = _DN_PAT.search(text)
    if m:
        return attr(f"DN{int(m.group(1))}", m.group(0), "rule", 0.98)
    return None


# ==========================================================================
# Gate valve
# ==========================================================================

# Class markers must be explicit. A bare `150` is ambiguous (it could be the
# nominal bore) so it is never read as a pressure class.
_CLASS_PAT = re.compile(
    r"\b(?:CL|CLASS|ANSI|ASME)\s*[#]?\s*(150|300|400|600|800|900|1500|2500)\b"
    r"|\b(150|300|400|600|800|900|1500|2500)\s*#"
    r"|#\s*(150|300|400|600|800|900|1500|2500)\b",
    re.IGNORECASE,
)
_PN_PAT = re.compile(r"\bPN\s*(\d{1,3})\b", re.IGNORECASE)
_END_PAT = re.compile(
    r"\b(FLANGED|FLANGE|BUTT\s+WELD|SOCKET\s+WELD|SCREWED|THREADED|WAFER|LUG)\b",
    re.IGNORECASE,
)
_VALVE_STD_PAT = re.compile(
    r"\b(API\s*6D|API\s*600|API\s*602|BS\s*1868|BS\s*5352|IS\s*14846|ASME\s*B16\.34)\b",
    re.IGNORECASE,
)


def _extract_pressure_class(text: str) -> Attribute | None:
    m = _CLASS_PAT.search(text)
    if m:
        val = next(g for g in m.groups() if g)
        return attr(f"CL{val}", m.group(0), "rule", 0.98)
    m = _PN_PAT.search(text)
    if m:
        # Kept as PN -- NOT rewritten to a CL equivalent. standards.py scores
        # the cross-notation relationship as a soft feature.
        return attr(f"PN{int(m.group(1))}", m.group(0), "rule", 0.95)
    return None


def extract_gate_valve(text: str) -> Attributes:
    out: Attributes = {"item_type": attr("GATE VALVE", "gate valve", "rule", 0.99)}
    if (a := _extract_dn(text)) is not None:
        out["size"] = a
    if (a := extract_material(text)) is not None:
        out["material"] = a
    if (a := _extract_pressure_class(text)) is not None:
        out["pressure_class"] = a
    if (m := _END_PAT.search(text)) is not None:
        val = m.group(1).upper().replace("FLANGE", "FLANGED").replace("FLANGEDD", "FLANGED")
        out["end_connection"] = attr(val, m.group(0), "rule", 0.92)
    if (m := _VALVE_STD_PAT.search(text)) is not None:
        out["standard"] = attr(re.sub(r"\s+", " ", m.group(1).upper()), m.group(0), "rule", 0.95)
    if (a := _extract_oem(text)) is not None:
        out["oem"] = a
    return out


# ==========================================================================
# Pipe
# ==========================================================================

_SCHEDULE_PAT = re.compile(
    r"\b(?:SCHEDULE|SCH)\s*[.:#]?\s*(5S|10S|40S|80S|5|10|20|30|40|60|80|100|120|140|160)\b"
    r"|\b(XXS|XS|STD)\b",
    re.IGNORECASE,
)
_PIPE_STD_PAT = re.compile(
    r"\b(ASTM\s*A106\s*(?:GRADE\s*|GR\s*)?[AB]?|ASTM\s*A53|API\s*5L|IS\s*1239|IS\s*3589|ASTM\s*A312)\b",
    re.IGNORECASE,
)
_PIPE_TYPE_PAT = re.compile(r"\b(SEAMLESS|ELECTRIC RESISTANCE WELDED|WELDED|SPIRAL)\b", re.IGNORECASE)


def extract_pipe(text: str) -> Attributes:
    out: Attributes = {"item_type": attr("PIPE", "pipe", "rule", 0.99)}
    if (a := _extract_dn(text)) is not None:
        out["size"] = a
    if (a := extract_material(text)) is not None:
        out["material"] = a
    if (m := _SCHEDULE_PAT.search(text)) is not None:
        val = next(g for g in m.groups() if g).upper()
        out["schedule"] = attr(val if val in ("XXS", "XS", "STD") else f"SCH{val}", m.group(0), "rule", 0.97)
    if (m := _PIPE_STD_PAT.search(text)) is not None:
        out["standard"] = attr(re.sub(r"\s+", " ", m.group(1).upper()), m.group(0), "rule", 0.95)
    if (m := _PIPE_TYPE_PAT.search(text)) is not None:
        out["manufacture"] = attr(m.group(1).upper(), m.group(0), "rule", 0.90)
    if (a := _extract_oem(text)) is not None:
        out["oem"] = a
    return out


# ==========================================================================
# Bearing
# ==========================================================================

_BRG_DESIG_PAT = re.compile(
    r"\b(N[UJ]\s?\d{3,4}|\d{4,5})\s*[-]?\s*(2RS1|2RS|2Z|ZZ|RS|C3|C4)?\b",
    re.IGNORECASE,
)
_BRG_TYPE_PAT = re.compile(
    r"\b(DEEP GROOVE BALL BEARING|SPHERICAL ROLLER BEARING|CYLINDRICAL ROLLER BEARING|"
    r"TAPER(?:ED)? ROLLER BEARING|ANGULAR CONTACT BALL BEARING|BALL BEARING|ROLLER BEARING|BEARING)\b",
    re.IGNORECASE,
)
# Both orderings occur in real ERP text ("BORE 25 MM" and "25MM BORE"). The
# value-first form is checked first: it is unambiguous, whereas the
# keyword-first form can be captured by a following measurement --
# in "25MM BORE 52MM OD" a keyword-first match reads BORE as 52.
_BORE_VALUE_FIRST = re.compile(
    r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*MM\s*(?:BORE|INSIDE\s+DIAMETER|ID)\b", re.IGNORECASE
)
_BORE_KEY_FIRST = re.compile(
    r"\b(?:BORE|INSIDE\s+DIAMETER|ID)\s*[:=]?\s*(\d{1,3}(?:\.\d+)?)\s*MM\b", re.IGNORECASE
)
_OD_VALUE_FIRST = re.compile(
    r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*MM\s*(?:OUTSIDE\s+DIAMETER|OD)\b", re.IGNORECASE
)
_OD_KEY_FIRST = re.compile(
    r"\b(?:OUTSIDE\s+DIAMETER|OD)\s*[:=]?\s*(\d{1,3}(?:\.\d+)?)\s*MM\b", re.IGNORECASE
)
_WIDTH_VALUE_FIRST = re.compile(
    r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*MM\s*(?:WIDTH|W)\b", re.IGNORECASE
)
_WIDTH_KEY_FIRST = re.compile(
    r"\b(?:WIDTH|W)\s*[:=]?\s*(\d{1,3}(?:\.\d+)?)\s*MM\b", re.IGNORECASE
)


_ANY_VALUE_FIRST = re.compile(
    r"(?<![\d.])\d{1,3}(?:\.\d+)?\s*MM\s*(?:BORE|INSIDE\s+DIAMETER|ID|OUTSIDE\s+DIAMETER|OD|WIDTH|W)\b",
    re.IGNORECASE,
)
_ANY_KEY_FIRST = re.compile(
    r"\b(?:BORE|INSIDE\s+DIAMETER|ID|OUTSIDE\s+DIAMETER|OD|WIDTH|W)\s*[:=]?\s*\d{1,3}(?:\.\d+)?\s*MM\b",
    re.IGNORECASE,
)


def _measurement_orientation(text: str) -> str | None:
    """Decide once whether this description writes "BORE 25MM" or "25MM BORE".

    A single description uses one convention throughout, but the two forms
    overlap: in "ID 25MM OD 52MM" a value-first reading finds "25MM OD" and
    reports the bore as the outer diameter. Counting which orientation
    explains more of the string resolves it, instead of letting whichever
    pattern is tried first win.
    """
    value_first = len(_ANY_VALUE_FIRST.findall(text))
    key_first = len(_ANY_KEY_FIRST.findall(text))
    if value_first == 0 and key_first == 0:
        return None
    return "value_first" if value_first > key_first else "key_first"


def _measure(
    text: str,
    orientation: str | None,
    value_first: re.Pattern[str],
    key_first: re.Pattern[str],
) -> re.Match[str] | None:
    """Read one measurement using the description's established convention.

    Once the orientation is known there is deliberately NO fallback to the
    other form. Truncated text such as "BORE 25 MM OD 52" (the unit lost) would
    otherwise fall back and match "25 MM OD", reporting the bore as the outer
    diameter. Returning nothing -- UNKNOWN -- is the correct answer there.
    """
    if orientation == "value_first":
        return value_first.search(text)
    if orientation == "key_first":
        return key_first.search(text)
    return value_first.search(text) or key_first.search(text)
_SEAL_PAT = re.compile(r"\b(2RS1|2RS|2Z|ZZ|RS|OPEN|SEALED|SHIELDED)\b", re.IGNORECASE)

# ISO 15 bore code: for designations ending 04 and above the bore is the last
# two digits x 5 mm; 00/01/02/03 are special-cased. A genuine standard, so the
# derivation is recorded with method="derived".
_ISO_BORE_SPECIAL = {"00": 10, "01": 12, "02": 15, "03": 17}


def _bore_from_designation(desig: str) -> int | None:
    core = re.sub(r"[^0-9]", "", desig)
    if len(core) < 3:
        return None
    last2 = core[-2:]
    if last2 in _ISO_BORE_SPECIAL:
        return _ISO_BORE_SPECIAL[last2]
    try:
        n = int(last2)
    except ValueError:
        return None
    if n < 4:
        return None
    return n * 5


def extract_bearing(text: str) -> Attributes:
    out: Attributes = {}
    if (m := _BRG_TYPE_PAT.search(text)) is not None:
        out["item_type"] = attr(m.group(1).upper(), m.group(0), "rule", 0.95)
    else:
        out["item_type"] = attr("BEARING", "bearing", "rule", 0.60)

    desig: str | None = None
    for m in _BRG_DESIG_PAT.finditer(text):
        cand = m.group(1).strip()
        digits = re.sub(r"[^0-9]", "", cand)
        if len(digits) >= 4 or cand.upper().startswith(("NU", "NJ")):
            desig = re.sub(r"\s+", "", cand.upper())
            out["designation"] = attr(desig, m.group(0), "rule", 0.96)
            break

    orientation = _measurement_orientation(text)

    if (m := _measure(text, orientation, _BORE_VALUE_FIRST, _BORE_KEY_FIRST)) is not None:
        out["bore_mm"] = attr(float(m.group(1)), m.group(0), "rule", 0.98)
    elif desig:
        # The ISO bore code is the last two digits for every metric series,
        # including the NU/NJ cylindrical roller families.
        b = _bore_from_designation(desig)
        if b is not None:
            out["bore_mm"] = attr(
                float(b), f"designation {desig}", "derived", 0.90
            )

    if (m := _measure(text, orientation, _OD_VALUE_FIRST, _OD_KEY_FIRST)) is not None:
        out["outer_diameter_mm"] = attr(float(m.group(1)), m.group(0), "rule", 0.97)
    if (m := _measure(text, orientation, _WIDTH_VALUE_FIRST, _WIDTH_KEY_FIRST)) is not None:
        out["width_mm"] = attr(float(m.group(1)), m.group(0), "rule", 0.95)
    if (m := _SEAL_PAT.search(text)) is not None:
        raw = m.group(1).upper()
        canon = {"2RS1": "2RS", "RS": "2RS", "Z": "ZZ", "2Z": "ZZ", "SEALED": "2RS", "SHIELDED": "ZZ"}.get(raw, raw)
        out["seal_type"] = attr(canon, m.group(0), "rule", 0.88)
    elif desig:
        # ISO designation convention: a bearing number carrying no closure
        # suffix denotes the open variant (6205 is open; 6205-2RS is sealed).
        # Recorded as "derived" so a reviewer can see this was inferred from
        # the designation rather than read from the description.
        out["seal_type"] = attr("OPEN", f"designation {desig} (no closure suffix)", "derived", 0.85)
    if (a := _extract_oem(text)) is not None:
        out["oem"] = a
    return out


# ==========================================================================
# Electrical cable
# ==========================================================================

# Trailing lookahead rather than \b so "3CX95" (no separators, common in ERP
# text) still yields 3 cores.
_CORES_PAT = re.compile(r"\b(\d{1,2})\s*(?:CORES|CORE|CX|C)(?![A-Z])", re.IGNORECASE)
# `(?<![\d.])` rather than `\b`: in "2CX2.5 MM2" there is no word boundary
# before the 2, and a `\b` anchor would skip forward and capture "5 MM2".
_SQMM_PAT = re.compile(
    r"(?<![\d.])(\d{1,4}(?:\.\d+)?)\s*(?:SQ\.?\s*MM|SQMM|MM2|MM\^2|SQUARE\s*MM)\b",
    re.IGNORECASE,
)
# Combined "<cores>C x <area> sq mm" form, resolved in one shot so the two
# numbers cannot be attributed to the wrong field.
_CORES_X_CS_PAT = re.compile(
    r"(?<![\d.])(\d{1,2})\s*(?:CORES|CORE|C)\s*[X*]\s*(\d{1,4}(?:\.\d+)?)"
    r"\s*(?:SQ\.?\s*MM|SQMM|MM2|MM\^2|SQUARE\s*MM)\b",
    re.IGNORECASE,
)
_KV_PAT = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*KV\b", re.IGNORECASE)
_VOLT_PAT = re.compile(r"(?<![\d.])(\d{3,5})\s*(?:V|VOLTS?)\b", re.IGNORECASE)

# Standard Indian LV/MV cable voltage grades, in kV. A value derived from a
# volts figure is accepted only if it lands on one of these; OCR damage such
# as "650/11100 V" would otherwise yield a confident but fictional "11.1KV".
_STANDARD_KV_GRADES = (0.65, 1.1, 3.3, 6.6, 11.0, 22.0, 33.0, 66.0, 132.0)
_INSULATION_PAT = re.compile(r"\b(XLPE|PVC|EPR|RUBBER|FRLS)\b", re.IGNORECASE)
_ARMOUR_PAT = re.compile(r"\b(UNARMOURED|ARMOURED)\b", re.IGNORECASE)
_COND_MAT_PAT = re.compile(r"\b(ALUMINIUM|COPPER)\b", re.IGNORECASE)


# "650/1100 V" is the standard LT designation for a 1.1 kV grade cable. Matched
# before the generic volt pattern, which would otherwise read the 650 and
# report a 0.65 kV grade.
_LT_GRADE_PAT = re.compile(r"\b650\s*[/\s]\s*1100\s*(?:V|VOLTS?)?\b", re.IGNORECASE)


def _canonical_voltage(text: str) -> Attribute | None:
    if (m := _LT_GRADE_PAT.search(text)) is not None:
        return attr("1.1KV", m.group(0), "derived", 0.95)
    if (m := _KV_PAT.search(text)) is not None:
        v = float(m.group(1))
        val = f"{v:g}KV"
        return attr(val, m.group(0), "rule", 0.98)
    if (m := _VOLT_PAT.search(text)) is not None:
        volts = int(m.group(1))
        # 1100 V and 650/1100 V are the standard LT designations for 1.1 kV.
        kv = volts / 1000.0
        if any(abs(kv - g) < 0.01 for g in _STANDARD_KV_GRADES):
            return attr(f"{kv:g}KV", m.group(0), "derived", 0.92)
        # Not a real grade -- most likely corrupted text. Reporting nothing
        # (UNKNOWN, routed to review) is safer than reporting a fiction.
        return None
    return None


def extract_cable(text: str) -> Attributes:
    out: Attributes = {"item_type": attr("CABLE", "cable", "rule", 0.95)}

    if (m := _CORES_X_CS_PAT.search(text)) is not None:
        out["cores"] = attr(int(m.group(1)), m.group(0), "rule", 0.96)
        out["cross_section_sqmm"] = attr(float(m.group(2)), m.group(0), "rule", 0.96)
    else:
        if (m := _CORES_PAT.search(text)) is not None:
            out["cores"] = attr(int(m.group(1)), m.group(0), "rule", 0.95)
        if (m := _SQMM_PAT.search(text)) is not None:
            out["cross_section_sqmm"] = attr(float(m.group(1)), m.group(0), "rule", 0.97)
    if (a := _canonical_voltage(text)) is not None:
        out["voltage_grade"] = a
    if (m := _COND_MAT_PAT.search(text)) is not None:
        out["conductor_material"] = attr(m.group(1).upper(), m.group(0), "rule", 0.95)
    if (m := _INSULATION_PAT.search(text)) is not None:
        out["insulation"] = attr(m.group(1).upper(), m.group(0), "rule", 0.95)
    if (m := _ARMOUR_PAT.search(text)) is not None:
        out["armour"] = attr(m.group(1).upper(), m.group(0), "rule", 0.93)
    if (a := _extract_oem(text)) is not None:
        out["oem"] = a
    return out


# ==========================================================================
# Fastener
# ==========================================================================

_THREAD_PAT = re.compile(r"\bM\s?(\d{1,2})(?:\s*[X*]\s*(\d{1,3}(?:\.\d+)?))?\b")
_LENGTH_PAT = re.compile(r"\b(?:LENGTH|LG|L)\s*[:=]?\s*(\d{1,4})\s*MM\b", re.IGNORECASE)
_PROP_CLASS_PAT = re.compile(r"\b(?:GRADE|CLASS|PROPERTY\s*CLASS)?\s*(4\.6|5\.6|5\.8|8\.8|10\.9|12\.9)\b", re.IGNORECASE)
_SS_FASTENER_PAT = re.compile(r"\b(A2-?70|A4-?80|A2|A4)\b", re.IGNORECASE)
_FINISH_PAT = re.compile(
    r"\b(HOT DIP GALVANIZED|GALVANIZED|ZINC PLATED|ZINC|PLAIN|BLACK|PTFE COATED)\b", re.IGNORECASE
)
_FASTENER_TYPE_PAT = re.compile(
    r"\b(HEXAGON HEAD BOLT|HEX HEAD BOLT|HEXAGON BOLT|HEXAGON NUT|HEX NUT|"
    r"STUD BOLT|STUD|BOLT|NUT|WASHER|SCREW)\b",
    re.IGNORECASE,
)
_FASTENER_STD_PAT = re.compile(
    r"\b(IS\s*1364|IS\s*1367|ASTM\s*A193\s*(?:GRADE\s*|GR\s*)?B7|ASTM\s*A194|DIN\s*931|DIN\s*933|ISO\s*4014)\b",
    re.IGNORECASE,
)


def extract_fastener(text: str) -> Attributes:
    out: Attributes = {}
    if (m := _FASTENER_TYPE_PAT.search(text)) is not None:
        raw = re.sub(r"\s+", " ", m.group(1).upper())
        canon = {
            "HEX HEAD BOLT": "HEXAGON HEAD BOLT",
            "HEXAGON BOLT": "HEXAGON HEAD BOLT",
            "HEX NUT": "HEXAGON NUT",
        }.get(raw, raw)
        out["item_type"] = attr(canon, m.group(0), "rule", 0.95)

    if (m := _THREAD_PAT.search(text)) is not None:
        out["thread_size"] = attr(f"M{int(m.group(1))}", m.group(0), "rule", 0.97)
        if m.group(2):
            out["length_mm"] = attr(float(m.group(2)), m.group(0), "rule", 0.95)
    if "length_mm" not in out and (m := _LENGTH_PAT.search(text)) is not None:
        out["length_mm"] = attr(float(m.group(1)), m.group(0), "rule", 0.95)

    if (m := _SS_FASTENER_PAT.search(text)) is not None:
        val = m.group(1).upper().replace("A270", "A2-70").replace("A480", "A4-80")
        out["property_class"] = attr(val, m.group(0), "rule", 0.95)
    elif (m := _PROP_CLASS_PAT.search(text)) is not None:
        out["property_class"] = attr(m.group(1), m.group(0), "rule", 0.96)

    if (a := extract_material(text)) is not None:
        out["material"] = a
    if (m := _FINISH_PAT.search(text)) is not None:
        out["finish"] = attr(re.sub(r"\s+", " ", m.group(1).upper()), m.group(0), "rule", 0.90)
    if (m := _FASTENER_STD_PAT.search(text)) is not None:
        out["standard"] = attr(re.sub(r"\s+", " ", m.group(1).upper()), m.group(0), "rule", 0.94)
    if (a := _extract_oem(text)) is not None:
        out["oem"] = a
    return out


# ==========================================================================
# Registry
# ==========================================================================

_EXTRACTORS: dict[str, Callable[[str], Attributes]] = {
    GATE_VALVE: extract_gate_valve,
    PIPE: extract_pipe,
    BEARING: extract_bearing,
    ELECTRICAL_CABLE: extract_cable,
    FASTENER: extract_fastener,
}

# Display order and labels, used by the evidence UI.
ATTRIBUTE_SCHEMA: dict[str, list[tuple[str, str]]] = {
    GATE_VALVE: [
        ("item_type", "Item Type"), ("size", "Size"), ("material", "Material"),
        ("pressure_class", "Pressure Class"), ("end_connection", "End Connection"),
        ("standard", "Standard"), ("oem", "OEM"),
    ],
    PIPE: [
        ("item_type", "Item Type"), ("size", "Size"), ("material", "Material"),
        ("schedule", "Schedule"), ("manufacture", "Manufacture"),
        ("standard", "Standard"), ("oem", "OEM"),
    ],
    BEARING: [
        ("item_type", "Item Type"), ("designation", "Designation"), ("bore_mm", "Bore (mm)"),
        ("outer_diameter_mm", "Outer Dia (mm)"), ("width_mm", "Width (mm)"),
        ("seal_type", "Seal Type"), ("oem", "OEM"),
    ],
    ELECTRICAL_CABLE: [
        ("item_type", "Item Type"), ("cores", "Cores"),
        ("cross_section_sqmm", "Cross Section (sq mm)"), ("voltage_grade", "Voltage Grade"),
        ("conductor_material", "Conductor"), ("insulation", "Insulation"),
        ("armour", "Armour"), ("oem", "OEM"),
    ],
    FASTENER: [
        ("item_type", "Item Type"), ("thread_size", "Thread Size"), ("length_mm", "Length (mm)"),
        ("property_class", "Property Class"), ("material", "Material"),
        ("finish", "Finish"), ("standard", "Standard"), ("oem", "OEM"),
    ],
}


def schema_for(commodity: str | None) -> list[tuple[str, str]]:
    return ATTRIBUTE_SCHEMA.get(commodity or "", [])


class LLMExtractor(Protocol):
    """Optional enrichment seam. The demo never requires an implementation."""

    def extract(self, text: str, commodity: str) -> Attributes: ...


_llm_extractor: LLMExtractor | None = None


def register_llm_extractor(extractor: LLMExtractor | None) -> None:
    global _llm_extractor
    _llm_extractor = extractor


def extract_attributes(text: str, commodity: str | None) -> Attributes:
    """Deterministic extraction, optionally topped up by an LLM extractor.

    LLM output can only FILL GAPS -- it never overwrites a rule-extracted
    value, so an unavailable or hallucinating model cannot degrade a
    deterministic result.
    """
    fn = _EXTRACTORS.get(commodity or "")
    if fn is None:
        return {}
    out = fn(text)

    if _llm_extractor is not None:
        try:
            for key, val in _llm_extractor.extract(text, commodity or "").items():
                if key not in out and isinstance(val, dict) and "value" in val:
                    val.setdefault("method", "llm")
                    val.setdefault("confidence", 0.75)
                    val.setdefault("source", "llm")
                    out[key] = val
        except Exception as exc:  # noqa: BLE001 - enrichment must never break ingest
            import logging

            logging.getLogger(__name__).warning("LLM extractor failed, ignoring: %s", exc)
    return out
