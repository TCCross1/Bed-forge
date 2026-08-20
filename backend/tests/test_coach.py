"""Ask Expert contract load, audit-style fix guidance, insert vs mesh."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bedforge_contract import CONTRACT_TEXT, contract_prompt_block
from beam_spec import materialize_job_beam_specs, twin_beam_from_spec
from blueprint_pipeline import extract_structured_fields, normalize_locked_blueprint
from coach import OVERRIDE_ANSWER, answer_coach, compose_local, is_override_ask
from coach_audit import (
    audit_twin_vs_spec,
    compose_audit_answer,
    format_audit_report,
    is_audit_ask,
    parse_job_mark,
)
from tests.test_blueprint_extraction import L25390_FIXTURE


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


def test_contract_is_the_product_matrix():
    text = contract_prompt_block()
    assert "BEDFORGE PRODUCT CONTRACT" in text
    assert "Blueprint Intelligence" in CONTRACT_TEXT
    assert "Spec DNA" in text
    assert "JOB SPECS" in text
    assert "silent omit" in text.lower()
    assert "/job-specs" in text
    assert "Batch Plant" in text
    assert "Command Board" in text


def test_what_needs_to_be_fixed_is_sectioned_fail_warn_pass():
    assert is_audit_ask("What needs to be fixed?")
    rec = answer_coach(
        "What needs to be fixed?",
        live={
            "live_ok": True,
            "errors": [],
            "findings": [
                {
                    "section": "C",
                    "title": "JOB SPECS / DRAWINGS (Digital Twin)",
                    "status": "Fail",
                    "evidence": "Spec MK 205 declares 1 insert; twin hardware empty.",
                    "fix": "Render UNCONFIRMED placeholder.",
                },
                {
                    "section": "G",
                    "title": "Batch Plant",
                    "status": "Warn",
                    "evidence": "Live weather missing on tickets.",
                    "fix": "Wire current conditions into /batch.",
                },
                {
                    "section": "D",
                    "title": "Open Job / Job Cabinet",
                    "status": "Pass",
                    "evidence": "Open job is L25390 via GET /api/jobs/open.",
                    "fix": "",
                },
            ],
        },
    )
    assert rec["source"] == "audit"
    answer = rec["answer"]
    assert "Summary" in answer
    assert "Failures" in answer
    assert "Warnings" in answer
    assert "Suggested order of work" in answer
    assert "Fail" in answer
    assert "Warn" in answer
    assert "Pass" in answer
    assert "MK 205" in answer
    assert "do not invent" in answer.lower() or "will not invent" in answer.lower()


def test_audit_without_live_snapshot_is_cannot_verify_not_pass():
    text = compose_audit_answer("What needs to be fixed?", None)
    assert "cannot verify" in text.lower()
    assert "Summary" in text
    assert "do not guess pass" in text.lower() or "cannot verify" in text.lower()
    # Offline snapshot must not stamp every section Pass.
    pass_only = [line for line in text.splitlines() if line.endswith("— Pass")]
    assert pass_only == [] or any("cannot verify" in line.lower() for line in text.splitlines())


def test_parse_l25390_mk205():
    job, mark = parse_job_mark("Audit L25390 MK 205 twin vs Spec DNA.")
    assert job == "L25390"
    assert mark == "205"


def test_l25390_mk205_insert_unconfirmed_is_warn_not_silent_omit():
    result = extract_structured_fields(L25390_FIXTURE, page_sources=["text_layer"] * len(L25390_FIXTURE))
    normalized = normalize_locked_blueprint(result.fields)
    specs = materialize_job_beam_specs(
        result.fields,
        document={"id": "doc-l25390", "project_name_hint": "L25390"},
        revision={"id": "rev-1", "normalized_blueprint": normalized, "product_family": "i_beam"},
    )
    spec = next(item for item in specs if item["beam_mark"] == "205")
    twin = twin_beam_from_spec(spec)
    findings = audit_twin_vs_spec(spec, twin, job_number="L25390", mark="205")
    insert_rows = [row for row in findings if "insert" in row["evidence"].lower()]
    assert insert_rows
    assert insert_rows[0]["status"] == "Warn"
    assert "UNCONFIRMED" in insert_rows[0]["evidence"]
    assert insert_rows[0]["status"] != "Fail"


def test_insert_count_vs_empty_mesh_is_fail():
    spec = {
        "id": "spec-205",
        "beam_mark": "205",
        "job_number": "L25390",
        "identity": {"job_number": "L25390", "beam_mark": "205"},
        "geometry": {"length_ft": 52},
        "blueprint": {"inserts": [{"type": "F-64", "quantity": 1}]},
        "hardware": [],
    }
    twin = {
        "id": "spec:spec-205",
        "mark": "205",
        "beam_spec": spec,
        "embedded_hardware": {"insert": []},
    }
    findings = audit_twin_vs_spec(spec, twin, job_number="L25390", mark="205")
    fails = [row for row in findings if row["status"] == "Fail" and "insert" in row["evidence"].lower()]
    assert fails
    assert "silent omit" in fails[0]["evidence"].lower()


def test_format_report_never_guesses_pass_on_api_down():
    text = format_audit_report(
        [{
            "section": "C",
            "title": "JOB SPECS / DRAWINGS (Digital Twin)",
            "status": "cannot verify",
            "evidence": "GET /api/beam-specs/{id}/twin failed.",
            "fix": "Do not guess Pass.",
        }],
        question="Audit twin vs Spec",
        live_ok=False,
        errors=["GET /api/beam-specs/{id}/twin"],
    )
    assert "cannot verify" in text.lower()
    assert "— Pass" not in text
    assert "Suggested order of work" in text


def test_live_gather_scores_contract_without_guessing_missing_spec():
    import asyncio
    from coach_audit import gather_live_audit

    async def run():
        return await gather_live_audit(
            {"id": "admin-test", "role": "admin", "email": "admin@bedforge.com"},
            "What needs to be fixed?",
        )

    live = asyncio.run(run())
    assert live["findings"]
    statuses = {row["status"] for row in live["findings"]}
    assert "Pass" in statuses or "Warn" in statuses or "cannot verify" in statuses
    answer = compose_audit_answer("What needs to be fixed?", live)
    assert "Summary" in answer
    assert "Failures" in answer
    assert "Warnings" in answer
    assert "Pass" in answer
    twin = asyncio.run(gather_live_audit(
        {"id": "admin-test", "role": "admin", "email": "admin@bedforge.com"},
        "Audit L25390 MK 205 twin vs Spec DNA.",
    ))
    insert_rows = [row for row in twin["findings"] if "insert" in row["evidence"].lower()]
    assert insert_rows
    assert insert_rows[0]["status"] in ("Fail", "Warn", "cannot verify")
    assert "Pass" != insert_rows[0]["status"] or "mesh" in insert_rows[0]["evidence"].lower()
    text = format_audit_report(
        [{
            "section": "C",
            "title": "JOB SPECS / DRAWINGS (Digital Twin)",
            "status": "cannot verify",
            "evidence": "GET /api/beam-specs/{id}/twin failed.",
            "fix": "Do not guess Pass.",
        }],
        question="Audit twin vs Spec",
        live_ok=False,
        errors=["GET /api/beam-specs/{id}/twin"],
    )
    assert "cannot verify" in text.lower()
    assert "— Pass" not in text
    assert "Suggested order of work" in text
