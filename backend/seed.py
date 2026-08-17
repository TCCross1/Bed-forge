"""Idempotent demo data seed: product types, a job/pour, 8 beds, sample beams, anomalies."""
from db import db
from models import (
    ProductType, Job, Pour, Bed, Beam, Anomaly, TensionReport, CamberReading,
    now_iso,
)
from tension import calc_theoretical_elongation, evaluate_tension


PRODUCT_TYPES = [
    dict(name="AASHTO Type III I-Beam", category="i_beam", depth_in=45, width_in=16, default_length_ft=90, description="Standard highway girder"),
    dict(name="AASHTO Type IV I-Beam", category="i_beam", depth_in=54, width_in=20, default_length_ft=110, description="Long-span girder"),
    dict(name="BT-72 Bulb Tee", category="i_beam", depth_in=72, width_in=42, default_length_ft=140, description="Bulb tee girder"),
    dict(name="Box Beam 48\"", category="box_beam", depth_in=27, width_in=48, default_length_ft=80, description="Adjacent box beam"),
    dict(name="Box Beam 36\"", category="box_beam", depth_in=33, width_in=36, default_length_ft=70, description="Adjacent box beam"),
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
                marked_end_in=0.35,
                midspan_in=1.9,
                unmarked_end_in=0.40,
                required_strength_psi=5500,
                release_strength_psi=6100,
            )
            await db.camber_readings.insert_one(cr.model_dump())

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
