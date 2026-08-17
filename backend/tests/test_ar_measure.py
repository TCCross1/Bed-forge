"""AR level math and measurement packing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ar_math import derive_metrics, evaluate_level, meters_to_in
from models import LEVEL_TOLERANCE_IN


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
