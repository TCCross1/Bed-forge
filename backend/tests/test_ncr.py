"""NCR close rules, linkage, roles, 409s, and auto-prompt idempotency."""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ncr import (
    attach_prompt,
    build_prompt,
    can_close,
    can_create,
    can_manage,
    can_raise_severity,
    close_blockers,
    close_http_code,
    frequency_insights,
    is_escalated,
    is_immutable,
    match_open_source,
    ncr_from_anomaly,
    ncr_photo_url,
    photos_required,
    public_ncr,
    sanitize_severity,
    transition_blockers,
    validate_transition,
)


def _major_ready(**overrides):
    rec = {
        "severity": "major",
        "status": "verification",
        "root_cause": "Insert jig walked 1/2 inch",
        "corrective_action": "grind and patch",
        "verification_by": "Dana",
        "signoff": "Dana Reyes",
        "category": "documentation",
        "photos": [],
    }
    rec.update(overrides)
    return rec


def test_major_cannot_close_without_root_cause():
    rec = _major_ready(root_cause="")
    assert close_blockers(rec, "qc_supervisor") == "Root cause is required before closing a Major or Critical NCR"
    rec["root_cause"] = "Insert jig walked 1/2 inch"
    assert close_blockers(rec, "qc_supervisor") is None


def test_major_close_without_root_cause_is_409():
    rec = _major_ready(root_cause="")
    assert close_http_code(rec, "qc_supervisor") == 409
    assert transition_blockers(rec, "closed", "qc_supervisor") == "Root cause is required before closing a Major or Critical NCR"
    rec["root_cause"] = "Insert jig walked 1/2 inch"
    assert close_http_code(rec, "qc_supervisor") == 200
    assert transition_blockers(rec, "closed", "qc_supervisor") is None


def test_tech_cannot_close_major():
    rec = {
        "severity": "critical",
        "status": "verification",
        "root_cause": "strand pattern",
        "corrective_action": "re-lay",
        "verification_by": "Tyler",
        "signoff": "Tyler Chen",
        "category": "documentation",
        "photos": [],
    }
    assert "supervisor" in (close_blockers(rec, "qc_tech") or "").lower()
    assert close_http_code(rec, "qc_tech") == 409
    assert close_blockers(rec, "qc_supervisor") is None
    assert can_close("qc_tech", "major") is False
    assert can_close("qc_supervisor", "major") is True
    assert can_close("admin", "critical") is True
    assert can_close("qc_tech", "minor") is True


def test_tech_cannot_skip_or_reject_or_reopen():
    assert validate_transition("open", "closed", "admin")
    assert validate_transition("verification", "closed", "qc_tech", "major")
    assert validate_transition("verification", "closed", "qc_supervisor", "major") is None
    assert validate_transition("open", "rejected", "qc_tech")
    assert validate_transition("open", "rejected", "qc_supervisor") is None
    assert validate_transition("closed", "investigating", "qc_tech")
    assert validate_transition("closed", "investigating", "qc_supervisor") is None
    assert "Written reason" in (transition_blockers({"status": "closed", "severity": "minor"}, "investigating", "qc_supervisor", "") or "")
    assert transition_blockers({"status": "closed", "severity": "minor"}, "investigating", "qc_supervisor", "recheck camber") is None


def test_roles_who_can_file():
    assert can_create("qc_tech") is True
    assert can_create("production") is True
    assert can_create("qc_supervisor") is True
    assert can_create("") is False
    assert can_create("visitor") is False
    assert can_manage("qc_tech") is False
    assert can_manage("admin") is True
    assert can_raise_severity("qc_tech", "minor", "major") is False
    assert can_raise_severity("qc_supervisor", "minor", "critical") is True
    assert can_raise_severity("qc_tech", "major", "minor") is True


def test_visual_requires_photos():
    rec = {
        "severity": "minor",
        "status": "verification",
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
    assert close_http_code(rec, "qc_tech") == 200


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
    assert validate_transition("open", "closed", "admin")


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


def test_auto_prompt_idempotent_by_open_source():
    open_row = {
        "id": "ncr-open",
        "source_type": "fresh",
        "source_id": "ft-1",
        "status": "investigating",
        "severity": "major",
    }
    closed_row = {
        "id": "ncr-old",
        "source_type": "fresh",
        "source_id": "ft-1",
        "status": "closed",
        "severity": "major",
    }
    assert match_open_source([open_row, closed_row], source_type="fresh", source_id="ft-1")["id"] == "ncr-open"
    assert match_open_source([closed_row], source_type="fresh", source_id="ft-1") is None
    assert match_open_source([open_row], source_type="cylinder", source_id="ft-1") is None
    assert match_open_source([open_row], source_type="fresh", source_id="ft-2") is None
    assert match_open_source([open_row], source_type="manual", source_id="ft-1") is None
    pin = {"id": "ncr-pin", "anomaly_id": "an-9", "source_type": "anomaly", "source_id": "an-9", "status": "open"}
    assert match_open_source([pin], anomaly_id="an-9")["id"] == "ncr-pin"
    assert match_open_source([pin], anomaly_id="an-other") is None


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


def test_public_ncr_photo_urls_do_not_embed_bytes():
    out = public_ncr({"id": "abc12345xxxx", "photos": ["ncr-abc12345-1.jpg"], "status": "open", "severity": "minor", "category": "visual"})
    assert out["photos"] == ["ncr-abc12345-1.jpg"]
    assert out["photo_urls"] == [ncr_photo_url("abc12345xxxx", "ncr-abc12345-1.jpg")]
    assert "/api/ncrs/abc12345xxxx/photos/ncr-abc12345-1.jpg" in out["photo_urls"][0]
    assert "AAAA" not in str(out)


def test_ncr_routes_module_parses():
    src = Path(__file__).resolve().parents[1] / "ncr_routes.py"
    compile(src.read_text(encoding="utf-8"), str(src), "exec")
    text = src.read_text(encoding="utf-8")
    assert "bytes=%s" not in text
    assert '"bytes"' not in text
    assert "async async def" not in text
