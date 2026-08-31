"""Synthetic but realistic CPSE material catalogue.

Structure:

    Canonical material (ground truth, ~38 items)
        -> 3-6 CPSE variants, each with a different legacy code format and a
           differently-mangled description

`hard_negative_group` marks canonicals that are deliberately confusable --
identical except for one safety-critical attribute (CL150 vs CL300, SS316 vs
SS316L, 25 mm bore vs 30 mm bore, 1.1 kV vs 3.3 kV). Any pair drawn from two
different canonicals in the same group is a hard negative: high textual
similarity, must never merge.

The canonical id is written to the `ground_truth` table only. Nothing in the
matching pipeline reads it.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from app.core.commodities import (
    BEARING,
    ELECTRICAL_CABLE,
    FASTENER,
    GATE_VALVE,
    PIPE,
)

# --------------------------------------------------------------------------
# CPSE organisations -- each with a genuinely different code convention
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Cpse:
    code: str
    name: str
    style: str


CPSES: list[Cpse] = [
    Cpse("BHEL", "Bharat Heavy Electricals Limited", "numeric8"),
    Cpse("IOCL", "Indian Oil Corporation Limited", "prefixed"),
    Cpse("NTPC", "NTPC Limited", "sap12"),
    Cpse("GAIL", "GAIL (India) Limited", "slashed"),
    Cpse("SAIL", "Steel Authority of India Limited", "hyphenated"),
]

_COMMODITY_ABBR = {
    GATE_VALVE: "GV", PIPE: "PP", BEARING: "BR",
    ELECTRICAL_CABLE: "CB", FASTENER: "FS",
}


def make_legacy_code(cpse: Cpse, commodity: str, serial: int, rng: random.Random) -> str:
    """Produce a code in that CPSE's own house format."""
    abbr = _COMMODITY_ABBR.get(commodity, "MT")
    if cpse.style == "numeric8":
        return f"{10000000 + serial * 137 + rng.randint(0, 99):08d}"
    if cpse.style == "prefixed":
        return f"MAT-{abbr}-{serial:04d}"
    if cpse.style == "sap12":
        return f"{400000000000 + serial * 4391 + rng.randint(0, 999):012d}"
    if cpse.style == "slashed":
        return f"GL/{abbr}/{serial:05d}"
    if cpse.style == "hyphenated":
        return f"SAIL-M-{serial:06d}"
    return f"{abbr}{serial:05d}"


# --------------------------------------------------------------------------
# Canonical materials
# --------------------------------------------------------------------------

@dataclass
class Canonical:
    canonical_id: str
    commodity: str
    attributes: dict
    hard_negative_group: str | None = None
    variants: int = 4
    inventory: tuple[int, int] = (0, 0)   # (min, max) illustrative quantity
    unit_value_inr: float = 0.0
    uom: str = "NOS"
    oem_pool: list[str] = field(default_factory=list)


VALVE_OEMS = ["KSB", "AUDCO", "BDK", "IVC", "FOURESS"]
BEARING_OEMS = ["SKF", "FAG", "NTN", "TIMKEN", "NSK"]
CABLE_OEMS = ["POLYCAB", "HAVELLS", "KEI", "FINOLEX"]
PIPE_OEMS = ["JINDAL", "ISMT", "MAHARASHTRA SEAMLESS"]
FASTENER_OEMS = ["UNBRAKO", "SUNDRAM", "TVS"]


CANONICALS: list[Canonical] = [
    # ---------------- gate valves ----------------
    Canonical("GV-DN150-CS-CL150", GATE_VALVE, {
        "size": "DN150", "material": "CARBON STEEL", "pressure_class": "CL150",
        "end_connection": "FLANGED", "standard": "API 600"},
        hard_negative_group="gv-dn150", variants=6,
        inventory=(4, 40), unit_value_inr=48000),
    Canonical("GV-DN150-CS-CL300", GATE_VALVE, {
        "size": "DN150", "material": "CARBON STEEL", "pressure_class": "CL300",
        "end_connection": "FLANGED", "standard": "API 600"},
        hard_negative_group="gv-dn150", variants=5,
        inventory=(2, 25), unit_value_inr=71000),
    Canonical("GV-DN150-SS316-CL150", GATE_VALVE, {
        "size": "DN150", "material": "STAINLESS STEEL 316", "pressure_class": "CL150",
        "end_connection": "FLANGED", "standard": "API 600"},
        hard_negative_group="gv-dn150", variants=5,
        inventory=(1, 18), unit_value_inr=126000),
    Canonical("GV-DN150-SS316L-CL150", GATE_VALVE, {
        "size": "DN150", "material": "STAINLESS STEEL 316L", "pressure_class": "CL150",
        "end_connection": "FLANGED", "standard": "API 600"},
        hard_negative_group="gv-dn150", variants=4,
        inventory=(1, 12), unit_value_inr=138000),
    Canonical("GV-DN100-CS-CL150", GATE_VALVE, {
        "size": "DN100", "material": "CARBON STEEL", "pressure_class": "CL150",
        "end_connection": "FLANGED", "standard": "API 600"},
        hard_negative_group="gv-cs-cl150-size", variants=5,
        inventory=(6, 55), unit_value_inr=32000),
    Canonical("GV-DN200-SS304-CL300", GATE_VALVE, {
        "size": "DN200", "material": "STAINLESS STEEL 304", "pressure_class": "CL300",
        "end_connection": "FLANGED", "standard": "ASME B16.34"},
        variants=4, inventory=(1, 9), unit_value_inr=185000),
    Canonical("GV-DN50-CS-CL800", GATE_VALVE, {
        "size": "DN50", "material": "CARBON STEEL", "pressure_class": "CL800",
        "end_connection": "SOCKET WELD", "standard": "API 602"},
        variants=4, inventory=(10, 90), unit_value_inr=14500),
    Canonical("GV-DN250-CS-CL150", GATE_VALVE, {
        "size": "DN250", "material": "CARBON STEEL", "pressure_class": "CL150",
        "end_connection": "FLANGED", "standard": "API 600"},
        hard_negative_group="gv-cs-cl150-size", variants=4,
        inventory=(1, 14), unit_value_inr=96000),

    # ---------------- pipes ----------------
    Canonical("PP-DN150-CS-SCH40", PIPE, {
        "size": "DN150", "material": "CARBON STEEL", "schedule": "SCH40",
        "manufacture": "SEAMLESS", "standard": "ASTM A106"},
        hard_negative_group="pp-dn150", variants=6,
        inventory=(50, 600), unit_value_inr=2100, uom="MTR"),
    Canonical("PP-DN150-CS-SCH80", PIPE, {
        "size": "DN150", "material": "CARBON STEEL", "schedule": "SCH80",
        "manufacture": "SEAMLESS", "standard": "ASTM A106"},
        hard_negative_group="pp-dn150", variants=5,
        inventory=(30, 400), unit_value_inr=3050, uom="MTR"),
    Canonical("PP-DN150-SS316-SCH40", PIPE, {
        "size": "DN150", "material": "STAINLESS STEEL 316", "schedule": "SCH40",
        "manufacture": "SEAMLESS", "standard": "ASTM A312"},
        hard_negative_group="pp-dn150", variants=4,
        inventory=(10, 150), unit_value_inr=8900, uom="MTR"),
    Canonical("PP-DN150-SS316L-SCH40", PIPE, {
        "size": "DN150", "material": "STAINLESS STEEL 316L", "schedule": "SCH40",
        "manufacture": "SEAMLESS", "standard": "ASTM A312"},
        hard_negative_group="pp-dn150", variants=4,
        inventory=(5, 90), unit_value_inr=9600, uom="MTR"),
    Canonical("PP-DN100-CS-SCH40", PIPE, {
        "size": "DN100", "material": "CARBON STEEL", "schedule": "SCH40",
        "manufacture": "SEAMLESS", "standard": "ASTM A106"},
        variants=5, inventory=(80, 700), unit_value_inr=1350, uom="MTR"),
    Canonical("PP-DN200-SS304-SCH40", PIPE, {
        "size": "DN200", "material": "STAINLESS STEEL 304", "schedule": "SCH40",
        "manufacture": "SEAMLESS", "standard": "ASTM A312"},
        variants=4, inventory=(5, 70), unit_value_inr=12400, uom="MTR"),
    Canonical("PP-DN50-CS-SCH80", PIPE, {
        "size": "DN50", "material": "CARBON STEEL", "schedule": "SCH80",
        "manufacture": "SEAMLESS", "standard": "ASTM A106"},
        variants=4, inventory=(100, 900), unit_value_inr=640, uom="MTR"),
    Canonical("PP-DN300-CS-SCH40", PIPE, {
        "size": "DN300", "material": "CARBON STEEL", "schedule": "SCH40",
        "manufacture": "ELECTRIC RESISTANCE WELDED", "standard": "API 5L"},
        variants=4, inventory=(20, 260), unit_value_inr=4700, uom="MTR"),

    # ---------------- bearings ----------------
    Canonical("BR-6205-OPEN", BEARING, {
        "item_type": "DEEP GROOVE BALL BEARING", "designation": "6205",
        "bore_mm": 25.0, "outer_diameter_mm": 52.0, "width_mm": 15.0,
        "seal_type": "OPEN"},
        hard_negative_group="br-6205", variants=6,
        inventory=(20, 300), unit_value_inr=420),
    Canonical("BR-6205-2RS", BEARING, {
        "item_type": "DEEP GROOVE BALL BEARING", "designation": "6205",
        "bore_mm": 25.0, "outer_diameter_mm": 52.0, "width_mm": 15.0,
        "seal_type": "2RS"},
        hard_negative_group="br-6205", variants=4,
        inventory=(15, 220), unit_value_inr=560),
    Canonical("BR-6206-OPEN", BEARING, {
        "item_type": "DEEP GROOVE BALL BEARING", "designation": "6206",
        "bore_mm": 30.0, "outer_diameter_mm": 62.0, "width_mm": 16.0,
        "seal_type": "OPEN"},
        hard_negative_group="br-6205", variants=5,
        inventory=(18, 240), unit_value_inr=510),
    Canonical("BR-6305-OPEN", BEARING, {
        "item_type": "DEEP GROOVE BALL BEARING", "designation": "6305",
        "bore_mm": 25.0, "outer_diameter_mm": 62.0, "width_mm": 17.0,
        "seal_type": "OPEN"},
        hard_negative_group="br-6205", variants=4,
        inventory=(10, 180), unit_value_inr=650),
    Canonical("BR-6204-OPEN", BEARING, {
        "item_type": "DEEP GROOVE BALL BEARING", "designation": "6204",
        "bore_mm": 20.0, "outer_diameter_mm": 47.0, "width_mm": 14.0,
        "seal_type": "OPEN"},
        variants=4, inventory=(25, 320), unit_value_inr=360),
    Canonical("BR-22220-SPH", BEARING, {
        "item_type": "SPHERICAL ROLLER BEARING", "designation": "22220",
        "bore_mm": 100.0, "outer_diameter_mm": 180.0, "width_mm": 46.0,
        "seal_type": "OPEN"},
        variants=4, inventory=(2, 30), unit_value_inr=18500),
    Canonical("BR-NU210-CYL", BEARING, {
        "item_type": "CYLINDRICAL ROLLER BEARING", "designation": "NU210",
        "bore_mm": 50.0, "outer_diameter_mm": 90.0, "width_mm": 20.0,
        "seal_type": "OPEN"},
        variants=4, inventory=(4, 60), unit_value_inr=3400),

    # ---------------- electrical cables ----------------
    Canonical("CB-3C-95-1.1KV-AL", ELECTRICAL_CABLE, {
        "cores": 3, "cross_section_sqmm": 95.0, "voltage_grade": "1.1KV",
        "conductor_material": "ALUMINIUM", "insulation": "XLPE", "armour": "ARMOURED"},
        hard_negative_group="cb-3c-95", variants=6,
        inventory=(200, 2500), unit_value_inr=310, uom="MTR"),
    Canonical("CB-3C-95-3.3KV-AL", ELECTRICAL_CABLE, {
        "cores": 3, "cross_section_sqmm": 95.0, "voltage_grade": "3.3KV",
        "conductor_material": "ALUMINIUM", "insulation": "XLPE", "armour": "ARMOURED"},
        hard_negative_group="cb-3c-95", variants=4,
        inventory=(100, 1200), unit_value_inr=470, uom="MTR"),
    Canonical("CB-3C-95-1.1KV-CU", ELECTRICAL_CABLE, {
        "cores": 3, "cross_section_sqmm": 95.0, "voltage_grade": "1.1KV",
        "conductor_material": "COPPER", "insulation": "XLPE", "armour": "ARMOURED"},
        hard_negative_group="cb-3c-95", variants=4,
        inventory=(80, 900), unit_value_inr=980, uom="MTR"),
    Canonical("CB-4C-16-1.1KV-AL", ELECTRICAL_CABLE, {
        "cores": 4, "cross_section_sqmm": 16.0, "voltage_grade": "1.1KV",
        "conductor_material": "ALUMINIUM", "insulation": "XLPE", "armour": "ARMOURED"},
        variants=5, inventory=(300, 3000), unit_value_inr=96, uom="MTR"),
    Canonical("CB-1C-630-11KV-AL", ELECTRICAL_CABLE, {
        "cores": 1, "cross_section_sqmm": 630.0, "voltage_grade": "11KV",
        "conductor_material": "ALUMINIUM", "insulation": "XLPE", "armour": "UNARMOURED"},
        variants=4, inventory=(50, 600), unit_value_inr=1450, uom="MTR"),
    Canonical("CB-3C-240-11KV-AL", ELECTRICAL_CABLE, {
        "cores": 3, "cross_section_sqmm": 240.0, "voltage_grade": "11KV",
        "conductor_material": "ALUMINIUM", "insulation": "XLPE", "armour": "ARMOURED"},
        variants=4, inventory=(40, 500), unit_value_inr=1180, uom="MTR"),
    Canonical("CB-2C-2.5-1.1KV-CU", ELECTRICAL_CABLE, {
        "cores": 2, "cross_section_sqmm": 2.5, "voltage_grade": "1.1KV",
        "conductor_material": "COPPER", "insulation": "PVC", "armour": "UNARMOURED"},
        variants=4, inventory=(500, 5000), unit_value_inr=42, uom="MTR"),

    # ---------------- fasteners ----------------
    Canonical("FS-BOLT-M16-100-8.8", FASTENER, {
        "item_type": "HEXAGON HEAD BOLT", "thread_size": "M16", "length_mm": 100.0,
        "property_class": "8.8", "finish": "ZINC PLATED", "standard": "IS 1364"},
        hard_negative_group="fs-m16-100", variants=6,
        inventory=(200, 4000), unit_value_inr=38),
    Canonical("FS-BOLT-M16-100-10.9", FASTENER, {
        "item_type": "HEXAGON HEAD BOLT", "thread_size": "M16", "length_mm": 100.0,
        "property_class": "10.9", "finish": "ZINC PLATED", "standard": "IS 1364"},
        hard_negative_group="fs-m16-100", variants=4,
        inventory=(100, 2000), unit_value_inr=61),
    Canonical("FS-BOLT-M16-150-8.8", FASTENER, {
        "item_type": "HEXAGON HEAD BOLT", "thread_size": "M16", "length_mm": 150.0,
        "property_class": "8.8", "finish": "ZINC PLATED", "standard": "IS 1364"},
        hard_negative_group="fs-m16-100", variants=4,
        inventory=(150, 2500), unit_value_inr=52),
    Canonical("FS-BOLT-M16-100-A4-80", FASTENER, {
        "item_type": "HEXAGON HEAD BOLT", "thread_size": "M16", "length_mm": 100.0,
        "property_class": "A4-80", "material": "STAINLESS STEEL 316",
        "finish": "PLAIN", "standard": "IS 1364"},
        hard_negative_group="fs-m16-100", variants=4,
        inventory=(50, 900), unit_value_inr=210),
    Canonical("FS-BOLT-M20-100-8.8", FASTENER, {
        "item_type": "HEXAGON HEAD BOLT", "thread_size": "M20", "length_mm": 100.0,
        "property_class": "8.8", "finish": "HOT DIP GALVANIZED", "standard": "IS 1364"},
        variants=4, inventory=(120, 1800), unit_value_inr=74),
    Canonical("FS-NUT-M16-8", FASTENER, {
        "item_type": "HEXAGON NUT", "thread_size": "M16",
        "property_class": "8.8", "finish": "ZINC PLATED", "standard": "IS 1364"},
        variants=4, inventory=(400, 6000), unit_value_inr=12),
    Canonical("FS-STUD-M20-200-B7", FASTENER, {
        "item_type": "STUD BOLT", "thread_size": "M20", "length_mm": 200.0,
        "material": "ALLOY STEEL A193 B7", "finish": "PLAIN",
        "standard": "ASTM A193 B7"},
        variants=4, inventory=(80, 1200), unit_value_inr=165),
    Canonical("FS-WASHER-M16", FASTENER, {
        "item_type": "WASHER", "thread_size": "M16",
        "finish": "ZINC PLATED", "standard": "IS 1367"},
        variants=3, inventory=(600, 9000), unit_value_inr=4),
]


# --------------------------------------------------------------------------
# Description synthesis
# --------------------------------------------------------------------------

_INCH_BY_DN = {
    "DN15": "1/2", "DN20": "3/4", "DN25": "1", "DN32": "1-1/4", "DN40": "1-1/2",
    "DN50": "2", "DN65": "2-1/2", "DN80": "3", "DN100": "4", "DN125": "5",
    "DN150": "6", "DN200": "8", "DN250": "10", "DN300": "12", "DN350": "14",
    "DN400": "16",
}

_MATERIAL_FORMS = {
    "CARBON STEEL": ["CARBON STEEL", "CS", "A216 WCB", "WCB", "ASTM A105"],
    "STAINLESS STEEL 316": ["SS316", "SS 316", "AISI 316", "STAINLESS STEEL 316", "CF8M"],
    "STAINLESS STEEL 316L": ["SS316L", "SS 316L", "AISI 316L", "STAINLESS STEEL 316L"],
    "STAINLESS STEEL 304": ["SS304", "SS 304", "AISI 304", "STAINLESS STEEL 304"],
    "STAINLESS STEEL 304L": ["SS304L", "SS 304L", "AISI 304L"],
    "ALLOY STEEL A193 B7": ["ASTM A193 B7", "A193 GR B7", "ALLOY STEEL B7"],
}

_CLASS_FORMS = {
    "CL150": ["CLASS 150", "CL150", "150#", "ANSI 150", "CL 150"],
    "CL300": ["CLASS 300", "CL300", "300#", "ANSI 300", "CL 300"],
    "CL800": ["CLASS 800", "CL800", "800#", "CL 800"],
}

_END_FORMS = {
    "FLANGED": ["FLANGED", "FLGD", "FLANGE END", "FL"],
    "SOCKET WELD": ["SOCKET WELD", "SW", "SOCKETWELD"],
}


def _mat(material: str, rng: random.Random) -> str:
    return rng.choice(_MATERIAL_FORMS.get(material, [material]))


def _cls(pc: str, rng: random.Random) -> str:
    return rng.choice(_CLASS_FORMS.get(pc, [pc]))


def _size_form(dn: str, rng: random.Random) -> str:
    inch = _INCH_BY_DN.get(dn)
    mm = dn.replace("DN", "")
    options = [dn, f"{mm} MM", f"{mm}MM", f"{mm} NB"]
    if inch:
        options += [f'{inch}"', f"{inch} INCH", f"{inch}IN", f"{inch} IN"]
    return rng.choice(options)


def _valve_templates(a: dict, rng: random.Random, oem: str | None) -> list[str]:
    size, mat = _size_form(a["size"], rng), _mat(a["material"], rng)
    cls, end = _cls(a["pressure_class"], rng), rng.choice(_END_FORMS.get(a["end_connection"], [a["end_connection"]]))
    std = a.get("standard", "")
    o = f" {oem}" if oem else ""
    return [
        f"GATE VALVE {size} {mat} {cls} {end} {std}{o}",
        f"GT VLV {size} {mat} {cls} {end}{o}",
        f"VALVE, GATE, {size}, {mat}, {cls}",
        f"{size} {mat} GATE VALVE {cls} {end}{o}",
        f"GATE V/V {size} {cls} {mat} {std}",
        f"GATE VALVE {mat} {size} {cls}{o}",
        f"VALVE GATE TYPE {size} {end} {cls} {mat} {std}",
    ]


def _pipe_templates(a: dict, rng: random.Random, oem: str | None) -> list[str]:
    size, mat = _size_form(a["size"], rng), _mat(a["material"], rng)
    sch = a["schedule"]
    sch_form = rng.choice([sch, sch.replace("SCH", "SCH "), sch.replace("SCH", "SCHEDULE ")])
    manuf = a.get("manufacture", "")
    manuf_form = "SMLS" if manuf == "SEAMLESS" and rng.random() < 0.4 else manuf
    std = a.get("standard", "")
    o = f" {oem}" if oem else ""
    return [
        f"PIPE {manuf_form} {size} {sch_form} {mat} {std}{o}",
        f"{manuf_form} PIPE {size} {sch_form} {mat}",
        f"{std} PIPE {size} {sch_form} {manuf_form}{o}",
        f"PIPE, {mat}, {size}, {sch_form}",
        f"{mat} PIPE {size} {sch_form} {manuf_form} {std}",
        f"PIPE {size} {mat} {sch_form}{o}",
    ]


# Abbreviated forms must stay faithful to the bearing family -- describing a
# spherical roller bearing as "DGBB" would be wrong seed data, not a hard
# negative.
_BEARING_ABBR = {
    "DEEP GROOVE BALL BEARING": ("DGBB", "BEARING BALL"),
    "SPHERICAL ROLLER BEARING": ("SPH RLR BRG", "BEARING SPHERICAL ROLLER"),
    "CYLINDRICAL ROLLER BEARING": ("CYL RLR BRG", "BEARING CYLINDRICAL ROLLER"),
}


def _bearing_templates(a: dict, rng: random.Random, oem: str | None) -> list[str]:
    d = a["designation"]
    bore, od, w = a["bore_mm"], a["outer_diameter_mm"], a["width_mm"]
    seal = a.get("seal_type", "OPEN")
    itype = a["item_type"]
    abbr, long_form = _BEARING_ABBR.get(itype, ("BRG", "BEARING"))
    o = f" {oem}" if oem else ""
    seal_tok = "" if seal == "OPEN" else f"-{seal}"
    seal_word = "OPEN" if seal == "OPEN" else ("SEALED" if seal == "2RS" else "SHIELDED")
    return [
        f"{itype} {d}{seal_tok} BORE {bore:g} MM OD {od:g} MM{o}",
        f"BRG {d}{seal_tok} {seal_word} ID {bore:g}MM OD {od:g}MM W {w:g}MM",
        f"{long_form} {d}{seal_tok} {seal_word}{o}",
        f"{o.strip()} {d}{seal_tok} {abbr} BORE {bore:g} MM {seal_word}".strip(),
        f"{abbr} {d}{seal_tok} {bore:g}MM BORE {od:g}MM OD {seal_word}",
        f"{itype}, {d}{seal_tok}, BORE {bore:g} MM, {seal_word}",
    ]


def _cable_templates(a: dict, rng: random.Random, oem: str | None) -> list[str]:
    cores, cs = a["cores"], a["cross_section_sqmm"]
    kv = a["voltage_grade"]
    volt_form = rng.choice(
        [kv, kv.replace("KV", " KV"), "650/1100 V" if kv == "1.1KV" else kv]
    )
    cond = a["conductor_material"]
    cond_form = rng.choice([cond, "AL" if cond == "ALUMINIUM" else "CU"])
    ins, arm = a["insulation"], a["armour"]
    arm_form = rng.choice([arm, "ARMD" if arm == "ARMOURED" else "UNARMD"])
    cs_form = rng.choice([f"{cs:g} SQ MM", f"{cs:g}SQMM", f"{cs:g} MM2", f"{cs:g} SQ.MM"])
    o = f" {oem}" if oem else ""
    return [
        f"{ins} CABLE {cores} CORE {cs_form} {cond_form} {arm_form} {volt_form}{o}",
        f"CABLE {cores}C X {cs_form} {cond_form} {ins} {volt_form} {arm_form}",
        f"POWER CABLE {cores} CORE X {cs_form} {volt_form} {ins} {arm_form} {cond_form}{o}",
        f"{cores}CX{cs_form} {cond_form} {ins} {arm_form} {volt_form} CABLE",
        f"CABLE, {cores} CORE, {cs_form}, {cond_form}, {ins}, {volt_form}",
        f"{volt_form} {ins} {arm_form} CABLE {cores} CORE {cs_form} {cond_form}{o}",
    ]


def _fastener_templates(a: dict, rng: random.Random, oem: str | None) -> list[str]:
    itype = a["item_type"]
    thread = a["thread_size"]
    length = a.get("length_mm")
    pc = a.get("property_class", "")
    mat = a.get("material")
    mat_form = _mat(mat, rng) if mat else ""
    finish = a.get("finish", "")
    finish_form = finish
    if finish == "ZINC PLATED" and rng.random() < 0.4:
        finish_form = "ZN PLTD"
    elif finish == "HOT DIP GALVANIZED" and rng.random() < 0.4:
        finish_form = "HDG"
    std = a.get("standard", "")
    o = f" {oem}" if oem else ""
    size_tok = f"{thread} X {length:g}" if length else thread
    size_tok_tight = f"{thread}X{length:g}" if length else thread
    pc_form = rng.choice([f"GRADE {pc}", f"CLASS {pc}", pc, f"GR {pc}"]) if pc else ""
    short = {
        "HEXAGON HEAD BOLT": "HEX BOLT",
        "HEXAGON NUT": "HEX NUT",
        "STUD BOLT": "STUD",
    }.get(itype, itype)
    # The abbreviated head-noun must match the actual item -- a washer written
    # as "BOLT HEX HD" would be wrong seed data rather than realistic variation.
    terse = {
        "HEXAGON HEAD BOLT": "BOLT HEX HD",
        "HEXAGON NUT": "NUT HEX",
        "STUD BOLT": "STUD BOLT",
        # "WSHR PLAIN" would collide with PLAIN as a surface finish.
        "WASHER": "WSHR FLAT",
    }.get(itype, itype)
    return [
        f"{itype} {size_tok} {pc_form} {finish_form} {std}{o}",
        f"{short} {size_tok_tight} {pc_form} {finish_form}",
        f"{terse} {size_tok} MM {pc_form} {mat_form}".replace("  ", " "),
        f"{std} {short} {size_tok_tight} {pc_form} {finish_form}{o}",
        f"{itype}, {size_tok}, {pc_form}, {finish_form}",
        f"{short} {size_tok} {mat_form} {pc_form} {finish_form}".replace("  ", " "),
    ]


_TEMPLATE_FNS = {
    GATE_VALVE: _valve_templates,
    PIPE: _pipe_templates,
    BEARING: _bearing_templates,
    ELECTRICAL_CABLE: _cable_templates,
    FASTENER: _fastener_templates,
}

_OEM_POOLS = {
    GATE_VALVE: VALVE_OEMS, PIPE: PIPE_OEMS, BEARING: BEARING_OEMS,
    ELECTRICAL_CABLE: CABLE_OEMS, FASTENER: FASTENER_OEMS,
}


# --------------------------------------------------------------------------
# Corruption
# --------------------------------------------------------------------------

# Tokens that carry safety-critical meaning. Corruption avoids these most of
# the time, and when it does hit one the record legitimately becomes an
# UNKNOWN/review case rather than a silent wrong merge.
_PROTECTED = ("316L", "316", "304", "150", "300", "800", "8.8", "10.9", "A4-80", "SCH")

_OCR_MAP = {"O": "0", "0": "O", "I": "1", "1": "I", "S": "5", "5": "S", "B": "8"}


def _typo(word: str, rng: random.Random) -> str:
    if len(word) < 4:
        return word
    i = rng.randrange(1, len(word) - 1)
    mode = rng.random()
    if mode < 0.45:  # transpose
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if mode < 0.8:  # drop
        return word[:i] + word[i + 1:]
    return word[:i] + word[i] + word[i:]  # duplicate


def _ocr(word: str, rng: random.Random) -> str:
    chars = list(word)
    idxs = [i for i, c in enumerate(chars) if c in _OCR_MAP]
    if not idxs:
        return word
    i = rng.choice(idxs)
    chars[i] = _OCR_MAP[chars[i]]
    return "".join(chars)


def _corrupt(text: str, rng: random.Random, allow_critical: bool) -> str:
    words = text.split()
    if not words:
        return text
    candidates = [
        i for i, w in enumerate(words)
        if allow_critical or not any(p in w.upper() for p in _PROTECTED)
    ]
    if not candidates:
        return text
    n = 1 if len(candidates) < 6 else rng.choice([1, 1, 2])
    for i in rng.sample(candidates, min(n, len(candidates))):
        words[i] = _typo(words[i], rng) if rng.random() < 0.6 else _ocr(words[i], rng)
    return " ".join(words)


def _restyle(text: str, rng: random.Random) -> str:
    """Apply capitalisation / punctuation variation for display realism."""
    r = rng.random()
    if r < 0.45:
        return text
    if r < 0.65:
        return text.lower()
    if r < 0.80:
        return text.title()
    if r < 0.90:
        return text.replace(" ", ", ", 1)
    return "  ".join(text.split())


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

@dataclass
class SeedRecord:
    cpse_org: str
    legacy_code: str
    raw_description: str
    commodity_type: str
    canonical_id: str
    quantity: int
    uom: str
    unit_value_inr: float


def generate_records(seed: int = 20260101) -> list[SeedRecord]:
    """Deterministically generate the full synthetic CPSE dataset."""
    rng = random.Random(seed)
    out: list[SeedRecord] = []
    serial = 1

    for canon in CANONICALS:
        tmpl_fn = _TEMPLATE_FNS[canon.commodity]
        oem_pool = _OEM_POOLS[canon.commodity]
        # Each canonical is stocked by a different, overlapping subset of CPSEs.
        orgs = rng.sample(CPSES, k=min(canon.variants, len(CPSES)))
        if canon.variants > len(CPSES):
            orgs += rng.sample(CPSES, k=canon.variants - len(CPSES))

        for idx, cpse in enumerate(orgs):
            oem = rng.choice(oem_pool) if rng.random() < 0.45 else None
            templates = tmpl_fn(canon.attributes, rng, oem)
            text = templates[idx % len(templates)]
            text = " ".join(text.split())

            # ~30% of records carry a typo or OCR-style corruption; of those a
            # small share hits a safety-critical token, which is exactly the
            # situation the review queue exists for.
            if rng.random() < 0.30:
                text = _corrupt(text, rng, allow_critical=rng.random() < 0.20)

            # ~12% drop a trailing attribute entirely (incomplete ERP master data).
            if rng.random() < 0.12:
                parts = text.split()
                if len(parts) > 4:
                    text = " ".join(parts[:-1])

            raw = _restyle(text, rng)
            lo, hi = canon.inventory
            out.append(
                SeedRecord(
                    cpse_org=cpse.code,
                    legacy_code=make_legacy_code(cpse, canon.commodity, serial, rng),
                    raw_description=raw,
                    commodity_type=canon.commodity,
                    canonical_id=canon.canonical_id,
                    quantity=rng.randint(lo, hi) if hi > 0 else 0,
                    uom=canon.uom,
                    unit_value_inr=canon.unit_value_inr,
                )
            )
            serial += 1

    # A CPSE cannot hold the same legacy code twice; keep the first occurrence.
    seen: set[tuple[str, str]] = set()
    deduped = []
    for r in out:
        key = (r.cpse_org, r.legacy_code)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


def hard_negative_groups() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for c in CANONICALS:
        if c.hard_negative_group:
            groups.setdefault(c.hard_negative_group, []).append(c.canonical_id)
    return {g: ids for g, ids in groups.items() if len(ids) > 1}


def canonical_by_id() -> dict[str, Canonical]:
    return {c.canonical_id: c for c in CANONICALS}
