"""Idempotent demo data seed: product types, a job/pour, 8 beds, sample beams, anomalies."""
from db import db
from models import (
    ProductType, Job, Pour, Bed, Beam, Anomaly, TensionReport, CamberReading,
    Inspection, BatchRecord, NCR, LicenseState,
    now_iso,
)
from tension import calc_theoretical_elongation, evaluate_tension


PRODUCT_TYPES = [
    dict(
        name="AASHTO Type III I-Beam",
        category="i_beam",
        depth_in=45,
        width_in=16,
        default_length_ft=90,
        description="Standard highway girder",
        blueprint={
            "cross_section": {
                "bottom_flange_width_in": 28,
                "bottom_flange_thickness_in": 8,
                "web_thickness_in": 7,
                "top_flange_width_in": 16,
                "top_flange_thickness_in": 7,
                "overall_depth_in": 45,
            },
            "lift_loops": [{"x_ft": 13}, {"x_ft": 77}],
            "inserts": [{"x_ft": 15, "side": "left"}, {"x_ft": 75, "side": "right"}],
            "tubes": [{"x_ft": 30, "diameter_in": 3}, {"x_ft": 60, "diameter_in": 3}],
            "drain_holes": [{"x_ft": 6, "diameter_in": 2}, {"x_ft": 84, "diameter_in": 2}],
            "hold_downs": [{"x_ft": 9}, {"x_ft": 18}, {"x_ft": 72}, {"x_ft": 81}],
            "bituminous_ends": [{"end": "start", "length_in": 18}, {"end": "end", "length_in": 18}],
            "strand_pattern": {
                "start_y_in": 5,
                "row_spacing_in": 4.5,
                "rows": [{"count": 4, "spacing_in": 4}, {"count": 4, "spacing_in": 4}],
            },
            "stirrups": {"start_ft": 2, "end_ft": 88, "spacing_in": 24, "cover_in": 2.5},
        },
    ),
    dict(
        name="AASHTO Type IV I-Beam",
        category="i_beam",
        depth_in=54,
        width_in=20,
        default_length_ft=110,
        description="Long-span girder",
        blueprint={
            "cross_section": {
                "bottom_flange_width_in": 32,
                "bottom_flange_thickness_in": 8.5,
                "web_thickness_in": 7,
                "top_flange_width_in": 20,
                "top_flange_thickness_in": 7.5,
                "overall_depth_in": 54,
            },
            "lift_loops": [{"x_ft": 16}, {"x_ft": 94}],
            "inserts": [{"x_ft": 22, "side": "left"}, {"x_ft": 88, "side": "right"}],
            "tubes": [{"x_ft": 38, "diameter_in": 4}, {"x_ft": 72, "diameter_in": 4}],
            "drain_holes": [{"x_ft": 8, "diameter_in": 2}, {"x_ft": 102, "diameter_in": 2}],
            "hold_downs": [{"x_ft": 12}, {"x_ft": 24}, {"x_ft": 86}, {"x_ft": 98}],
            "bituminous_ends": [{"end": "start", "length_in": 24}, {"end": "end", "length_in": 24}],
            "strand_pattern": {
                "start_y_in": 5.5,
                "row_spacing_in": 4.5,
                "rows": [{"count": 5, "spacing_in": 4}, {"count": 5, "spacing_in": 4}],
            },
            "stirrups": {"start_ft": 2, "end_ft": 108, "spacing_in": 18, "cover_in": 2.5},
        },
    ),
    dict(
        name="BT-72 Bulb Tee",
        category="i_beam",
        depth_in=72,
        width_in=42,
        default_length_ft=140,
        description="Bulb tee girder",
        blueprint={
            "cross_section": {
                "bottom_flange_width_in": 26,
                "bottom_flange_thickness_in": 9,
                "web_thickness_in": 8,
                "top_flange_width_in": 42,
                "top_flange_thickness_in": 8,
                "overall_depth_in": 72,
            },
            "lift_loops": [{"x_ft": 20}, {"x_ft": 120}],
            "inserts": [{"x_ft": 26, "side": "left"}, {"x_ft": 114, "side": "right"}],
            "tubes": [{"x_ft": 44, "diameter_in": 4}, {"x_ft": 96, "diameter_in": 4}],
            "drain_holes": [{"x_ft": 10, "diameter_in": 2}, {"x_ft": 130, "diameter_in": 2}],
            "hold_downs": [{"x_ft": 16}, {"x_ft": 30}, {"x_ft": 110}, {"x_ft": 124}],
            "bituminous_ends": [{"end": "start", "length_in": 30}, {"end": "end", "length_in": 30}],
            "strand_pattern": {
                "start_y_in": 6,
                "row_spacing_in": 4.75,
                "rows": [{"count": 6, "spacing_in": 4}, {"count": 6, "spacing_in": 4}, {"count": 4, "spacing_in": 4}],
            },
            "stirrups": {"start_ft": 3, "end_ft": 137, "spacing_in": 18, "cover_in": 3},
        },
    ),
    dict(
        name="Box Beam 48\"",
        category="box_beam",
        depth_in=27,
        width_in=48,
        default_length_ft=80,
        description="Adjacent box beam",
        blueprint={
            "cross_section": {
                "outer_width_in": 48,
                "outer_depth_in": 27,
                "wall_thickness_in": 4,
                "void_width_in": 30,
                "void_depth_in": 16,
            },
            "lift_loops": [{"x_ft": 12}, {"x_ft": 68}],
            "inserts": [{"x_ft": 18, "side": "left"}, {"x_ft": 62, "side": "right"}],
            "tubes": [{"x_ft": 28, "diameter_in": 3}, {"x_ft": 52, "diameter_in": 3}],
            "drain_holes": [{"x_ft": 5, "diameter_in": 2}, {"x_ft": 75, "diameter_in": 2}],
            "hold_downs": [{"x_ft": 10}, {"x_ft": 22}, {"x_ft": 58}, {"x_ft": 70}],
            "bituminous_ends": [{"end": "start", "length_in": 18}, {"end": "end", "length_in": 18}],
            "strand_pattern": {
                "start_y_in": 4.5,
                "row_spacing_in": 4,
                "rows": [{"count": 4, "spacing_in": 8}, {"count": 4, "spacing_in": 8}],
            },
            "stirrups": {"start_ft": 2, "end_ft": 78, "spacing_in": 24, "cover_in": 2.5},
        },
    ),
    dict(
        name="Box Beam 36\"",
        category="box_beam",
        depth_in=33,
        width_in=36,
        default_length_ft=70,
        description="Adjacent box beam",
        blueprint={
            "cross_section": {
                "outer_width_in": 36,
                "outer_depth_in": 33,
                "wall_thickness_in": 4,
                "void_width_in": 20,
                "void_depth_in": 22,
            },
            "lift_loops": [{"x_ft": 10}, {"x_ft": 60}],
            "inserts": [{"x_ft": 14, "side": "left"}, {"x_ft": 56, "side": "right"}],
            "tubes": [{"x_ft": 24, "diameter_in": 3}, {"x_ft": 46, "diameter_in": 3}],
            "drain_holes": [{"x_ft": 5, "diameter_in": 2}, {"x_ft": 65, "diameter_in": 2}],
            "hold_downs": [{"x_ft": 8}, {"x_ft": 18}, {"x_ft": 52}, {"x_ft": 62}],
            "bituminous_ends": [{"end": "start", "length_in": 18}, {"end": "end", "length_in": 18}],
            "strand_pattern": {
                "start_y_in": 5,
                "row_spacing_in": 4.5,
                "rows": [{"count": 3, "spacing_in": 7}, {"count": 3, "spacing_in": 7}, {"count": 2, "spacing_in": 7}],
            },
            "stirrups": {"start_ft": 2, "end_ft": 68, "spacing_in": 20, "cover_in": 2.5},
        },
    ),
]

BED_STATES = ["curing", "casting", "tensioning", "setup", "idle", "stripping", "complete", "curing"]


async def seed_plant():
    if await db.beds.count_documents({}) >= 8:
        return

    # Product types
    pt_ids = {}
    for p in PRODUCT_TYPES:
        pt = ProductType(**p)
        await db.product_types.insert_one(pt.model_dump())
        pt_ids[pt.name] = pt

    # Job + Pour
    job = Job(job_number="J-26-0412", name="I-70 Bridge Girders", customer="Kansas DOT", state_spec="KDOT")
    await db.jobs.insert_one(job.model_dump())
    pour = Pour(job_id=job.id, pour_number="P-118", pour_date=now_iso()[:10], concrete_mix="8500psi HPC", status="active")
    await db.pours.insert_one(pour.model_dump())

    pt_list = list(pt_ids.values())

    # 8 beds
    beds = []
    for i in range(1, 9):
        bed = Bed(
            bed_number=i,
            name=f"Bed {i}",
            length_ft=400.0 if i <= 4 else 300.0,
            status=BED_STATES[i - 1],
            current_pour_id=pour.id if BED_STATES[i - 1] in ("tensioning", "casting", "curing") else None,
        )
        beds.append(bed)
        await db.beds.insert_one(bed.model_dump())

    # Beams on active beds
    qc_states = ["passed", "in_progress", "pending", "hold", "failed", "passed", "in_progress", "pending"]
    beam_index = 0
    for bed in beds:
        if bed.status in ("idle",):
            continue
        num = 2 if bed.status in ("curing", "casting", "complete") else 1
        for pos in range(1, num + 1):
            pt = pt_list[beam_index % len(pt_list)]
            beam = Beam(
                mark=f"B{bed.bed_number}-{pos:02d}",
                bed_id=bed.id,
                pour_id=pour.id,
                job_id=job.id,
                product_type_id=pt.id,
                twin_type=pt.category,
                length_ft=pt.default_length_ft,
                position_on_bed=pos,
                status=bed.status,
                qc_state=qc_states[beam_index % len(qc_states)],
                traceability={
                    "strand_rolls": [f"SR-{bed.bed_number:02d}{pos:02d}-A", f"SR-{bed.bed_number:02d}{pos:02d}-B"],
                    "release_tag": f"REL-{bed.bed_number:02d}{pos:02d}",
                    "cast_sequence": pos,
                },
            )
            await db.beams.insert_one(beam.model_dump())
            beam_index += 1

            # Add an anomaly to a couple beams
            if beam.qc_state in ("hold", "failed"):
                an = Anomaly(
                    beam_id=beam.id,
                    type="crack",
                    severity="moderate" if beam.qc_state == "hold" else "major",
                    position={"x": beam.length_ft * 0.4, "y": 1.2, "z": 0.0},
                    length_in=6.5,
                    note="Transverse crack observed near midspan during strip.",
                    inspector="Tyler Chen",
                )
                await db.anomalies.insert_one(an.model_dump())

            # Camber reading
            cr = CamberReading(
                beam_id=beam.id,
                design_camber_in=1.75,
                measured_camber_in=1.9,
                required_strength_psi=5500,
                release_strength_psi=6100,
            )
            await db.camber_readings.insert_one(cr.model_dump())

            for section, note in [
                ("pre_pour", "Bed cleaned, soffit forms aligned, release applied."),
                ("strand", "Pattern verified against shop sheet; pull records matched."),
                ("concrete", "Batch ticket, slump, air, and cylinders recorded."),
                ("finish", "Edges rubbed and dimensions checked after strip."),
                ("camber", "3-point camber verified at release."),
                ("pre_delivery", "Marked end, dunnage, and shipping points approved."),
            ]:
                await db.inspections.insert_one(
                    Inspection(
                        beam_id=beam.id,
                        section=section,
                        status="hold" if beam.qc_state == "hold" and section == "finish" else "pass",
                        inspector="Dana Reyes",
                        notes=note,
                        data={"signature": "Dana Reyes", "verified_at": now_iso()},
                    ).model_dump()
                )

    # A tension report per active bed
    for bed in beds:
        if bed.status in ("tensioning", "casting", "curing"):
            theo = calc_theoretical_elongation(43.94, bed.length_ft, 0.217, 28500.0)
            measured = round(theo * 1.02, 3)
            var, within = evaluate_tension(theo, measured)
            tr = TensionReport(
                bed_id=bed.id,
                pour_id=pour.id,
                bed_length_ft=bed.length_ft,
                jacking_force_kip=43.94,
                theoretical_elongation_in=round(theo, 3),
                measured_elongation_in=measured,
                variance_pct=var,
                within_tolerance=within,
                num_strands=24,
            )
            await db.tension_reports.insert_one(tr.model_dump())

    active_beds = [bed for bed in beds if bed.current_pour_id]
    active_beams = await db.beams.find({"pour_id": pour.id}, {"_id": 0}).to_list(500)
    if active_beds:
        batch = BatchRecord(
            pour_id=pour.id,
            job_id=job.id,
            bed_ids=[bed.id for bed in active_beds],
            beam_ids=[beam["id"] for beam in active_beams],
            ticket_number="BT-118-01",
            mix_design="8500psi HPC",
            ambient_temp_f=78,
            concrete_temp_f=72,
            humidity_pct=58,
            wind_mph=7,
            weather="Partly Cloudy",
            ingredients=[
                {"name": "Type III Cement", "target_lb": 940, "actual_lb": 938},
                {"name": "Coarse Aggregate", "target_lb": 1780, "actual_lb": 1788},
                {"name": "Fine Aggregate", "target_lb": 1335, "actual_lb": 1330},
                {"name": "Water", "target_lb": 282, "actual_lb": 280},
            ],
            admixtures=[
                {"name": "Mid-range Water Reducer", "dosage_oz": 112},
                {"name": "Air Entrainer", "dosage_oz": 8},
            ],
            cylinders=[
                {"id": "CYL-118-A", "age_hr": 18, "strength_psi": 6120},
                {"id": "CYL-118-B", "age_hr": 28, "strength_psi": 6840},
            ],
            notes="Environmental snapshot captured from bed-side station.",
            created_by="Marcus Hill",
        )
        await db.batch_records.insert_one(batch.model_dump())

    hold_beam = next((beam for beam in active_beams if beam["qc_state"] in ("hold", "failed")), None)
    if hold_beam:
        linked_anomalies = await db.anomalies.find({"beam_id": hold_beam["id"]}, {"_id": 0}).to_list(50)
        ncr = NCR(
            code="NCR-26-011",
            title="Finish crack and edge repair review",
            severity="major",
            status="investigation",
            beam_id=hold_beam["id"],
            pour_id=pour.id,
            anomaly_ids=[item["id"] for item in linked_anomalies],
            source_measurement={"type": "finish", "detail": "Transverse crack outside finish tolerance"},
            investigation="QC and production reviewed strip timing, vibration pattern, and end release sequence.",
            corrective_action="Repair crack, add hold-down check at next setup, and re-inspect after patch cure.",
            owner="Dana Reyes",
            linked_photo_urls=["photo://beam-crack-01", "photo://beam-crack-02"],
            audit_trail=[
                {"status": "open", "user": "Tyler Chen", "note": "Created from failed finish review", "at": now_iso()},
                {"status": "investigation", "user": "Dana Reyes", "note": "Root-cause review started", "at": now_iso()},
            ],
        )
        await db.ncrs.insert_one(ncr.model_dump())

    await db.licenses.insert_one(
        LicenseState(
            status="trial",
            tier="trial",
            expires_at=now_iso()[:10],
            feature_flags={
                "digital_twin": True,
                "package_export": True,
                "ncr": True,
                "batch_plant": True,
                "licensing": True,
                "command_board": True,
                "blueprint_intelligence": True,
                "advanced_exports": False,
            },
        ).model_dump()
    )
