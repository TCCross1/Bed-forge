"""Batch plant — w/cm, immutability, AI cannot write mix."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from batch_plant import (
    AI_CAN_WRITE_MIX,
    apply_recommendations_to_batch,
    build_recommendations,
    is_immutable,
    water_cementitious_ratio,
)
from fresh_concrete import blocking_assessment, diameter_average


def test_wcm_counts_cement_scm_water_and_ice():
    ingredients = [
        {"kind": "cement", "weight_lb": 600},
        {"kind": "scm", "name": "Fly ash", "weight_lb": 100},
        {"kind": "water", "weight_lb": 250},
        {"kind": "ice", "weight_lb": 30},
        {"kind": "sand", "weight_lb": 1400},
    ]
    assert water_cementitious_ratio(ingredients) == pytest.approx(280 / 700, rel=1e-4)
    assert water_cementitious_ratio([{"kind": "sand", "weight_lb": 10}]) is None


def test_confirmed_batch_is_immutable():
    assert is_immutable({"status": "confirmed", "immutable": True}) is True
    assert is_immutable({"status": "draft", "immutable": False}) is False
    assert is_immutable({"status": "confirmed"}) is True


def test_ai_cannot_write_mix():
    assert AI_CAN_WRITE_MIX is False
    with pytest.raises(PermissionError, match="cannot change the mix"):
        apply_recommendations_to_batch({"ingredients": [{"kind": "cement", "weight_lb": 600}]}, [{"suggested_aea_delta_oz_cwt": 0.5}])


def test_recommendations_cite_history_and_never_flag_write():
    batch = {
        "id": "now",
        "mix_code": "SCC-8K",
        "target_air_pct": 6.0,
        "target_strength_psi": 8000,
        "w_cm": 0.38,
        "environment": {"ambient_f": 92, "rh_pct": 28, "weather": "sunny"},
        "ingredients": [{"kind": "admixture", "name": "AEA", "dosage": 0.8}],
        "linked_fresh": [{"air_content_pct": 4.2}],
    }
    history = [{
        "id": "hist-1",
        "status": "confirmed",
        "mix_code": "SCC-8K",
        "w_cm": 0.36,
        "target_strength_psi": 8000,
        "ingredients": [{"kind": "admixture", "name": "Retarder", "dosage": 2.0}],
        "linked_cylinders": [{"crush_age_days": 28, "crush_psi": 9200}],
    }]
    recs = build_recommendations(batch, history)
    assert recs
    assert all(r.get("ai_writes_mix") is False for r in recs)
    assert any(r.get("id") == "hot-dry-air" for r in recs)
    cited = [cid for r in recs for cid in (r.get("cite_batch_ids") or [])]
    assert "hist-1" in cited or any(r.get("id") == "wcm-retarder" for r in recs)


def test_jring_bands_still_match_astm():
    assert diameter_average(26, 28) == 27
    assert blocking_assessment(0.5)["code"] == "pass"
    assert blocking_assessment(1.5)["code"] == "borderline"
    assert blocking_assessment(2.5)["code"] == "blocking"
