"""Plant-manager override targets resolve from bed numbers and beam marks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from override_target import OverrideTargetError, classify_override_target


def test_strand_tension_accepts_bed_number():
    lookup = classify_override_target("strand_tension", "3")
    assert lookup["collection"] == "beds"
    assert lookup["query"] == {"bed_number": 3}


def test_strand_tension_accepts_uuid():
    lookup = classify_override_target("strand_tension", "bed-uuid-here")
    assert lookup["query"] == {"id": "bed-uuid-here"}


def test_qc_force_falls_back_to_beam_mark():
    lookup = classify_override_target("qc_force", "L25390-B1")
    assert lookup["collection"] == "beams"
    assert lookup["query"] == {"id": "L25390-B1"}
    assert lookup["alt_query"] == {"mark": "L25390-B1"}


def test_release_strength_targets_beam_mark():
    lookup = classify_override_target("release_strength", "L25390-B1")
    assert lookup["collection"] == "beams"
    assert lookup["alt_query"]["mark"] == "L25390-B1"


def test_empty_target_rejected():
    try:
        classify_override_target("strand_tension", "  ")
        assert False, "expected OverrideTargetError"
    except OverrideTargetError as err:
        assert "required" in err.message.lower()


def test_unknown_kind_rejected():
    try:
        classify_override_target("delete_audit", "1")
        assert False, "expected OverrideTargetError"
    except OverrideTargetError:
        pass
