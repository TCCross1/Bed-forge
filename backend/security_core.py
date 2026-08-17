"""Plant security primitives — roles, encryption at rest, IP allow-list, production guards."""
import base64
import hashlib
import ipaddress
import logging
import os
import re
from typing import Iterable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

ROLES = ["qc_tech", "qc_supervisor", "production", "admin", "executive"]
EXEC_ROLES = ("admin", "executive")
SUPERVISOR_ROLES = ("admin", "executive", "qc_supervisor")
PLAN_ROLES = ("admin", "executive", "qc_supervisor", "production")
FILE_MAGIC = b"BFENC1"
WEAK_SECRETS = {
    "changeme",
    "secret",
    "admin123",
    "bedforge-local-dev-secret-change-me",
}


def is_production() -> bool:
    return (os.environ.get("BEDFORGE_ENV") or os.environ.get("APP_ENV") or "").lower() in ("production", "prod")


def allow_demo_users() -> bool:
    flag = (os.environ.get("BEDFORGE_DEMO_USERS") or "").strip().lower()
    if flag in ("0", "false", "no"):
        return False
    if flag in ("1", "true", "yes"):
        return True
    return not is_production()


def allow_open_register() -> bool:
    flag = (os.environ.get("BEDFORGE_ALLOW_REGISTER") or "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    return False


def is_exec(role: Optional[str]) -> bool:
    return (role or "") in EXEC_ROLES


def is_supervisor(role: Optional[str]) -> bool:
    return (role or "") in SUPERVISOR_ROLES


def session_minutes(settings: Optional[dict] = None) -> int:
    raw = (settings or {}).get("session_minutes")
    try:
        minutes = int(raw if raw is not None else os.environ.get("SESSION_MINUTES") or 480)
    except (TypeError, ValueError):
        minutes = 480
    return max(15, min(minutes, 12 * 60))


def idle_minutes(settings: Optional[dict] = None) -> int:
    raw = (settings or {}).get("idle_minutes")
    try:
        minutes = int(raw if raw is not None else os.environ.get("IDLE_MINUTES") or 30)
    except (TypeError, ValueError):
        minutes = 30
    return max(5, min(minutes, 240))


def _fernet():
    from cryptography.fernet import Fernet

    secret = (os.environ.get("FILE_ENCRYPTION_KEY") or os.environ.get("JWT_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("FILE_ENCRYPTION_KEY or JWT_SECRET is required for file encryption")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_bytes(data: bytes) -> bytes:
    if not data:
        return data
    try:
        return FILE_MAGIC + _fernet().encrypt(data)
    except Exception:
        logger.exception("file encrypt failed")
        raise


def decrypt_bytes(data: bytes) -> bytes:
    if not data:
        return data
    if not data.startswith(FILE_MAGIC):
        return data
    try:
        return _fernet().decrypt(data[len(FILE_MAGIC):])
    except Exception:
        logger.exception("file decrypt failed")
        raise ValueError("Unable to decrypt file")


def write_protected(path, data: bytes) -> None:
    path.write_bytes(encrypt_bytes(data))


def read_protected(path) -> bytes:
    return decrypt_bytes(path.read_bytes())


def protected_file_response(path, filename: str = "", media_type: str = "application/octet-stream") -> Response:
    payload = read_protected(path)
    headers = {}
    if filename:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[:180]
        headers["Content-Disposition"] = f'inline; filename="{safe}"'
    headers["X-Content-Type-Options"] = "nosniff"
    headers["Cache-Control"] = "private, no-store"
    return Response(content=payload, media_type=media_type or "application/octet-stream", headers=headers)


def client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return (request.client.host if request.client else "") or ""


def parse_cidrs(raw: Iterable[str]) -> list:
    out = []
    for item in raw or []:
        text = str(item or "").strip()
        if not text:
            continue
        try:
            out.append(ipaddress.ip_network(text, strict=False))
        except ValueError:
            logger.warning("ignored invalid CIDR")
    return out


def ip_allowed(ip: str, cidrs: Iterable[str]) -> bool:
    networks = parse_cidrs(cidrs)
    if not networks:
        return True
    text = (ip or "").strip()
    if not text:
        return False
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return False
    return any(addr in net for net in networks)


def redact_value(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in ("password", "hash", "token", "secret", "photo_data", "raw_text", "authorization")):
                out[key] = "[redacted]"
            else:
                out[key] = redact_value(item)
        return out
    if isinstance(value, list):
        return [redact_value(item) for item in value[:40]]
    if isinstance(value, (bytes, bytearray)):
        return f"[bytes:{len(value)}]"
    return value


def assert_production_safe():
    if not is_production():
        return
    secret = (os.environ.get("JWT_SECRET") or "").strip()
    if not secret or secret.lower() in WEAK_SECRETS or len(secret) < 32:
        raise RuntimeError("Production JWT_SECRET is missing or too weak")
    origins = (os.environ.get("CORS_ORIGINS") or "").strip()
    if not origins or origins == "*":
        raise RuntimeError("Production CORS_ORIGINS must be an explicit origin list")
    if not (os.environ.get("FILE_ENCRYPTION_KEY") or "").strip():
        logger.warning("FILE_ENCRYPTION_KEY unset — files will be wrapped with JWT_SECRET. Set a dedicated key.")


def security_headers_middleware(app):
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        if is_production() and request.url.scheme != "https" and request.headers.get("x-forwarded-proto") != "https":
            path = request.url.path or ""
            if not path.startswith("/api/health"):
                return JSONResponse({"detail": "HTTPS is required"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control") or "no-store"
        if is_production():
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    return app
