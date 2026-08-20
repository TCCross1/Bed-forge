import os
import secrets
from datetime import date, datetime, timezone
from fastapi import Depends, HTTPException

from auth import get_current_user
from db import db
from models import LicenseActivateInput, LicenseState, now_iso

LICENSE_FEATURES_BY_TIER = {
    "trial": {
        "digital_twin": True,
        "package_export": True,
        "ncr": True,
        "batch_plant": True,
        "licensing": True,
        "command_board": True,
        "blueprint_intelligence": True,
        "advanced_exports": False,
    },
    "standard": {
        "digital_twin": True,
        "package_export": True,
        "ncr": True,
        "batch_plant": True,
        "licensing": True,
        "command_board": True,
        "blueprint_intelligence": True,
        "advanced_exports": False,
    },
    "enterprise": {
        "digital_twin": True,
        "package_export": True,
        "ncr": True,
        "batch_plant": True,
        "licensing": True,
        "command_board": True,
        "blueprint_intelligence": True,
        "advanced_exports": True,
    },
}


def license_features_for_tier(tier: str) -> dict:
    return dict(LICENSE_FEATURES_BY_TIER.get(tier, LICENSE_FEATURES_BY_TIER["trial"]))


def license_has_expired(expires_at: str) -> bool:
    if not expires_at:
        return False
    try:
        return date.fromisoformat(expires_at) < datetime.now(timezone.utc).date()
    except ValueError:
        return True


async def load_license_state() -> dict:
    license_state = await db.licenses.find_one({"id": "license"}, {"_id": 0})
    if not license_state:
        created = LicenseState(status="trial", tier="trial", feature_flags=license_features_for_tier("trial")).model_dump()
        await db.licenses.insert_one(created)
        return created
    updates = {}
    normalized_flags = {
        **license_features_for_tier(license_state.get("tier", "trial")),
        **license_state.get("feature_flags", {}),
    }
    if normalized_flags != license_state.get("feature_flags", {}):
        updates["feature_flags"] = normalized_flags
        license_state["feature_flags"] = normalized_flags
    if license_has_expired(license_state.get("expires_at", "")) and license_state.get("status") != "expired":
        updates["status"] = "expired"
        license_state["status"] = "expired"
    if updates:
        updates["updated_at"] = now_iso()
        license_state["updated_at"] = updates["updated_at"]
        await db.licenses.update_one({"id": "license"}, {"$set": updates})
    return license_state


async def ensure_feature_enabled(feature: str) -> dict:
    license_state = await load_license_state()
    if license_state.get("status") == "expired":
        raise HTTPException(status_code=403, detail="License expired")
    if not license_state.get("feature_flags", {}).get(feature, False):
        raise HTTPException(status_code=403, detail=f"Feature not licensed: {feature}")
    return license_state


def require_feature(feature: str, *roles: str):
    async def checker(user: dict = Depends(get_current_user)):
        if roles and user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        await ensure_feature_enabled(feature)
        return user
    return checker


async def activate_license_state(payload: LicenseActivateInput) -> dict:
    configured_key = os.environ.get("LICENSE_ACTIVATION_KEY", "").strip()
    if not configured_key:
        raise HTTPException(status_code=503, detail="License activation is not configured")
    if not secrets.compare_digest(payload.license_key, configured_key):
        raise HTTPException(status_code=403, detail="Invalid license activation key")
    try:
        expires_at = date.fromisoformat(payload.expires_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Expiration date must use YYYY-MM-DD") from exc
    if expires_at < datetime.now(timezone.utc).date():
        raise HTTPException(status_code=400, detail="License expiration date cannot be in the past")
    updates = LicenseState(
        status="active",
        tier=payload.tier,
        license_key=f"****{payload.license_key[-4:]}",
        expires_at=payload.expires_at,
        feature_flags=license_features_for_tier(payload.tier),
        last_checked_at=now_iso(),
        updated_at=now_iso(),
    ).model_dump()
    current = await db.licenses.find_one({"id": "license"}, {"_id": 0})
    if current:
        await db.licenses.update_one({"id": "license"}, {"$set": updates})
    else:
        await db.licenses.insert_one(updates)
    return updates
