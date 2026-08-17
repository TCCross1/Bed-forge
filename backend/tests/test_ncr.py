"""NCR close rules, linkage, and escalation."""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ncr import (
    attach_prompt,
    build_prompt,
    close_blockers,
    frequency_insights,
    is_escalated,
    is_immutable,
    ncr_from_anomaly,
    photos_required,
    sanitize_severity,
    validate_transition,
)


def test_major_cannot_close_without_root_cause():
    rec = {
        "severity": "major",
        "status": "verification",
        "root_cause": "",
        "corrective_action": "grind and patch",
        "verification_by": "Dana",
        "signoff": "Dana Reyes",
        "category": "documentation",
        "photos": [],
    }
    assert close_blockers(rec, "qc_supervisor") == "Root cause is required before closing a Major or Critical NCR"
    rec["root_cause"] = "Insert jig walked 1/2 inch"
    assert close_blockers(rec, "qc_supervisor") is None


def test_tech_cannot_close_major():
    rec = {
        "severity": "critical",
        "root_cause": "strand pattern",
        "corrective_action": "re-lay",
        "verification_by": "Tyler",
        "signoff": "Tyler Chen",
        "category": "documentation",
        "photos": [],
    }
    assert "supervisor" in (close_blockers(rec, "qc_tech") or "").lower()
    assert close_blockers(rec, "qc_supervisor") is None


def test_visual_requires_photos():
    rec = {
        "severity": "minor",
        "category": "visual",
        "photos": [],
        "root_cause": "x",
        "corrective_action": "y",
        "verification_by": "z",
        "signoff": "z",
    }
    assert photos_required("visual") is True
    assert "Photos" in (close_blockers(rec, "qc_tech") or "")
    rec["photos"] = ["ncr-1.jpg"]
    assert close_blockers(rec, "qc_tech") is None


def test_linkage_from_anomaly():
    ncr = ncr_from_anomaly(
        {"id": "an-1", "beam_id": "b1", "type": "crack", "severity": "major", "note": "web crack", "position": {"x": 12}},
        {"id": "b1", "job_id": "j1", "pour_id": "p1", "bed_id": "bed-3"},
    )
    assert ncr["anomaly_id"] == "an-1"
    assert ncr["beam_ids"] == ["b1"]
    assert ncr["job_id"] == "j1"
    assert ncr["pour_id"] == "p1"
    assert ncr["bed_id"] == "bed-3"
    assert ncr["category"] == "visual"
    assert ncr["severity"] == "critical"
    assert ncr["twin_position"]["x"] == 12
    assert ncr["source_type"] == "anomaly"


def test_critical_escalates_immediately():
    rec = {"severity": "critical", "status": "open", "created_at": datetime.now(timezone.utc).isoformat()}
    assert is_escalated(rec) is True
    old = {
        "severity": "minor",
        "status": "open",
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=80)).isoformat(),
    }
    assert is_escalated(old) is True


def test_closed_is_immutable_until_supervisor_reopen():
    rec = {"status": "closed"}
    assert is_immutable(rec) is True
    assert validate_transition("closed", "investigating", "qc_tech")
    assert validate_transition("closed", "investigating", "qc_supervisor") is None
    assert validate_transition("open", "closed", "admin")  # skip verification


def test_prompt_attaches_without_dropping_payload():
    prompt = build_prompt(
        source_type="tension",
        source_id="s1",
        title="Strand out of ±5%",
        category="strand",
        severity="major",
        description="variance 8%",
        beam_id="b1",
    )
    out = attach_prompt({"id": "shot", "within_tolerance": False}, prompt)
    assert out["id"] == "shot"
    assert out["ncr_prompt"]["source_type"] == "tension"
    assert out["ncr_prompt"]["beam_id"] == "b1"


def test_frequency_insights_hot_type():
    rows = [{"sub_type": "insert", "category": "hardware", "status": "open", "bed_id": "bed-1", "severity": "minor", "created_at": datetime.now(timezone.utc).isoformat()} for _ in range(7)]
    recs = frequency_insights(rows)
    assert any(r["id"] == "ncr-hot-type" and r["count"] == 7 for r in recs)
    assert all(r.get("ai_writes_mix") is False for r in recs)


def test_moderate_maps_to_major():
    assert sanitize_severity("moderate") == "major"
    assert sanitize_severity("CRITICAL") == "critical"


def test_linkage_fields_required_shape():
    ncr = ncr_from_anomaly(
        {"id": "an-2", "beam_id": "b9", "type": "spall", "severity": "minor"},
        {"job_id": "j", "pour_id": "p", "bed_id": "bed"},
    )
    for key in ("beam_ids", "job_id", "pour_id", "bed_id", "anomaly_id", "source_id", "twin_position"):
        assert key in ncr
    assert ncr["beam_ids"] == ["b9"]
