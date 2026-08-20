"""Public DOT standard-drawing corpus: gold BeamSpecs + fingerprint matching.

Gold JSON lives in training-data/extracted-json/. This module can rebuild it
and can match an uploaded shop drawing against the catalog.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from beam_spec import (
    BeamGeometry, BeamSpec, BillItem, HardwareItem, StationRef, StrandItem, StirrupZone,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = ROOT / "training-data" / "extracted-json"

# PCI / AASHTO I-beam section properties used across NY/SC/NC/OR/TN standards.
AASHTO_I = {
    "type_i": dict(depth_in=28.0, top_flange_width_in=12.0, top_flange_thick_in=4.0,
                   bot_flange_width_in=16.0, bot_flange_thick_in=5.0, web_thick_in=6.0, width_in=16.0),
    "type_i_mod": dict(depth_in=28.0, top_flange_width_in=16.0, top_flange_thick_in=4.0,
                       bot_flange_width_in=16.0, bot_flange_thick_in=5.0, web_thick_in=6.0, width_in=16.0),
    "type_ii": dict(depth_in=36.0, top_flange_width_in=12.0, top_flange_thick_in=6.0,
                    bot_flange_width_in=18.0, bot_flange_thick_in=6.0, web_thick_in=6.0, width_in=18.0),
    "type_iii": dict(depth_in=45.0, top_flange_width_in=16.0, top_flange_thick_in=7.0,
                     bot_flange_width_in=22.0, bot_flange_thick_in=7.0, web_thick_in=7.0, width_in=22.0),
    "type_iv": dict(depth_in=54.0, top_flange_width_in=20.0, top_flange_thick_in=8.0,
                    bot_flange_width_in=26.0, bot_flange_thick_in=8.0, web_thick_in=8.0, width_in=26.0),
    "type_v": dict(depth_in=63.0, top_flange_width_in=42.0, top_flange_thick_in=5.0,
                   bot_flange_width_in=28.0, bot_flange_thick_in=8.0, web_thick_in=8.0, width_in=42.0),
    "type_vi": dict(depth_in=72.0, top_flange_width_in=42.0, top_flange_thick_in=5.0,
                    bot_flange_width_in=28.0, bot_flange_thick_in=8.0, web_thick_in=8.0, width_in=42.0),
}

# Florida I-Beam (SCDOT 704-FIB / FDOT). Top flange 42", web 7".
FIB = {
    36: dict(depth_in=36.0, top_flange_width_in=42.0, top_flange_thick_in=5.5,
             bot_flange_width_in=28.0, bot_flange_thick_in=7.0, web_thick_in=7.0, width_in=42.0),
    45: dict(depth_in=45.0, top_flange_width_in=42.0, top_flange_thick_in=5.5,
             bot_flange_width_in=28.0, bot_flange_thick_in=7.0, web_thick_in=7.0, width_in=42.0),
    54: dict(depth_in=54.0, top_flange_width_in=42.0, top_flange_thick_in=5.5,
             bot_flange_width_in=28.0, bot_flange_thick_in=7.5, web_thick_in=7.0, width_in=42.0),
    63: dict(depth_in=63.0, top_flange_width_in=42.0, top_flange_thick_in=5.5,
             bot_flange_width_in=28.0, bot_flange_thick_in=8.0, web_thick_in=7.0, width_in=42.0),
    72: dict(depth_in=72.0, top_flange_width_in=42.0, top_flange_thick_in=5.5,
             bot_flange_width_in=28.0, bot_flange_thick_in=8.0, web_thick_in=7.0, width_in=42.0),
}

# NYSDOT NEBT / PCEF typical (42" top flange bulb tees).
NEBT = {
    39: dict(depth_in=39.0, top_flange_width_in=42.0, top_flange_thick_in=3.5,
             bot_flange_width_in=29.0, bot_flange_thick_in=6.0, web_thick_in=6.0, width_in=42.0),
    63: dict(depth_in=63.0, top_flange_width_in=42.0, top_flange_thick_in=3.5,
             bot_flange_width_in=29.0, bot_flange_thick_in=6.0, web_thick_in=6.0, width_in=42.0),
}


def _id(catalog_id: str, suffix: str) -> str:
    return f"{catalog_id}--{suffix}"


def _hw(catalog_id, kind, name, station_ft, height_in, *, offset_in=0.0, face="top",
        type_code="", size="", material="", end_station_ft=None, notes="",
        tolerance_in=1.0, quantity=1, page=1, suffix=None):
    return HardwareItem(
        id=_id(catalog_id, suffix or name.lower().replace(" ", "-").replace("/", "-")),
        kind=kind,
        name=name,
        type_code=type_code,
        quantity=quantity,
        size=size,
        material=material,
        position=StationRef(
            station_ft=round(station_ft, 3),
            offset_in=offset_in,
            height_from_soffit_in=height_in,
            face=face,
            page=page,
            source_note=f"{catalog_id} p.{page}",
        ),
        end_station_ft=end_station_ft,
        notes=notes,
        tolerance_in=tolerance_in,
    )


def _typical_strands(catalog_id: str, count_straight: int, count_draped: int, length_ft: float,
                     offsets: List[float], soffit_in: float = 2.0) -> List[StrandItem]:
    strands = []
    n = 1
    hd = [round(length_ft * 0.40, 2), round(length_ft * 0.60, 2)]
    for i in range(count_straight):
        off = offsets[i % len(offsets)]
        debond = 4.0 if abs(off) >= max(abs(x) for x in offsets) * 0.85 and n <= 4 else 0.0
        strands.append(StrandItem(
            id=_id(catalog_id, f"strand-{n}"),
            number=n,
            size="0.5in",
            detensioning="straight",
            soffit_in=soffit_in,
            offset_in=off,
            debond_me_ft=debond,
            debond_ue_ft=debond,
            notes="Outer straight strands bituminous-debonded 4'-0\" each end (NCDOT min. 4')." if debond else "",
            page=2,
        ))
        n += 1
    for i in range(count_draped):
        off = offsets[i % len(offsets)]
        strands.append(StrandItem(
            id=_id(catalog_id, f"strand-{n}"),
            number=n,
            size="0.5in",
            detensioning="draped",
            soffit_in=soffit_in,
            drape_peak_in=18.0,
            hold_down_stations_ft=hd,
            offset_in=off,
            notes="Harped / draped. Hold-downs at 0.4L and 0.6L.",
            page=2,
        ))
        n += 1
    return strands


def _i_beam_hardware(catalog_id: str, geo: BeamGeometry, draped: bool = True) -> List[HardwareItem]:
    L = geo.length_ft
    d = geo.depth_in
    hw = [
        _hw(catalog_id, "bituminous_zone", "Bituminous / debond ME", 0.0, 2.0,
            face="bottom", size="4'-0\"", material="bituminous coating",
            end_station_ft=4.0, notes="Strands cut/debonded at Marked End. Min. 4' (NCDOT).",
            tolerance_in=2.0, suffix="bit-me"),
        _hw(catalog_id, "bituminous_zone", "Bituminous / debond UE", L - 4.0, 2.0,
            face="bottom", size="4'-0\"", material="bituminous coating",
            end_station_ft=L, notes="Strands cut/debonded at Unmarked End.",
            tolerance_in=2.0, suffix="bit-ue"),
        _hw(catalog_id, "lift_loop", "Lift loop ME", round(L * 0.20, 2), d,
            face="top", type_code="LL-1", size='1" 7-wire loop', material="Grade 270 strand",
            notes="0.2L from Marked End. ~4\" projection above top flange.", suffix="ll-me"),
        _hw(catalog_id, "lift_loop", "Lift loop UE", round(L * 0.80, 2), d,
            face="top", type_code="LL-2", size='1" 7-wire loop', material="Grade 270 strand",
            notes="0.2L from Unmarked End.", suffix="ll-ue"),
        _hw(catalog_id, "bearing_plate", "Bearing plate ME", 0.625, 0.0,
            face="bottom", type_code="BRG-ME", size='3/4" plate', material="A36",
            notes="CL bearing ~7.5\" from end (ODOT BR325 family).", tolerance_in=0.25, suffix="brg-me"),
        _hw(catalog_id, "bearing_plate", "Bearing plate UE", L - 0.625, 0.0,
            face="bottom", type_code="BRG-UE", size='3/4" plate', material="A36",
            notes="CL bearing at Unmarked End.", tolerance_in=0.25, suffix="brg-ue"),
        _hw(catalog_id, "tie_rod", "Diaphragm hole ME", 1.5, d / 2,
            face="web_left", type_code="TR-1", size='2-1/2" Ø', material="void tube",
            notes="End diaphragm / tie-rod opening.", tolerance_in=0.5, suffix="tr-me"),
        _hw(catalog_id, "tie_rod", "Diaphragm hole UE", L - 1.5, d / 2,
            face="web_left", type_code="TR-2", size='2-1/2" Ø', material="void tube",
            notes="End diaphragm / tie-rod opening.", tolerance_in=0.5, suffix="tr-ue"),
        _hw(catalog_id, "diaphragm", "Intermediate diaphragm L/2", round(L / 2, 2), d / 2,
            face="web_left", type_code="DIA-MID", size="steel diaphragm", material="A36",
            notes="Midpoint diaphragm (SCDOT Alt 1 / NCDOT PCG10).", suffix="dia-mid"),
        _hw(catalog_id, "drain", "Drain hole 1", round(L * 0.28, 2), 3.0,
            face="bottom", type_code="DR-1", size='2" Ø', material="PVC sleeve", suffix="dr-1"),
        _hw(catalog_id, "drain", "Drain hole 2", round(L * 0.72, 2), 3.0,
            face="bottom", type_code="DR-2", size='2" Ø', material="PVC sleeve", suffix="dr-2"),
        _hw(catalog_id, "projecting_rebar", "Projecting bars UE", L, d / 2,
            face="end_ue", type_code="PR-UE", size="4-#6 x 12\"", material="Grade 60",
            notes="Continuity / diaphragm projection at Unmarked End where required.",
            quantity=4, suffix="pr-ue"),
    ]
    insert_step = 8.0
    st = insert_step
    i = 1
    while st < L - 4:
        for side, off in (("L", -3.5), ("R", 3.5)):
            hw.append(_hw(
                catalog_id, "insert", f"F-64 {side}{i}", st, max(d - 3.0, 6.0),
                offset_in=off, face="top", type_code="F-64",
                size='F-64 ferrule 3/4"-10', material="malleable insert",
                notes="Deck / shear insert. Height from soffit ≈ top flange minus 3\".",
                tolerance_in=0.5, suffix=f"f64-{side.lower()}{i}",
            ))
        i += 1
        st += insert_step
    if draped:
        hw.append(_hw(catalog_id, "hold_down", "Hold-down 1", round(L * 0.40, 2), 2.5,
                      face="bottom", type_code="HD-1", size="hold-down assembly",
                      material="steel", notes="Draped-strand hold-down at 0.4L.", suffix="hd-1"))
        hw.append(_hw(catalog_id, "hold_down", "Hold-down 2", round(L * 0.60, 2), 2.5,
                      face="bottom", type_code="HD-2", size="hold-down assembly",
                      material="steel", notes="Draped-strand hold-down at 0.6L.", suffix="hd-2"))
    return hw


def _box_hardware(catalog_id: str, geo: BeamGeometry) -> List[HardwareItem]:
    L = geo.length_ft
    d = geo.depth_in
    w = geo.width_in
    hw = [
        _hw(catalog_id, "grout_groove", "Grout groove left", 0.0, d * 0.45,
            offset_in=-(w / 2) + 1.0, face="side", type_code="GG-L", size='1" x 1"',
            material="cast key", end_station_ft=L, notes="Longitudinal shear key / grout groove.",
            suffix="gg-l"),
        _hw(catalog_id, "grout_groove", "Grout groove right", 0.0, d * 0.45,
            offset_in=(w / 2) - 1.0, face="side", type_code="GG-R", size='1" x 1"',
            material="cast key", end_station_ft=L, notes="Longitudinal shear key / grout groove.",
            suffix="gg-r"),
        _hw(catalog_id, "lift_loop", "Lift loop ME", round(L * 0.20, 2), d,
            face="top", type_code="LL-1", size='1" 7-wire loop', material="Grade 270 strand", suffix="ll-me"),
        _hw(catalog_id, "lift_loop", "Lift loop UE", round(L * 0.80, 2), d,
            face="top", type_code="LL-2", size='1" 7-wire loop', material="Grade 270 strand", suffix="ll-ue"),
        _hw(catalog_id, "bearing_plate", "Bearing plate ME", 0.5, 0.0,
            face="bottom", type_code="BRG-ME", size="elastomeric seat", material="A36",
            tolerance_in=0.25, suffix="brg-me"),
        _hw(catalog_id, "bearing_plate", "Bearing plate UE", L - 0.5, 0.0,
            face="bottom", type_code="BRG-UE", size="elastomeric seat", material="A36",
            tolerance_in=0.25, suffix="brg-ue"),
        _hw(catalog_id, "drain", "Void drain ME", round(L * 0.25, 2), 3.0,
            face="bottom", type_code="DR-1", size='2" Ø', material="PVC", suffix="dr-1"),
        _hw(catalog_id, "drain", "Void drain UE", round(L * 0.75, 2), 3.0,
            face="bottom", type_code="DR-2", size='2" Ø', material="PVC", suffix="dr-2"),
    ]
    for i, frac in enumerate((0.25, 0.50, 0.75), start=1):
        hw.append(_hw(
            catalog_id, "tie_rod", f"Transverse tendon {i}", round(L * frac, 2), d / 2,
            face="web_left", type_code=f"TT-{i}", size='1" Ø duct', material="post-tension duct",
            notes="Adjacent-member transverse tendon / tie rod (NCDOT PCBB / NYSDOT BD-PC10E).",
            suffix=f"tt-{i}",
        ))
    return hw


def _stirrups(length_ft: float, catalog_id: str) -> List[StirrupZone]:
    return [
        StirrupZone(id=_id(catalog_id, "stz-me"), from_ft=0.0, to_ft=6.0, spacing_in=4.0,
                    bar_size="#3", shape="hoop", notes="Confined end-zone hoops — Marked End", page=2),
        StirrupZone(id=_id(catalog_id, "stz-typ"), from_ft=6.0, to_ft=max(length_ft - 6.0, 6.0),
                    spacing_in=8.0, bar_size="#3", shape="stirrup", notes="Typical spacing", page=2),
        StirrupZone(id=_id(catalog_id, "stz-ue"), from_ft=max(length_ft - 6.0, 6.0), to_ft=length_ft,
                    spacing_in=4.0, bar_size="#3", shape="hoop", notes="Confined end-zone hoops — Unmarked End", page=2),
    ]


def build_i_beam(
    catalog_id: str, *, agency: str, drawing: str, url: str, product: str,
    section: dict, length_ft: float, n_straight: int, n_draped: int,
    fingerprints: List[str], extra_notes: List[str],
) -> BeamSpec:
    geo = BeamGeometry(twin_type="i_beam", length_ft=length_ft, product_name=product, **section)
    offsets = [-6.0, -3.6, -1.2, 1.2, 3.6, 6.0]
    spec = BeamSpec(
        id=catalog_id,
        catalog_id=catalog_id,
        source_agency=agency,
        source_drawing=drawing,
        source_url=url,
        job_number=catalog_id.upper(),
        beam_mark="STD",
        product_name=product,
        state_spec=agency,
        geometry=geo,
        marked_end_id=f"{agency} / {drawing} / ME",
        unmarked_end_id=f"{agency} / {drawing} / UE",
        strands=_typical_strands(catalog_id, n_straight, n_draped, length_ft, offsets),
        hardware=_i_beam_hardware(catalog_id, geo, draped=n_draped > 0),
        stirrup_zones=_stirrups(length_ft, catalog_id),
        bill_of_materials=[
            BillItem(item="0.5in Grade 270 LR strand", quantity=n_straight + n_draped, unit="EA"),
            BillItem(item="Lift loop", quantity=2, unit="EA"),
            BillItem(item="F-64 insert", quantity=len([h for h in _i_beam_hardware(catalog_id, geo, n_draped > 0) if h.kind == "insert"]), unit="EA"),
            BillItem(item="Bearing plate", quantity=2, unit="EA"),
        ],
        notes=[
            f"Gold BeamSpec from {agency} {drawing}.",
            "Stations are feet from the Marked End. Heights are inches from soffit.",
            "Lift loops at 0.2L / 0.8L. Hold-downs at 0.4L / 0.6L when draped strands are used.",
            "Minimum strand debond 4'-0\" (NCDOT); subsequent lengths in 2' increments.",
        ] + extra_notes,
        special_finishes=["Trowel finish top flange", "As-cast sides / soffit"],
        status="reviewed",
        extractor="gold_corpus",
        extractor_confidence=0.9,
        source_pages=2,
        review_notes="Gold standard for extraction evaluation. Supervisor must still confirm against the specific shop drawing span.",
    )
    spec.notes.append("FINGERPRINTS: " + " | ".join(fingerprints))
    return spec


def build_box(
    catalog_id: str, *, agency: str, drawing: str, url: str, product: str,
    width_in: float, depth_in: float, length_ft: float, wall_in: float = 5.0,
    n_strands: int = 16, fingerprints: List[str], extra_notes: List[str],
) -> BeamSpec:
    geo = BeamGeometry(
        twin_type="box_beam", length_ft=length_ft, depth_in=depth_in, width_in=width_in,
        top_flange_width_in=width_in, top_flange_thick_in=wall_in,
        bot_flange_width_in=width_in, bot_flange_thick_in=wall_in,
        web_thick_in=wall_in, product_name=product,
    )
    pitch = max(width_in / 8.0, 2.0)
    offsets = [-(width_in / 2 - 3) + i * pitch for i in range(8)]
    spec = BeamSpec(
        id=catalog_id,
        catalog_id=catalog_id,
        source_agency=agency,
        source_drawing=drawing,
        source_url=url,
        job_number=catalog_id.upper(),
        beam_mark="STD",
        product_name=product,
        state_spec=agency,
        geometry=geo,
        marked_end_id=f"{agency} / {drawing} / ME",
        unmarked_end_id=f"{agency} / {drawing} / UE",
        strands=_typical_strands(catalog_id, n_strands, 0, length_ft, offsets, soffit_in=2.5),
        hardware=_box_hardware(catalog_id, geo),
        stirrup_zones=_stirrups(length_ft, catalog_id),
        bill_of_materials=[
            BillItem(item="0.5in Grade 270 LR strand", quantity=n_strands, unit="EA"),
            BillItem(item="Lift loop", quantity=2, unit="EA"),
            BillItem(item="Transverse tendon / tie rod", quantity=3, unit="EA"),
            BillItem(item="Grout groove", quantity=2, unit="LF", notes="Each long face"),
        ],
        notes=[
            f"Gold BeamSpec from {agency} {drawing}.",
            "Adjacent box: grout grooves both faces; transverse tendons at 0.25L / 0.50L / 0.75L.",
            "Void drains near 0.25L and 0.75L. Marked End stamped per erection plan.",
        ] + extra_notes,
        special_finishes=["Raked or trowel finish top", "As-cast sides / soffit"],
        status="reviewed",
        extractor="gold_corpus",
        extractor_confidence=0.9,
        source_pages=2,
        review_notes="Gold standard for extraction evaluation. Confirm void layout and tendon count on the print.",
    )
    spec.notes.append("FINGERPRINTS: " + " | ".join(fingerprints))
    return spec


def all_gold_specs() -> List[BeamSpec]:
    specs: List[BeamSpec] = []

    # --- NCDOT AASHTO I ---
    specs.append(build_i_beam(
        "ncdot-pcg-type-ii", agency="NCDOT", drawing="PCG1 / pcg1_24",
        url="https://connect.ncdot.gov/resources/Structures/Pages/Structure-Standards.aspx",
        product="NCDOT AASHTO Type II Prestressed Concrete Girder",
        section=AASHTO_I["type_ii"], length_ft=70.0, n_straight=12, n_draped=8,
        fingerprints=["PCG1", "TYPE II", "NCDOT", "36\" GIRDER", "AASHTO TYPE II"],
        extra_notes=["NCDOT FIG 6-66: 36\" deep, 12\" top, 18\" bottom, 6\" web. Area 369 in².",
                     "End-zone top-flange notches detailed for skew; omit at 90°."],
    ))
    specs.append(build_i_beam(
        "ncdot-pcg-type-iii", agency="NCDOT", drawing="PCG2 / pcg2_24",
        url="https://connect.ncdot.gov/resources/Structures/Pages/Structure-Standards.aspx",
        product="NCDOT AASHTO Type III Prestressed Concrete Girder",
        section=AASHTO_I["type_iii"], length_ft=90.0, n_straight=16, n_draped=8,
        fingerprints=["PCG2", "TYPE III", "NCDOT", "45\" GIRDER", "AASHTO TYPE III"],
        extra_notes=["NCDOT FIG 6-66: 45\" deep, 16\" top, 22\" bottom, 7\" web. Area 560 in²."],
    ))
    specs.append(build_i_beam(
        "ncdot-pcg-type-iv", agency="NCDOT", drawing="PCG3 / pcg3_24",
        url="https://connect.ncdot.gov/resources/Structures/Pages/Structure-Standards.aspx",
        product="NCDOT AASHTO Type IV Prestressed Concrete Girder",
        section=AASHTO_I["type_iv"], length_ft=110.0, n_straight=20, n_draped=10,
        fingerprints=["PCG3", "TYPE IV", "NCDOT", "54\" GIRDER", "AASHTO TYPE IV"],
        extra_notes=["NCDOT FIG 6-66: 54\" deep, 20\" top, 26\" bottom, 8\" web. Area 789 in²."],
    ))

    # --- SCDOT AASHTO + FIB ---
    specs.append(build_i_beam(
        "scdot-aashto-type-i-mod", agency="SCDOT", drawing="704-AASHTO.T01MOD",
        url="https://www.scdot.org/business/structural-drawings-704.html",
        product="SCDOT AASHTO Type I Modified Prestressed Concrete Beam",
        section=AASHTO_I["type_i_mod"], length_ft=50.0, n_straight=10, n_draped=4,
        fingerprints=["704-AASHTO", "TYPE I MOD", "T01MOD", "SCDOT"],
        extra_notes=["SCDOT IM704-AASHTO, June 26 2024. Type I Modified, II, III, IV available."],
    ))
    specs.append(build_i_beam(
        "scdot-aashto-type-ii", agency="SCDOT", drawing="704-AASHTO.T02",
        url="https://www.scdot.org/business/structural-drawings-704.html",
        product="SCDOT AASHTO Type II Prestressed Concrete Beam",
        section=AASHTO_I["type_ii"], length_ft=70.0, n_straight=12, n_draped=8,
        fingerprints=["704-AASHTO.T02", "TYPE II", "SCDOT AASHTO"],
        extra_notes=["SCDOT IM704-AASHTO Table 1 section properties. Diaphragm alts: mid / third-point, 2-hole."],
    ))
    specs.append(build_i_beam(
        "scdot-aashto-type-iii", agency="SCDOT", drawing="704-AASHTO.T03",
        url="https://www.scdot.org/business/structural-drawings-704.html",
        product="SCDOT AASHTO Type III Prestressed Concrete Beam",
        section=AASHTO_I["type_iii"], length_ft=90.0, n_straight=16, n_draped=8,
        fingerprints=["704-AASHTO.T03", "TYPE III", "SCDOT"],
        extra_notes=["SCDOT Type III depth 45\"."],
    ))
    specs.append(build_i_beam(
        "scdot-aashto-type-iv", agency="SCDOT", drawing="704-AASHTO.T04",
        url="https://www.scdot.org/business/structural-drawings-704.html",
        product="SCDOT AASHTO Type IV Prestressed Concrete Beam",
        section=AASHTO_I["type_iv"], length_ft=110.0, n_straight=20, n_draped=10,
        fingerprints=["704-AASHTO.T04", "TYPE IV", "SCDOT"],
        extra_notes=["SCDOT Type IV depth 54\"."],
    ))
    for depth in (36, 45, 54, 63, 72):
        specs.append(build_i_beam(
            f"scdot-fib-{depth}", agency="SCDOT", drawing=f"704-FIB.{depth}",
            url="https://www.scdot.org/content/dam/scdot-legacy/business/structuraldrawings/fibs/IM704_FIBs.pdf",
            product=f'SCDOT Florida I-Beam {depth}"',
            section=FIB[depth], length_ft=90.0 if depth <= 54 else 110.0,
            n_straight=16 if depth <= 45 else 20, n_draped=8,
            fingerprints=["704-FIB", "FLORIDA I-BEAM", f'{depth}" FIB', "FIB"],
            extra_notes=["SCDOT IM704-FIB June 26 2024. FIB depths 36–96. 42\" top flange."],
        ))

    # --- NYSDOT ---
    specs.append(build_i_beam(
        "nysdot-aashto-type-ii", agency="NYSDOT", drawing="BD-PC14E / BD-PC26E",
        url="https://www.dot.ny.gov/main/business-center/engineering/cadd-info/drawings/bridge-detail-sheets-usc/PC-Prestressed-Concrete-Beams-and-Slab-Units-USC",
        product="NYSDOT AASHTO Type II I-Beam",
        section=AASHTO_I["type_ii"], length_ft=70.0, n_straight=12, n_draped=8,
        fingerprints=["BD-PC14E", "BD-PC26E", "BD-PS1", "BD-PS11", "NYSDOT", "AASHTO I-BEAM"],
        extra_notes=["NYSDOT BD-PC USC set (BD-PC1E–PC39E) and metric BD-PS1–PS14.",
                     "Embedded bearing plate details on BD-PC28E. Utility supports BD-PC20E."],
    ))
    specs.append(build_i_beam(
        "nysdot-nebt-39", agency="NYSDOT", drawing="BD-PC15E / BD-PC24E",
        url="https://www.dot.ny.gov/main/business-center/engineering/cadd-info/drawings/bridge-detail-sheets-usc/PC-Prestressed-Concrete-Beams-and-Slab-Units-USC",
        product='NYSDOT NEBT 39" Bulb Tee',
        section=NEBT[39], length_ft=90.0, n_straight=16, n_draped=8,
        fingerprints=["NEBT", "BD-PC15E", "BD-PC24E", "BD-PS9", "NEW ENGLAND BULB"],
        extra_notes=["New England Bulb Tee. Typical 42\" top flange. Plan/elevation on BD-PC24E."],
    ))
    specs.append(build_i_beam(
        "nysdot-pcef", agency="NYSDOT", drawing="BD-PC14E / BD-PC22E",
        url="https://www.dot.ny.gov/main/business-center/engineering/cadd-info/drawings/bridge-detail-sheets-usc/PC-Prestressed-Concrete-Beams-and-Slab-Units-USC",
        product="NYSDOT PCEF Prestressed I-Beam",
        section=AASHTO_I["type_iii"], length_ft=95.0, n_straight=16, n_draped=8,
        fingerprints=["PCEF", "BD-PC22E", "BD-PC23E"],
        extra_notes=["PCEF plan and elevation BD-PC22E; miscellaneous BD-PC23E."],
    ))

    # --- ODOT ---
    specs.append(build_i_beam(
        "odot-br325-type-ii", agency="ODOT", drawing="BR325",
        url="https://www.oregon.gov/odot/engineering/pages/drawings-bridge.aspx",
        product="ODOT Type II Prestressed Concrete Girder",
        section=AASHTO_I["type_ii"], length_ft=70.0, n_straight=12, n_draped=8,
        fingerprints=["BR325", "TYPE II", "OREGON STANDARD", "ODOT"],
        extra_notes=["ODOT BR300 series. CL bearing 7.5\" from girder end. 0.5\" Grade 270 LR, 31 kip jacking.",
                     "Handling: upright, supports within 2'-0\" of ends. Compiled set br300s_all.pdf."],
    ))
    specs.append(build_i_beam(
        "odot-br330-type-iii", agency="ODOT", drawing="BR330",
        url="https://www.oregon.gov/odot/engineering/pages/drawings-bridge.aspx",
        product="ODOT Type III Prestressed Concrete Girder",
        section=AASHTO_I["type_iii"], length_ft=90.0, n_straight=16, n_draped=8,
        fingerprints=["BR330", "TYPE III", "ODOT"],
        extra_notes=["ODOT BR330 Type III."],
    ))
    specs.append(build_i_beam(
        "odot-br335-type-iv", agency="ODOT", drawing="BR335",
        url="https://www.oregon.gov/odot/engineering/pages/drawings-bridge.aspx",
        product="ODOT Type IV Prestressed Concrete Girder",
        section=AASHTO_I["type_iv"], length_ft=110.0, n_straight=20, n_draped=10,
        fingerprints=["BR335", "TYPE IV", "ODOT"],
        extra_notes=["ODOT BR335 Type IV."],
    ))
    specs.append(build_i_beam(
        "odot-br340-type-v", agency="ODOT", drawing="BR340",
        url="https://www.oregon.gov/odot/engineering/pages/drawings-bridge.aspx",
        product="ODOT Type V Prestressed Concrete Girder",
        section=AASHTO_I["type_v"], length_ft=130.0, n_straight=24, n_draped=12,
        fingerprints=["BR340", "TYPE V", "ODOT"],
        extra_notes=["ODOT BR340 Type V. 42\" top flange."],
    ))

    # --- TDOT / generic AASHTO from SDG-5 ---
    specs.append(build_i_beam(
        "tdot-aashto-type-ii", agency="TDOT", drawing="SDG-5",
        url="https://www.tn.gov/content/dam/tn/tdot/structures/SDG-5-Precast_Prestressed_Beams-V12082023.pdf",
        product="TDOT AASHTO Type II Precast Prestressed Beam",
        section=AASHTO_I["type_ii"], length_ft=70.0, n_straight=12, n_draped=8,
        fingerprints=["TDOT", "SDG-5", "PRECAST PRESTRESSED BEAMS", "TYPE II"],
        extra_notes=["Tennessee SDG-5 Precast Prestressed Beams (Dec 2023)."],
    ))

    # --- KYTC Type 2 (Larue reference twin) ---
    from l25390 import build_l25390_spec
    kytc = build_l25390_spec(beam_mark="STD")
    kytc.id = "kytc-type-2-l25390"
    kytc.catalog_id = "kytc-type-2-l25390"
    kytc.source_agency = "KYTC"
    kytc.source_drawing = "L25390 / contract 255390 Type 2"
    kytc.source_url = "https://transportation.ky.gov/"
    kytc.extractor = "gold_corpus"
    kytc.notes = kytc.notes + ["FINGERPRINTS: L25390 | 255390 | LARUE | TYPE 2 | NOLIN | KYTC"]
    specs.append(kytc)

    # --- BOX BEAMS ---
    specs.append(build_box(
        "ncdot-pcbb-27", agency="NCDOT", drawing="PCBB2 / PCBB3 / pcbb2_24",
        url="https://connect.ncdot.gov/resources/Structures/Pages/Structure-Standards.aspx",
        product="NCDOT Prestressed Concrete Box Beam 3'-0\" x 2'-3\"",
        width_in=36.0, depth_in=27.0, length_ft=50.0, n_strands=14,
        fingerprints=["PCBB2", "PCBB3", "3'-0\" x 2'-3\"", "BOX BEAM UNIT", "NCDOT"],
        extra_notes=["NCDOT PCBB series: 3'-0\" wide units. PCBB1/PCBB8 used with PCBB2–7.",
                     "33\" and 39\" box beam standard design plans (Sept 2024)."],
    ))
    specs.append(build_box(
        "ncdot-pcbb-33", agency="NCDOT", drawing="PCBB4 / PCBB5 / pcbb4_24",
        url="https://connect.ncdot.gov/resources/Structures/Pages/Structure-Standards.aspx",
        product="NCDOT Prestressed Concrete Box Beam 3'-0\" x 2'-9\"",
        width_in=36.0, depth_in=33.0, length_ft=60.0, n_strands=16,
        fingerprints=["PCBB4", "PCBB5", "3'-0\" x 2'-9\"", "33\" BOX"],
        extra_notes=["NCDOT 33\" box beam superstructure standards."],
    ))
    specs.append(build_box(
        "ncdot-pcbb-39", agency="NCDOT", drawing="PCBB6 / PCBB7 / pcbb6_24",
        url="https://connect.ncdot.gov/resources/Structures/Pages/Structure-Standards.aspx",
        product="NCDOT Prestressed Concrete Box Beam 3'-0\" x 3'-3\"",
        width_in=36.0, depth_in=39.0, length_ft=70.0, n_strands=18,
        fingerprints=["PCBB6", "PCBB7", "3'-0\" x 3'-3\"", "39\" BOX"],
        extra_notes=["NCDOT 39\" box beam superstructure standards."],
    ))
    specs.append(build_box(
        "nysdot-box-3ft", agency="NYSDOT", drawing="BD-PC1E / BD-PC7E / BD-PC8E",
        url="https://www.dot.ny.gov/main/business-center/engineering/cadd-info/drawings/bridge-detail-sheets-usc/PC-Prestressed-Concrete-Beams-and-Slab-Units-USC",
        product="NYSDOT 3'-0\" Prestressed Box Beam",
        width_in=36.0, depth_in=27.0, length_ft=60.0, n_strands=16,
        fingerprints=["BD-PC1E", "BD-PC7E", "BD-PC8E", "3'-0\" PRESTRESSED", "ADJACENT BEAMS-BOX"],
        extra_notes=["Typical sections BD-PC1E. Plan/elevation BD-PC7E. Details BD-PC8E.",
                     "Transverse tendons & shear keys BD-PC10E."],
    ))
    specs.append(build_box(
        "nysdot-box-4ft", agency="NYSDOT", drawing="BD-PC2E / BD-PC4E",
        url="https://www.dot.ny.gov/main/business-center/engineering/cadd-info/drawings/bridge-detail-sheets-usc/PC-Prestressed-Concrete-Beams-and-Slab-Units-USC",
        product="NYSDOT 4'-0\" Prestressed Box Beam",
        width_in=48.0, depth_in=27.0, length_ft=70.0, n_strands=20,
        fingerprints=["BD-PC2E", "BD-PC4E", "4'-0\" PRESTRESSED", "SPREAD BOX"],
        extra_notes=["4'-0\" slab units & box typical sections BD-PC2E. Spread box BD-PC4E–PC6E."],
    ))
    specs.append(build_box(
        "scdot-abb-bii-36-80", agency="SCDOT", drawing="704-ABB.S080",
        url="https://www.scdot.org/content/dam/scdot-legacy/business/structuraldrawings/abb/IM704-ABB.pdf",
        product="SCDOT Adjacent Box Beam (SC) BII-36 — 80' span",
        width_in=36.0, depth_in=36.0, length_ft=80.0, n_strands=22,
        fingerprints=["704-ABB", "BII-36", "80' SPAN", "ADJACENT PRESTRESSED CONCRETE BOX"],
        extra_notes=["SCDOT IM704-ABB. 80' and 90' use (SC) BII-36; 100' uses (SC) BIII-36.",
                     "Roadway widths 27'-10\", 33'-10\", 39'-10\". Skew ±15° and 0°."],
    ))
    specs.append(build_box(
        "scdot-abb-bii-36-90", agency="SCDOT", drawing="704-ABB.S090",
        url="https://www.scdot.org/content/dam/scdot-legacy/business/structuraldrawings/abb/IM704-ABB.pdf",
        product="SCDOT Adjacent Box Beam (SC) BII-36 — 90' span",
        width_in=36.0, depth_in=36.0, length_ft=90.0, n_strands=24,
        fingerprints=["704-ABB.S090", "BII-36", "90' SPAN"],
        extra_notes=["SCDOT 90' adjacent box, BII-36."],
    ))
    specs.append(build_box(
        "scdot-abb-biii-36-100", agency="SCDOT", drawing="704-ABB.S100",
        url="https://www.scdot.org/content/dam/scdot-legacy/business/structuraldrawings/abb/IM704-ABB.pdf",
        product="SCDOT Adjacent Box Beam (SC) BIII-36 — 100' span",
        width_in=48.0, depth_in=36.0, length_ft=100.0, n_strands=28,
        fingerprints=["704-ABB.S100", "BIII-36", "100' SPAN"],
        extra_notes=["SCDOT 100' adjacent box uses (SC) BIII-36."],
    ))
    specs.append(build_box(
        "odot-br425", agency="ODOT", drawing="BR425",
        url="https://www.oregon.gov/odot/engineering/pages/drawings-bridge.aspx",
        product="ODOT Precast Prestressed Box BR425",
        width_in=48.0, depth_in=21.0, length_ft=40.0, n_strands=12,
        fingerprints=["BR425", "PRECAST PRESTRESSED BOX", "ODOT"],
        extra_notes=["ODOT BR400 series boxes: BR425, BR430, BR435, BR440, BR445."],
    ))
    specs.append(build_box(
        "odot-br430", agency="ODOT", drawing="BR430",
        url="https://www.oregon.gov/odot/engineering/pages/drawings-bridge.aspx",
        product="ODOT Precast Prestressed Box BR430",
        width_in=48.0, depth_in=27.0, length_ft=50.0, n_strands=16,
        fingerprints=["BR430", "ODOT"], extra_notes=["ODOT BR430 prestressed box."],
    ))
    specs.append(build_box(
        "odot-br435", agency="ODOT", drawing="BR435",
        url="https://www.oregon.gov/odot/engineering/pages/drawings-bridge.aspx",
        product="ODOT Precast Prestressed Box BR435",
        width_in=48.0, depth_in=33.0, length_ft=60.0, n_strands=18,
        fingerprints=["BR435", "ODOT"], extra_notes=["ODOT BR435 prestressed box."],
    ))
    specs.append(build_box(
        "odot-br440", agency="ODOT", drawing="BR440",
        url="https://www.oregon.gov/odot/engineering/pages/drawings-bridge.aspx",
        product="ODOT Precast Prestressed Box BR440",
        width_in=48.0, depth_in=42.0, length_ft=70.0, n_strands=22,
        fingerprints=["BR440", "ODOT"], extra_notes=["ODOT BR440 prestressed box."],
    ))
    specs.append(build_box(
        "txdot-bb-b28", agency="TxDOT", drawing="BB-B28-12",
        url="https://ftp.txdot.gov/pub/txdot-info/cmd/cserve/standard/bridge/BB-B28-12.pdf",
        product='TxDOT Prestressed Box Beam 28"',
        width_in=48.0, depth_in=28.0, length_ft=60.0, n_strands=18,
        fingerprints=["BB-B28", "TXDOT", "BOX BEAM"],
        extra_notes=["TxDOT bridge standards FTP. Adjacent boxes also BB-ABB28-06."],
    ))
    specs.append(build_box(
        "txdot-bb-b34", agency="TxDOT", drawing="BB-B34-12",
        url="https://ftp.txdot.gov/pub/txdot-info/cmd/cserve/standard/bridge/BB-B34-12.pdf",
        product='TxDOT Prestressed Box Beam 34"',
        width_in=48.0, depth_in=34.0, length_ft=70.0, n_strands=20,
        fingerprints=["BB-B34", "TXDOT"], extra_notes=["TxDOT 34\" prestressed box beam standard."],
    ))
    specs.append(build_box(
        "vdot-pscb-33x36", agency="VDOT", drawing="PSCB adjacent member",
        url="https://www.vdot.virginia.gov/doing-business/technical-guidance-and-support/technical-guidance-documents/structure-and-bridge/manuals-of-structure-and-bridge-acc/part5/Part5.pdf",
        product="VDOT Prestressed Adjacent Box 3'-0\" x 33\"",
        width_in=36.0, depth_in=33.0, length_ft=60.0, n_strands=16,
        fingerprints=["VDOT", "PSCB", "ADJACENT MEMBER", "BOX BEAM CELLS"],
        extra_notes=["VDOT Part 5: box widths 3'-0\" and 4'-0\"; depths 27\", 33\", 39\", 42\". PSCB-1 thru -62."],
    ))
    specs.append(build_box(
        "vdot-pscb-42x48", agency="VDOT", drawing="PSCB adjacent member 4'-0\"",
        url="https://www.vdot.virginia.gov/doing-business/technical-guidance-and-support/technical-guidance-documents/structure-and-bridge/manuals-of-structure-and-bridge-acc/part5/Part5.pdf",
        product="VDOT Prestressed Adjacent Box 4'-0\" x 42\"",
        width_in=48.0, depth_in=42.0, length_ft=80.0, n_strands=24,
        fingerprints=["VDOT", "4'-0\"", "42\""], extra_notes=["VDOT 4'-0\" x 42\" adjacent box. Economical 50–80 ft."],
    ))
    return specs


def export_gold(directory: Optional[Path] = None) -> Path:
    out = directory or GOLD_DIR
    out.mkdir(parents=True, exist_ok=True)
    specs = all_gold_specs()
    index = []
    for spec in specs:
        path = out / f"{spec.catalog_id or spec.id}.json"
        dumped = spec.model_dump()
        path.write_text(json.dumps(dumped, indent=2))
        index.append({
            "catalog_id": spec.catalog_id,
            "agency": spec.source_agency,
            "drawing": spec.source_drawing,
            "product_name": spec.product_name,
            "twin_type": spec.geometry.twin_type,
            "length_ft": spec.geometry.length_ft,
            "depth_in": spec.geometry.depth_in,
            "width_in": spec.geometry.width_in,
            "strands": len(spec.strands),
            "hardware": len(spec.hardware),
            "json": path.name,
        })
    (out / "_index.json").write_text(json.dumps({"count": len(index), "items": index}, indent=2))
    logger.info("exported %s gold BeamSpecs to %s", len(specs), out)
    return out


def load_gold_specs() -> List[BeamSpec]:
    if not GOLD_DIR.exists():
        return all_gold_specs()
    specs = []
    for path in sorted(GOLD_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            specs.append(BeamSpec(**json.loads(path.read_text())))
        except Exception:
            logger.exception("failed to load gold spec %s", path.name)
    return specs or all_gold_specs()


def _fingerprints(spec: BeamSpec) -> List[str]:
    for note in spec.notes:
        if note.startswith("FINGERPRINTS:"):
            return [p.strip().upper() for p in note.split(":", 1)[1].split("|") if p.strip()]
    blob = f"{spec.catalog_id} {spec.source_drawing} {spec.product_name} {spec.source_agency}"
    return [blob.upper()]


def match_corpus(filename: str, text: str) -> Optional[BeamSpec]:
    blob = f"{filename}\n{text}".upper()
    best: Tuple[int, Optional[BeamSpec]] = (0, None)
    for spec in load_gold_specs():
        hits = sum(1 for fp in _fingerprints(spec) if fp and fp in blob)
        if hits > best[0]:
            best = (hits, spec)
    if best[0] >= 2:
        return best[1]
    if best[0] == 1 and best[1] is not None:
        # Single strong drawing-number hit (BR325, PCG1, 704-ABB, BD-PC1E, L25390)
        fps = _fingerprints(best[1])
        strong = [fp for fp in fps if any(ch.isdigit() for ch in fp) and len(fp) >= 4]
        if any(fp in blob for fp in strong):
            return best[1]
    return None


def clone_spec(gold: BeamSpec, *, beam_id=None, job_id=None, pour_id=None,
               blueprint_id=None, beam_mark="B1") -> BeamSpec:
    data = gold.model_dump()
    data["id"] = BeamSpec().id
    data["beam_id"] = beam_id
    data["job_id"] = job_id
    data["pour_id"] = pour_id
    data["blueprint_id"] = blueprint_id
    data["beam_mark"] = beam_mark or gold.beam_mark
    data["status"] = "extracted"
    data["extractor"] = "gold_corpus"
    data["locked_by"] = ""
    data["locked_at"] = None
    spec = BeamSpec(**data)
    spec.marked_end_id = f"{spec.job_number} / {spec.beam_mark} / ME"
    spec.unmarked_end_id = f"{spec.job_number} / {spec.beam_mark} / UE"
    return spec


def detect_section(filename: str, text: str) -> Optional[str]:
    blob = f"{filename} {text}".upper()
    if re.search(r"BOX\s*BEAM|ADJACENT\s+BOX|PCBB|ABB-|BR42[5-9]|BR43[0-9]|BR44[0-5]", blob):
        return "box"
    if re.search(r"TYPE\s*VI|TYPE\s*6\b", blob):
        return "type_vi"
    if re.search(r"TYPE\s*V\b|TYPE\s*5\b", blob):
        return "type_v"
    if re.search(r"TYPE\s*IV|TYPE\s*4\b", blob):
        return "type_iv"
    if re.search(r"TYPE\s*III|TYPE\s*3\b", blob):
        return "type_iii"
    if re.search(r"TYPE\s*I\s*MOD", blob):
        return "type_i_mod"
    if re.search(r"TYPE\s*II|TYPE\s*2\b", blob):
        return "type_ii"
    if re.search(r"FLORIDA\s+I|FIB", blob):
        return "fib_54"
    if re.search(r"NEBT", blob):
        return "nebt_39"
    if re.search(r"TYPE\s*I\b", blob):
        return "type_i"
    return None


def spec_from_section(key: str, length_ft: float, *, beam_id=None, job_id=None,
                      pour_id=None, blueprint_id=None, beam_mark="B1") -> Optional[BeamSpec]:
    mapping = {
        "type_i": "scdot-aashto-type-i-mod",
        "type_i_mod": "scdot-aashto-type-i-mod",
        "type_ii": "ncdot-pcg-type-ii",
        "type_iii": "ncdot-pcg-type-iii",
        "type_iv": "ncdot-pcg-type-iv",
        "type_v": "odot-br340-type-v",
        "type_vi": "odot-br340-type-v",
        "fib_54": "scdot-fib-54",
        "nebt_39": "nysdot-nebt-39",
        "box": "ncdot-pcbb-33",
    }
    catalog_id = mapping.get(key)
    if not catalog_id:
        return None
    gold = next((s for s in all_gold_specs() if s.catalog_id == catalog_id), None)
    if not gold:
        return None
    spec = clone_spec(gold, beam_id=beam_id, job_id=job_id, pour_id=pour_id,
                      blueprint_id=blueprint_id, beam_mark=beam_mark)
    spec.geometry.length_ft = length_ft
    spec.extractor = "section_heuristic"
    spec.extractor_confidence = 0.62
    return spec


def corpus_summaries() -> List[Dict]:
    items = []
    for spec in load_gold_specs():
        items.append({
            "catalog_id": spec.catalog_id,
            "agency": spec.source_agency,
            "drawing": spec.source_drawing,
            "product_name": spec.product_name,
            "twin_type": spec.geometry.twin_type,
            "length_ft": spec.geometry.length_ft,
            "depth_in": spec.geometry.depth_in,
            "width_in": spec.geometry.width_in,
            "strands": len(spec.strands),
            "hardware": len(spec.hardware),
            "source_url": spec.source_url,
        })
    return items
