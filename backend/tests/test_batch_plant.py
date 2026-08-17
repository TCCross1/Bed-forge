"""Batch plant — w/cm, immutability, AI cannot write mix."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from batch_plant import (
    AI_CAN_WRITE_MIX,
    apply_recommendations_to_batch,
    build_recommendations,
    confirm_blocker,
    copy_library_into_batch,
    is_immutable,
    water_cementitious_ratio,
    weather_failure_env,
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


def test_confirm_requires_mix_code():
    assert confirm_blocker({"mix_code": ""}) == "Mix code is required before confirm"
    assert confirm_blocker({"mix_code": "  "}) == "Mix code is required before confirm"
    assert confirm_blocker({"mix_code": "SCC-8K"}) is None


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


def test_library_weights_copy_into_empty_batch():
    design = {
        "id": "mix-1",
        "mix_code": "SCC-8K",
        "target_strength_psi": 8000,
        "target_air_pct": 6.0,
        "ingredients": [
            {"kind": "cement", "name": "Type III cement", "weight_lb": 658},
            {"kind": "water", "name": "Batch water", "weight_lb": 250},
        ],
    }
    filled = copy_library_into_batch({"mix_design_id": "mix-1", "ingredients": []}, design)
    assert filled["mix_code"] == "SCC-8K"
    assert filled["target_strength_psi"] == 8000
    assert filled["ingredients"][0]["weight_lb"] == 658
    blank_template = copy_library_into_batch(
        {"mix_design_id": "mix-1", "ingredients": [{"kind": "cement", "name": "Type III cement", "weight_lb": "", "dosage": ""}]},
        design,
    )
    assert blank_template["ingredients"][0]["weight_lb"] == 658
    keyed = copy_library_into_batch(
        {"mix_code": "CUSTOM", "ingredients": [{"kind": "cement", "weight_lb": 600}], "target_strength_psi": 9000},
        design,
    )
    assert keyed["mix_code"] == "CUSTOM"
    assert keyed["ingredients"][0]["weight_lb"] == 600
    assert keyed["target_strength_psi"] == 9000


def test_weather_failure_never_blocks_and_omits_geo():
    env = weather_failure_env(manual_override=True)
    assert env["env_flag"] == "estimated/manual"
    assert env["source"] == "manual"
    assert "lat" not in env
    assert "lon" not in env


def test_batch_routes_module_parses():
    src = Path(__file__).resolve().parents[1] / "batch_routes.py"
    compile(src.read_text(encoding="utf-8"), str(src), "exec")
    assert "async async def" not in src.read_text(encoding="utf-8")


def test_jring_bands_still_match_astm():
    assert diameter_average(26, 28) == 27
    assert blocking_assessment(0.5)["code"] == "pass"
    assert blocking_assessment(1.5)["code"] == "borderline"
    assert blocking_assessment(2.5)["code"] == "blocking"
