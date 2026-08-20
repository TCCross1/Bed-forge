"""Batch Intelligence — full QC lab suite scoring, never invent doses."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from batch_intelligence import (
    INSUFFICIENT,
    INSUFFICIENT_MESSAGE,
    MIN_WINNERS,
    classify_test_type,
    envelope_to_ticket_fields,
    lab_completeness,
    normalize_qc_results,
    recommend_from_history,
    score_snapshot,
)
from batch_plant import AI_CAN_WRITE_MIX, apply_recommendations_to_batch


def _winner(**kwargs):
    qc = normalize_qc_results(
        {
            "compressive": kwargs.pop("compressive", [
                {"age_hours": 16, "psi": 5200, "test_type": "release", "pass_fail": "pass", "break_load": 118000},
                {"age_hours": 168, "psi": 7800, "test_type": "7d", "pass_fail": "pass"},
                {"age_hours": 672, "psi": 9100, "test_type": "28d", "pass_fail": "pass"},
            ]),
            "air_content_pct": kwargs.pop("air_content_pct", 5.8),
            "slump_in": kwargs.pop("slump_in", 5.5),
            "concrete_temp_f": kwargs.pop("concrete_temp_f", 72),
            "unit_weight_pcf": kwargs.pop("unit_weight_pcf", 147.5),
            "ncr_ids": kwargs.pop("ncr_ids", []),
            "time_to_release_hours": kwargs.pop("time_to_release_hours", 16),
        }
    )
    row = {
        "id": kwargs.pop("id", "b1"),
        "batch_id": kwargs.pop("batch_id", "b1"),
        "pour_id": kwargs.pop("pour_id", "p1"),
        "mix_code": kwargs.pop("mix_code", "HPC-8500"),
        "ticket_number": kwargs.pop("ticket_number", "T-1"),
        "environment": kwargs.pop("environment", {"ambient_f": 70, "rh_pct": 55}),
        "ingredients": kwargs.pop("ingredients", [
            {"name": "Type III Cement", "kind": "cement", "actual_lb": 940},
            {"name": "Coarse Aggregate", "kind": "coarse", "actual_lb": 1780},
        ]),
        "admixtures": kwargs.pop("admixtures", [
            {"name": "AEA", "dosage_oz": 4.0},
            {"name": "HRWR", "dosage_oz": 42.0},
        ]),
        "qc_results": qc,
    }
    row.update(kwargs)
    return row


QUERY = {
    "mix_code": "HPC-8500",
    "required_release_psi": 4500,
    "required_7d_psi": 7000,
    "required_28d_psi": 8500,
    "target_air_pct": 6.0,
    "target_slump_in": 5.5,
    "ambient_f": 72,
    "rh_pct": 50,
}


def test_qc_results_store_full_lab_suite():
    qc = normalize_qc_results(
        {
            "compressive": [
                {"age_hours": 18, "psi": 4800, "break_load": 110000, "test_type": "release"},
            ],
            "air_content_pct": 6.2,
            "slump_in": 5.25,
            "concrete_temp_f": 71,
            "unit_weight_pcf": 148.1,
            "retest_of": "cyl-old",
            "ncr_ids": ["ncr-1"],
            "time_to_release_hours": 18,
        }
    )
    assert qc["air_content_pct"] == 6.2
    assert qc["slump_in"] == 5.25
    assert qc["concrete_temp_f"] == 71
    assert qc["unit_weight_pcf"] == 148.1
    assert qc["retest_of"] == "cyl-old"
    assert qc["ncr_ids"] == ["ncr-1"]
    assert qc["time_to_release_hours"] == 18
    assert qc["compressive"][0]["test_type"] == "release"
    assert qc["compressive"][0]["break_load"] == 110000


def test_age_hours_classify_release_7d_28d():
    assert classify_test_type(16) == "release"
    assert classify_test_type(168) == "7d"
    assert classify_test_type(672) == "28d"
    assert classify_test_type(40, explicit="other") == "other"


def test_complete_lab_outscores_sparse_psi_only():
    query = dict(QUERY)
    complete = score_snapshot(_winner(id="full"), query)
    sparse = score_snapshot(
        _winner(
            id="sparse",
            air_content_pct=None,
            slump_in=None,
            concrete_temp_f=None,
            unit_weight_pcf=None,
            compressive=[{"age_hours": 16, "psi": 5200, "test_type": "release", "pass_fail": "pass"}],
        ),
        query,
    )
    assert complete["eligible"] is True
    assert sparse["eligible"] is True
    assert lab_completeness(complete["qc_results"]) > lab_completeness(sparse["qc_results"])
    assert complete["score"] > sparse["score"]
    assert "air" in complete["factors"]
    assert "slump" in complete["factors"]
    assert "environment" in complete["factors"]


def test_failed_release_or_open_ncr_is_not_a_winner():
    query = dict(QUERY)
    failed = score_snapshot(
        _winner(compressive=[{"age_hours": 16, "psi": 3000, "test_type": "release", "pass_fail": "fail"}]),
        query,
    )
    ncr = score_snapshot(
        _winner(ncr_ids=["ncr-open"]),
        query,
        ncrs=[{"id": "ncr-open", "status": "open", "category": "material", "pour_id": "p1"}],
    )
    air_out = score_snapshot(_winner(air_content_pct=2.0), query)
    env_out = score_snapshot(_winner(environment={"ambient_f": 95, "rh_pct": 20}), query)
    assert failed["eligible"] is False
    assert ncr["eligible"] is False
    assert air_out["eligible"] is False
    assert env_out["eligible"] is False


def test_thin_history_returns_insufficient_and_never_invents_doses():
    result = recommend_from_history([_winner(), _winner(id="b2", batch_id="b2")], QUERY)
    assert result["status"] == INSUFFICIENT
    assert result["message"] == INSUFFICIENT_MESSAGE
    assert result["mix_envelope"] is None
    assert result["comparables"] == []
    assert result["ai_writes_mix"] is False
    assert result["confidence"]["winner_count"] < MIN_WINNERS
    assert envelope_to_ticket_fields(result["mix_envelope"]) == ([], [])


def test_envelope_min_median_max_from_winners_only():
    history = [
        _winner(id="a", batch_id="a", admixtures=[{"name": "AEA", "dosage_oz": 3.0}], ingredients=[{"name": "Type III Cement", "kind": "cement", "actual_lb": 900}]),
        _winner(id="b", batch_id="b", admixtures=[{"name": "AEA", "dosage_oz": 4.0}], ingredients=[{"name": "Type III Cement", "kind": "cement", "actual_lb": 940}]),
        _winner(id="c", batch_id="c", admixtures=[{"name": "AEA", "dosage_oz": 5.0}], ingredients=[{"name": "Type III Cement", "kind": "cement", "actual_lb": 980}]),
    ]
    result = recommend_from_history(history, QUERY)
    assert result["status"] == "ok"
    materials = {row["name"]: row for row in result["mix_envelope"]["materials"]}
    aea = materials["AEA"]
    cement = materials["Type III Cement"]
    assert aea["min"] == 3.0
    assert aea["median"] == 4.0
    assert aea["max"] == 5.0
    assert cement["min"] == 900
    assert cement["median"] == 940
    assert cement["max"] == 980
    assert result["confidence"]["sample_size"] == 3
    assert result["drivers"]["strength_curve"]["used"] is True
    assert result["drivers"]["air"]["used"] is True
    assert result["comparables"][0]["lab_snapshot"]["air_content_pct"] is not None
    ingredients, admixtures = envelope_to_ticket_fields(result["mix_envelope"])
    assert any(item["name"] == "Type III Cement" for item in ingredients)
    assert any(item["name"] == "AEA" for item in admixtures)


def test_missing_admixture_is_omitted_never_invented():
    history = [
        _winner(id="a", batch_id="a", admixtures=[], ingredients=[{"name": "Type III Cement", "kind": "cement", "actual_lb": 940}]),
        _winner(id="b", batch_id="b", admixtures=[], ingredients=[{"name": "Type III Cement", "kind": "cement", "actual_lb": 940}]),
        _winner(id="c", batch_id="c", admixtures=[], ingredients=[{"name": "Type III Cement", "kind": "cement", "actual_lb": 940}]),
    ]
    result = recommend_from_history(history, QUERY)
    names = [row["name"] for row in result["mix_envelope"]["materials"]]
    assert "AEA" not in names
    assert "Retarder" not in names
    _ing, admixed = envelope_to_ticket_fields(result["mix_envelope"])
    assert admixed == []


def test_ai_still_cannot_write_mix():
    assert AI_CAN_WRITE_MIX is False
    with pytest.raises(PermissionError):
        apply_recommendations_to_batch({"ingredients": []}, [{"suggested_aea_delta_oz_cwt": 0.4}])


def test_routes_module_parses():
    src = Path(__file__).resolve().parents[1] / "batch_intelligence_routes.py"
    compile(src.read_text(encoding="utf-8"), str(src), "exec")
    text = src.read_text(encoding="utf-8")
    assert "/batch-intelligence/recommend" in text
    assert "/batch-intelligence/export" in text
    assert "append_batch_event" in text
    assert "update_one" not in text
