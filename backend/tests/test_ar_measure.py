"""AR level math, digital-tape vs twin matching, daily calibration lock, and QC narrative fallback."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ar_math import (
    CAL_EXPIRED_DETAIL,
    CAL_LOCK_HOURS,
    CAL_TOLERANCE_PCT,
    STATION_MATCH_WINDOW_FT,
    WEB_HONESTY_LABEL,
    apply_device_scale,
    cal_expires_at,
    cal_lock_status,
    compare_tape_shots,
    derive_metrics,
    design_stations_from_spec,
    evaluate_calibration,
    evaluate_level,
    measure_block,
    meters_to_in,
    public_cal_audit,
    sanitize_engine,
    scale_for_device,
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


def test_cal_tolerance_is_point_one_five_percent():
    assert CAL_TOLERANCE_PCT == 0.15
    assert CAL_LOCK_HOURS == 24
    edge = evaluate_calibration(10.0, 10.015)
    assert edge["passed"] is True
    assert abs(edge["error_pct"] - 0.15) < 1e-6
    over = evaluate_calibration(10.0, 10.016)
    assert over["passed"] is False
    assert over["error_pct"] > 0.15
    under = evaluate_calibration(10.0, 9.985)
    assert under["passed"] is True
    fail_low = evaluate_calibration(10.0, 9.98)
    assert fail_low["passed"] is False
    assert fail_low["scale_factor"] == round(10.0 / 9.98, 8)


def test_failed_cal_does_not_unlock():
    result = evaluate_calibration(10.0, 10.05)
    assert result["passed"] is False
    rec = {
        "device_id": "phone-a",
        "passed": False,
        "scale_factor": result["scale_factor"],
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": cal_expires_at().isoformat(),
    }
    status = cal_lock_status(rec)
    assert status["allowed"] is False
    assert status["http_code"] == 409
    blocked = measure_block(status)
    assert blocked is not None
    assert blocked[0] == 409


def test_24h_lock_allows_then_expires_409():
    now = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    rec = {
        "device_id": "phone-a",
        "passed": True,
        "scale_factor": 0.999,
        "calibrated_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
        "calibrated_by": "Dana",
        "known_length_ft": 10.0,
        "measured_length_ft": 10.01,
    }
    live = cal_lock_status(rec, now=now + timedelta(hours=23, minutes=59))
    assert live["allowed"] is True
    assert live["http_code"] == 200
    assert live["remaining_seconds"] > 0
    assert measure_block(live) is None
    dead = cal_lock_status(rec, now=now + timedelta(hours=24, seconds=1))
    assert dead["allowed"] is False
    assert dead["http_code"] == 409
    assert dead["detail"] == CAL_EXPIRED_DETAIL
    code, detail = measure_block(dead)
    assert code == 409
    assert "expired" in detail.lower()


def test_missing_cal_is_409():
    status = cal_lock_status(None)
    assert status["allowed"] is False
    assert status["http_code"] == 409
    assert measure_block(status)[0] == 409


def test_scale_is_per_device_not_plant_wide():
    now = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    phone_a = {
        "device_id": "phone-a",
        "passed": True,
        "scale_factor": 0.9985,
        "calibrated_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
    }
    phone_b = {
        "device_id": "phone-b",
        "passed": True,
        "scale_factor": 1.012,
        "calibrated_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
    }
    assert scale_for_device(phone_a, "phone-a", now=now) == 0.9985
    assert scale_for_device(phone_b, "phone-b", now=now) == 1.012
    assert scale_for_device(phone_a, "phone-b", now=now) is None
    assert scale_for_device(phone_b, "phone-a", now=now) is None
    assert apply_device_scale(10.0, 0.9985) == 9.985
    expired = {**phone_a, "expires_at": (now - timedelta(minutes=1)).isoformat()}
    assert scale_for_device(expired, "phone-a", now=now) is None


def test_web_engine_cannot_claim_lidar_or_arkit():
    web = sanitize_engine("web", lidar=True)
    assert web["lidar"] is False
    assert web["is_native"] is False
    assert web["honesty_label"] == WEB_HONESTY_LABEL
    assert "not ARKit" in web["honesty_label"]
    gravity = sanitize_engine("gravity", lidar=True)
    assert gravity["lidar"] is False
    assert "LiDAR" in gravity["honesty_label"] and "not" in gravity["honesty_label"]
    native = sanitize_engine("arkit", lidar=False)
    assert native["is_native"] is True
    assert native["lidar"] is False
    assert "ARKit" in native["honesty_label"]
    lidar = sanitize_engine("arkit-lidar", lidar=True)
    assert lidar["lidar"] is True
    assert lidar["honesty_label"].startswith("ARKit")
    assert "LiDAR" in lidar["honesty_label"]


def test_cal_audit_omits_photo_and_gps():
    row = public_cal_audit({
        "id": "c1",
        "device_id": "phone-a",
        "known_length_ft": 10.0,
        "measured_length_ft": 10.01,
        "scale_factor": 0.999,
        "error_pct": 0.1,
        "passed": True,
        "engine": "web",
        "calibrated_by": "Dana",
        "calibrated_at": "2026-08-17T12:00:00+00:00",
        "photo_data": "VERY-LONG-BASE64",
        "gps": {"lat": 38.2, "lng": -85.7},
        "latitude": 38.2,
    })
    blob = str(row)
    assert "VERY-LONG-BASE64" not in blob
    assert "38.2" not in blob
    assert "gps" not in row
    assert "photo_data" not in row
    assert row["passed"] is True
    assert row["device_id"] == "phone-a"
    assert row["scale_factor"] == 0.999
