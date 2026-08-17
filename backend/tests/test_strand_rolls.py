"""Strand roll OCR, pour matching, and tensioning gate."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strand_gate import GATE_MESSAGE, gate_ok, pour_matches, roll_is_ready
from strand_ocr import extract_from_text, merge_extraction, _normalize_astm


TAG = """
SUMIDEN WIRE PRODUCTS
HEAT: H270-88412
REEL: R-44190
LOT: 26-0412
ASTM A416
GRADE 270
0.50 IN LOW RELAXATION
PACK WT 3500 LB
PACK LENGTH 12000 FT
"""


def test_extract_heat_reel_and_spec_from_tag_text():
    result = extract_from_text(TAG)
    fields = result["fields"]
    assert fields["heat_number"] == "H270-88412"
    assert fields["reel_number"] == "R-44190"
    assert fields["lot_number"] == "26-0412"
    assert fields["astm_standard"] == "ASTM A416"
    assert fields["strand_grade"] == "270"
    assert fields["strand_type"] == "Low-Relaxation"
    assert fields["nominal_diameter"] == "0.50in"
    assert fields["area_in2"] == 0.153
    assert "3500" in fields["pack_weight"]
    assert result["confidence"]["heat_number"] >= 0.9
    assert result["extractor_confidence"] >= 0.9


def test_products_is_not_a_lot_number():
    result = extract_from_text("SUMIDEN WIRE PRODUCTS GRADE 270 ASTM A416")
    assert result["fields"]["lot_number"] == ""
    assert result["fields"]["strand_grade"] == "270"

    result = extract_from_text("ASTM A416 GRADE 270 0.60 in")
    assert result["fields"]["heat_number"] == ""
    assert result["confidence"]["heat_number"] == 0.0
    assert result["fields"]["nominal_diameter"] == "0.60in"
    assert result["fields"]["area_in2"] == 0.217


def test_normalize_astm():
    assert _normalize_astm("A 416 M") == "ASTM A416M"
    assert _normalize_astm("astm a416") == "ASTM A416"


def test_merge_prefers_higher_confidence_heat():
    vision = {
        "fields": {"heat_number": "H1", "reel_number": ""},
        "confidence": {"heat_number": 0.95, "reel_number": 0.0},
        "extractor": "openai_vision",
    }
    regex = extract_from_text("HEAT: H2 REEL: R9 ASTM A416")
    merged = merge_extraction(vision, regex)
    assert merged["fields"]["heat_number"] == "H1"
    assert merged["fields"]["reel_number"] == "R9"


def test_gate_blocks_without_confirmed_heat():
    assignments = [{"roll_id": "r1", "bed_id": "b1", "pour_id": "p1"}]
    rolls = {"r1": {"heat_number": "H270", "status": "draft"}}
    assert gate_ok(assignments, rolls, "p1") is False
    rolls["r1"]["status"] = "confirmed"
    assert gate_ok(assignments, rolls, "p1") is True


def test_gate_requires_heat_and_pour_match():
    assignments = [{"roll_id": "r1", "bed_id": "b1", "pour_id": "p1"}]
    rolls = {"r1": {"heat_number": "H270-1", "status": "assigned"}}
    assert gate_ok(assignments, rolls, "p2") is False
    assert gate_ok(assignments, rolls, "p1") is True
    assert pour_matches({"pour_id": ""}, "p1") is True
    assert roll_is_ready({"heat_number": "", "status": "confirmed"}) is False
    assert GATE_MESSAGE.startswith("Strand roll not logged")
