"""Mill-tag OCR / vision extraction for strand roll traceability.

Never logs image bytes or API keys. Missing vision keys fall back to empty
fields so the tech can still confirm after a photo is stored.
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

LOW_CONFIDENCE = 0.72

FIELD_KEYS = (
    "reel_number",
    "heat_number",
    "lot_number",
    "pack_weight",
    "pack_length",
    "astm_standard",
    "strand_grade",
    "strand_type",
    "nominal_diameter",
    "area_in2",
)

VISION_PROMPT = """You are a prestressed-concrete mill-tag and MTC reader for BedForge QC.
Read EVERY visible tag, coil card, and mill test certificate in the photo(s).
Return JSON only (no markdown) with this exact shape:
{
  "reel_number": "",
  "heat_number": "",
  "lot_number": "",
  "pack_weight": "",
  "pack_length": "",
  "astm_standard": "",
  "strand_grade": "",
  "strand_type": "",
  "nominal_diameter": "",
  "area_in2": null,
  "cert_values": {},
  "received_date": "",
  "raw_text": "",
  "confidence": {
    "reel_number": 0.0,
    "heat_number": 0.0,
    "lot_number": 0.0,
    "pack_weight": 0.0,
    "pack_length": 0.0,
    "astm_standard": 0.0,
    "strand_grade": 0.0,
    "strand_type": 0.0,
    "nominal_diameter": 0.0,
    "area_in2": 0.0
  }
}
Rules:
- heat_number is the mill heat (most critical). Copy it exactly.
- reel_number is reel / pack / coil / pack no.
- lot_number is lot or production number.
- pack_weight include units if shown (lb).
- pack_length include units if shown (ft).
- astm_standard is typically ASTM A416 or A416M.
- strand_grade is 270 or 250.
- strand_type is Low-Relaxation when LR / lo-lax / low relaxation is shown.
- nominal_diameter is 0.50in / 0.60in / 0.70in style.
- area_in2 is numeric (0.153, 0.217, 0.294) when printed.
- cert_values holds extra cert numbers (UTS, yield, elongation, modulus, mill name).
- confidence is 0-1 per field. Use <0.72 when a character is guessed or glare hides it.
- raw_text is the full readable text from the tag/MTC.
"""

AREA_BY_DIAMETER = {
    "0.5": 0.153,
    "0.50": 0.153,
    "0.6": 0.217,
    "0.60": 0.217,
    "0.7": 0.294,
    "0.70": 0.294,
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:120]


def _first(pattern: str, text: str, flags=re.I) -> str:
    match = re.search(pattern, text or "", flags)
    if not match:
        return ""
    return _clean(match.group(1) if match.lastindex else match.group(0))


def extract_from_text(text: str) -> Dict[str, Any]:
    blob = text or ""
    fields = {
        "reel_number": _first(r"(?:\breel|\bcoil|\bpack\s*(?:no\.?|number|#))\s*[:#]?\s*([A-Z0-9][A-Z0-9._/-]+)", blob),
        "heat_number": _first(r"\bheat(?:\s*(?:no\.?|number))?\s*[:#]?\s*([A-Z0-9][A-Z0-9._/-]+)", blob),
        "lot_number": _first(r"(?:\blot|\bproduction)\s*(?:no\.?|number)?\s*[:#]?\s*([A-Z0-9][A-Z0-9._/-]+)", blob),
        "pack_weight": _first(r"(?:pack\s*)?(?:wt|weight)\s*[:#]?\s*([0-9][0-9,.]*(?:\s*(?:lb|lbs|#))?)", blob),
        "pack_length": _first(r"(?:pack\s*)?(?:length|len)\s*[:#]?\s*([0-9][0-9,.]*(?:\s*(?:ft|feet)')?)", blob),
        "astm_standard": "",
        "strand_grade": "",
        "strand_type": "",
        "nominal_diameter": "",
        "area_in2": None,
        "cert_values": {},
        "received_date": _first(r"(?:date|received)\s*[:#]?\s*(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})", blob),
        "raw_text": blob[:8000],
    }
    astm = re.search(r"A\s*416\s*M?", blob, re.I)
    if astm:
        fields["astm_standard"] = _normalize_astm(astm.group(0))

    grade = re.search(r"(?:grade|gr)\s*[:#]?\s*(270|250)\b", blob, re.I) or re.search(r"\b(270|250)\s*(?:ksi|grade)?", blob, re.I)
    if grade:
        fields["strand_grade"] = grade.group(1)
    if re.search(r"low[\s-]*rel|lo[\s-]*lax|lr\b", blob, re.I):
        fields["strand_type"] = "Low-Relaxation"
    diam = re.search(r"0?\.(50|5|60|6|70|7)\s*(?:in|inch|\")?", blob, re.I)
    if diam:
        raw = diam.group(1)
        mapped = {"5": "0.50", "50": "0.50", "6": "0.60", "60": "0.60", "7": "0.70", "70": "0.70"}
        inch = mapped.get(raw, raw)
        fields["nominal_diameter"] = f"{inch}in"
        fields["area_in2"] = AREA_BY_DIAMETER.get(inch)
    area = _first(r"(?:area|a)\s*[:#]?\s*(0\.\d{2,4})", blob)
    if area:
        try:
            fields["area_in2"] = float(area)
        except ValueError:
            pass
    mill = _first(r"(sumiden|sumitomo|insteel|wmc|wire\s*mill|posco|tatung)[^\n]{0,40}", blob)
    if mill:
        fields["cert_values"]["mill"] = mill

    confidence = {}
    for key in FIELD_KEYS:
        val = fields.get(key)
        present = val not in (None, "", [])
        if key == "heat_number" and present:
            confidence[key] = 0.9
        elif present:
            confidence[key] = 0.82
        else:
            confidence[key] = 0.0
    overall = max(confidence.values()) if confidence else 0.0
    return {"fields": fields, "confidence": confidence, "extractor_confidence": overall, "extractor": "regex"}


def _normalize_astm(value: str) -> str:
    token = re.sub(r"\s+", "", (value or "").upper())
    if "416M" in token:
        return "ASTM A416M"
    if "416" in token:
        return "ASTM A416"
    return _clean(value)


def merge_extraction(primary: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    fields = dict(fallback.get("fields") or {})
    confidence = dict(fallback.get("confidence") or {})
    src_fields = primary.get("fields") or {}
    src_conf = primary.get("confidence") or {}
    for key in FIELD_KEYS:
        src_val = src_fields.get(key)
        src_c = float(src_conf.get(key) or 0)
        fb_val = fields.get(key)
        fb_c = float(confidence.get(key) or 0)
        if src_val not in (None, "", []) and src_c >= fb_c:
            fields[key] = src_val
            confidence[key] = src_c
        elif fb_val not in (None, "", []) and not (src_val not in (None, "", [])):
            fields[key] = fb_val
            confidence[key] = fb_c
    if src_fields.get("cert_values"):
        merged = dict(fields.get("cert_values") or {})
        merged.update(src_fields.get("cert_values") or {})
        fields["cert_values"] = merged
    if src_fields.get("raw_text"):
        fields["raw_text"] = src_fields["raw_text"]
    elif fallback.get("fields", {}).get("raw_text"):
        fields["raw_text"] = fallback["fields"]["raw_text"]
    if src_fields.get("received_date") and not fields.get("received_date"):
        fields["received_date"] = src_fields["received_date"]
    if fields.get("astm_standard"):
        fields["astm_standard"] = _normalize_astm(str(fields["astm_standard"]))
    if fields.get("nominal_diameter") and fields.get("area_in2") in (None, ""):
        inch = re.sub(r"[^0-9.]", "", str(fields["nominal_diameter"]))
        fields["area_in2"] = AREA_BY_DIAMETER.get(inch)
    overall = max([float(v or 0) for v in confidence.values()] + [0.0])
    extractor = primary.get("extractor") or fallback.get("extractor") or "regex"
    if primary.get("extractor") and fallback.get("extractor") and primary.get("extractor") != fallback.get("extractor"):
        extractor = f"{primary.get('extractor')}+{fallback.get('extractor')}"
    return {
        "fields": fields,
        "confidence": confidence,
        "extractor_confidence": round(overall, 3),
        "extractor": extractor,
    }


def _parse_vision_json(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    data = json.loads(text)
    fields = {k: data.get(k) for k in list(FIELD_KEYS) + ("cert_values", "received_date", "raw_text")}
    if fields.get("astm_standard"):
        fields["astm_standard"] = _normalize_astm(str(fields["astm_standard"]))
    conf = data.get("confidence") or {}
    confidence = {k: float(conf.get(k) or (0.85 if fields.get(k) not in (None, "", []) else 0.0)) for k in FIELD_KEYS}
    return {
        "fields": fields,
        "confidence": confidence,
        "extractor_confidence": max(confidence.values()) if confidence else 0.0,
        "extractor": "openai_vision",
    }


def extract_from_images(paths: List[Path]) -> Dict[str, Any]:
    empty = extract_from_text("")
    empty["extractor"] = "none"
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        logger.info("strand OCR vision skipped — no OPENAI_API_KEY / EMERGENT_LLM_KEY")
        return empty
    try:
        import base64
        import httpx

        content: List[Dict[str, Any]] = [{"type": "text", "text": VISION_PROMPT}]
        for path in paths[:8]:
            suffix = path.suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else ("image/webp" if suffix == ".webp" else "image/png")
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        if len(content) == 1:
            logger.info("strand OCR vision skipped — no raster images")
            return empty
        model = os.environ.get("STRAND_ROLL_VISION_MODEL") or os.environ.get("BEAMSPEC_VISION_MODEL") or "gpt-4o-mini"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.0,
        }
        with httpx.Client(timeout=90.0) as client:
            res = client.post(
                os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            res.raise_for_status()
            raw = res.json()["choices"][0]["message"]["content"]
        parsed = _parse_vision_json(raw)
        regex = extract_from_text(parsed.get("fields", {}).get("raw_text") or "")
        merged = merge_extraction(parsed, regex)
        logger.info(
            "strand OCR vision complete extractor=%s heat=%s conf=%s",
            merged.get("extractor"),
            bool((merged.get("fields") or {}).get("heat_number")),
            merged.get("extractor_confidence"),
        )
        return merged
    except Exception:
        logger.exception("strand OCR vision failed")
        return empty


def extract_roll(paths: List[Path], extra_text: str = "") -> Dict[str, Any]:
    vision = extract_from_images(paths)
    regex = extract_from_text(extra_text)
    return merge_extraction(vision, regex)
