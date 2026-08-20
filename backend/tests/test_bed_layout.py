"""Unit tests for bed packing and assignment conflict checks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from bed_layout import (
    HEADER_SETBACK_FT, covers, find_conflicts, map_production_status, pack_stations, remaining_ft,
)


def test_pack_stations_fits_typical_four():
    stations = pack_stations(300, [60, 60, 60, 60])
    assert len(stations) == 4
    assert stations[0] == HEADER_SETBACK_FT
    assert stations[1] == pytest.approx(8 + 60 + 2.5)
    leftover = remaining_ft(300, [60, 60, 60, 60])
    assert leftover > 0


def test_pack_stations_overflow_raises():
    with pytest.raises(ValueError, match="usable"):
        pack_stations(300, [140, 140, 140])


def test_pack_stations_allows_more_than_four_if_they_fit():
    stations = pack_stations(400, [40, 40, 40, 40, 40])
    assert len(stations) == 5


def test_find_conflicts_same_beam_overlapping_dates():
    existing = [{
        "id": "a1",
        "bed_id": "bed-1",
        "beam_id": "beam-9",
        "scheduled_date": "2026-08-17",
        "scheduled_end_date": "2026-08-18",
    }]
    bed_hits, beam_hits = find_conflicts(
        existing, bed_id="bed-2", beam_id="beam-9", start="2026-08-18", end="2026-08-19",
    )
    assert beam_hits == ["a1"]
    assert bed_hits == []


def test_find_conflicts_ignore_self_and_non_overlap():
    existing = [{
        "id": "a1",
        "bed_id": "bed-1",
        "beam_id": "beam-9",
        "scheduled_date": "2026-08-17",
        "scheduled_end_date": "2026-08-17",
    }]
    bed_hits, beam_hits = find_conflicts(
        existing, bed_id="bed-1", beam_id="beam-9", start="2026-08-17", end="2026-08-17", ignore_id="a1",
    )
    assert bed_hits == []
    assert beam_hits == []
    _, later = find_conflicts(
        existing, bed_id="bed-1", beam_id="beam-9", start="2026-08-19", end="2026-08-19",
    )
    assert later == []


def test_covers_and_status_map():
    rec = {"scheduled_date": "2026-08-17", "scheduled_end_date": "2026-08-19"}
    assert covers(rec, "2026-08-18") is True
    assert covers(rec, "2026-08-20") is False
    assert map_production_status("tensioning", "in_progress") == "stressed"
    assert map_production_status("complete", "shipped") == "released"
