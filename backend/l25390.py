"""Larue County / L25390 (KYTC 255390) reference BeamSpec.

Source: KY 210 over Fork of Nolin River, Larue County, Contract 255390,
item 08632 PRECAST PC I BEAM TYPE 2 — 733 LF. Two-stage part-width
construction → 10 Type 2 girders @ 73'-4" (5 per stage).

Geometry follows AASHTO Type II / KYTC PC I-Beam Type 2:
36" deep, 18" bottom flange, 12" top flange, 6" web.
"""
from beam_spec import (
    BeamSpec, BeamGeometry, HardwareItem, StationRef, StrandItem, StirrupZone,
)


JOB_NUMBER = "L25390"
CONTRACT_ID = "255390"
PRODUCT_NAME = "KYTC Precast PC I-Beam Type 2"
LENGTH_FT = 73.333
DEPTH_IN = 36.0


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
    # Draped hold-downs at ~0.4L / 0.6L
    hd1, hd2 = round(length * 0.40, 2), round(length * 0.60, 2)
    ll1, ll2 = round(length * 0.20, 2), round(length * 0.80, 2)

    strand_offsets = [-6.0, -3.6, -1.2, 1.2, 3.6, 6.0]
    strands = []
    n = 1
    for _row in range(2):
        for off in strand_offsets:
            debond = 4.0 if abs(off) >= 5.5 and n <= 4 else 0.0
            strands.append(StrandItem(
                number=n,
                size="0.5in",
                detensioning="straight",
                area_in2=0.153,
                jacking_kip=31.0,
                soffit_in=2.0,
                offset_in=off,
                debond_me_ft=debond,
                debond_ue_ft=debond,
                notes="Bottom flange straight. Outer pair bituminous-debonded 4'-0\" each end." if debond else "",
                page=2,
            ))
            n += 1
    # 8 draped strands
    drape_off = [-4.8, -1.6, 1.6, 4.8, -4.8, -1.6, 1.6, 4.8]
    for i, off in enumerate(drape_off):
        strands.append(StrandItem(
            number=n,
            size="0.5in",
            detensioning="draped",
            area_in2=0.153,
            jacking_kip=31.0,
            soffit_in=2.0,
            drape_peak_in=18.0,
            hold_down_stations_ft=[hd1, hd2],
            offset_in=off,
            notes="Harped / draped. Hold-downs at 0.4L and 0.6L.",
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

    # Hold-downs
    hardware.append(_hw(
        "hold_down", "Hold-down 1", hd1, 2.5,
        face="bottom", type_code="HD-1", size="hold-down assembly",
        material="steel", notes="Draped-strand hold-down at 0.4L.",
        tolerance_in=1.0, page=2,
    ))
    hardware.append(_hw(
        "hold_down", "Hold-down 2", hd2, 2.5,
        face="bottom", type_code="HD-2", size="hold-down assembly",
        material="steel", notes="Draped-strand hold-down at 0.6L.",
        tolerance_in=1.0, page=2,
    ))

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

    return BeamSpec(
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
        hardware=hardware,
        stirrup_zones=stirrup_zones,
        notes=[
            f"Larue County KY 210 over Fork of Nolin River — Contract {CONTRACT_ID} (job {JOB_NUMBER}).",
            "Plan item 08632 PRECAST PC I BEAM TYPE 2, 733 LF (10 girders @ 73'-4\", two-stage part-width).",
            "Strands: 20 – ½\" Ø 270k low-relaxation (AASHTO M203). 12 straight + 8 draped.",
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
