"""Tension twin: strand grid, hold-downs, and ±5% capture math."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from beam_spec import StrandItem, assign_strand_grid, drape_elevation_in, ensure_tension_geometry, hold_downs_from_hardware, strand_end_y_in, strand_hold_y_in
    from l25390 import HOLD_DOWN_ME_FT, HOLD_DOWN_TYPE, HOLD_DOWN_UE_FT, build_l25390_spec
    from tension import strand_capture_result
except ImportError:
    pytest.skip("legacy BeamSpec tension twin is superseded by Spec DNA strand engine", allow_module_level=True)


def test_assign_strand_grid_rows_and_columns():
    strands = [
        StrandItem(number=1, offset_in=-6, soffit_in=2),
        StrandItem(number=2, offset_in=6, soffit_in=2),
        StrandItem(number=3, offset_in=-6, soffit_in=4),
        StrandItem(number=4, offset_in=6, soffit_in=4),
    ]
    assign_strand_grid(strands)
    assert {s.row for s in strands} == {1, 2}
    bottom = [s for s in strands if s.row == 1]
    assert [s.column for s in sorted(bottom, key=lambda s: s.column)] == [1, 2]
    assert all(s.x_in == s.offset_in and s.y_in == s.soffit_in for s in strands)


def test_hold_downs_from_hardware():
    spec = build_l25390_spec(beam_mark="B2")
    from_hw = hold_downs_from_hardware(spec.hardware)
    assert len(from_hw) == 2
    assert all(hd.station_from_marked_end > 0 for hd in from_hw)
    assert spec.hold_downs
    assert len(spec.hold_downs) == 2
    assert spec.hold_downs[0].quantity_at_station == 2


def test_l25390_strand_pattern_is_unique():
    spec = ensure_tension_geometry(build_l25390_spec())
    assert len(spec.strands) == 20
    assert all(s.row >= 1 and s.column >= 1 for s in spec.strands)
    assert all(s.draped == (s.detensioning == "draped") for s in spec.strands)
    ids = [s.id for s in spec.strands]
    assert len(ids) == len(set(ids))
    end_xy = {(round(s.x_in, 2), round(strand_end_y_in(s), 2)) for s in spec.strands}
    assert len(end_xy) == 20


def test_l25390_end_view_does_not_overlap_draped_on_straight():
    spec = ensure_tension_geometry(build_l25390_spec())
    straight = [s for s in spec.strands if not s.draped]
    draped = [s for s in spec.strands if s.draped]
    assert len(straight) == 12
    assert len(draped) == 8
    row_counts = {}
    for s in spec.strands:
        row_counts[s.row] = row_counts.get(s.row, 0) + 1
    assert row_counts == {1: 8, 2: 4, 3: 2, 4: 4, 5: 2}
    assert {round(s.soffit_in, 1) for s in straight} == {2.0, 4.0}
    assert {round(s.x_in, 1) for s in straight} == {-7.0, -5.0, -3.0, -1.0, 1.0, 3.0, 5.0, 7.0}
    assert {round(s.x_in, 1) for s in draped} == {-3.0, -1.0, 1.0, 3.0}
    assert {round(strand_end_y_in(s), 1) for s in draped} == {18.0, 22.0, 26.0}
    assert spec.strand_spec["area_in2"] == 0.167
    assert spec.strand_spec["final_pull_lbs"] == 33817
    for s in draped:
        assert strand_end_y_in(s) > strand_hold_y_in(s)


def test_draped_path_descends_through_hold_downs():
    spec = ensure_tension_geometry(build_l25390_spec())
    draped = next(s for s in spec.strands if s.draped)
    length = spec.geometry.length_ft
    y_end = drape_elevation_in(draped, 0.0, length, spec.hold_downs)
    y_mid_hd = drape_elevation_in(draped, HOLD_DOWN_ME_FT, length, spec.hold_downs)
    y_far = drape_elevation_in(draped, length, length, spec.hold_downs)
    y_before = drape_elevation_in(draped, HOLD_DOWN_ME_FT * 0.5, length, spec.hold_downs)
    assert abs(y_end - strand_end_y_in(draped)) < 0.05
    assert abs(y_far - strand_end_y_in(draped)) < 0.05
    assert abs(y_mid_hd - strand_hold_y_in(draped)) < 0.05
    assert y_end > y_before > y_mid_hd


def test_hold_downs_h56s_stations():
    spec = build_l25390_spec(beam_mark="B2")
    assert len(spec.hold_downs) == 2
    assert spec.hold_downs[0].station_from_marked_end == HOLD_DOWN_ME_FT
    assert spec.hold_downs[1].station_from_marked_end == HOLD_DOWN_UE_FT
    assert all(HOLD_DOWN_TYPE in (hd.type_spec or "") for hd in spec.hold_downs)
    assert all(hd.quantity_at_station == 2 for hd in spec.hold_downs)
    assert all(abs((hd.offset_in or 0) - 2.0) < 0.01 for hd in spec.hold_downs)


def test_strand_capture_within_and_outside():
    ok = strand_capture_result(
        jacking_force_kip=31.0,
        bed_length_ft=400,
        strand_area_in2=0.153,
        measured_elongation_in=None,
    )
    assert ok["status"] == "pending"
    assert ok["theoretical_elongation"] > 0
    theo = ok["theoretical_elongation"]
    pass_rec = strand_capture_result(
        jacking_force_kip=31.0,
        bed_length_ft=400,
        strand_area_in2=0.153,
        measured_elongation_in=theo,
    )
    assert pass_rec["status"] == "pass"
    assert pass_rec["within_tolerance"] is True
    fail_rec = strand_capture_result(
        jacking_force_kip=31.0,
        bed_length_ft=400,
        strand_area_in2=0.153,
        measured_elongation_in=theo * 1.2,
    )
    assert fail_rec["status"] == "fail"
    na = strand_capture_result(
        jacking_force_kip=31.0,
        bed_length_ft=400,
        strand_area_in2=0.153,
        na=True,
    )
    assert na["status"] == "na"
    assert na["measured_elongation"] is None
