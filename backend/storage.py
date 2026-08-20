"""Local blueprint file storage. Paths only — never log file bytes."""
import os
import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent / "uploads" / "blueprints"
MAX_BYTES = 25 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}


def safe_name(name: str) -> str:
    base = os.path.basename(name or "drawing")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base[:180] or "drawing"


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value or "bp")
    return cleaned[:80] or "bp"


def blueprint_dir(blueprint_id: str) -> Path:
    ROOT.mkdir(parents=True, exist_ok=True)
    path = (ROOT / safe_id(blueprint_id)).resolve()
    root = ROOT.resolve()
    if path != root and root not in path.parents:
        raise ValueError("Invalid blueprint path")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(blueprint_id: str, filename: str, data: bytes) -> Path:
    if len(data) > MAX_BYTES:
        raise ValueError("File exceeds 25 MB limit")
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError("Unsupported file type. Use PDF or image.")
    dest = blueprint_dir(blueprint_id) / safe_name(filename)
    from security_core import write_protected
    write_protected(dest, data)
    return dest


def list_files(blueprint_id: str):
    folder = blueprint_dir(blueprint_id)
    return sorted([p for p in folder.iterdir() if p.is_file()])


ROLL_ROOT = Path(__file__).parent / "uploads" / "strand-rolls"
ROLL_MAX_BYTES = 12 * 1024 * 1024
ROLL_ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}


def roll_dir(roll_id: str) -> Path:
    ROLL_ROOT.mkdir(parents=True, exist_ok=True)
    path = (ROLL_ROOT / safe_id(roll_id)).resolve()
    root = ROLL_ROOT.resolve()
    if path != root and root not in path.parents:
        raise ValueError("Invalid strand-roll path")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_roll_photo(roll_id: str, filename: str, data: bytes) -> Path:
    if len(data) > ROLL_MAX_BYTES:
        raise ValueError("Photo exceeds 12 MB limit")
    ext = Path(filename).suffix.lower() or ".jpg"
    if ext not in ROLL_ALLOWED_EXT:
        raise ValueError("Unsupported file type. Use JPEG, PNG, WebP, TIFF, or PDF.")
    dest = roll_dir(roll_id) / safe_name(filename)
    from security_core import write_protected
    write_protected(dest, data)
    return dest


def roll_photo_path(roll_id: str, filename: str) -> Path:
    folder = roll_dir(roll_id)
    dest = (folder / safe_name(filename)).resolve()
    if folder.resolve() not in dest.parents and dest != folder.resolve():
        raise ValueError("Invalid strand-roll photo path")
    return dest


COMPANY_ROOT = Path(__file__).parent / "uploads" / "company"
LOGO_MAX_BYTES = 4 * 1024 * 1024
LOGO_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def company_dir() -> Path:
    COMPANY_ROOT.mkdir(parents=True, exist_ok=True)
    return COMPANY_ROOT.resolve()


def save_company_logo(filename: str, data: bytes) -> Path:
    if len(data) > LOGO_MAX_BYTES:
        raise ValueError("Logo exceeds 4 MB limit")
    ext = Path(filename).suffix.lower() or ".png"
    if ext not in LOGO_ALLOWED_EXT:
        raise ValueError("Unsupported logo type. Use PNG, JPEG, or WebP.")
    folder = company_dir()
    for old in folder.glob("logo.*"):
        try:
            old.unlink()
        except OSError:
            pass
    dest = folder / f"logo{ext}"
    from security_core import write_protected
    write_protected(dest, data)
    return dest


def company_logo_path(filename: str = "") -> Optional[Path]:
    folder = company_dir()
    if filename:
        dest = (folder / safe_name(filename)).resolve()
        if folder not in dest.parents and dest != folder:
            raise ValueError("Invalid logo path")
        return dest if dest.exists() and dest.is_file() else None
    matches = sorted(p for p in folder.glob("logo.*") if p.is_file())
    return matches[0] if matches else None


VAULT_ROOT = Path(__file__).parent / "uploads" / "company"
VAULT_KINDS = {"drawings", "photos", "forms", "strand-certs", "qr", "packages"}


def vault_dir(company_id: str, job_id: str, pour_id: str, beam_id: str, kind: str) -> Path:
    if kind not in VAULT_KINDS:
        raise ValueError("Invalid vault kind")
    root = VAULT_ROOT.resolve()
    path = (
        root
        / safe_id(company_id or "plant")
        / "jobs"
        / safe_id(job_id or "unassigned")
        / "pours"
        / safe_id(pour_id or "unassigned")
        / "beams"
        / safe_id(beam_id or "unassigned")
        / kind
    ).resolve()
    if root not in path.parents and path != root:
        raise ValueError("Invalid vault path")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_vault_file(company_id: str, job_id: str, pour_id: str, beam_id: str, kind: str, filename: str, data: bytes) -> Path:
    if len(data) > MAX_BYTES:
        raise ValueError("File exceeds 25 MB limit")
    dest = vault_dir(company_id, job_id, pour_id, beam_id, kind) / safe_name(filename)
    from security_core import write_protected
    write_protected(dest, data)
    return dest


def vault_file_path(company_id: str, job_id: str, pour_id: str, beam_id: str, kind: str, filename: str) -> Path:
    folder = vault_dir(company_id, job_id, pour_id, beam_id, kind)
    dest = (folder / safe_name(filename)).resolve()
    if folder.resolve() not in dest.parents and dest != folder.resolve():
        raise ValueError("Invalid vault path")
    return dest


def file_response(path, filename: str = "", media_type: str = "application/octet-stream"):
    from security_core import protected_file_response
    return protected_file_response(path, filename, media_type)
