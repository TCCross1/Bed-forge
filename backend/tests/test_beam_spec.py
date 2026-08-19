"""Beam Spec DNA materialization from locked/confirmed extraction."""
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
