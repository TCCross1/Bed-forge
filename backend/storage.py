"""Local blueprint file storage. Paths only — never log file bytes."""
import os
import re
from pathlib import Path

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
    dest.write_bytes(data)
    return dest


def list_files(blueprint_id: str):
    folder = blueprint_dir(blueprint_id)
    return sorted([p for p in folder.iterdir() if p.is_file()])
