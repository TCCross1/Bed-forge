import os
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException, Depends, Response
from fastapi.responses import JSONResponse

from models import RegisterInput, LoginInput, UserPublic, PasswordChange, new_id, now_iso
from db import db
from audit import write_audit
from sessions import create_session, get_session, touch_session, revoke_session
from security_core import (
    ROLES, EXEC_ROLES, allow_demo_users, allow_open_register, client_ip,
    is_production, session_minutes,
)

import bcrypt
import jwt

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
LOCK_WINDOW_MIN = 15
LOCK_MAX = 8


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET") or ""
    if not secret:
        raise RuntimeError("JWT_SECRET is not set")
    return secret


def create_access_token(user_id: str, email: str, session_id: str, role: str, minutes: int) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "sid": session_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=max(15, minutes)),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def _public(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "disabled": bool(user.get("disabled")),
        "must_change_password": bool(user.get("must_change_password")),
        "created_at": user.get("created_at", ""),
    }


def _cookie_args(minutes: int) -> dict:
    return {
        "key": "access_token",
        "httponly": True,
        "samesite": "strict" if is_production() else "lax",
        "secure": is_production(),
        "max_age": minutes * 60,
        "path": "/",
    }


async def _settings() -> dict:
    return await db.company_settings.find_one({"id": "plant"}, {"_id": 0}) or {}


async def _failures(email: str) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=LOCK_WINDOW_MIN)).isoformat()
    return await db.login_attempts.count_documents({"email": email, "ok": False, "created_at": {"$gte": cutoff}})


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        if user.get("disabled"):
            raise HTTPException(status_code=401, detail="Account disabled")
        sid = payload.get("sid") or ""
        if sid:
            settings = await _settings()
            if not await touch_session(sid, settings):
                raise HTTPException(status_code=401, detail="Session expired")
            rec = await get_session(sid)
            if rec and settings.get("bind_device"):
                header_dev = request.headers.get("x-device-id") or ""
                if rec.get("device_id") and header_dev and rec.get("device_id") != header_dev:
                    raise HTTPException(status_code=401, detail="Device mismatch")
        request.state.session_id = sid
        return user
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_optional_user(request: Request):
    """Return the user when a valid JWT is present; otherwise None. Never 401."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None
    except Exception:
        return None


def require_roles(*roles):
    async def checker(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker


def require_exec():
    return require_roles(*EXEC_ROLES)


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/public-config")
async def public_config():
    return {
        "demo": allow_demo_users(),
        "production": is_production(),
        "open_register": allow_open_register(),
    }


@router.post("/register")
async def register(payload: RegisterInput, request: Request):
    if not allow_open_register():
        raise HTTPException(status_code=403, detail="Open registration is disabled. Ask a plant manager to create your account.")
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    role = payload.role if payload.role in ROLES and payload.role not in EXEC_ROLES else "qc_tech"
    user = {
        "id": new_id(),
        "email": email,
        "password_hash": hash_password(payload.password),
        "name": payload.name,
        "role": role,
        "disabled": False,
        "must_change_password": False,
        "created_at": now_iso(),
    }
    await db.users.insert_one(user)
    await write_audit(action="user.register", user=user, request=request, entity_type="user", entity_id=user["id"])
    settings = await _settings()
    session = await create_session(user, ip=client_ip(request), user_agent=request.headers.get("user-agent") or "", device_id=request.headers.get("x-device-id") or "")
    token = create_access_token(user["id"], email, session["id"], user["role"], session_minutes(settings))
    body = {"user": _public(user), "access_token": token}
    response = JSONResponse(body)
    response.set_cookie(value=token, **_cookie_args(session_minutes(settings)))
    return response


@router.post("/login")
async def login(payload: LoginInput, request: Request):
    email = payload.email.lower()
    ip = client_ip(request)
    try:
        if await _failures(email) >= LOCK_MAX:
            await write_audit(action="auth.lockout", request=request, extra={"email": email}, ok=False)
            raise HTTPException(status_code=429, detail="Account locked after too many failed sign-ins. Wait 15 minutes.")
        user = await db.users.find_one({"email": email})
        if not user or not verify_password(payload.password, user.get("password_hash") or ""):
            await db.login_attempts.insert_one({"email": email, "ok": False, "ip": ip, "created_at": now_iso()})
            await write_audit(action="auth.login_failed", request=request, extra={"email": email}, ok=False)
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if user.get("disabled"):
            await write_audit(action="auth.disabled", user=user, request=request, ok=False)
            raise HTTPException(status_code=401, detail="Account disabled")
        await db.login_attempts.insert_one({"email": email, "ok": True, "ip": ip, "created_at": now_iso()})
        settings = await _settings()
        session = await create_session(
            user,
            ip=ip,
            user_agent=request.headers.get("user-agent") or "",
            device_id=request.headers.get("x-device-id") or "",
        )
        token = create_access_token(user["id"], email, session["id"], user["role"], session_minutes(settings))
        await write_audit(action="auth.login", user=user, request=request, entity_type="session", entity_id=session["id"])
        logger.info("login ok email=%s", email)
        body = {"user": _public(user), "access_token": token, "session_id": session["id"]}
        response = JSONResponse(body)
        response.set_cookie(value=token, **_cookie_args(session_minutes(settings)))
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception("login failed")
        raise HTTPException(status_code=500, detail="Sign-in failed")


@router.post("/logout")
async def logout(request: Request, user=Depends(get_current_user)):
    sid = getattr(request.state, "session_id", "") or ""
    await revoke_session(sid, "logout")
    await write_audit(action="auth.logout", user=user, request=request, entity_type="session", entity_id=sid)
    response = JSONResponse({"ok": True})
    response.delete_cookie("access_token", path="/")
    return response


@router.post("/password")
async def change_password(payload: PasswordChange, request: Request, user=Depends(get_current_user)):
    try:
        if not verify_password(payload.current_password, user.get("password_hash") or ""):
            raise HTTPException(status_code=401, detail="Current password is wrong")
        if len(payload.new_password or "") < 10:
            raise HTTPException(status_code=400, detail="New password must be at least 10 characters")
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"password_hash": hash_password(payload.new_password), "must_change_password": False, "password_changed_at": now_iso()}},
        )
        await write_audit(action="auth.password_change", user=user, request=request, entity_type="user", entity_id=user["id"])
        logger.info("password changed id=%s", user.get("id"))
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("password change failed")
        raise HTTPException(status_code=500, detail="Failed to change password")


@router.get("/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    return _public(user)


@router.get("/users")
async def list_users(user: dict = Depends(require_roles(*EXEC_ROLES, "qc_supervisor"))):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
    return users


async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@bedforge.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD") or ""
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        if not admin_password:
            logger.warning("ADMIN_PASSWORD unset — plant manager account was not created")
            return
        await db.users.insert_one({
            "id": new_id(),
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Plant Manager",
            "role": "admin",
            "disabled": False,
            "must_change_password": is_production(),
            "created_at": now_iso(),
        })
        logger.info("seeded plant manager email=%s", admin_email)
    # Never overwrite an existing password from env — that is a standing backdoor.

    if not allow_demo_users():
        return
    demo = [
        ("tech@bedforge.com", "Tech1234!", "Tyler Chen", "qc_tech"),
        ("supervisor@bedforge.com", "Super1234!", "Dana Reyes", "qc_supervisor"),
        ("production@bedforge.com", "Prod1234!", "Marcus Hill", "production"),
    ]
    for email, pw, name, role in demo:
        if not await db.users.find_one({"email": email}):
            await db.users.insert_one({
                "id": new_id(),
                "email": email,
                "password_hash": hash_password(pw),
                "name": name,
                "role": role,
                "disabled": False,
                "must_change_password": False,
                "created_at": now_iso(),
            })
