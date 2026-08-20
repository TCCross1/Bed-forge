"""Open Job cabinet and Spec-edit authorization."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from db import MemoryCollection
from job_cabinet import (
    _job_number_from_blueprint,
    persist_open_job_session,
    resolve_job_for_open,
    role_can_edit_unsupervised,
    role_can_open_blueprint_studio,
    role_can_request_override,
)
from models import Job, now_iso


def test_role_gates_are_minimal():
    assert role_can_edit_unsupervised("admin") is True
    assert role_can_edit_unsupervised("executive") is True
    assert role_can_edit_unsupervised("qc_supervisor") is False
    assert role_can_edit_unsupervised("qc_tech") is False
    assert role_can_request_override("qc_supervisor") is True
    assert role_can_request_override("qc_tech") is False
    assert role_can_request_override("admin") is False
    assert role_can_open_blueprint_studio("qc_tech") is False
    assert role_can_open_blueprint_studio("production") is False
    assert role_can_open_blueprint_studio("qc_supervisor") is True
    assert role_can_open_blueprint_studio("admin") is True


def test_memory_update_one_upsert_creates_and_updates_session():
    col = MemoryCollection()

    async def run():
        first = await col.update_one(
            {"user_id": "u1"},
            {"$set": {"user_id": "u1", "job_id": "j1", "updated_at": now_iso()}},
            upsert=True,
        )
        assert first.matched_count == 0
        row = await col.find_one({"user_id": "u1"})
        assert row["job_id"] == "j1"
        second = await col.update_one(
            {"user_id": "u1"},
            {"$set": {"job_id": "j2"}},
            upsert=True,
        )
        assert second.matched_count == 1
        row = await col.find_one({"user_id": "u1"})
        assert row["job_id"] == "j2"
        assert len(col.documents) == 1

    asyncio.run(run())


def test_job_number_from_blueprint_hint():
    assert _job_number_from_blueprint({"project_name_hint": "KYTC L25390 girders"}, "") == "L25390"
    assert _job_number_from_blueprint({"filename": "J-OPEN-77.pdf"}, "") == "J-OPEN-77"


def test_resolve_job_for_open_by_id_number_and_missing():
    from db import db

    async def run():
        job = Job(job_number="OPENTEST-991", name="Unit cabinet", customer="Test").model_dump()
        await db.jobs.insert_one(dict(job))
        by_number = await resolve_job_for_open("OPENTEST-991")
        assert by_number["id"] == job["id"]
        by_id = await resolve_job_for_open(job["id"])
        assert by_id["job_number"] == "OPENTEST-991"
        try:
            await resolve_job_for_open("does-not-exist-xyz")
            assert False, "expected 404"
        except HTTPException as exc:
            assert exc.status_code == 404
            assert exc.detail == "no job found"

    asyncio.run(run())


def test_resolve_job_from_blueprint_when_job_row_missing():
    from db import db

    async def run():
        doc = {
            "id": "bp-opentest-77",
            "filename": "J-OPEN-77.pdf",
            "project_name_hint": "J-OPEN-77 shop drawings",
            "job_id": None,
        }
        await db.blueprint_documents.insert_one(dict(doc))
        job = await resolve_job_for_open("J-OPEN-77")
        assert job["job_number"] == "J-OPEN-77"
        linked = await db.blueprint_documents.find_one({"id": "bp-opentest-77"}, {"_id": 0})
        assert linked["job_id"] == job["id"]

    asyncio.run(run())


def test_persist_open_job_session_upserts():
    from db import db

    async def run():
        await persist_open_job_session("user-open-test", "job-open-test")
        row = await db.user_open_jobs.find_one({"user_id": "user-open-test"}, {"_id": 0})
        assert row["job_id"] == "job-open-test"
        await persist_open_job_session("user-open-test", "job-open-test-2")
        row = await db.user_open_jobs.find_one({"user_id": "user-open-test"}, {"_id": 0})
        assert row["job_id"] == "job-open-test-2"

    asyncio.run(run())
