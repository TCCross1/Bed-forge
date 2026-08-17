"""Unit tests for BeamSpec, L25390 reference, and measured-vs-design compare."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beam_spec import SpecMeasurementCreate, compare_measurement
from extract import _looks_like_l25390, extract_beam_spec
from l25390 import JOB_NUMBER, LENGTH_FT, PRODUCT_NAME, build_l25390_spec
from storage import safe_id, safe_name


REQUIRED_KINDS = {
    "lift_loop",
    "insert",
    "drain",
    "downspout",
    "tube",
    "tie_rod",
    "hold_down",
    "projecting_rebar",
    "diaphragm",
    "bearing_plate",
    "bituminous_zone",
}


def test_l25390_geometry_and_identity():
    spec = build_l25390_spec(beam_mark="B1")
    assert spec.job_number == JOB_NUMBER
    assert spec.product_name == PRODUCT_NAME
    assert spec.geometry.twin_type == "i_beam"
    assert abs(spec.geometry.length_ft - LENGTH_FT) < 0.01
    assert spec.geometry.depth_in == 36.0
    assert spec.geometry.bot_flange_width_in == 18.0
    assert spec.geometry.top_flange_width_in == 12.0
    assert spec.geometry.web_thick_in == 6.0
    assert "ME" in spec.marked_end_id
    assert "UE" in spec.unmarked_end_id


def test_l25390_strands_and_hardware():
    spec = build_l25390_spec(beam_mark="B3")
    assert len(spec.strands) == 20
    assert len([s for s in spec.strands if s.detensioning == "straight"]) == 12
    assert len([s for s in spec.strands if s.detensioning == "draped"]) == 8
    kinds = {h.kind for h in spec.hardware}
    assert REQUIRED_KINDS <= kinds
    inserts = [h for h in spec.hardware if h.type_code == "F-64"]
    assert len(inserts) == 16
    loops = [h for h in spec.hardware if h.kind == "lift_loop"]
    assert len(loops) == 2
    assert spec.notes
    assert spec.special_finishes
    assert any(z.shape == "hoop" for z in spec.stirrup_zones)


def test_compare_within_and_out_of_tolerance():
    spec = build_l25390_spec()
    loop = next(h for h in spec.hardware if h.kind == "lift_loop")
    ok = compare_measurement(
        spec,
        SpecMeasurementCreate(element_id=loop.id, measured_station_ft=loop.position.station_ft),
        "tech",
    )
    assert ok.within_tolerance is True
    assert ok.delta_in == 0.0
    bad = compare_measurement(
        spec,
        SpecMeasurementCreate(element_id=loop.id, measured_station_ft=loop.position.station_ft + 1.0),
        "tech",
    )
    assert bad.within_tolerance is False
    assert bad.delta_in == 12.0


def test_path_sanitization_blocks_traversal():
    assert ".." not in safe_id("../etc/passwd")
    assert "/" not in safe_id("a/b/c")
    assert safe_name("../../secret.pdf") == "secret.pdf"


def test_extractor_matches_larue_fingerprint(tmp_path):
    dummy = tmp_path / "Larue_County_L25390_Type2.pdf"
    dummy.write_bytes(b"%PDF-1.4 placeholder")
    assert _looks_like_l25390(dummy.name, "")
    spec, name = extract_beam_spec([dummy], beam_mark="B1")
    assert name == "l25390_reference"
    assert spec.job_number == JOB_NUMBER
    assert len(spec.hardware) >= 20
