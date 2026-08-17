"""BedForge QC backend API tests."""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://beam-forge-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("tccrossmusic@gmail.com", "BedForge2026!")
DEMO_USERS = [
    ("supervisor@bedforge.com", "Super1234!"),
    ("tech@bedforge.com", "Tech1234!"),
    ("production@bedforge.com", "Prod1234!"),
]


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data and data["user"]["role"] == "admin"
    return data["access_token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- Auth ----------
class TestAuth:
    def test_login_admin_ok(self, admin_token):
        assert admin_token and isinstance(admin_token, str)

    @pytest.mark.parametrize("email,pw", DEMO_USERS)
    def test_login_demo_users(self, email, pw):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
        assert r.status_code == 200, f"{email}: {r.text}"
        assert r.json()["user"]["email"] == email

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": "bogus@x.com", "password": "wrong"}, timeout=30)
        assert r.status_code == 401

    def test_me_ok(self, auth_headers):
        r = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_dashboard_unauth_401(self):
        r = requests.get(f"{API}/dashboard", timeout=30)
        assert r.status_code == 401

    def test_beams_unauth_401(self):
        r = requests.get(f"{API}/beams", timeout=30)
        assert r.status_code == 401


# ---------- Dashboard ----------
class TestDashboard:
    def test_dashboard_shape(self, auth_headers):
        r = requests.get(f"{API}/dashboard", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "beds" in data and "stats" in data
        assert len(data["beds"]) == 8, f"expected 8 beds, got {len(data['beds'])}"
        stats = data["stats"]
        for k in ["total_beds", "active_beds", "total_beams", "passed", "in_progress", "hold", "failed"]:
            assert k in stats
        assert stats["total_beams"] >= 11
        # Ensure bed cards have expected keys
        for bed in data["beds"]:
            for k in ["id", "bed_number", "name", "status", "length_ft", "beam_count", "beams"]:
                assert k in bed, f"bed missing {k}"

    def test_beams_list(self, auth_headers):
        r = requests.get(f"{API}/beams", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        beams = r.json()
        assert isinstance(beams, list) and len(beams) >= 11
        assert all("_id" not in b for b in beams)

    def test_command_board_shape(self, auth_headers):
        r = requests.get(f"{API}/command-board", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["plant"] == "BedForge Command Center"
        assert "summary" in data and "analytics" in data and "events" in data
        assert len(data["lanes"]) == 8
        for key in ["beds_active", "beams_in_process", "releases_today", "open_ncrs"]:
            assert key in data["summary"]
        for lane in data["lanes"]:
            for key in ["bed_number", "status", "lane_state", "beam_order", "qc_owner", "estimated_release", "beams"]:
                assert key in lane, f"lane missing {key}"
            assert "key" in lane["lane_state"] and "label" in lane["lane_state"]
        for key in ["releases_today", "layout_to_release_hours", "open_ncrs_by_severity", "camber_pass_rate", "tension_within_tolerance_rate", "strength_trend"]:
            assert key in data["analytics"]


# ---------- Tension ----------
class TestTension:
    def test_calculate_defaults(self, auth_headers):
        payload = {
            "jacking_force_kip": 43.94,
            "bed_length_ft": 400,
            "strand_area_in2": 0.217,
            "modulus_ksi": 28500,
        }
        r = requests.post(f"{API}/tension/calculate", json=payload, headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        # (43.94 * 4800) / (0.217 * 28500) = 34.117..
        assert abs(data["theoretical_elongation_in"] - 34.117) < 0.05
        assert data["tolerance_pct"] == 5.0
        assert data["lower_bound_in"] < data["theoretical_elongation_in"] < data["upper_bound_in"]

    def test_calculate_within_tolerance(self, auth_headers):
        payload = {
            "jacking_force_kip": 43.94, "bed_length_ft": 400,
            "strand_area_in2": 0.217, "modulus_ksi": 28500,
            "measured_elongation_in": 34.5,
        }
        r = requests.post(f"{API}/tension/calculate", json=payload, headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["within_tolerance"] is True
        assert abs(data["variance_pct"]) < 5.0

    def test_calculate_out_of_tolerance(self, auth_headers):
        payload = {
            "jacking_force_kip": 43.94, "bed_length_ft": 400,
            "strand_area_in2": 0.217, "modulus_ksi": 28500,
            "measured_elongation_in": 40.0,
        }
        r = requests.post(f"{API}/tension/calculate", json=payload, headers=auth_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["within_tolerance"] is False


# ---------- Anomalies + Inspections ----------
class TestBeamOps:
    @pytest.fixture(scope="class")
    def some_beam_id(self):
        # Fetch a beam via list
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=30)
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        beams = requests.get(f"{API}/beams", headers=h, timeout=30).json()
        assert beams, "no beams seeded"
        return beams[0]["id"], h

    def test_create_anomaly_and_list(self, some_beam_id):
        beam_id, h = some_beam_id
        payload = {
            "beam_id": beam_id, "type": "spall", "severity": "minor",
            "length_in": 3.5, "note": "TEST_anomaly",
            "position": {"x": 0.5, "y": 0.5, "z": 0.5},
        }
        r = requests.post(f"{API}/anomalies", json=payload, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["type"] == "spall" and "id" in created

        r2 = requests.get(f"{API}/anomalies?beam_id={beam_id}", headers=h, timeout=30)
        assert r2.status_code == 200
        assert any(a["id"] == created["id"] for a in r2.json())

    def test_create_inspection_pass(self, some_beam_id):
        beam_id, h = some_beam_id
        payload = {
            "beam_id": beam_id, "section": "pre_pour",
            "status": "pass", "notes": "TEST_inspection", "data": {"formwork": True},
        }
        r = requests.post(f"{API}/inspections", json=payload, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "pass"


# ---------- Forms Export ----------
class TestFormsExport:
    @pytest.mark.parametrize("form_type", ["qir", "tension", "camber", "crackmap"])
    def test_export_xlsx(self, auth_headers, form_type):
        r = requests.get(f"{API}/forms/export/{form_type}", headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "spreadsheetml" in ct or "officedocument" in ct
        # xlsx = zip; magic bytes PK
        assert r.content[:2] == b"PK", f"{form_type}: not a valid xlsx"
        assert len(r.content) > 500

    def test_export_unknown_400(self, auth_headers):
        r = requests.get(f"{API}/forms/export/bogus", headers=auth_headers, timeout=30)
        assert r.status_code == 400
