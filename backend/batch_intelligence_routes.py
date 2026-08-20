"""Batch Intelligence API — append-only multi-year vault, recommend, manager accept, export.

POST /api/batch-intelligence/recommend never writes mix. Manager Accept is required
before a recommendation can land on a new batch ticket. Thin history returns
insufficient lab history and no invented admixture doses.
"""
from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from audit import write_audit
from auth import get_current_user, require_roles
from batch_intelligence import (
    EVENT_ACCEPT,
    EVENT_BATCH,
    EVENT_EXPORT,
    EVENT_LAB,
    EVENT_RECOMMEND,
    INSUFFICIENT,
    INSUFFICIENT_MESSAGE,
    envelope_to_ticket_fields,
    merge_history_rows,
    merge_qc,
    normalize_qc_results,
    qc_fingerprint,
    qc_from_batch_record,
    qc_from_cylinder,
    qc_from_fresh,
    recommend_from_history,
)
from batch_plant import AI_CAN_WRITE_MIX, apply_recommendations_to_batch
from db import db
from models import BatchRecord, now_iso, new_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["batch-intelligence"])

MANAGER = require_roles("admin", "executive")


class RecommendInput(BaseModel):
    mix_code: Optional[str] = None
    mix_design: Optional[str] = None
    pour_id: Optional[str] = None
    job_id: Optional[str] = None
    batch_id: Optional[str] = None
    required_release_psi: Optional[float] = None
    required_7d_psi: Optional[float] = None
    required_28d_psi: Optional[float] = None
    target_air_pct: Optional[float] = None
    target_slump_in: Optional[float] = None
    ambient_f: Optional[float] = None
    rh_pct: Optional[float] = None
    air_tolerance_pct: Optional[float] = 1.0
    slump_tolerance_in: Optional[float] = 1.5
    env_temp_window_f: Optional[float] = 5.0
    env_rh_window_pct: Optional[float] = 10.0


class AcceptInput(BaseModel):
    recommend_id: str
    pour_id: str
    ticket_number: str
    mix_design: str = ""
    job_id: Optional[str] = None
    beam_ids: Optional[List[str]] = None
    apply_to_ticket: bool = True
    notes: str = ""


class LabIngestInput(BaseModel):
    source_type: str
    source_id: Optional[str] = None
    pour_id: Optional[str] = None
    batch_id: Optional[str] = None
    job_id: Optional[str] = None
    mix_code: Optional[str] = None
    mix_design: Optional[str] = None
    ticket_number: Optional[str] = None
    qc_results: Optional[Dict[str, Any]] = None
    environment: Optional[Dict[str, Any]] = None
    ingredients: Optional[List[Dict[str, Any]]] = None
    admixtures: Optional[List[Dict[str, Any]]] = None
    document: Optional[Dict[str, Any]] = None
    ncr_ids: Optional[List[str]] = None
    retest_of: Optional[str] = None


def _public(doc: dict) -> dict:
    out = dict(doc or {})
    out.pop("_id", None)
    return out


async def resolve_batch_id(
    pour_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    ticket_number: Optional[str] = None,
    mix_ticket: Optional[str] = None,
) -> str:
    if batch_id:
        return str(batch_id)
    ticket = (ticket_number or mix_ticket or "").strip()
    if ticket:
        rec = await db.batch_records.find_one({"ticket_number": ticket}, {"_id": 0})
        if rec and rec.get("id"):
            return rec["id"]
        rec = await db.batch_records.find_one({"mix_code": ticket}, {"_id": 0})
        if rec and rec.get("id"):
            return rec["id"]
    if pour_id:
        rows = await db.batch_records.find({"pour_id": str(pour_id)}, {"_id": 0}).sort("created_at", -1).to_list(1)
        if rows and rows[0].get("id"):
            return rows[0]["id"]
    return ""


async def append_batch_event(doc: dict) -> dict:
    """Vault is append-only. Never update or delete historical lab rows."""
    stored = dict(doc or {})
    stored.setdefault("id", new_id())
    stored.setdefault("created_at", now_iso())
    stored["immutable"] = True
    stored["vault"] = True
    try:
        await db.batch_events.insert_one(stored)
        logger.info(
            "batch_events append type=%s source=%s pour=%s batch=%s",
            stored.get("event_type"),
            stored.get("source_type"),
            bool(stored.get("pour_id")),
            bool(stored.get("batch_id")),
        )
        return _public(stored)
    except Exception:
        logger.exception("batch_events append failed type=%s", stored.get("event_type"))
        raise


async def event_exists(source_type: str, source_id: str, fingerprint: str) -> bool:
    if not source_type or not source_id:
        return False
    rec = await db.batch_events.find_one(
        {"source_type": source_type, "source_id": source_id, "fingerprint": fingerprint},
        {"_id": 0, "id": 1},
    )
    return bool(rec)


def _environment_from_batch(rec: dict) -> dict:
    env = dict(rec.get("environment") or {})
    if rec.get("ambient_temp_f") is not None and env.get("ambient_f") is None:
        env["ambient_f"] = rec.get("ambient_temp_f")
    if rec.get("humidity_pct") is not None and env.get("rh_pct") is None:
        env["rh_pct"] = rec.get("humidity_pct")
    if rec.get("wind_mph") is not None and env.get("wind_mph") is None:
        env["wind_mph"] = rec.get("wind_mph")
    if rec.get("weather") and not env.get("weather"):
        env["weather"] = rec.get("weather")
    if rec.get("concrete_temp_f") is not None and env.get("mix_temp_f") is None:
        env["mix_temp_f"] = rec.get("concrete_temp_f")
    return env


async def ingest_lab_document(
    *,
    source_type: str,
    document: Optional[dict] = None,
    user: Optional[dict] = None,
    pour_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    job_id: Optional[str] = None,
    mix_code: Optional[str] = None,
    qc_results: Optional[dict] = None,
    environment: Optional[dict] = None,
    ingredients: Optional[list] = None,
    admixtures: Optional[list] = None,
    ncr_ids: Optional[list] = None,
    retest_of: Optional[str] = None,
    source_id: Optional[str] = None,
    ticket_number: Optional[str] = None,
    mix_design: Optional[str] = None,
) -> Optional[dict]:
    """Link a lab save (crush, air, slump, temp) to pour / batch_id and append the vault."""
    try:
        rec = dict(document or {})
        kind = (source_type or rec.get("source_type") or "lab").strip().lower()
        if kind in ("cylinder", "crush"):
            qc = merge_qc(qc_from_cylinder(rec), qc_results)
            kind = "cylinder"
        elif kind in ("fresh", "fresh_test", "air", "slump", "temp"):
            qc = merge_qc(qc_from_fresh(rec), qc_results)
            kind = "fresh"
        elif kind in ("batch", "batch_record", "ticket"):
            qc = merge_qc(qc_from_batch_record(rec), qc_results)
            kind = "batch_record"
        else:
            qc = normalize_qc_results(qc_results or rec.get("qc_results"))
        if retest_of:
            qc["retest_of"] = retest_of
        if ncr_ids:
            qc["ncr_ids"] = list(dict.fromkeys((qc.get("ncr_ids") or []) + [str(x) for x in ncr_ids if x]))

        resolved_pour = pour_id or rec.get("pour_id") or ""
        resolved_ticket = ticket_number or rec.get("ticket_number") or rec.get("mix_ticket") or ""
        resolved_batch = await resolve_batch_id(
            pour_id=resolved_pour,
            batch_id=batch_id or rec.get("batch_id"),
            ticket_number=resolved_ticket,
            mix_ticket=rec.get("mix_ticket"),
        )
        fingerprint = qc_fingerprint(qc)
        sid = source_id or rec.get("id") or ""
        if sid and await event_exists(kind, sid, fingerprint):
            logger.info("batch_events skip duplicate source=%s id=%s", kind, sid)
            return None

        event = {
            "id": new_id(),
            "event_type": EVENT_BATCH if kind == "batch_record" else EVENT_LAB,
            "source_type": kind,
            "source_id": sid,
            "pour_id": resolved_pour,
            "batch_id": resolved_batch,
            "job_id": job_id or rec.get("job_id") or "",
            "mix_code": mix_code or rec.get("mix_code") or rec.get("mix_design") or rec.get("mix_ticket") or "",
            "mix_design": mix_design or rec.get("mix_design") or rec.get("mix_code") or "",
            "ticket_number": resolved_ticket,
            "qc_results": qc,
            "environment": environment or _environment_from_batch(rec),
            "ingredients": ingredients if ingredients is not None else list(rec.get("ingredients") or []),
            "admixtures": admixtures if admixtures is not None else list(rec.get("admixtures") or []),
            "fingerprint": fingerprint,
            "created_by": (user or {}).get("name") or rec.get("created_by") or rec.get("tested_by") or rec.get("inspector") or "",
            "created_at": now_iso(),
        }
        return await append_batch_event(event)
    except Exception:
        logger.exception("ingest_lab_document failed source=%s", source_type)
        return None


async def backfill_vault() -> int:
    """Copy live lab / batch rows into the vault when they are not yet stored."""
    written = 0
    try:
        batches = await db.batch_records.find({}, {"_id": 0}).to_list(5000)
        for rec in batches:
            event = await ingest_lab_document(source_type="batch_record", document=rec)
            if event:
                written += 1
        cylinders = await db.cylinders.find({}, {"_id": 0}).to_list(8000)
        for rec in cylinders:
            if rec.get("crush_psi") in (None, ""):
                continue
            event = await ingest_lab_document(source_type="cylinder", document=rec)
            if event:
                written += 1
        fresh_rows = await db.fresh_concrete_tests.find({}, {"_id": 0}).to_list(8000)
        for rec in fresh_rows:
            has_lab = any(rec.get(k) not in (None, "") for k in ("air_content_pct", "slump_in", "concrete_temp_f", "unit_weight_pcf"))
            if not has_lab:
                continue
            event = await ingest_lab_document(source_type="fresh", document=rec)
            if event:
                written += 1
        if written:
            logger.info("batch_events backfill wrote=%s", written)
        return written
    except Exception:
        logger.exception("batch_events backfill failed")
        return written


async def load_history_snapshots() -> List[dict]:
    await backfill_vault()
    events = await db.batch_events.find({}, {"_id": 0}).to_list(20000)
    usable = [
        row
        for row in events
        if row.get("event_type") in (EVENT_LAB, EVENT_BATCH, "lab", "batch")
    ]
    return merge_history_rows(usable)


async def load_ncrs() -> List[dict]:
    try:
        return await db.ncrs.find({}, {"_id": 0}).to_list(4000)
    except Exception:
        logger.exception("load_ncrs for batch intelligence failed")
        return []


@router.post("/batch-intelligence/lab")
async def ingest_lab(payload: LabIngestInput, user=Depends(get_current_user)):
    try:
        event = await ingest_lab_document(
            source_type=payload.source_type,
            document=payload.document,
            user=user,
            pour_id=payload.pour_id,
            batch_id=payload.batch_id,
            job_id=payload.job_id,
            mix_code=payload.mix_code,
            mix_design=payload.mix_design,
            ticket_number=payload.ticket_number,
            qc_results=payload.qc_results,
            environment=payload.environment,
            ingredients=payload.ingredients,
            admixtures=payload.admixtures,
            ncr_ids=payload.ncr_ids,
            retest_of=payload.retest_of,
            source_id=payload.source_id,
        )
        if event is None:
            return {"ok": True, "duplicate": True, "event": None}
        return {"ok": True, "duplicate": False, "event": event}
    except HTTPException:
        raise
    except Exception:
        logger.exception("ingest_lab failed")
        raise HTTPException(status_code=500, detail="Failed to store lab result in batch vault")


@router.post("/batch-intelligence/recommend")
async def recommend(payload: RecommendInput, request: Request, user=Depends(get_current_user)):
    try:
        history = await load_history_snapshots()
        ncrs = await load_ncrs()
        result = recommend_from_history(history, payload.model_dump(), ncrs)
        result["ai_writes_mix"] = bool(AI_CAN_WRITE_MIX)
        event = await append_batch_event(
            {
                "id": new_id(),
                "event_type": EVENT_RECOMMEND,
                "source_type": "recommend",
                "source_id": "",
                "pour_id": payload.pour_id or "",
                "batch_id": payload.batch_id or "",
                "job_id": payload.job_id or "",
                "mix_code": payload.mix_code or payload.mix_design or "",
                "qc_results": normalize_qc_results({}),
                "recommend": {
                    "status": result.get("status"),
                    "winner_count": result.get("winner_count"),
                    "scanned_count": result.get("scanned_count"),
                    "confidence": result.get("confidence"),
                    "drivers": result.get("drivers"),
                    "mix_envelope": result.get("mix_envelope"),
                    "comparables": result.get("comparables"),
                    "query": result.get("query"),
                    "message": result.get("message"),
                },
                "created_by": user.get("name") or "",
                "created_at": now_iso(),
            }
        )
        result["recommend_id"] = event["id"]
        result["accepted"] = False
        await write_audit(
            action="batch_intelligence.recommend",
            user=user,
            request=request,
            entity_type="batch_events",
            entity_id=event["id"],
            extra={"status": result.get("status"), "winners": result.get("winner_count")},
        )
        logger.info(
            "batch intelligence recommend id=%s status=%s winners=%s by=%s",
            event["id"],
            result.get("status"),
            result.get("winner_count"),
            user.get("email"),
        )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("batch intelligence recommend failed")
        raise HTTPException(status_code=500, detail="Failed to score batch intelligence")


@router.post("/batch-intelligence/accept")
async def accept_recommendation(payload: AcceptInput, request: Request, user=Depends(MANAGER)):
    try:
        event = await db.batch_events.find_one({"id": payload.recommend_id}, {"_id": 0})
        if not event:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        blob = event.get("recommend") or {}
        if blob.get("status") == INSUFFICIENT or not blob.get("mix_envelope"):
            raise HTTPException(
                status_code=409,
                detail="insufficient lab history — will not invent admixture doses",
            )
        envelope = blob.get("mix_envelope") or {}
        materials = envelope.get("materials") or []
        if not materials:
            raise HTTPException(
                status_code=409,
                detail="insufficient lab history — will not invent admixture doses",
            )
        try:
            apply_recommendations_to_batch({}, [])
        except PermissionError:
            pass
        if AI_CAN_WRITE_MIX:
            raise HTTPException(status_code=403, detail="AI cannot change the mix")

        ticket = None
        if payload.apply_to_ticket:
            ingredients, admixtures = envelope_to_ticket_fields(envelope)
            mix_name = payload.mix_design or blob.get("query", {}).get("mix_code") or event.get("mix_code") or "MIX"
            record = BatchRecord(
                pour_id=payload.pour_id,
                job_id=payload.job_id,
                beam_ids=payload.beam_ids or [],
                ticket_number=payload.ticket_number,
                mix_design=mix_name,
                ingredients=ingredients,
                admixtures=admixtures,
                notes=(payload.notes or "Applied from Mix Intelligence after manager accept. Recorded medians only — not invented."),
                created_by=user.get("name") or "",
            )
            dumped = record.model_dump()
            dumped["source_recommend_id"] = payload.recommend_id
            dumped["accepted_mix"] = True
            await db.batch_records.insert_one(dumped)
            await ingest_lab_document(source_type="batch_record", document=dumped, user=user)
            ticket = _public(dumped)

        accept_event = await append_batch_event(
            {
                "id": new_id(),
                "event_type": EVENT_ACCEPT,
                "source_type": "accept",
                "source_id": payload.recommend_id,
                "pour_id": payload.pour_id,
                "batch_id": (ticket or {}).get("id") or "",
                "job_id": payload.job_id or "",
                "mix_code": (ticket or {}).get("mix_design") or event.get("mix_code") or "",
                "qc_results": normalize_qc_results({}),
                "recommend_id": payload.recommend_id,
                "ticket_id": (ticket or {}).get("id"),
                "created_by": user.get("name") or "",
                "created_at": now_iso(),
            }
        )
        await write_audit(
            action="batch_intelligence.accept",
            user=user,
            request=request,
            entity_type="batch_events",
            entity_id=accept_event["id"],
            extra={"recommend_id": payload.recommend_id, "ticket_id": (ticket or {}).get("id")},
        )
        logger.info(
            "batch intelligence accept recommend=%s ticket=%s by=%s",
            payload.recommend_id,
            (ticket or {}).get("id"),
            user.get("email"),
        )
        return {"ok": True, "accepted": True, "event": accept_event, "ticket": ticket, "ai_writes_mix": False}
    except HTTPException:
        raise
    except Exception:
        logger.exception("batch intelligence accept failed")
        raise HTTPException(status_code=500, detail="Failed to accept mix recommendation")


@router.get("/batch-intelligence/events")
async def list_events(
    pour_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    event_type: Optional[str] = None,
    user=Depends(get_current_user),
):
    try:
        q = {}
        if pour_id:
            q["pour_id"] = pour_id
        if batch_id:
            q["batch_id"] = batch_id
        if event_type:
            q["event_type"] = event_type
        rows = await db.batch_events.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
        logger.info("batch_events listed count=%s by=%s", len(rows), user.get("email"))
        return rows
    except Exception:
        logger.exception("list batch_events failed")
        raise HTTPException(status_code=500, detail="Failed to list batch vault")


@router.get("/batch-intelligence/export")
async def export_vault(
    request: Request,
    format: str = Query("json"),
    user=Depends(get_current_user),
):
    try:
        await backfill_vault()
        rows = await db.batch_events.find({}, {"_id": 0}).sort("created_at", 1).to_list(50000)
        await append_batch_event(
            {
                "id": new_id(),
                "event_type": EVENT_EXPORT,
                "source_type": "export",
                "qc_results": normalize_qc_results({}),
                "export_count": len(rows),
                "export_format": format,
                "created_by": user.get("name") or "",
                "created_at": now_iso(),
            }
        )
        await write_audit(
            action="batch_intelligence.export",
            user=user,
            request=request,
            entity_type="batch_events",
            entity_id="vault",
            extra={"count": len(rows), "format": format},
        )
        logger.info("batch_events export count=%s format=%s by=%s", len(rows), format, user.get("email"))
        kind = (format or "json").lower()
        if kind == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                [
                    "id",
                    "created_at",
                    "event_type",
                    "source_type",
                    "source_id",
                    "pour_id",
                    "batch_id",
                    "job_id",
                    "mix_code",
                    "ticket_number",
                    "air_content_pct",
                    "slump_in",
                    "concrete_temp_f",
                    "unit_weight_pcf",
                    "retest_of",
                    "ncr_ids",
                    "time_to_release_hours",
                    "compressive_json",
                    "ambient_f",
                    "rh_pct",
                ]
            )
            for row in rows:
                qc = row.get("qc_results") or {}
                env = row.get("environment") or {}
                writer.writerow(
                    [
                        row.get("id"),
                        row.get("created_at"),
                        row.get("event_type"),
                        row.get("source_type"),
                        row.get("source_id"),
                        row.get("pour_id"),
                        row.get("batch_id"),
                        row.get("job_id"),
                        row.get("mix_code"),
                        row.get("ticket_number"),
                        qc.get("air_content_pct"),
                        qc.get("slump_in"),
                        qc.get("concrete_temp_f"),
                        qc.get("unit_weight_pcf"),
                        qc.get("retest_of"),
                        ",".join(qc.get("ncr_ids") or []),
                        qc.get("time_to_release_hours"),
                        json.dumps(qc.get("compressive") or []),
                        env.get("ambient_f"),
                        env.get("rh_pct"),
                    ]
                )
            return StreamingResponse(
                io.BytesIO(buf.getvalue().encode("utf-8")),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=batch-intelligence-vault.csv"},
            )
        return {"count": len(rows), "events": rows, "append_only": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("batch_events export failed")
        raise HTTPException(status_code=500, detail="Failed to export batch vault")
