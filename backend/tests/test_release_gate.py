"""Release gate — crush or predicted must meet required. Override is explicit."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maturity import evaluate_release_gate
from override_target import classify_override_target


def test_crush_pass_allows_release():
    gate = evaluate_release_gate(required_psi=4500, crush_psi=4600, predicted_psi=3000)
    assert gate["allow"] is True
    assert gate["via"] == "crush"
    assert gate["prompt_ncr"] is False


def test_predicted_pass_allows_without_crush():
    gate = evaluate_release_gate(required_psi=4500, crush_psi=None, predicted_psi=4700)
    assert gate["allow"] is True
    assert gate["via"] == "predicted"


def test_below_required_blocks_and_prompts_ncr():
    gate = evaluate_release_gate(required_psi=4500, crush_psi=3000, predicted_psi=3200)
    assert gate["allow"] is False
    assert gate["prompt_ncr"] is True
    assert "4500" in gate["reason"]


def test_override_allows_without_weakening_math():
    blocked = evaluate_release_gate(required_psi=4500, crush_psi=2000, predicted_psi=2000)
    assert blocked["allow"] is False
    allowed = evaluate_release_gate(required_psi=4500, crush_psi=2000, predicted_psi=2000, override_active=True)
    assert allowed["allow"] is True
    assert allowed["via"] == "override"


def test_release_strength_override_targets_beam():
    lookup = classify_override_target("release_strength", "L25390-B1")
    assert lookup["collection"] == "beams"
    assert lookup["alt_query"] == {"mark": "L25390-B1"}
