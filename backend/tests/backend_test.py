"""BedForge QC backend API tests."""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("tccrossmusic@gmail.com", "BedForge2026!")
ADMIN_FALLBACK = ("admin@bedforge.com", "admin123")
DEMO_USERS = [
    ("admin@bedforge.com", "admin123"),
    ("supervisor@bedforge.com", "super123"),
    ("qc@bedforge.com", "qc123"),
    ("production@bedforge.com", "prod123"),
]


@pytest.fixture(scope="session")
def admin_token():
    for email, password in [ADMIN, ADMIN_FALLBACK]:
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            assert "access_token" in data and data["user"]["role"] == "admin"
            return data["access_token"]
    raise AssertionError(f"Unable to authenticate admin with known credentials: {r.text}")


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
        tok = None
        for email, password in [ADMIN, ADMIN_FALLBACK]:
            r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
            if r.status_code == 200:
                tok = r.json()["access_token"]
                break
        assert tok, "unable to get admin token for beam ops"
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


def _sample_blueprint_pdf():
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.drawString(72, 760, "JOB NO: J-88-2001")
    pdf.drawString(72, 744, "PROJECT: KDOT BRIDGE WIDENING")
    pdf.drawString(72, 728, "SHEET NO: S4")
    pdf.drawString(72, 712, "REV: B")
    pdf.drawString(72, 696, "BEAM MARK: B9-01")
    pdf.drawString(72, 680, "AASHTO TYPE IV I-BEAM")
    pdf.drawString(72, 664, "OVERALL LENGTH: 110' 0\"")
    pdf.drawString(72, 648, "OVERALL DEPTH: 54 IN")
    pdf.drawString(72, 632, "TOP FLANGE WIDTH: 20 IN")
    pdf.drawString(72, 616, "TOP FLANGE THICKNESS: 7.5 IN")
    pdf.drawString(72, 600, "BOTTOM FLANGE WIDTH: 32 IN")
    pdf.drawString(72, 584, "BOTTOM FLANGE THICKNESS: 8.5 IN")
    pdf.drawString(72, 568, "WEB THICKNESS: 7 IN")
    pdf.drawString(72, 552, "10 STRANDS")
    pdf.drawString(72, 536, "4 STRANDS @ 4 IN")
    pdf.drawString(72, 520, "6 STRANDS @ 4 IN")
    pdf.drawString(72, 504, "2 DRAPED STRANDS")
    pdf.drawString(72, 488, "HOLD-DOWN @ 24' 0\"")
    pdf.drawString(72, 472, "HOLD-DOWN @ 86' 0\"")
    pdf.drawString(72, 456, "LIFT LOOP @ 16' 0\"")
    pdf.drawString(72, 440, "LIFT LOOP @ 94' 0\"")
    pdf.drawString(72, 424, "JACKING FORCE: 43.94 KIP")
    pdf.drawString(72, 408, "ELONGATION: 34.12 IN")
    pdf.drawString(72, 392, "MARKED END: HEAD / START")
    pdf.showPage()
    pdf.drawString(72, 760, "SPECIAL INSPECTION NOTES: VERIFY END GEOMETRY BEFORE CAST")
    pdf.drawString(72, 744, "BITUMINOUS END TREATMENT REQUIRED")
    pdf.save()
    buf.seek(0)
    return buf


class TestBlueprintPipeline:
    def test_upload_extract_edit_and_lock(self, auth_headers):
        beams = requests.get(f"{API}/beams", headers=auth_headers, timeout=30).json()
        assert beams, "expected seeded beams"
        beam_id = beams[0]["id"]
        files = {"file": ("sample-blueprint.pdf", _sample_blueprint_pdf().getvalue(), "application/pdf")}
        data = {
            "beam_id": beam_id,
            "beam_mark_hint": "B9-01",
            "product_family_hint": "i_beam",
        }
        upload = requests.post(f"{API}/blueprints/upload", headers=auth_headers, files=files, data=data, timeout=60)
        assert upload.status_code == 200, upload.text
        document = upload.json()
        assert document["page_count"] == 2

        extract = requests.post(f"{API}/blueprints/{document['id']}/extract", headers=auth_headers, timeout=60)
        assert extract.status_code == 200, extract.text
        extracted = extract.json()
        fields = extracted["latest_extraction"]["fields"]
        assert fields["beam_mark"]["value"] == "B9-01"
        assert fields["product_family"]["value"] == "i_beam"
        assert abs(fields["overall_length_ft"]["value"] - 110.0) < 0.01

        patch = {
            "fields": {
                "design_camber_in": {
                    "value": "4.5",
                    "status": "manually_confirmed",
                    "confidence": "high",
                    "source_page": 1,
                    "extraction_notes": "Reviewed against title block notes",
                }
            }
        }
        review = requests.patch(f"{API}/blueprints/{document['id']}/extraction", headers=auth_headers, json=patch, timeout=60)
        assert review.status_code == 200, review.text

        lock = requests.post(f"{API}/blueprints/{document['id']}/lock", headers=auth_headers, json={"beam_ids": [beam_id]}, timeout=60)
        assert lock.status_code == 200, lock.text
        locked = lock.json()
        assert locked["status"] == "locked"
        assert locked["locked_revision"]["product_family"] == "i_beam"

        beam = requests.get(f"{API}/beams/{beam_id}", headers=auth_headers, timeout=30)
        assert beam.status_code == 200, beam.text
        beam_data = beam.json()
        assert beam_data["blueprint_source"]["status"] == "locked"
        assert beam_data["product_type"]["blueprint"]["cross_section"]["overall_depth_in"] == 54.0
        assert len(beam_data["product_type"]["blueprint"]["hold_downs"]) == 2
        specs = requests.get(f"{API}/beam-specs", headers=auth_headers, params={"document_id": document["id"]}, timeout=30)
        assert specs.status_code == 200, specs.text
        spec_rows = specs.json()
        assert spec_rows, "lock should materialize at least one beam spec"
        assert spec_rows[0]["beam_mark"] == "B9-01"
        assert spec_rows[0]["geometry"]["depth_in"] == 54.0
        twin = requests.get(f"{API}/beam-specs/{spec_rows[0]['id']}/twin", headers=auth_headers, timeout=30)
        assert twin.status_code == 200, twin.text
        assert twin.json()["mark"] == "B9-01"


class TestOpenJob:
    def _token(self, email, password):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    def test_l25390_is_open_job_for_admin(self, auth_headers):
        jobs = requests.get(f"{API}/jobs", headers=auth_headers, timeout=30)
        assert jobs.status_code == 200, jobs.text
        numbers = [item.get("job_number") for item in jobs.json()]
        assert "L25390" in numbers
        opened = requests.get(f"{API}/jobs/open", headers=auth_headers, timeout=30)
        assert opened.status_code == 200, opened.text
        data = opened.json()
        assert data["job"]["job_number"] == "L25390"
        assert data["privileges"]["can_edit_job"] is True

    def test_qc_tech_cannot_create_or_patch_job(self):
        token = self._token("qc@bedforge.com", "qc123")
        headers = {"Authorization": f"Bearer {token}"}
        opened = requests.get(f"{API}/jobs/open", headers=headers, timeout=30)
        assert opened.status_code == 200, opened.text
        assert opened.json()["privileges"]["can_edit_job"] is False
        created = requests.post(
            f"{API}/jobs",
            headers=headers,
            json={"job_number": "X-FORBIDDEN", "name": "Nope", "customer": "Nope"},
            timeout=30,
        )
        assert created.status_code == 403
        job_id = opened.json()["job"]["id"]
        patched = requests.patch(f"{API}/jobs/{job_id}", headers=headers, json={"notes": "tech edit"}, timeout=30)
        assert patched.status_code == 403
        blueprints = requests.get(f"{API}/blueprints", headers=headers, timeout=30)
        assert blueprints.status_code == 403

    def test_supervisor_needs_override_to_patch_job(self):
        token = self._token("supervisor@bedforge.com", "super123")
        headers = {"Authorization": f"Bearer {token}"}
        opened = requests.get(f"{API}/jobs/open", headers=headers, timeout=30)
        assert opened.status_code == 200, opened.text
        job_id = opened.json()["job"]["id"]
        blocked = requests.patch(f"{API}/jobs/{job_id}", headers=headers, json={"notes": "no override"}, timeout=30)
        assert blocked.status_code == 403
        override = requests.post(
            f"{API}/job-overrides",
            headers=headers,
            json={
                "note": "Shop drawing revision confirmed on bed with Plant Manager.",
                "manager_email": "admin@bedforge.com",
                "manager_password": "admin123",
            },
            timeout=30,
        )
        assert override.status_code == 200, override.text
        assert override.json()["privileges"]["can_edit_job"] is True
        patched = requests.patch(f"{API}/jobs/{job_id}", headers=headers, json={"notes": "override edit"}, timeout=30)
        assert patched.status_code == 200, patched.text
        requests.delete(f"{API}/job-overrides", headers=headers, timeout=30)


class TestInstrumentReadings:
    def test_evaluate_and_create_and_override(self, auth_headers):
        preview = requests.post(
            f"{API}/instrument-readings/evaluate",
            headers=auth_headers,
            json={"measured_in": 120.5, "target_in": 120.0, "tolerance_in": 0.125},
            timeout=30,
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["status"] == "fail"
        created = requests.post(
            f"{API}/instrument-readings",
            headers=auth_headers,
            json={"purpose": "length", "source": "manual", "measured_in": 120.5, "target_in": 120.0, "tolerance_in": 0.125},
            timeout=30,
        )
        assert created.status_code == 200, created.text
        row = created.json()
        assert row["status"] == "fail"
        listed = requests.get(f"{API}/instrument-readings", headers=auth_headers, timeout=30)
        assert listed.status_code == 200, listed.text
        assert any(item["id"] == row["id"] for item in listed.json())
        overridden = requests.post(
            f"{API}/instrument-readings/{row['id']}/override",
            headers=auth_headers,
            json={"note": "Plant manager accepted laser shot after re-check on bed."},
            timeout=30,
        )
        assert overridden.status_code == 200, overridden.text
        assert overridden.json()["status"] == "override"
