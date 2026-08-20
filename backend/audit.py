"""Append-only audit log. Never update or delete rows from the API."""
import logging
from typing import Any, Optional

from fastapi import Request

from db import db
from models import new_id, now_iso
from security_core import client_ip, redact_value

logger = logging.getLogger(__name__)

MAX_AUDIT = 20000


async def write_audit(
    *,
    action: str,
    user: Optional[dict] = None,
    request: Optional[Request] = None,
    entity_type: str = "",
    entity_id: str = "",
    before: Any = None,
    after: Any = None,
    reason: str = "",
    ok: bool = True,
    extra: Optional[dict] = None,
) -> None:
    try:
        rec = {
            "id": new_id(),
            "action": action,
            "ok": bool(ok),
            "actor_id": (user or {}).get("id") or "",
            "actor_email": (user or {}).get("email") or "",
            "actor_role": (user or {}).get("role") or "",
            "entity_type": entity_type or "",
            "entity_id": entity_id or "",
            "reason": (reason or "")[:500],
            "before": redact_value(before) if before is not None else None,
            "after": redact_value(after) if after is not None else None,
            "ip": client_ip(request) if request else "",
            "user_agent": ((request.headers.get("user-agent") if request else "") or "")[:180],
            "extra": redact_value(extra or {}),
            "created_at": now_iso(),
        }
        await db.audit_log.insert_one(rec)
    except Exception:
        logger.exception("audit write failed action=%s", action)


async def override_active(kind: str, target_id: str) -> Optional[dict]:
    stamp = now_iso()
    rec = await db.overrides.find_one(
        {
            "kind": kind,
            "target_id": target_id,
            "revoked": {"$ne": True},
            "$or": [{"expires_at": None}, {"expires_at": ""}, {"expires_at": {"$gt": stamp}}],
        },
        {"_id": 0},
    )
    return rec
