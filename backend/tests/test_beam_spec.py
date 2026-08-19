"""Beam Spec DNA materialization from locked/confirmed extraction."""
from models import BlueprintField
from blueprint_pipeline import extract_structured_fields, normalize_locked_blueprint
from beam_spec import materialize_job_beam_specs, twin_beam_from_spec
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
    assert not [item for item in specs[0]["hardware"] if item.get("kind") == "hold_down"]
