"""Control-plane helpers: revocable sessions and executive overrides."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from db import db
from models import new_id, now_iso
from security_core import idle_minutes


def _parse_stamp(value: str) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


async def create_session(user: dict, *, ip: str, user_agent: str, device_id: str = "") -> dict:
    rec = {
        "id": new_id(),
        "user_id": user.get("id"),
        "email": user.get("email") or "",
        "device_id": (device_id or "")[:80],
        "ip": ip or "",
        "user_agent": (user_agent or "")[:180],
        "revoked": False,
        "created_at": now_iso(),
        "last_seen": now_iso(),
    }
    await db.sessions.insert_one(rec)
    return rec


async def get_session(session_id: str) -> Optional[dict]:
    if not session_id:
        return None
    return await db.sessions.find_one({"id": session_id}, {"_id": 0})


async def touch_session(session_id: str, settings: Optional[dict] = None) -> bool:
    rec = await get_session(session_id)
    if not rec or rec.get("revoked"):
        return False
    last = _parse_stamp(rec.get("last_seen") or rec.get("created_at") or "")
    now = datetime.now(timezone.utc)
    if last:
        idle = idle_minutes(settings)
        if now - last > timedelta(minutes=idle):
            await db.sessions.update_one({"id": session_id}, {"$set": {"revoked": True, "revoked_reason": "idle", "revoked_at": now_iso()}})
            return False
        if now - last < timedelta(seconds=60):
            return True
    await db.sessions.update_one({"id": session_id}, {"$set": {"last_seen": now_iso()}})
    return True


async def revoke_session(session_id: str, reason: str = "logout") -> None:
    if not session_id:
        return
    await db.sessions.update_one(
        {"id": session_id},
        {"$set": {"revoked": True, "revoked_reason": reason, "revoked_at": now_iso()}},
    )


async def revoke_user_sessions(user_id: str, reason: str = "revoke") -> int:
    result = await db.sessions.update_many(
        {"user_id": user_id, "revoked": {"$ne": True}},
        {"$set": {"revoked": True, "revoked_reason": reason, "revoked_at": now_iso()}},
    )
    return int(result.modified_count or 0)
