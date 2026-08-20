"""Fresh (plastic) concrete ticket math — spread average and ASTM C1621 J-ring bands."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fresh_concrete import (
    apply_computed_fields,
    blocking_assessment,
    blocking_delta,
    diameter_average,
    sanitize_gate,
    sanitize_test_types,
)


def test_spread_average_two_orthogonal_diameters():
    assert diameter_average(26, 28) == 27.0
    assert diameter_average("24.5", "25.5") == 25.0
    assert diameter_average(27, None) == 27.0
    assert diameter_average("", "") is None
    assert diameter_average(None, None) is None


def test_jring_blocking_bands_astm_c1621():
    assert blocking_assessment(0).get("code") == "pass"
    assert blocking_assessment(1.0).get("label") == "PASS"
    assert blocking_assessment(1.01).get("code") == "borderline"
    assert blocking_assessment(2.0).get("label") == "BORDERLINE"
    assert blocking_assessment(2.01).get("code") == "blocking"
    assert blocking_assessment(3.5).get("label") == "BLOCKING"
    assert blocking_assessment(-0.25).get("code") == "pass"
    assert blocking_assessment(None) is None


def test_blocking_delta_is_unconstrained_minus_jring():
    assert blocking_delta(28, 26.5) == 1.5
    assert blocking_delta(27, 27) == 0.0
    assert blocking_delta(None, 26) is None


def test_jring_reuses_spread_average_as_unconstrained():
    out = apply_computed_fields({
        "spread_d1_in": 27,
        "spread_d2_in": 29,
        "jring_d1_in": 25,
        "jring_d2_in": 25,
    })
    assert out["spread_avg_in"] == 28.0
    assert out["unconstrained_avg_in"] == 28.0
    assert out["jring_avg_in"] == 25.0
    assert out["blocking_delta_in"] == 3.0
    assert out["blocking_assessment"] == "blocking"
    assert out["blocking_label"] == "BLOCKING"


def test_sanitize_jring_keeps_spread_fields_in_play():
    types = sanitize_test_types(["jring"])
    assert types[0] == "spread"
    assert "jring" in types
    assert sanitize_test_types(["Spread", "J-Ring"]) == ["spread", "jring"]
    assert sanitize_gate("PASS") == "pass"
    assert sanitize_gate("nope") == "hold"
