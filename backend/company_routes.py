"""Plant company / tenant branding. Logo is interchangeable — never hard-coded."""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from auth import get_current_user, require_roles
from db import db
from models import CompanySettings, CompanySettingsUpdate, now_iso
from storage import LOGO_ALLOWED_EXT, company_logo_path, save_company_logo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["company"])

DEFAULT_COMPANY = CompanySettings()


def public_view(doc: dict) -> dict:
    doc = doc or {}
    path = company_logo_path(doc.get("logo_filename") or "") or company_logo_path("")
    has_logo = bool(path)
    return {
        "company_name": doc.get("company_name") or DEFAULT_COMPANY.company_name,
        "app_name": doc.get("app_name") or DEFAULT_COMPANY.app_name,
        "tag_header": doc.get("tag_header") or "",
        "has_logo": has_logo,
        "logo_url": "/api/company/logo" if has_logo else "",
        "updated_at": doc.get("updated_at") or "",
    }


async def get_company_doc() -> dict:
    doc = await db.company_settings.find_one({"id": "plant"}, {"_id": 0})
    if doc:
        return doc
    seeded = DEFAULT_COMPANY.model_dump()
    await db.company_settings.insert_one(seeded)
    return seeded


@router.get("/company/public")
async def company_public():
    try:
        doc = await db.company_settings.find_one({"id": "plant"}, {"_id": 0})
        return public_view(doc or DEFAULT_COMPANY.model_dump())
    except Exception:
        logger.exception("company_public failed")
        return public_view(DEFAULT_COMPANY.model_dump())


@router.get("/company")
async def get_company(user=Depends(get_current_user)):
    try:
        doc = await get_company_doc()
        view = public_view(doc)
        view["id"] = doc.get("id")
        view["tenant_id"] = doc.get("tenant_id")
        view["logo_filename"] = doc.get("logo_filename") or ""
        view["updated_by"] = doc.get("updated_by") or ""
        return view
    except Exception:
        logger.exception("get_company failed")
        raise HTTPException(status_code=500, detail="Failed to load company settings")


@router.patch("/company")
async def update_company(payload: CompanySettingsUpdate, user=Depends(require_roles("admin", "qc_supervisor"))):
    try:
        doc = await get_company_doc()
        updates = {k: v.strip() if isinstance(v, str) else v for k, v in payload.model_dump().items() if v is not None}
        if not updates:
            return public_view(doc)
        updates["updated_by"] = user.get("name") or ""
        updates["updated_at"] = now_iso()
        await db.company_settings.update_one({"id": "plant"}, {"$set": updates})
        saved = await get_company_doc()
        logger.info("company settings updated by=%s fields=%s", user.get("email"), list(updates.keys()))
        return {**public_view(saved), "updated_by": saved.get("updated_by") or ""}
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_company failed")
        raise HTTPException(status_code=500, detail="Failed to update company settings")


@router.post("/company/logo")
async def upload_company_logo(file: UploadFile = File(...), user=Depends(require_roles("admin", "qc_supervisor"))):
    try:
        raw = await file.read()
        name = file.filename or "logo.png"
        ext = Path(name).suffix.lower() or ".png"
        if ext not in LOGO_ALLOWED_EXT:
            raise HTTPException(status_code=400, detail="Unsupported logo type. Use PNG, JPEG, or WebP.")
        path = save_company_logo(name, raw)
        await get_company_doc()
        await db.company_settings.update_one(
            {"id": "plant"},
            {"$set": {
                "logo_filename": path.name,
                "logo_content_type": file.content_type or "image/png",
                "updated_by": user.get("name") or "",
                "updated_at": now_iso(),
            }},
        )
        saved = await get_company_doc()
        logger.info("company logo uploaded by=%s name=%s bytes=%s", user.get("email"), path.name, len(raw))
        return public_view(saved)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("upload_company_logo failed")
        raise HTTPException(status_code=500, detail="Failed to upload company logo")


@router.get("/company/logo")
async def serve_company_logo():
    try:
        doc = await db.company_settings.find_one({"id": "plant"}, {"_id": 0})
        filename = (doc or {}).get("logo_filename") or ""
        path = company_logo_path(filename) if filename else company_logo_path("")
        if not path or not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="No company logo uploaded")
        media = (doc or {}).get("logo_content_type") or "image/png"
        return FileResponse(path, media_type=media)
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid logo path")
    except Exception:
        logger.exception("serve_company_logo failed")
        raise HTTPException(status_code=500, detail="Failed to load company logo")
