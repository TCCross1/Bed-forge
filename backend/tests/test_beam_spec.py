"""Beam Spec DNA materialization from locked/confirmed extraction."""
from models import BlueprintField
from blueprint_pipeline import extract_structured_fields, normalize_locked_blueprint
from beam_spec import materialize_job_beam_specs, strand_engine_stale, twin_beam_from_spec, beam_record_from_locked_spec
from tests.test_blueprint_extraction import L25390_FIXTURE


def test_l25390_specs_one_per_mark_and_family_length():
    result = extract_structured_fields(L25390_FIXTURE, page_sources=["text_layer"] * len(L25390_FIXTURE))
    normalized = normalize_locked_blueprint(result.fields)
    specs = materialize_job_beam_specs(
        result.fields,
        document={"id": "doc-l25390", "project_name_hint": "L25390"},
        revision={"id": "rev-1", "normalized_blueprint": normalized, "product_family": "i_beam", "beam_mark": "201-209"},
    )
    marks = [item["beam_mark"] for item in specs]
    assert marks == ["201", "202", "203", "204", "205", "206", "207", "208", "209"]
    by_mark = {item["beam_mark"]: item for item in specs}
    assert abs(by_mark["201"]["geometry"]["length_ft"] - 47.25) < 0.01
    assert abs(by_mark["204"]["geometry"]["length_ft"] - 52.0) < 0.01
    assert abs(by_mark["201"]["blueprint"]["casting_length_ft"] - (47 + 3.75 / 12)) < 0.01
    assert abs(by_mark["204"]["blueprint"]["casting_length_ft"] - (52 + 0.75 / 12)) < 0.01
    assert by_mark["201"]["geometry"]["depth_in"] == 36.0
    assert by_mark["201"]["identity"]["job_number"] == "L25390"
    assert by_mark["201"]["identity"]["county"] == "Larue County, Kentucky"
    assert not by_mark["201"]["blueprint"]["lift_loops"] or isinstance(by_mark["201"]["blueprint"]["lift_loops"], list)


def test_specs_do_not_invent_hardware_stations():
    result = extract_structured_fields(
        ["JOB NO: L25390\nBEAM MARKS: 201-203\nType 2 I-Beam\nOVERALL LENGTH 47'-3\"\nOVERALL DEPTH: 36 IN"],
        page_sources=["text_layer"],
    )
    specs = materialize_job_beam_specs(result.fields, document={"id": "doc-1"}, revision={"id": "rev-1", "product_family": "i_beam"})
    assert len(specs) == 3
    for spec in specs:
        assert spec["blueprint"].get("lift_loops") in ([], None) or spec["blueprint"]["lift_loops"] == []
        invented = [item for item in spec["hardware"] if (item.get("position") or {}).get("station_ft") not in (None,)]
        assert invented == []


def test_type_iv_explicit_depth_is_not_overwritten():
    result = extract_structured_fields(
        ["JOB NO: J-88-2001\nBEAM MARK: B9-01\nAASHTO TYPE IV I-BEAM\nOVERALL LENGTH: 110' 0\"\nOVERALL DEPTH: 54 IN"],
        page_sources=["text_layer"],
    )
    specs = materialize_job_beam_specs(result.fields, document={"id": "doc-iv"}, revision={"id": "rev-iv", "product_family": "i_beam"})
    assert len(specs) == 1
    spec = specs[0]
    assert spec["beam_mark"] == "B9-01"
    assert spec["geometry"]["depth_in"] == 54.0
    twin = twin_beam_from_spec(spec)
    assert twin["length_ft"] == 110.0
    assert twin["product_type"]["blueprint"]["cross_section"]["overall_depth_in"] == 54.0
    assert twin["blueprint_source"]["status"] == "locked"


def test_l25390_draped_path_is_parametric_not_invented_hardware():
    result = extract_structured_fields(L25390_FIXTURE, page_sources=["text_layer"] * len(L25390_FIXTURE))
    specs = materialize_job_beam_specs(
        result.fields,
        document={"id": "doc-l25390", "project_name_hint": "L25390"},
        revision={"id": "rev-1", "product_family": "i_beam"},
    )
    spec = next(item for item in specs if item["beam_mark"] == "201")
    strand = spec["strand"]
    assert strand["draped"] is True
    assert strand["hold_down_type"]
    assert "H-56-S" in str(strand["hold_down_type"])
    assert strand["path_model"]["source"] == "parametric_midspan"
    assert strand["path_model"]["profile"] == "end_high_hold_down_low"
    assert strand["path_model"]["routing"] == "end_hold_down_end"
    assert strand["path_model"]["hold_down_stations_ft"] == [round(47.25 * 0.5, 3)]
    assert strand["pattern_source"] == "unconfirmed"
    assert strand["end_treatments"]["marked_end"]["type"] == "unspecified"
    hold_hardware = [item for item in spec["hardware"] if item.get("kind") == "hold_down"]
    assert hold_hardware == []
    spec204 = next(item for item in specs if item["beam_mark"] == "204")
    assert spec204["strand"]["path_model"]["hold_down_stations_ft"] == [26.0]


def test_extracted_hold_down_stations_drive_path_model():
    result = extract_structured_fields(
        [
            "JOB NO: J-1\nBEAM MARK: 301\nType 2 I-Beam\nOVERALL LENGTH 60'-0\"\nOVERALL DEPTH: 36 IN\nDRAPED STRANDS\nHOLD-DOWN AT 24'-0\"\nHOLD-DOWN AT 36'-0\"\nH-56-S"
        ],
        page_sources=["text_layer"],
    )
    specs = materialize_job_beam_specs(result.fields, document={"id": "doc-hd"}, revision={"id": "rev-hd", "product_family": "i_beam"})
    spec = specs[0]
    assert spec["strand"]["path_model"]["source"] == "extracted_stations"
    assert spec["strand"]["path_model"]["hold_down_stations_ft"] == [24.0, 36.0]
    stations = sorted((item.get("position") or {}).get("station_ft") for item in spec["hardware"] if item.get("kind") == "hold_down")
    assert stations == [24.0, 36.0]


def test_no_drape_without_draped_evidence():
    result = extract_structured_fields(
        ["JOB NO: J-2\nBEAM MARK: B9-01\nAASHTO TYPE IV I-BEAM\nOVERALL LENGTH: 110' 0\"\nOVERALL DEPTH: 54 IN"],
        page_sources=["text_layer"],
    )
    specs = materialize_job_beam_specs(result.fields, document={"id": "doc-iv-2"}, revision={"id": "rev-iv-2", "product_family": "i_beam"})
    strand = specs[0]["strand"]
    assert strand.get("draped") is False
    assert (strand.get("path_model") or {}).get("source") in (None, "none")
    hold_only = extract_structured_fields(
        ["JOB NO: J-3\nBEAM MARK: 201\nType 2 I-Beam\nOVERALL LENGTH 40'-0\"\nH-56-S hold-downs"],
        page_sources=["text_layer"],
    )
    hold_specs = materialize_job_beam_specs(hold_only.fields, document={"id": "doc-h"}, revision={"id": "rev-h", "product_family": "i_beam"})
    assert hold_specs[0]["strand"].get("draped") is True
    assert hold_specs[0]["strand"]["path_model"]["source"] == "parametric_midspan"
    unlabeled = extract_structured_fields(
        ["JOB NO: J-4\nBEAM MARK: 201\nType 2 I-Beam\nOVERALL LENGTH 40'-0\"\nhold-downs present"],
        page_sources=["text_layer"],
    )
    unlabeled_specs = materialize_job_beam_specs(unlabeled.fields, document={"id": "doc-u"}, revision={"id": "rev-u", "product_family": "i_beam"})
    assert unlabeled_specs[0]["strand"].get("draped") is False


def test_legacy_unconfirmed_draped_keyword_builds_parametric_path():
    result = extract_structured_fields(
        ["JOB NO: J-9\nBEAM MARK: 201\nType 2 I-Beam\nOVERALL LENGTH 47'-3\"\nOVERALL DEPTH: 36 IN"],
        page_sources=["text_layer"],
    )
    fields = result.fields
    fields["draped_strand_count"] = BlueprintField(
        value="draped",
        confidence="medium",
        source_page=1,
        status="unconfirmed",
        extraction_notes="Draped strand system mentioned; explicit count was not found so status stays unconfirmed.",
    )
    fields["hold_down_type"] = BlueprintField(
        value="H-56-S",
        confidence="high",
        source_page=1,
        status="confirmed",
        extraction_notes="Hold-down type from hardware callout.",
    )
    specs = materialize_job_beam_specs(fields, document={"id": "doc-legacy"}, revision={"id": "rev-legacy", "product_family": "i_beam"})
    strand = specs[0]["strand"]
    assert strand["draped"] is True
    assert strand["path_model"]["source"] == "parametric_midspan"
    assert strand["path_model"]["span_path"] == "end -> hold-down -> end"
    assert not [item for item in specs[0]["hardware"] if item.get("kind") == "hold_down"]


def test_strand_engine_stale_detects_legacy_specs_without_inventing_hardware():
    assert strand_engine_stale(None) is True
    assert strand_engine_stale({"strand": {"draped": True, "hold_down_type": "H-56-S"}}) is True
    assert strand_engine_stale({"strand": {"path_model": {"source": "parametric_midspan"}}}) is True
    result = extract_structured_fields(L25390_FIXTURE, page_sources=["text_layer"] * len(L25390_FIXTURE))
    specs = materialize_job_beam_specs(
        result.fields,
        document={"id": "doc-stale", "project_name_hint": "L25390"},
        revision={"id": "rev-stale", "product_family": "i_beam"},
    )
    spec = next(item for item in specs if item["beam_mark"] == "201")
    assert strand_engine_stale(spec) is False
    assert spec["strand"]["end_treatments"]["marked_end"]["type"] in ("cut_flush_bituminous", "bent_90", "unspecified")
    assert spec["strand"]["path_model"]["routing"] == "end_hold_down_end"
    hold_hardware = [item for item in spec["hardware"] if item.get("kind") == "hold_down"]
    assert hold_hardware == []


def test_beam_record_from_locked_spec_copies_dna_only():
    spec = {
        "id": "spec-201",
        "status": "locked",
        "job_id": "job-l25390",
        "beam_mark": "201",
        "document_id": "doc-1",
        "locked_revision_id": "rev-1",
        "product_family": "i_beam",
        "identity": {"county": "Larue County, Kentucky", "route": "KY 61", "cid": "255390"},
        "geometry": {"length_ft": 47.25, "depth_in": 36.0, "twin_type": "i_beam"},
        "blueprint": {"length": 47.25, "hold_downs": [], "lift_loops": []},
        "strand": {"final_pull_lb": None},
        "hardware": [],
    }
    row = beam_record_from_locked_spec(spec, bed_id="bed-1", pour_id="pour-1", position_on_bed=1)
    assert row["mark"] == "201"
    assert row["job_id"] == "job-l25390"
    assert row["spec_id"] == "spec-201"
    assert row["length_ft"] == 47.25
    assert row["twin_type"] == "i_beam"
    assert row["traceability"]["overall_depth_in"] == 36.0
    assert row["traceability"]["county"] == "Larue County, Kentucky"
    assert row["traceability"]["route"] == "KY 61"
    assert row["traceability"]["cid"] == "255390"
    assert "hold_downs" not in row
    assert "final_pull" not in str(row)
    again = beam_record_from_locked_spec(spec, bed_id="bed-1", pour_id="pour-1", position_on_bed=1)
    assert again["mark"] == row["mark"] and again["length_ft"] == row["length_ft"]
    assert beam_record_from_locked_spec({**spec, "status": "extracted"}, bed_id="bed-1") is None
    assert beam_record_from_locked_spec({**spec, "job_id": None}, bed_id="bed-1") is None
    assert beam_record_from_locked_spec({**spec, "geometry": {}, "blueprint": {}}, bed_id="bed-1") is None


def test_materialize_beams_from_locked_specs_idempotent():
    import asyncio
    from models import Bed, Job, Pour
    from db import db
    from job_cabinet import materialize_beams_from_locked_specs, materialize_beams_for_job

    async def run():
        job = Job(job_number="L25390-BEAM-TEST", name="beam materialize", customer="KYTC", status="open").model_dump()
        bed = Bed(bed_number=99, name="Test Bed", length_ft=400).model_dump()
        pour = Pour(job_id=job["id"], pour_number="P-TEST", pour_date="2026-08-20", status="active").model_dump()
        await db.jobs.insert_one(dict(job))
        await db.beds.insert_one(dict(bed))
        await db.pours.insert_one(dict(pour))
        specs = []
        lengths = {"201": 47.25, "202": 47.25, "203": 47.25, "204": 52.0, "205": 52.0, "206": 52.0, "207": 47.25, "208": 47.25, "209": 47.25}
        for mark, length in lengths.items():
            spec = {
                "id": f"spec-{job['id']}-{mark}",
                "status": "locked",
                "job_id": job["id"],
                "job_number": "L25390-BEAM-TEST",
                "beam_mark": mark,
                "document_id": "doc-test",
                "locked_revision_id": "rev-test",
                "product_family": "i_beam",
                "identity": {"county": "Larue County, Kentucky"},
                "geometry": {"length_ft": length, "depth_in": 36.0},
                "blueprint": {"length": length},
            }
            specs.append(spec)
            await db.beam_specs.insert_one(dict(spec))
        first = await materialize_beams_from_locked_specs(specs)
        assert [item["mark"] for item in first] == ["201", "202", "203", "204", "205", "206", "207", "208", "209"]
        rows = await db.beams.find({"job_id": job["id"]}, {"_id": 0}).to_list(50)
        assert len(rows) == 9
        by_mark = {item["mark"]: item for item in rows}
        assert by_mark["201"]["length_ft"] == 47.25
        assert by_mark["204"]["length_ft"] == 52.0
        assert by_mark["201"]["spec_id"] == f"spec-{job['id']}-201"
        assert by_mark["201"]["traceability"]["overall_depth_in"] == 36.0
        assert "hold_down" not in str(by_mark["201"].get("traceability"))
        second = await materialize_beams_for_job(job["id"])
        rows_again = await db.beams.find({"job_id": job["id"]}, {"_id": 0}).to_list(50)
        assert len(rows_again) == 9
        assert {item["id"] for item in rows} == {item["id"] for item in rows_again}
        assert len(second) == 9

    asyncio.run(run())
