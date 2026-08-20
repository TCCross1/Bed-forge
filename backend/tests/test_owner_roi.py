"""Predictive release, packing suggestions, and owner cost signals."""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bed_layout import remaining_ft, suggest_fit, utilization_pct
from finance_signals import build_finance_signals
from maturity import classify_release, forecast_release, nurse_saul_increment_c_hours, predict_strength_psi
from package_export import build_package_xlsx


def test_warm_overnight_expected_pass():
    start = datetime(2026, 8, 16, 16, 0, tzinfo=timezone.utc)
    samples = [{"recorded_at": start.isoformat(), "temp_f": 70}]
    as_of = (start + timedelta(hours=18)).isoformat()
    fc = forecast_release(required_psi=4000, samples=samples, pour_at=start.isoformat(), as_of=as_of)
    assert fc["status"] == "expected_pass"
    assert fc["predicted_psi"] >= 4000


def test_cold_pour_fail_risk():
    start = datetime(2026, 8, 16, 16, 0, tzinfo=timezone.utc)
    samples = [{"recorded_at": start.isoformat(), "temp_f": 48}]
    as_of = (start + timedelta(hours=12)).isoformat()
    fc = forecast_release(required_psi=4000, samples=samples, pour_at=start.isoformat(), as_of=as_of)
    assert fc["status"] == "fail_risk"
    assert "early" in fc["advice"].lower() or "under" in fc["advice"].lower()


def test_crush_overrides_prediction():
    assert classify_release(3000, 4000, crush_psi=4200) == "confirmed_pass"
    assert classify_release(5000, 4000, crush_psi=3500) == "confirmed_fail"


def test_nurse_saul_zero_below_datum():
    assert nurse_saul_increment_c_hours(30, 10, datum_c=0) == 0  # -1.1 C
    assert predict_strength_psi(0) == 0


def test_suggest_least_changeover_same_job():
    beds = [
        {"id": "b3", "bed_number": 3, "length_ft": 400},
        {"id": "b4", "bed_number": 4, "length_ft": 400},
    ]
    occupied = {
        "b3": [{"id": "x", "job_id": "j1", "twin_type": "i_beam", "length_ft": 60}],
    }
    unassigned = [
        {"id": "a", "mark": "B1", "length_ft": 60, "job_id": "j1", "twin_type": "i_beam"},
        {"id": "b", "mark": "B2", "length_ft": 60, "job_id": "j1", "twin_type": "i_beam"},
        {"id": "c", "mark": "B3", "length_ft": 60, "job_id": "j1", "twin_type": "i_beam"},
        {"id": "d", "mark": "B4", "length_ft": 60, "job_id": "j1", "twin_type": "i_beam"},
    ]
    out = suggest_fit(beds, occupied, unassigned, "2026-08-18")
    assert out["suggestions"]
    top = out["suggestions"][0]
    assert top["bed_number"] == 3
    assert top["count"] == 4
    assert top["changeover"] == "least changeover"
    assert "Bed 3" in top["headline"]


def test_utilization_and_remaining():
    assert remaining_ft(300, [60, 60]) > 100
    assert utilization_pct(300, [60, 60]) < 50


def test_finance_ncr_and_scrap_tally():
    beams = [
        {"id": "1", "mark": "H1", "qc_state": "hold", "production_status": "cured"},
        {"id": "2", "mark": "H2", "qc_state": "failed"},
        {"id": "3", "mark": "OK", "qc_state": "passed"},
    ]
    sig = build_finance_signals(
        beams=beams,
        anomalies=[{"severity": "major"}],
        assignments=[{"bed_id": "b1", "scheduled_date": "2026-08-17"}],
        forecasts=[{"status": "fail_risk", "bed_id": "b1"}],
        settings={"ncr_cost_usd": 1000, "scrap_cost_usd": 2000, "bed_day_cost_usd": 500, "overtime_hold_usd": 100},
    )
    assert sig["open_ncrs"] == 3
    assert sig["scrap_count"] == 1
    assert sig["estimated_scrap_cost"] == 2000
    assert sig["total_quality_dollars_at_risk"] > 0


def test_package_xlsx_builds():
    data = build_package_xlsx({
        "company": {"company_name": "TEST PLANT"},
        "job": {"job_number": "L25390", "customer": "KYTC"},
        "pour": {"pour_number": "P1", "pour_date": "2026-08-17"},
        "beam_marks": ["B1"],
        "inspections": [{"beam_mark": "B1", "section": "layout", "status": "pass", "inspector": "QC"}],
        "tension_reports": [],
        "camber_readings": [],
        "cylinders": [],
        "finish_sheets": [],
        "pre_delivery": [],
        "strand_rolls": [{"heat_number": "H1", "reel_number": "R1"}],
        "drawings": [],
    })
    assert data[:2] == b"PK"
