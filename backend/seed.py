"""Idempotent demo data seed: product types, a job/pour, 8 beds, sample beams, anomalies."""
import logging
from datetime import datetime, timezone
from db import db
from models import (
    ProductType, Job, Pour, Bed, Beam, Anomaly, TensionReport, CamberReading,
    BedAssignment, CompanySettings, MixDesign, now_iso,
)
from tension import calc_theoretical_elongation, evaluate_tension
from bed_layout import map_production_status, pack_stations

logger = logging.getLogger(__name__)


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
                production_status=map_production_status(bed.status, qc_states[beam_index % len(qc_states)]),
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


async def seed_l25390():
    """Idempotent Larue County / L25390 Type 2 I-beam spec for the digital twin.

    Always refreshes strand pattern + H-56-S hold-downs from the shop-drawing
    gold standard so the tension twin cannot drift to a generic layout.
    Locks the spec to a dedicated demo beam (L25390-B1) on a tensioning bed.
    """
    try:
        from models import Job
        from l25390 import DEMO_MARK, LENGTH_FT, build_l25390_spec, merge_l25390_pattern

        job = await db.jobs.find_one({"job_number": "L25390"}, {"_id": 0})
        if not job:
            job_obj = Job(
                job_number="L25390",
                name="KY 210 over Fork of Nolin River",
                customer="KYTC / Larue County",
                state_spec="KYTC 2024",
            )
            job = job_obj.model_dump()
            await db.jobs.insert_one(job)

        bed = await db.beds.find_one({"status": "tensioning"}, {"_id": 0})
        if not bed:
            bed = await db.beds.find_one({}, {"_id": 0})
        if not bed:
            logger.warning("seed_l25390 skipped — no beds")
            return

        beam = await db.beams.find_one({"mark": DEMO_MARK}, {"_id": 0})
        if not beam:
            occupants = await db.beams.find({"bed_id": bed["id"]}, {"_id": 0}).to_list(50)
            position = max([int(b.get("position_on_bed") or 0) for b in occupants] or [0]) + 1
            pt = await db.product_types.find_one({"category": "i_beam"}, {"_id": 0})
            beam_obj = Beam(
                mark=DEMO_MARK,
                bed_id=bed["id"],
                pour_id=bed.get("current_pour_id") or (occupants[0].get("pour_id") if occupants else None),
                job_id=job["id"],
                product_type_id=(pt or {}).get("id"),
                twin_type="i_beam",
                length_ft=LENGTH_FT,
                position_on_bed=position,
                status="tensioning",
                qc_state="in_progress",
                production_status="forming",
            )
            beam = beam_obj.model_dump()
            await db.beams.insert_one(beam)
            logger.info("seeded demo beam mark=%s bed=%s", DEMO_MARK, bed.get("bed_number"))
        else:
            await db.beams.update_one({"id": beam["id"]}, {"$set": {
                "length_ft": LENGTH_FT,
                "job_id": job["id"],
                "twin_type": "i_beam",
                "bed_id": beam.get("bed_id") or bed["id"],
            }})
            beam = await db.beams.find_one({"id": beam["id"]}, {"_id": 0})

        beam_id = beam["id"]
        mark = DEMO_MARK
        bed_id = beam.get("bed_id") or bed["id"]

        today = datetime.now(timezone.utc).date().isoformat()
        if not await db.bed_assignments.find_one({"beam_id": beam_id}):
            rec = BedAssignment(
                bed_id=bed_id,
                beam_id=beam_id,
                job_id=job["id"],
                pour_id=beam.get("pour_id"),
                position_on_bed=int(beam.get("position_on_bed") or 1),
                station_ft=8.0,
                marked_end_toward="header",
                scheduled_date=today,
                scheduled_end_date=today,
                production_status=beam.get("production_status") or "forming",
                created_by="system-seed",
            )
            await db.bed_assignments.insert_one(rec.model_dump())
        await db.beds.update_one(
            {"id": bed_id},
            {"$set": {"active_beam_id": beam_id, "updated_at": now_iso()}},
        )
        await db.strand_roll_assignments.update_many(
            {"bed_id": bed_id},
            {"$addToSet": {"beam_ids": beam_id}},
        )

        fresh = build_l25390_spec(
            beam_id=beam_id,
            job_id=job["id"],
            pour_id=beam.get("pour_id"),
            beam_mark=mark,
        )
        existing = await db.beam_specs.find_one({"job_number": "L25390"}, {"_id": 0})
        spec_id = None
        if existing:
            dumped = merge_l25390_pattern(existing, fresh)
            dumped["review_notes"] = (
                existing.get("review_notes")
                or "Seeded from Larue County contract 255390 / L25390 Type 2 shop-drawing reference."
            )
            spec_id = existing["id"]
            await db.beam_specs.update_one({"id": spec_id}, {"$set": {
                "strands": dumped["strands"],
                "hold_downs": dumped["hold_downs"],
                "hardware": dumped["hardware"],
                "notes": dumped["notes"],
                "geometry": dumped["geometry"],
                "review_notes": dumped["review_notes"],
                "beam_id": beam_id,
                "beam_mark": mark,
                "job_id": job["id"],
                "pour_id": beam.get("pour_id"),
                "marked_end_id": dumped.get("marked_end_id") or fresh.marked_end_id,
                "unmarked_end_id": dumped.get("unmarked_end_id") or fresh.unmarked_end_id,
            }})
            logger.info("l25390 strand pattern refreshed spec=%s strands=%s beam=%s", spec_id, len(dumped.get("strands") or []), mark)
        else:
            fresh.status = "locked"
            fresh.locked_by = "system-seed"
            fresh.locked_at = now_iso()
            fresh.review_notes = "Seeded from Larue County contract 255390 / L25390 Type 2 shop-drawing reference."
            dumped = fresh.model_dump()
            await db.beam_specs.insert_one(dumped)
            spec_id = fresh.id
            logger.info("l25390 spec locked spec=%s beam=%s", spec_id, mark)

        if spec_id:
            await db.beams.update_many(
                {"spec_id": spec_id, "mark": {"$ne": mark}},
                {"$unset": {"spec_id": ""}},
            )
            await db.beams.update_one({"id": beam_id}, {"$set": {"spec_id": spec_id}})
    except Exception:
        logger.exception("seed_l25390 failed")


async def seed_bed_assignments():
    """Idempotent BedAssignment rows for today's plant plus a drag-pool of planned beams."""
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        existing = await db.bed_assignments.count_documents({})
        beds = await db.beds.find({}, {"_id": 0}).sort("bed_number", 1).to_list(20)
        beams = await db.beams.find({}, {"_id": 0}).to_list(2000)
        if existing == 0:
            by_bed = {}
            for beam in beams:
                if not beam.get("bed_id"):
                    continue
                by_bed.setdefault(beam["bed_id"], []).append(beam)
            for bed in beds:
                occupants = sorted(by_bed.get(bed["id"], []), key=lambda b: b.get("position_on_bed") or 0)
                lengths = [float(b.get("length_ft") or 0) for b in occupants]
                try:
                    stations = pack_stations(bed.get("length_ft") or 300, lengths)
                except ValueError:
                    logger.warning("seed layout overflow bed=%s; packing sequentially from header", bed.get("bed_number"))
                    stations = [8.0]
                    cursor = 8.0
                    for length in lengths[1:]:
                        cursor += length + 2.5
                        stations.append(round(cursor, 3))
                active = None
                for index, beam in enumerate(occupants):
                    status = map_production_status(beam.get("status"), beam.get("qc_state"))
                    rec = BedAssignment(
                        bed_id=bed["id"],
                        beam_id=beam["id"],
                        job_id=beam.get("job_id"),
                        pour_id=beam.get("pour_id"),
                        position_on_bed=index + 1,
                        station_ft=stations[index] if index < len(stations) else 8.0,
                        marked_end_toward="header",
                        scheduled_date=today,
                        scheduled_end_date=today,
                        production_status=status,
                        created_by="system-seed",
                    )
                    await db.bed_assignments.insert_one(rec.model_dump())
                    await db.beams.update_one({"id": beam["id"]}, {"$set": {"production_status": status, "position_on_bed": index + 1}})
                    if beam.get("qc_state") == "in_progress" or (not active and status in ("forming", "stressed", "poured")):
                        active = beam["id"]
                if active:
                    await db.beds.update_one({"id": bed["id"]}, {"$set": {"active_beam_id": active, "updated_at": now_iso()}})
            logger.info("seeded bed assignments for %s beds on %s", len(beds), today)

        job = await db.jobs.find_one({}, {"_id": 0})
        pt = await db.product_types.find_one({}, {"_id": 0})
        if job and not await db.beams.find_one({"mark": "PLAN-01"}):
            pour = await db.pours.find_one({"job_id": job["id"]}, {"_id": 0})
            for i in range(1, 5):
                beam = Beam(
                    mark=f"PLAN-{i:02d}",
                    bed_id="",
                    pour_id=(pour or {}).get("id"),
                    job_id=job["id"],
                    product_type_id=(pt or {}).get("id"),
                    twin_type=(pt or {}).get("category") or "i_beam",
                    length_ft=float((pt or {}).get("default_length_ft") or 90),
                    position_on_bed=0,
                    status="idle",
                    qc_state="pending",
                    production_status="planned",
                )
                await db.beams.insert_one(beam.model_dump())
            logger.info("seeded planner pool beams PLAN-01..04 for job=%s", job.get("job_number"))
    except Exception:
        logger.exception("seed_bed_assignments failed")


async def seed_strand_rolls():
    """Idempotent mill-traceable rolls so seeded beds can pass the tensioning gate."""
    try:
        beds = await db.beds.find({}, {"_id": 0}).sort("bed_number", 1).to_list(20)
        if not beds:
            return
        from models import StrandRoll, StrandRollAssignment
        for bed in beds:
            if not bed.get("current_pour_id") and bed.get("status") in ("idle",):
                continue
            heat = f"H270-SEED-{bed.get('bed_number')}"
            if await db.strand_rolls.find_one({"heat_number": heat}):
                continue
            beams = await db.beams.find({"bed_id": bed["id"]}, {"_id": 0}).to_list(50)
            roll = StrandRoll(
                reel_number=f"R-SEED-{bed.get('bed_number'):02d}",
                heat_number=heat,
                lot_number=f"LOT-SEED-{bed.get('bed_number')}",
                pack_weight="6400 lb",
                pack_length="14500 ft",
                astm_standard="ASTM A416",
                strand_grade="270",
                strand_type="Low-Relaxation",
                nominal_diameter="0.50in",
                area_in2=0.153,
                received_date=now_iso()[:10],
                status="assigned",
                extractor="seed",
                extractor_confidence=1.0,
                field_confidence={
                    "reel_number": 1.0,
                    "heat_number": 1.0,
                    "lot_number": 1.0,
                    "pack_weight": 1.0,
                    "pack_length": 1.0,
                    "astm_standard": 1.0,
                    "strand_grade": 1.0,
                    "strand_type": 1.0,
                    "nominal_diameter": 1.0,
                    "area_in2": 1.0,
                },
                logged_by="system-seed",
                confirmed_by="system-seed",
                confirmed_at=now_iso(),
                notes="Seeded mill-tag record so demo beds can tension. Replace by scanning the live coil tag.",
            )
            await db.strand_rolls.insert_one(roll.model_dump())
            rec = StrandRollAssignment(
                roll_id=roll.id,
                bed_id=bed["id"],
                pour_id=bed.get("current_pour_id") or (beams[0].get("pour_id") if beams else None),
                beam_ids=[b["id"] for b in beams],
                allocated_length=float(bed.get("length_ft") or 0),
                logged_by="system-seed",
            )
            await db.strand_roll_assignments.insert_one(rec.model_dump())
        logger.info("seeded strand rolls for %s beds", len(beds))
    except Exception:
        logger.exception("seed_strand_rolls failed")


async def seed_company():
    """Idempotent plant branding so tags and exports are white-label ready."""
    try:
        if await db.company_settings.find_one({"id": "plant"}):
            return
        settings = CompanySettings()
        await db.company_settings.insert_one(settings.model_dump())
        logger.info("seeded company settings name=%s", settings.company_name)
    except Exception:
        logger.exception("seed_company failed")


async def seed_mix_designs():
    """Idempotent SCC starter mix so the batch plant is not an empty library."""
    ingredients = [
        {"kind": "cement", "name": "Type III cement", "source": "", "size": "", "weight_lb": 658, "moisture_pct": None, "dosage": None, "dosage_unit": "lb", "notes": ""},
        {"kind": "scm", "name": "Fly ash", "source": "", "size": "", "weight_lb": 120, "moisture_pct": None, "dosage": None, "dosage_unit": "lb", "notes": ""},
        {"kind": "scm", "name": "Slag", "source": "", "size": "", "weight_lb": 0, "moisture_pct": None, "dosage": None, "dosage_unit": "lb", "notes": ""},
        {"kind": "coarse", "name": "Coarse #67", "source": "", "size": "#67", "weight_lb": 1680, "moisture_pct": None, "dosage": None, "dosage_unit": "lb", "notes": ""},
        {"kind": "sand", "name": "Sand", "source": "", "size": "", "weight_lb": 1420, "moisture_pct": None, "dosage": None, "dosage_unit": "lb", "notes": ""},
        {"kind": "water", "name": "Batch water", "source": "", "size": "", "weight_lb": 250, "moisture_pct": None, "dosage": None, "dosage_unit": "lb", "notes": ""},
        {"kind": "ice", "name": "Ice / chilled water", "source": "", "size": "", "weight_lb": 0, "moisture_pct": None, "dosage": None, "dosage_unit": "lb", "notes": ""},
        {"kind": "admixture", "name": "AEA", "source": "", "size": "", "weight_lb": None, "moisture_pct": None, "dosage": 0.8, "dosage_unit": "oz/cwt", "notes": ""},
        {"kind": "admixture", "name": "HRWR", "source": "", "size": "", "weight_lb": None, "moisture_pct": None, "dosage": 6.0, "dosage_unit": "oz/cwt", "notes": ""},
        {"kind": "admixture", "name": "Retarder", "source": "", "size": "", "weight_lb": None, "moisture_pct": None, "dosage": 0, "dosage_unit": "oz/cwt", "notes": ""},
        {"kind": "admixture", "name": "Accelerator", "source": "", "size": "", "weight_lb": None, "moisture_pct": None, "dosage": 0, "dosage_unit": "oz/cwt", "notes": ""},
        {"kind": "admixture", "name": "Corrosion inhibitor", "source": "", "size": "", "weight_lb": None, "moisture_pct": None, "dosage": 0, "dosage_unit": "oz/cwt", "notes": ""},
    ]
    try:
        existing = await db.mix_designs.find_one({"mix_code": "SCC-8K"}, {"_id": 0})
        if existing:
            if not existing.get("ingredients"):
                await db.mix_designs.update_one({"id": existing["id"]}, {"$set": {"ingredients": ingredients}})
                logger.info("backfilled SCC-8K starter ingredient weights")
            return
        rec = MixDesign(
            mix_code="SCC-8K",
            name="Plant SCC 8,000 psi",
            target_strength_psi=8000,
            target_air_pct=6.0,
            target_spread_in=26.0,
            target_temp_f=70.0,
            notes="Starter mix for the mixer office. Confirm against the plant's approved mix card.",
            created_by="system-seed",
            ingredients=ingredients,
        )
        await db.mix_designs.insert_one(rec.model_dump())
        logger.info("seeded mix design SCC-8K")
    except Exception:
        logger.exception("seed_mix_designs failed")


async def seed_beam_qr_tokens():
    """Issue a permanent QR token for any beam that was created before identity labels existed."""
    from beam_qr import ensure_beam_token

    try:
        missing = await db.beams.find(
            {"$or": [{"qr_token": {"$exists": False}}, {"qr_token": ""}, {"qr_token": None}]},
            {"_id": 0},
        ).to_list(5000)
        for beam in missing:
            await ensure_beam_token(beam)
        if missing:
            logger.info("backfilled beam QR tokens count=%s", len(missing))
    except Exception:
        logger.exception("seed_beam_qr_tokens failed")

