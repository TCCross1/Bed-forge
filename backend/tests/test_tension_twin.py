"""Tension twin: strand grid, hold-downs, and ±5% capture math."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beam_spec import StrandItem, assign_strand_grid, ensure_tension_geometry, hold_downs_from_hardware
from l25390 import build_l25390_spec
from tension import strand_capture_result


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
