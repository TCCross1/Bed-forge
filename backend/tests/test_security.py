"""Security primitives — encryption, IP allow-list, redaction, roles."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("JWT_SECRET", "unit-test-secret-not-for-production-use-32")

from security_core import (
    EXEC_ROLES, decrypt_bytes, encrypt_bytes, ip_allowed, is_exec, parse_cidrs,
    redact_value, write_protected, read_protected,
)
from storage import vault_dir


def test_exec_roles_include_plant_manager_and_owner():
    assert "admin" in EXEC_ROLES
    assert "executive" in EXEC_ROLES
    assert is_exec("admin")
    assert is_exec("executive")
    assert not is_exec("qc_tech")


def test_encrypt_roundtrip_and_plaintext_passthrough(tmp_path):
    payload = b"mill-cert-secret"
    wrapped = encrypt_bytes(payload)
    assert wrapped.startswith(b"BFENC1")
    assert decrypt_bytes(wrapped) == payload
    assert decrypt_bytes(b"plain-drawing") == b"plain-drawing"
    dest = tmp_path / "tag.bin"
    write_protected(dest, payload)
    assert read_protected(dest) == payload


def test_ip_allowlist_office_vpn():
    cidrs = ["10.0.0.0/8", "192.168.1.0/24"]
    assert parse_cidrs(cidrs)
    assert ip_allowed("10.4.2.9", cidrs)
    assert ip_allowed("192.168.1.40", cidrs)
    assert not ip_allowed("8.8.8.8", cidrs)
    assert ip_allowed("8.8.8.8", [])


def test_redact_strips_secrets_and_photos():
    dirty = {
        "email": "tech@plant.com",
        "password_hash": "bcrypt",
        "access_token": "abc",
        "photo_data": "AAAA",
        "raw_text": "HEAT 123",
        "nested": {"secret": "nope", "mark": "B1"},
    }
    clean = redact_value(dirty)
    assert clean["email"] == "tech@plant.com"
    assert clean["password_hash"] == "[redacted]"
    assert clean["access_token"] == "[redacted]"
    assert clean["photo_data"] == "[redacted]"
    assert clean["raw_text"] == "[redacted]"
    assert clean["nested"]["secret"] == "[redacted]"
    assert clean["nested"]["mark"] == "B1"


def test_vault_path_stays_inside_company_tree():
    path = vault_dir("plant", "job-1", "pour-1", "beam-1", "drawings")
    assert "company" in str(path)
    assert path.name == "drawings"
    try:
        vault_dir("plant", "job-1", "pour-1", "beam-1", "../etc")
        assert False, "should reject kind"
    except ValueError:
        pass
