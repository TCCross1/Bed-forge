"""AR level math, digital-tape vs twin matching, and QC narrative fallback."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ar_math import (
    STATION_MATCH_WINDOW_FT,
    compare_tape_shots,
    derive_metrics,
    design_stations_from_spec,
    evaluate_level,
    meters_to_in,
)
from models import LEVEL_TOLERANCE_IN
from tape_ai import heuristic_tape_summary


def test_level_within_eighth_inch():
    assert evaluate_level(0.10) is True
    assert evaluate_level(0.125) is True
    assert evaluate_level(-0.125) is True
    assert evaluate_level(0.20) is False
    assert LEVEL_TOLERANCE_IN == 0.125


def test_derive_metrics_distance_and_height():
    a = {"x": 0.0, "y": 1.0, "z": 0.0}
    b = {"x": 3.048, "y": 1.0, "z": 0.0}  # 10 ft east, same height
    dist, delta, level = derive_metrics(a, b)
    assert abs(dist - 10.0) < 0.02
    assert abs(delta) < 0.05
    assert level is True


def test_derive_metrics_off_level():
    a = {"x": 0.0, "y": 1.0, "z": 0.0}
    b = {"x": 1.0, "y": 1.02, "z": 0.0}  # ~0.79 in high
    dist, delta, level = derive_metrics(a, b)
    assert dist > 3.0
    assert delta > 0.5
    assert level is False
    assert meters_to_in(0.0254) == 1.0 or abs(meters_to_in(0.0254) - 1.0) < 0.001


INSERT_A = {"id": "hw-a", "name": "Insert A", "kind": "insert", "station_ft": 10.0, "tolerance_in": 0.5}
LIFT_B = {"id": "hw-b", "name": "Lift 1", "kind": "lift_loop", "station_ft": 25.0, "tolerance_in": 1.0}


def test_tape_stations_within_tolerance_pass():
    shots = [
        {"station_index": 1, "station_ft": 10.02, "delta_height_in": 0.04, "level": True},
        {"station_index": 2, "station_ft": 25.04, "delta_height_in": 0.02, "level": True},
    ]
    out = compare_tape_shots(shots, [INSERT_A, LIFT_B], default_tol_in=0.5)
    assert out["pass_count"] == 2
    assert out["rescan_count"] == 0
    assert out["matches"][0]["element_id"] == "hw-a"
    assert out["matches"][1]["element_id"] == "hw-b"
    assert out["matches"][0]["delta_in"] == 0.24
    assert out["matches"][1]["delta_in"] == 0.48
    assert out["unshot_count"] == 0


def test_tape_station_outside_tolerance_flags_rescan():
    shots = [
        {"station_index": 1, "station_ft": 10.08, "level": True},  # 0.96" > 0.5"
    ]
    out = compare_tape_shots(shots, [INSERT_A, LIFT_B], default_tol_in=0.5)
    assert out["matches"][0]["rescan"] is True
    assert out["matches"][0]["flag"] == "station_out_of_tolerance"
    assert out["rescan_count"] == 1
    assert out["unshot_count"] == 1
    assert out["unshot"][0]["id"] == "hw-b"


def test_tape_off_level_flags_rescan_even_when_station_matches():
    shots = [{"station_index": 1, "station_ft": 10.0, "level": False, "forced": False}]
    out = compare_tape_shots(shots, [INSERT_A], default_tol_in=0.5)
    assert out["matches"][0]["matched"] is True
    assert out["matches"][0]["within_tolerance"] is True
    assert out["matches"][0]["rescan"] is True
    assert "off_level" in out["matches"][0]["reasons"]


def test_tape_does_not_match_beyond_window():
    shots = [{"station_index": 1, "station_ft": 20.0, "level": True}]
    out = compare_tape_shots(shots, [INSERT_A, LIFT_B], default_tol_in=0.5)
    assert STATION_MATCH_WINDOW_FT == 3.0
    assert out["matches"][0]["matched"] is False
    assert out["matches"][0]["flag"] == "no_spec_match"
    assert out["matches"][0]["rescan"] is False
    assert out["unshot_count"] == 2


def test_tape_greedy_unused_ids():
    shots = [
        {"station_index": 1, "station_ft": 10.01, "level": True},
        {"station_index": 2, "station_ft": 10.04, "level": True},
    ]
    out = compare_tape_shots(shots, [INSERT_A, LIFT_B], default_tol_in=0.5)
    assert out["matches"][0]["element_id"] == "hw-a"
    assert out["matches"][1]["matched"] is False


def test_design_stations_from_spec_include_hold_downs():
    spec = {
        "hardware": [{"id": "h1", "kind": "insert", "name": "I1", "position": {"station_ft": 12.5}, "tolerance_in": 0.5}],
        "hold_downs": [{"id": "hd1", "type_spec": "HD", "station_from_marked_end": 33.0}],
        "tolerances": {"hold_down": 1.0},
    }
    rows = design_stations_from_spec(spec, 0.5)
    assert [r["id"] for r in rows] == ["h1", "hd1"]
    assert rows[1]["station_ft"] == 33.0
    assert rows[1]["kind"] == "hold_down"


def test_heuristic_summary_names_rescan_stations():
    compare = compare_tape_shots(
        [{"station_index": 1, "station_ft": 10.08, "level": True}],
        [INSERT_A],
        default_tol_in=0.5,
    )
    review = heuristic_tape_summary(compare)
    assert review["source"] == "heuristic"
    assert review["rescan_labels"]
    assert "Insert A" in review["rescan_labels"][0]
    assert "rescan" in review["summary"].lower()
