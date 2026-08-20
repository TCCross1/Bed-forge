import os
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException, Depends
from models import RegisterInput, LoginInput, UserPublic, new_id, now_iso
from db import db

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
ROLES = ["qc_tech", "qc_supervisor", "production", "admin"]

# Must stay in lockstep with frontend/src/pages/Login.jsx DEMO_USERS.
DEMO_USERS = [
    {"email": "admin@bedforge.com", "password": "admin123", "name": "Plant Admin", "role": "admin"},
    {"email": "supervisor@bedforge.com", "password": "super123", "name": "Supervisor", "role": "qc_supervisor"},
    {"email": "qc@bedforge.com", "password": "qc123", "name": "QC Tech", "role": "qc_tech"},
    {"email": "production@bedforge.com", "password": "prod123", "name": "Production", "role": "production"},
]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def get_jwt_secret() -> str:
    return os.environ.get("JWT_SECRET", "bedforge-dev-secret")


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def _public(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "created_at": user.get("created_at", ""),
    }


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
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_optional_user(request: Request) -> dict | None:
    """Return the user when a valid JWT is present; otherwise None. Never 401."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None
    except Exception:
        logger.exception("Optional auth lookup failed")
        return None


def require_roles(*roles):
    async def checker(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker


def require_exec():
    return require_roles("admin", "executive")


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
async def register(payload: RegisterInput):
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    role = payload.role if payload.role in ROLES else "qc_tech"
    user = {
        "id": new_id(),
        "email": email,
        "password_hash": hash_password(payload.password),
        "name": payload.name,
        "role": role,
        "created_at": now_iso(),
    }
    await db.users.insert_one(user)
    token = create_access_token(user["id"], email)
    return {"user": _public(user), "access_token": token}


@router.post("/login")
async def login(payload: LoginInput):
    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], email)
    return {"user": _public(user), "access_token": token}


@router.get("/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    return _public(user)


@router.get("/users")
async def list_users(user: dict = Depends(require_roles("admin", "qc_supervisor"))):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
    return users


def _password_matches(plain: str, hashed) -> bool:
    if not hashed or not isinstance(hashed, str):
        return False
    try:
        return verify_password(plain, hashed)
    except Exception:
        logger.warning("Invalid password hash encountered; demo password will be reset")
        return False


async def _upsert_demo_user(email: str, password: str, name: str, role: str) -> None:
    email = (email or "").lower().strip()
    if not email or not password:
        raise ValueError("Demo user email and password are required")
    safe_role = role if role in ROLES else "qc_tech"
    try:
        existing = await db.users.find_one({"email": email})
        if existing is None:
            await db.users.insert_one({
                "id": new_id(),
                "email": email,
                "password_hash": hash_password(password),
                "name": name,
                "role": safe_role,
                "created_at": now_iso(),
            })
            logger.info("Seeded demo user %s role=%s", email, safe_role)
            return
        updates = {}
        if not _password_matches(password, existing.get("password_hash")):
            updates["password_hash"] = hash_password(password)
        if existing.get("name") != name:
            updates["name"] = name
        if existing.get("role") != safe_role:
            updates["role"] = safe_role
        if updates:
            await db.users.update_one({"email": email}, {"$set": updates})
            logger.info("Updated demo user %s fields=%s", email, sorted(updates.keys()))
    except Exception:
        logger.exception("Failed to seed demo user %s", email)
        raise


async def seed_admin():
    """Idempotently create/update Login.jsx demo users, plus optional env owner."""
    try:
        for user in DEMO_USERS:
            await _upsert_demo_user(user["email"], user["password"], user["name"], user["role"])
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@bedforge.com").lower().strip()
        admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
        demo_emails = {user["email"] for user in DEMO_USERS}
        if admin_email and admin_email not in demo_emails:
            await _upsert_demo_user(admin_email, admin_password, "Plant Admin", "admin")
        logger.info("Demo user seed complete.")
    except Exception:
        logger.exception("Demo user seed failed")
        raise
