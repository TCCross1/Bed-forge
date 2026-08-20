"""DISTO / LDM evaluation math."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from instrument_reading import can_override_instrument, evaluate_instrument_reading


def test_pass_within_eighth():
    result = evaluate_instrument_reading(47.25 * 12, 47.25 * 12, 0.125)
    assert result["within_tolerance"] is True
    assert result["status"] == "pass"
    assert result["delta_in"] == 0.0


def test_fail_outside_eighth():
    result = evaluate_instrument_reading(120.5, 120.0, 0.125)
    assert result["within_tolerance"] is False
    assert result["status"] == "fail"
    assert result["delta_in"] == 0.5
    assert result["lower_bound_in"] == 119.875
    assert result["upper_bound_in"] == 120.125


def test_capture_only_without_target():
    result = evaluate_instrument_reading(88.0)
    assert result["target_in"] is None
    assert result["within_tolerance"] is True
    assert result["status"] == "pass"


def test_override_roles():
    assert can_override_instrument("qc_supervisor") is True
    assert can_override_instrument("admin") is True
    assert can_override_instrument("qc_tech") is False
    assert can_override_instrument("production") is False
