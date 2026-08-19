"""Unit tests for Blueprint Intelligence parsers, confidence, and L25390-like fixtures."""
from models import BlueprintField
from blueprint_pipeline import (
    apply_confidence_guard,
    extract_mark_length_families,
    extract_structured_fields,
    parse_feet_inches,
    parse_mark_groups,
)


L25390_FIXTURE = [
    "PRESTRESS SERVICES INDUSTRIES LLC\nJob No: L25390   |   CID: 25-5390\nKY 210 over North Fork Nolin River — Larue County, Kentucky\nBridge ID: 062B00034R  |  Type 2 I-Beam  |  Contractor: JAVE, LLC\nBeam Marks: 201–209 (9 beams)",
    "L25390  ·  Sheet 1 of 17  ·  Cover Sheet\nJob L25390 · Type 2 I-Beam · Larue County KY",
    "MK 204/205/206 · 270' Bed · 1/2\" 270K low-relaxation strands\nFINAL PULL 33817 LB\nDRAPED hold-downs H-56-S",
    "MK 201–209 bed positions · Hold-downs H-56-S Dayton/Richmond",
    "Beam Shop Drawing — Marks 201 / 202 / 203\nOVERALL LENGTH 47'-3\"\nCASTING LENGTH 47'-3 3/4\"\nQty 1/3/1",
    "Beam Shop Drawing — Marks 204 / 205 / 206\nOVERALL LENGTH 52'-0\"\nCASTING LENGTH 52'-0 3/4\"\nQty 1/3/1",
    "Beam Shop Drawing — Marks 207 / 208 / 209\n47'-3\" overall\nCASTING LENGTH 47'-3 3/4\"",
    "Hardware — MARK 201 HARDWARE\nTRIPLE LIFT LOOPS 0.6\" EMBED 2'-7\"\nF-64 inserts · H-56-S hold-downs",
]


def test_parse_feet_inches_shop_drawing_forms():
    assert parse_feet_inches("47'-3\"") == 47.25
    assert abs(parse_feet_inches("47'-3 3/4\"") - (47 + 3.75 / 12)) < 0.0001
    assert abs(parse_feet_inches("47'-33/4\"") - (47 + 3.75 / 12)) < 0.0001
    assert abs(parse_feet_inches("47'-3¾\"") - (47 + 3.75 / 12)) < 0.0001
    assert parse_feet_inches("52'-0\"") == 52.0
    assert abs(parse_feet_inches("52'-0 3/4\"") - (52 + 0.75 / 12)) < 0.0001
    assert abs(parse_feet_inches("52'-03/4\"") - (52 + 0.75 / 12)) < 0.0001
    assert parse_feet_inches("110' 0\"") == 110.0
    assert abs(parse_feet_inches("2'-7\"") - (2 + 7 / 12)) < 0.0001


def test_parse_mark_groups_slash_range_and_hardware():
    assert parse_mark_groups("MARK: 201/202/203") == ["201", "202", "203"]
    assert parse_mark_groups("MK 201") == ["201"]
    assert parse_mark_groups("MK 204/205/206") == ["204", "205", "206"]
    assert parse_mark_groups("Beam Marks: 201–209") == ["201", "202", "203", "204", "205", "206", "207", "208", "209"]
    assert parse_mark_groups("Marks 201 / 202 / 203") == ["201", "202", "203"]
    assert parse_mark_groups("MARK 201 HARDWARE") == ["201"]
    assert "s" not in parse_mark_groups("Beam Marks: 201–209 (9 beams)")


def test_confidence_contradiction_ban():
    dirty = BlueprintField(
        value="L25390",
        confidence="high",
        source_page=1,
        status="confirmed",
        extraction_notes="Job number not confidently located.",
    )
    cleaned = apply_confidence_guard(dirty)
    assert cleaned.status == "unconfirmed"
    assert cleaned.confidence != "high" or "not confidently located" in cleaned.extraction_notes


def test_l25390_identity_geometry_strand_hardware_fixture():
    result = extract_structured_fields(L25390_FIXTURE, page_sources=["text_layer"] * len(L25390_FIXTURE))
    fields = result.fields
    assert fields["job_number"].value == "L25390"
    assert fields["job_number"].status == "confirmed"
    assert fields["cid"].value == "25-5390"
    assert fields["bridge_id"].value == "062B00034R"
    assert fields["county_dot"].value == "Larue County, Kentucky"
    assert fields["county_dot"].value != ", Kentucky"
    assert fields["product_family"].value == "i_beam"
    assert fields["beam_marks"].value == ["201", "202", "203", "204", "205", "206", "207", "208", "209"]
    assert fields["beam_mark"].value in ("201-209", "201/202/203/204/205/206/207/208/209")
    assert "s" != str(fields["beam_mark"].value).lower()

    families = {tuple(fam["marks"]): fam for fam in extract_mark_length_families(L25390_FIXTURE)}
    assert abs(families[("201", "202", "203")]["overall_length_ft"] - 47.25) < 0.01
    assert abs(families[("201", "202", "203")]["casting_length_ft"] - (47 + 3.75 / 12)) < 0.01
    assert abs(families[("204", "205", "206")]["overall_length_ft"] - 52.0) < 0.01
    assert abs(families[("204", "205", "206")]["casting_length_ft"] - (52 + 0.75 / 12)) < 0.01
    assert abs(families[("207", "208", "209")]["overall_length_ft"] - 47.25) < 0.01

    assert fields["strand_diameter_in"].value == 0.5
    assert "270" in str(fields["strand_grade"].value)
    assert "low-relaxation" in str(fields["strand_grade"].value)
    assert fields["strand_final_pull_lb"].value == 33817
    assert fields["overall_depth_in"].value == 36.0
    assert "H-56-S" in str(fields["hold_down_type"].value)
    assert "0.6" in str(fields["lift_loop_spec"].value)
    assert "2'-7" in str(fields["lift_loop_spec"].value) or "2'-7\"" in str(fields["lift_loop_spec"].value)
    insert_types = [item.get("type") for item in (fields["inserts"].value or []) if isinstance(item, dict)]
    assert "F-64" in insert_types
    for field in fields.values():
        if field.status == "confirmed":
            assert "not confidently located" not in (field.extraction_notes or "").lower()


def test_final_pull_ocr_variants():
    at_comma = extract_structured_fields(["FINAL PULL AT 33,817 LBS"])
    assert at_comma.fields["strand_final_pull_lb"].value == 33817
    dotted = extract_structured_fields(["JACKING TO 33.817"])
    assert dotted.fields["strand_final_pull_lb"].value == 33817
    spaced = extract_structured_fields(["FINAL PULL AT 33 817 LBS"])
    assert spaced.fields["strand_final_pull_lb"].value == 33817
    too_small = extract_structured_fields(["FINAL PULL AT 338 LBS"])
    assert too_small.fields["strand_final_pull_lb"].value is None


def test_type2_and_type_iv_overall_depth():
    type2 = extract_structured_fields(["Type 2 I-Beam\nMarks 201 / 202 / 203\nOVERALL LENGTH 47'-3\""])
    assert type2.fields["overall_depth_in"].value == 36.0
    type_iv_explicit = extract_structured_fields(
        ["BEAM MARK: B9-01\nAASHTO TYPE IV I-BEAM\nOVERALL LENGTH: 110' 0\"\nOVERALL DEPTH: 54 IN"]
    )
    assert type_iv_explicit.fields["overall_depth_in"].value == 54.0
    type_iv_fallback = extract_structured_fields(
        ["BEAM MARK: B9-01\nAASHTO TYPE IV I-BEAM\nOVERALL LENGTH: 110' 0\""]
    )
    assert type_iv_fallback.fields["overall_depth_in"].value == 54.0


def test_casting_inferred_from_based_on_note():
    pages = [
        "Beam Shop Drawing — Marks 201 / 202 / 203\nOVERALL LENGTH 47'-3\"\nNOTE: ALL DIMENSIONS ARE BASED ON CASTING LENGTH",
    ]
    result = extract_structured_fields(pages)
    families = {tuple(fam["marks"]): fam for fam in result.fields["mark_length_families"].value}
    assert abs(families[("201", "202", "203")]["overall_length_ft"] - 47.25) < 0.01
    assert abs(families[("201", "202", "203")]["casting_length_ft"] - (47 + 3.75 / 12)) < 0.01
    assert abs(result.fields["casting_length_ft"].value - (47 + 3.75 / 12)) < 0.01
    sample = extract_structured_fields(
        ["JOB NO: J-88-2001\nBEAM MARK: B9-01\nAASHTO TYPE IV I-BEAM\nOVERALL LENGTH: 110' 0\"\nOVERALL DEPTH: 54 IN"]
    )
    assert sample.fields["casting_length_ft"].value is None
    assert sample.fields["overall_depth_in"].value == 54.0
    assert sample.fields["overall_length_ft"].value == 110.0
