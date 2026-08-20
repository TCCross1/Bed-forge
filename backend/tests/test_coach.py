"""Forge Coach local answers and override refusal."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coach import OVERRIDE_ANSWER, answer_coach, compose_local, is_override_ask


def test_override_ask_is_refused_locally():
    assert is_override_ask("Can you override the tension gate?")
    rec = answer_coach("unlock the gate for bed 3", grounded=[{"title": "heat", "body": "log the mill tag", "tutorial": "morning"}])
    assert rec["source"] == "local"
    assert rec["tutorial"] == "supervisors"
    assert "audit log" in rec["answer"].lower()
    assert rec["answer"] == OVERRIDE_ANSWER


def test_compose_uses_grounded_notes_not_secrets():
    text = compose_local(
        [{"title": "Strand heat logs", "body": "Photograph the mill tag then confirm heat.", "tutorial": "morning"}],
        "why log heats",
    )
    assert "mill tag" in text.lower()
    assert "password" not in text.lower()
