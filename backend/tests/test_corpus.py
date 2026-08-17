"""Training corpus match + gold BeamSpec export tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from corpus import all_gold_specs, detect_section, export_gold, match_corpus
from extract import extract_beam_spec


REQUIRED_KINDS_I = {
    "lift_loop", "insert", "drain", "tie_rod", "hold_down",
    "bearing_plate", "bituminous_zone", "diaphragm",
}
REQUIRED_KINDS_BOX = {
    "lift_loop", "grout_groove", "tie_rod", "drain", "bearing_plate",
}


def test_gold_catalog_covers_priority_agencies():
    specs = all_gold_specs()
    agencies = {s.source_agency for s in specs}
    assert {"NYSDOT", "SCDOT", "NCDOT", "ODOT", "TDOT", "TxDOT", "VDOT", "KYTC"} <= agencies
    assert len(specs) >= 30
    i_beams = [s for s in specs if s.geometry.twin_type == "i_beam"]
    boxes = [s for s in specs if s.geometry.twin_type == "box_beam"]
    assert len(i_beams) >= 15
    assert len(boxes) >= 12


def test_gold_i_beam_has_critical_hardware():
    spec = next(s for s in all_gold_specs() if s.catalog_id == "ncdot-pcg-type-ii")
    kinds = {h.kind for h in spec.hardware}
    assert REQUIRED_KINDS_I <= kinds
    assert spec.geometry.depth_in == 36.0
    assert spec.geometry.bot_flange_width_in == 18.0
    assert spec.bill_of_materials
    assert spec.marked_end_id.endswith("ME")


def test_gold_box_has_grout_and_tendons():
    spec = next(s for s in all_gold_specs() if s.catalog_id == "ncdot-pcbb-33")
    kinds = {h.kind for h in spec.hardware}
    assert REQUIRED_KINDS_BOX <= kinds
    assert spec.geometry.width_in == 36.0
    assert spec.geometry.depth_in == 33.0


def test_match_ncdot_pcg1_filename():
    hit = match_corpus("pcg1_24.pdf", "AASHTO Type II Prestressed Concrete Girder")
    assert hit is not None
    assert hit.catalog_id == "ncdot-pcg-type-ii"


def test_match_scdot_abb():
    hit = match_corpus("704-ABB.S080.pdf", "Adjacent Prestressed Concrete Box Beams BII-36 80' span")
    assert hit is not None
    assert "abb" in hit.catalog_id and hit.geometry.twin_type == "box_beam"


def test_match_odot_br325():
    hit = match_corpus("BR325.pdf", "TYPE II PRESTRESSED CONCRETE GIRDERS OREGON STANDARD")
    assert hit is not None
    assert hit.catalog_id == "odot-br325-type-ii"


def test_section_detect_type_iv_and_box():
    assert detect_section("girder.pdf", "AASHTO Type IV") == "type_iv"
    assert detect_section("pcbb4_24.pdf", "Prestressed Concrete Box Beam Unit") == "box"


def test_extract_uses_corpus_for_ncdot_pdf(tmp_path):
    dummy = tmp_path / "pcg3_24.pdf"
    dummy.write_bytes(b"%PDF-1.4 NCDOT AASHTO TYPE IV PCG3")
    spec, name = extract_beam_spec([dummy], beam_mark="G1")
    assert name == "gold_corpus"
    assert spec.catalog_id == "ncdot-pcg-type-iv"
    assert spec.geometry.depth_in == 54.0


def test_export_gold_roundtrip(tmp_path):
    out = export_gold(tmp_path)
    files = list(Path(out).glob("*.json"))
    assert len(files) >= 30
    assert (Path(out) / "_index.json").exists()
