"""Larue County / L25390 (KYTC 255390) reference BeamSpec.

Source: KY 210 over Fork of Nolin River, Larue County, Contract 255390,
item 08632 PRECAST PC I BEAM TYPE 2 — 733 LF. Two-stage part-width
construction → 10 Type 2 girders @ 73'-4" (5 per stage).

Geometry follows AASHTO Type II / KYTC PC I-Beam Type 2:
36" deep, 18" bottom flange, 12" top flange, 6" web.
"""
from beam_spec import (
    BeamSpec, BeamGeometry, HardwareItem, StationRef, StrandItem, StirrupZone, HoldDownItem,
    ensure_tension_geometry,
)


JOB_NUMBER = "L25390"
CONTRACT_ID = "255390"
PRODUCT_NAME = "KYTC Precast PC I-Beam Type 2"
LENGTH_FT = 73.333
DEPTH_IN = 36.0
# Casting bed layout — Spans 1 & 3. Stations from Marked End.
HOLD_DOWN_ME_FT = 29.333  # 29'-4"
HOLD_DOWN_UE_FT = 44.0    # 44'-0"
HOLD_DOWN_TYPE = "Dayton/Richmond H-56-S"
DEMO_MARK = "L25390-B1"
HOLD_DOWN_CLAMP_OFFSET_IN = 2.0  # H-56-S pair, ±2" from web centerline (matches draped strands)


def _hw(kind, name, station_ft, height_in, *, offset_in=0.0, face="top",
        type_code="", size="", material="", end_station_ft=None, notes="",
        tolerance_in=1.0, quantity=1, page=1):
    return HardwareItem(
        kind=kind,
        name=name,
        type_code=type_code,
        quantity=quantity,
        size=size,
        material=material,
        position=StationRef(
            station_ft=station_ft,
            offset_in=offset_in,
            height_from_soffit_in=height_in,
            face=face,
            page=page,
            source_note=f"{JOB_NUMBER} shop drawing p.{page}",
        ),
        end_station_ft=end_station_ft,
        notes=notes,
        tolerance_in=tolerance_in,
    )


def build_l25390_spec(beam_id=None, job_id=None, pour_id=None, blueprint_id=None,
                      beam_mark="B1") -> BeamSpec:
    length = LENGTH_FT
    hd1, hd2 = HOLD_DOWN_ME_FT, HOLD_DOWN_UE_FT
    ll1, ll2 = round(length * 0.20, 2), round(length * 0.80, 2)

    # End-view pattern (looking at Marked End). 2" PCI grid.
    # Straight: 12 strands in the 18" bottom flange, rows at 2" and 4" soffit.
    # Draped: 8 strands in the 6" web at ±2" (H-56-S pitch). HIGH at ends,
    # depressed through hold-downs. Stressed in the draped position.
    straight_offsets = [-5.0, -3.0, -1.0, 1.0, 3.0, 5.0]
    strands = []
    n = 1
    for row, soffit in enumerate((2.0, 4.0), start=1):
        for col, off in enumerate(straight_offsets, start=1):
            debond = 4.0 if row == 1 and abs(off) >= 5.0 else 0.0
            strands.append(StrandItem(
                number=n,
                row=row,
                column=col,
                size="0.5in",
                detensioning="straight",
                draped=False,
                area_in2=0.153,
                jacking_kip=31.0,
                soffit_in=soffit,
                offset_in=off,
                x_in=off,
                y_in=soffit,
                debond_me_ft=debond,
                debond_ue_ft=debond,
                notes="Bottom flange straight. Outer pair bituminous-debonded 4'-0\" each end." if debond else "Bottom flange straight.",
                page=2,
            ))
            n += 1
    draped_rows = (
        (18.0, 2.0),
        (22.0, 4.0),
        (26.0, 6.0),
        (30.0, 8.0),
    )
    for end_y, hold_y in draped_rows:
        for off in (-2.0, 2.0):
            strands.append(StrandItem(
                number=n,
                size="0.5in",
                detensioning="draped",
                draped=True,
                area_in2=0.153,
                jacking_kip=31.0,
                soffit_in=hold_y,
                hold_down_y_in=hold_y,
                drape_peak_in=end_y,
                y_in=end_y,
                offset_in=off,
                x_in=off,
                hold_down_stations_ft=[hd1, hd2],
                notes="Harped / draped. Stressed in draped position. H-56-S hold-downs at 29'-4\" and 44'-0\" ME.",
                page=2,
            ))
            n += 1

    hardware = []

    # Bituminous paint zones (debond)
    hardware.append(_hw(
        "bituminous_zone", "Bituminous / debond ME", 0.0, 2.0,
        face="bottom", size="4'-0\"", material="bituminous coating",
        end_station_ft=4.0, notes="Strands 1–4 cut/debonded. Paint zone at Marked End.",
        tolerance_in=2.0, page=2,
    ))
    hardware.append(_hw(
        "bituminous_zone", "Bituminous / debond UE", length - 4.0, 2.0,
        face="bottom", size="4'-0\"", material="bituminous coating",
        end_station_ft=length, notes="Strands 1–4 cut/debonded. Paint zone at Unmarked End.",
        tolerance_in=2.0, page=2,
    ))

    # Lift loops
    hardware.append(_hw(
        "lift_loop", "Lift loop ME", ll1, 36.0,
        face="top", type_code="LL-1", size="1\" 7-wire loop", material="Grade 270 strand",
        notes="0.2L from Marked End. 4\" projection above top flange.",
        tolerance_in=1.0, page=1,
    ))
    hardware.append(_hw(
        "lift_loop", "Lift loop UE", ll2, 36.0,
        face="top", type_code="LL-2", size="1\" 7-wire loop", material="Grade 270 strand",
        notes="0.2L from Unmarked End. 4\" projection above top flange.",
        tolerance_in=1.0, page=1,
    ))

    # F-64 inserts — top flange, 3" from each edge, 8 ft spacing
    insert_stations = [8, 16, 24, 32, 40, 48, 56, 64]
    for i, st in enumerate(insert_stations, start=1):
        for side, off in (("L", -3.5), ("R", 3.5)):
            hardware.append(_hw(
                "insert", f"F-64 {side}{i}", float(st), 33.0,
                offset_in=off, face="top", type_code="F-64",
                size="F-64 ferrule 3/4\"-10", material="malleable insert",
                notes="Deck tie / shear insert. Height ~3\" below top of flange.",
                tolerance_in=0.5, page=3,
            ))

    # Drain holes / tubes
    hardware.append(_hw(
        "drain", "Drain hole 1", round(length * 0.28, 2), 3.0,
        face="bottom", type_code="DR-1", size="2\" Ø", material="PVC sleeve",
        notes="Bottom-flange drain / weep.", tolerance_in=1.0, page=1,
    ))
    hardware.append(_hw(
        "drain", "Drain hole 2", round(length * 0.72, 2), 3.0,
        face="bottom", type_code="DR-2", size="2\" Ø", material="PVC sleeve",
        notes="Bottom-flange drain / weep.", tolerance_in=1.0, page=1,
    ))
    hardware.append(_hw(
        "downspout", "Deck drain sleeve ME", 6.0, 36.0,
        offset_in=4.0, face="top", type_code="DS-1", size="4\" Ø",
        material="PVC", notes="Matches plan quantity: 2 deck drains on structure.",
        tolerance_in=1.0, page=1,
    ))
    hardware.append(_hw(
        "tube", "Utility sleeve", round(length / 2, 2), 18.0,
        face="web_left", type_code="TB-1", size="3\" Ø", material="PVC sleeve",
        notes="Transverse utility sleeve through web.", tolerance_in=1.0, page=3,
    ))

    # Tie-rod openings (diaphragm)
    hardware.append(_hw(
        "tie_rod", "Tie-rod ME", 1.5, 18.0,
        face="web_left", type_code="TR-1", size="2-1/2\" Ø", material="void tube",
        notes="Diaphragm tie-rod opening, Marked End.", tolerance_in=0.5, page=3,
    ))
    hardware.append(_hw(
        "tie_rod", "Tie-rod UE", length - 1.5, 18.0,
        face="web_left", type_code="TR-2", size="2-1/2\" Ø", material="void tube",
        notes="Diaphragm tie-rod opening, Unmarked End.", tolerance_in=0.5, page=3,
    ))

    # Hold-downs — I-beam clamps, pair at each harped station
    hardware.append(_hw(
        "hold_down", "Hold-down 1", hd1, 2.5,
        face="bottom", type_code="H-56-S", size=HOLD_DOWN_TYPE,
        material="steel", notes="Dayton/Richmond H-56-S pair at 29'-4\" from Marked End. Draped strands depressed here.",
        tolerance_in=1.0, quantity=2, page=2,
    ))
    hardware.append(_hw(
        "hold_down", "Hold-down 2", hd2, 2.5,
        face="bottom", type_code="H-56-S", size=HOLD_DOWN_TYPE,
        material="steel", notes="Dayton/Richmond H-56-S pair at 44'-0\" from Marked End. Draped strands depressed here.",
        tolerance_in=1.0, quantity=2, page=2,
    ))
    hold_downs = [
        HoldDownItem(
            station_from_marked_end=hd1,
            height=2.5,
            offset_in=HOLD_DOWN_CLAMP_OFFSET_IN,
            type_spec=HOLD_DOWN_TYPE,
            quantity_at_station=2,
            orientation="transverse",
            notes="Dayton/Richmond H-56-S. Casting bed layout Spans 1 & 3 — 29'-4\" ME. Pair at ±2\" web.",
            page=2,
        ),
        HoldDownItem(
            station_from_marked_end=hd2,
            height=2.5,
            offset_in=HOLD_DOWN_CLAMP_OFFSET_IN,
            type_spec=HOLD_DOWN_TYPE,
            quantity_at_station=2,
            orientation="transverse",
            notes="Dayton/Richmond H-56-S. Casting bed layout Spans 1 & 3 — 44'-0\" ME. Pair at ±2\" web.",
            page=2,
        ),
    ]

    # Projecting rebar at unmarked end (continuity)
    hardware.append(_hw(
        "projecting_rebar", "Projecting bars UE", length, 18.0,
        face="end_ue", type_code="PR-UE", size="4-#6 x 12\"",
        material="Grade 60", notes="Continuity / diaphragm projection at Unmarked End.",
        tolerance_in=0.5, quantity=4, page=3,
    ))

    # Diaphragm angles / plates
    hardware.append(_hw(
        "diaphragm", "Diaphragm angle L/3", round(length / 3, 2), 18.0,
        face="web_left", type_code="L4x4x3/8", size="4x4x3/8 angle",
        material="A36", notes="Intermediate diaphragm hardware.",
        tolerance_in=1.0, page=3,
    ))
    hardware.append(_hw(
        "diaphragm", "Diaphragm angle 2L/3", round(2 * length / 3, 2), 18.0,
        face="web_right", type_code="L4x4x3/8", size="4x4x3/8 angle",
        material="A36", notes="Intermediate diaphragm hardware.",
        tolerance_in=1.0, page=3,
    ))

    # Bearing plates
    hardware.append(_hw(
        "bearing_plate", "Bearing plate ME", 0.5, 0.0,
        face="bottom", type_code="BRG-ME", size="3/4\" x 8\" x 16\"",
        material="A36 plate", notes="Elastomeric bearing seat at Marked End.",
        tolerance_in=0.25, page=1,
    ))
    hardware.append(_hw(
        "bearing_plate", "Bearing plate UE", length - 0.5, 0.0,
        face="bottom", type_code="BRG-UE", size="3/4\" x 8\" x 16\"",
        material="A36 plate", notes="Elastomeric bearing seat at Unmarked End.",
        tolerance_in=0.25, page=1,
    ))

    stirrup_zones = [
        StirrupZone(from_ft=0.0, to_ft=6.0, spacing_in=4.0, bar_size="#3",
                    shape="hoop", notes="Confined end-zone hoops — Marked End", page=2),
        StirrupZone(from_ft=6.0, to_ft=length - 6.0, spacing_in=8.0, bar_size="#3",
                    shape="stirrup", notes="Typical spacing", page=2),
        StirrupZone(from_ft=length - 6.0, to_ft=length, spacing_in=4.0, bar_size="#3",
                    shape="hoop", notes="Confined end-zone hoops — Unmarked End", page=2),
    ]

    spec = BeamSpec(
        beam_id=beam_id,
        job_id=job_id,
        pour_id=pour_id,
        blueprint_id=blueprint_id,
        job_number=JOB_NUMBER,
        beam_mark=beam_mark,
        product_name=PRODUCT_NAME,
        state_spec="KYTC 2024",
        geometry=BeamGeometry(
            twin_type="i_beam",
            length_ft=length,
            depth_in=DEPTH_IN,
            width_in=18.0,
            top_flange_width_in=12.0,
            top_flange_thick_in=6.0,
            bot_flange_width_in=18.0,
            bot_flange_thick_in=6.0,
            web_thick_in=6.0,
            product_name=PRODUCT_NAME,
        ),
        marked_end_id=f"{JOB_NUMBER} / {beam_mark} / ME",
        unmarked_end_id=f"{JOB_NUMBER} / {beam_mark} / UE",
        strands=strands,
        hold_downs=hold_downs,
        hardware=hardware,
        stirrup_zones=stirrup_zones,
        notes=[
            f"Larue County KY 210 over Fork of Nolin River — Contract {CONTRACT_ID} (job {JOB_NUMBER}).",
            "Plan item 08632 PRECAST PC I BEAM TYPE 2, 733 LF (10 girders @ 73'-4\", two-stage part-width).",
            "Strands: 20 – ½\" Ø 270k low-relaxation (AASHTO M203). 12 straight in bottom flange + 8 draped in web.",
            "End view: straight at 2\"/4\" soffit on a 2\" grid (±1,3,5\"); draped at ±2\" (web) rising to 18/22/26/30\".",
            "Draped strands stressed in the draped position. Hold-downs: Dayton/Richmond H-56-S at 29'-4\" and 44'-0\" ME (qty 2 each).",
            "Detensioning sequence per shop drawing — cut outer straight strands after release; draped remain until hold-downs are released.",
            "Outer 4 straight strands bituminous-debonded 4'-0\" each end; cut and recessed after release.",
            "Release strength 4,500 psi. Design f'c = 7,000 psi. Design camber 1.25\".",
            "Finish: trowel top flange; as-cast sides and soffit; KYTC concrete sealer on exterior girders.",
            "Marked End = stamped beam mark facing traffic stage as shown on erection plan.",
        ],
        special_finishes=[
            "Trowel finish top flange",
            "As-cast sides / soffit",
            "KYTC concrete sealer — exterior girders, exterior face and bottom",
        ],
        status="extracted",
        extractor="l25390_reference",
        extractor_confidence=0.92,
        source_pages=3,
    )
    return ensure_tension_geometry(spec)


CAPTURE_STRAND_KEYS = (
    "measured_elongation", "jacking_force", "variance_pct", "within_tolerance",
    "na", "recorded_by", "recorded_at", "theoretical_elongation", "notes",
)
CAPTURE_HD_KEYS = ("status", "verified_by", "verified_at")


def merge_l25390_pattern(existing: dict, fresh: BeamSpec) -> dict:
    """Refresh strand/hold-down geometry from the shop drawing; keep capture data by strand number."""
    old_by_num = {int(s.get("number")): s for s in (existing.get("strands") or []) if s.get("number") is not None}
    merged_strands = []
    for strand in fresh.strands:
        row = strand.model_dump()
        prev = old_by_num.get(strand.number)
        if prev:
            row["id"] = prev.get("id") or row["id"]
            row["strand_id"] = prev.get("strand_id") or row["id"]
            for key in CAPTURE_STRAND_KEYS:
                if prev.get(key) not in (None, ""):
                    row[key] = prev[key]
        merged_strands.append(row)
    old_hds = list(existing.get("hold_downs") or [])
    merged_hds = []
    for i, item in enumerate(fresh.hold_downs):
        row = item.model_dump()
        if i < len(old_hds):
            row["id"] = old_hds[i].get("id") or row["id"]
            for key in CAPTURE_HD_KEYS:
                if old_hds[i].get(key) not in (None, "", "pending"):
                    row[key] = old_hds[i][key]
            if old_hds[i].get("notes") and "H-56" not in (old_hds[i].get("notes") or ""):
                row["notes"] = f"{row['notes']} {old_hds[i]['notes']}".strip()
        merged_hds.append(row)
    dumped = fresh.model_dump()
    dumped["id"] = existing.get("id") or dumped["id"]
    dumped["beam_id"] = existing.get("beam_id") or dumped.get("beam_id")
    dumped["job_id"] = existing.get("job_id") or dumped.get("job_id")
    dumped["status"] = existing.get("status") or dumped["status"]
    dumped["locked_by"] = existing.get("locked_by") or dumped.get("locked_by")
    dumped["locked_at"] = existing.get("locked_at") or dumped.get("locked_at")
    dumped["created_at"] = existing.get("created_at") or dumped.get("created_at")
    dumped["strands"] = merged_strands
    dumped["hold_downs"] = merged_hds
    hardware = list(existing.get("hardware") or dumped.get("hardware") or [])
    for item in hardware:
        if item.get("kind") == "hold_down":
            item["type_code"] = "H-56-S"
            item["size"] = HOLD_DOWN_TYPE
            st = (item.get("position") or {}).get("station_ft")
            if st is not None and abs(float(st) - HOLD_DOWN_ME_FT) < 1.5:
                item["position"]["station_ft"] = HOLD_DOWN_ME_FT
                item["notes"] = "Dayton/Richmond H-56-S pair at 29'-4\" from Marked End. Draped strands depressed here."
            elif st is not None and abs(float(st) - HOLD_DOWN_UE_FT) < 1.5:
                item["position"]["station_ft"] = HOLD_DOWN_UE_FT
                item["notes"] = "Dayton/Richmond H-56-S pair at 44'-0\" from Marked End. Draped strands depressed here."
    dumped["hardware"] = hardware
    dumped["notes"] = fresh.notes
    return dumped
