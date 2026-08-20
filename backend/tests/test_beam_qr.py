"""Beam QR identity — tokens, deep links, limited dossier, PNG, and laminate PDF."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beam_qr import (
    beam_deep_link,
    build_qr_label_pdf,
    limit_dossier,
    new_qr_token,
    normalize_token,
    parse_scanned_value,
    qr_png_bytes,
)


def test_parse_scanned_value_from_url_and_raw():
    token = "abc123def4567890"
    assert parse_scanned_value(f"https://plant.example/b/{token}") == token
    assert parse_scanned_value(f"http://localhost:3000/b/{token}?from=cam") == token
    assert parse_scanned_value(f"http://localhost:3000/b/{token}#dossier") == token
    assert parse_scanned_value(token) == token
    assert parse_scanned_value("") == ""


def test_normalize_token_rejects_junk():
    token = "deadbeefcafebabe"
    assert normalize_token(f"https://qc.example.com/b/{token}/") == token
    assert normalize_token("not-a-token") == ""
    assert normalize_token("/b/short") == ""


def test_beam_deep_link_shape(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://qc.example.com/")
    assert beam_deep_link("deadbeefcafebabe") == "https://qc.example.com/b/deadbeefcafebabe"


def test_public_app_url_ignores_wildcard_cors(monkeypatch):
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    from beam_qr import public_app_url

    assert public_app_url() == "http://localhost:3000"


def test_limit_dossier_omits_qc_worksheets():
    full = {
        "access": "full",
        "id": "beam-1",
        "mark": "B1",
        "qr_token": "deadbeefcafebabe",
        "qr_url": "http://localhost:3000/b/deadbeefcafebabe",
        "status": "curing",
        "qc_state": "passed",
        "production_status": "cured",
        "twin_type": "i_beam",
        "length_ft": 90,
        "job": {"job_number": "L25390"},
        "pour": {"pour_number": "P-118"},
        "bed": {"bed_number": 3},
        "marked_end": {"toward": "header"},
        "product_type": {"name": "Type III"},
        "spec": {
            "product_name": "AASHTO Type III",
            "geometry": {"length_ft": 90, "depth_in": 45, "width_in": 16},
            "strands": [{}, {}],
            "hold_downs": [{}],
            "hardware": [{}, {}, {}],
            "status": "locked",
        },
        "blueprints": [{"id": "bp-1"}],
        "company": {"company_name": "TEST"},
        "inspections": [{"id": "qir"}],
        "tension_reports": [{"id": "t1"}],
        "anomalies": [{"id": "a1"}],
        "camber_readings": [{"id": "c1"}],
        "finish_sheets": [{"id": "f1"}],
        "pre_delivery": [{"id": "p1"}],
        "created_at": "2026-08-17T00:00:00+00:00",
    }
    limited = limit_dossier(full)
    assert limited["access"] == "limited"
    assert limited["mark"] == "B1"
    assert limited["spec"]["product_name"] == "AASHTO Type III"
    assert limited["spec_summary"]["strand_count"] == 2
    assert limited["blueprints"] == [{"id": "bp-1"}]
    assert "inspections" not in limited
    assert "tension_reports" not in limited
    assert "anomalies" not in limited
    assert "camber_readings" not in limited
    assert "finish_sheets" not in limited
    assert "pre_delivery" not in limited


def test_qr_png_bytes_are_png():
    png = qr_png_bytes("https://example.com/b/deadbeefcafebabe")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 200


def test_qr_label_pdf_is_pdf():
    png = qr_png_bytes("https://example.com/b/deadbeefcafebabe")
    pdf = build_qr_label_pdf(
        [{"job_number": "L25390", "mark": "B1", "qr_png": png}],
        {"company_name": "PRESTRESS SERVICES INDUSTRIES LLC", "tag_header": ""},
        None,
    )
    assert pdf.startswith(b"%PDF")
    assert b"L25390" in pdf or b"B1" in pdf


def test_new_qr_token_is_16_hex():
    token = new_qr_token()
    assert len(token) == 16
    assert normalize_token(token) == token
