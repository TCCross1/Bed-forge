"""Sparse-page OCR for flattened / photo shop drawings."""
from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

SPARSE_CHAR_THRESHOLD = 400
OCR_RENDER_SCALE = 2.5
EXTRACTOR_OCR_LABEL = "ocr"
EXTRACTOR_TEXT_LABEL = "text_layer"
EXTRACTOR_MERGED_LABEL = "text_layer+ocr"


def _normalize_text(text: str) -> str:
    cleaned = (text or "").replace("\x00", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def page_is_sparse(text: str) -> bool:
    raw = text or ""
    if len(raw) < SPARSE_CHAR_THRESHOLD:
        return True
    if re.search(r"Flattened (?:for Blueprint Intelligence|photo captures|Shop Drawings)", raw, re.IGNORECASE):
        return len(raw) < 1200
    return False


def _tesseract_cmd() -> str | None:
    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd and Path(env_cmd).exists():
        return env_cmd
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract"):
        if Path(candidate).exists():
            return candidate
    return None


def ocr_pil_image(image) -> str:
    cmd = _tesseract_cmd()
    if not cmd:
        logger.warning("tesseract binary not found; skipping OCR for this page")
        return ""
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = cmd
        chunks = []
        for psm in ("6", "11"):
            try:
                text = pytesseract.image_to_string(image, lang="eng", config=f"--psm {psm}")
                chunks.append(_normalize_text(text))
            except Exception:
                logger.exception("pytesseract psm %s failed", psm)
        merged = "\n".join(chunk for chunk in chunks if chunk)
        return _normalize_text(merged)
    except Exception:
        logger.exception("pytesseract failed while OCRing a shop-drawing page")
        return ""


def render_pdf_page(path: str | Path, page_index: int):
    try:
        import pypdfium2 as pdfium
    except Exception:
        logger.warning("pypdfium2 is not installed; cannot rasterize PDF pages for OCR")
        return None
    try:
        pdf = pdfium.PdfDocument(str(path))
        try:
            if page_index < 0 or page_index >= len(pdf):
                return None
            page = pdf[page_index]
            bitmap = page.render(scale=OCR_RENDER_SCALE)
            return bitmap.to_pil()
        finally:
            pdf.close()
    except Exception:
        logger.exception("Failed to rasterize PDF page %s of %s", page_index + 1, path)
        return None


def ocr_pdf_page(path: str | Path, page_index: int) -> str:
    image = render_pdf_page(path, page_index)
    if image is None:
        return ""
    return ocr_pil_image(image)


def merge_native_and_ocr(native_text: str, ocr_text: str) -> Tuple[str, str]:
    native = _normalize_text(native_text)
    ocr = _normalize_text(ocr_text)
    if native and ocr:
        return f"{native}\n{ocr}", EXTRACTOR_MERGED_LABEL
    if ocr:
        return ocr, EXTRACTOR_OCR_LABEL
    return native, EXTRACTOR_TEXT_LABEL if native else "empty"


def read_pdf_pages_merged(path: str | Path, native_pages: List[str]) -> Tuple[List[str], List[str]]:
    """Merge OCR into sparse/empty native text layers. Always returns parallel source labels."""
    merged: List[str] = []
    sources: List[str] = []
    pdf_path = Path(path)
    for index, native in enumerate(native_pages):
        native_norm = _normalize_text(native)
        if not page_is_sparse(native_norm):
            merged.append(native_norm)
            sources.append(EXTRACTOR_TEXT_LABEL)
            continue
        logger.info("Sparse/empty text on page %s (%s chars); running OCR", index + 1, len(native_norm))
        ocr_text = ocr_pdf_page(pdf_path, index)
        combined, source = merge_native_and_ocr(native_norm, ocr_text)
        if source in (EXTRACTOR_OCR_LABEL, EXTRACTOR_MERGED_LABEL) and not ocr_text:
            logger.warning("OCR produced no text for page %s of %s", index + 1, pdf_path.name)
        merged.append(combined)
        sources.append(source)
    return merged, sources
