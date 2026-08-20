"""Cylinder tag generator — 6 beams per label, continuation pages, unused slots suppressed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cylinder_tags import (
    BEAMS_PER_LABEL,
    STATUS_INCOMPLETE,
    STATUS_READY,
    STATUS_UNUSED,
    build_pdf_bytes,
    build_run_payload,
    clean_beams,
    labels_per_cylinder,
    physical_labels,
    print_rows_for_slot,
    slot_status,
    summarize_slot,
)


def _slot(**kwargs):
    base = {
        "slot": 1,
        "use_today": True,
        "qc_tech": "Alex QC",
        "job_number": "L25390",
        "expected_beam_count": 0,
        "pour_number": "P-118",
        "pour_date": "2026-08-17",
        "cylinder_tags_needed": 2,
        "beam_marks": [],
    }
    base.update(kwargs)
    return base


def test_six_beams_one_label_per_cylinder():
    assert labels_per_cylinder(6) == 1
    assert physical_labels(6, 2) == 2
    assert BEAMS_PER_LABEL == 6


def test_thirteen_beams_three_labels_per_cylinder():
    assert labels_per_cylinder(13) == 3
    assert physical_labels(13, 2) == 6


def test_empty_and_zero_never_generate_labels():
    assert labels_per_cylinder(0) == 0
    assert physical_labels(0, 4) == 0
    assert physical_labels(8, 0) == 0
    assert clean_beams(["", "  ", None, "B-01", ""]) == ["B-01"]


def test_unused_slot_never_prints():
    slot = _slot(use_today=False, beam_marks=["B1", "B2"])
    assert slot_status(slot) == STATUS_UNUSED
    assert print_rows_for_slot(slot) == []
    summary = summarize_slot(slot)
    assert summary["physical_labels"] == 0
    assert summary["status"] == STATUS_UNUSED


def test_incomplete_without_heat_equivalent_fields():
    slot = _slot(job_number="", beam_marks=["B1"])
    assert slot_status(slot) == STATUS_INCOMPLETE
    assert print_rows_for_slot(slot) == []


def test_continuation_pages_for_seven_beams():
    marks = [f"B-{i:02d}" for i in range(1, 8)]
    slot = _slot(cylinder_tags_needed=1, beam_marks=marks)
    rows = print_rows_for_slot(slot)
    assert len(rows) == 2
    assert rows[0]["part_caption"] == "PAGE 1 OF 2"
    assert rows[1]["part_caption"] == "PAGE 2 OF 2"
    assert rows[0]["beam_1"] == "B-01"
    assert rows[0]["beam_6"] == "B-06"
    assert rows[1]["beam_1"] == "B-07"
    assert rows[1]["beam_2"] == ""
    assert rows[1]["beam_6"] == ""


def test_two_cylinders_duplicate_parts():
    marks = [f"G{i}" for i in range(1, 14)]
    slot = _slot(cylinder_tags_needed=2, beam_marks=marks)
    rows = print_rows_for_slot(slot)
    assert len(rows) == 6
    assert [r["cylinder_copy"] for r in rows] == [1, 1, 1, 2, 2, 2]
    assert rows[2]["part_caption"] == "PAGE 3 OF 3"
    assert rows[2]["beam_1"] == "G13"


def test_build_run_skips_unused_and_numbers_labels():
    payload = {
        "run_date": "2026-08-17",
        "job_count": 3,
        "slots": [
            _slot(slot=1, beam_marks=["A1", "A2", "A3"], cylinder_tags_needed=1),
            _slot(slot=2, use_today=False, job_number="X", beam_marks=["Z"]),
            _slot(slot=3, job_number="J-2", beam_marks=[f"B{i}" for i in range(1, 8)], cylinder_tags_needed=1),
        ],
    }
    built = build_run_payload(payload)
    assert built["ready_jobs"] == 2
    assert built["total_physical_labels"] == 3
    assert built["print_rows"][0]["label_number"] == 1
    assert built["print_rows"][-1]["label_number"] == 3
    assert built["print_rows"][-1]["job_number"] == "J-2"
    assert built["summaries"][1]["status"] == STATUS_UNUSED
    assert built["print_ready"] is True


def test_job_count_caps_extra_slots():
    payload = {
        "job_count": 1,
        "slots": [
            _slot(slot=1, beam_marks=["A1"], cylinder_tags_needed=1),
            _slot(slot=2, beam_marks=["B1"], cylinder_tags_needed=1),
        ],
    }
    built = build_run_payload(payload)
    assert built["slots"][1]["use_today"] is False
    assert built["ready_jobs"] == 1


def test_pdf_builds_for_ready_rows():
    slot = _slot(beam_marks=["L25390-1", "L25390-2"], cylinder_tags_needed=1)
    rows = print_rows_for_slot(slot)
    pdf = build_pdf_bytes(rows, {"company_name": "PRESTRESS SERVICES INDUSTRIES LLC"})
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 200
