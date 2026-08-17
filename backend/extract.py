"""Replaceable shop-drawing → BeamSpec extractor.

Backends (BEAMSPEC_EXTRACTOR env):
  auto      — L25390 reference if filename/text matches, else vision, else heuristic
  l25390    — force Larue County Type 2 reference
  openai    — vision model (OPENAI_API_KEY)
  heuristic — PDF/text regex only
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from beam_spec import BeamSpec, BeamGeometry, HardwareItem, StationRef
from l25390 import JOB_NUMBER, PRODUCT_NAME, build_l25390_spec

logger = logging.getLogger(__name__)

VISION_PROMPT = """You are a prestressed-concrete shop-drawing reader for BedForge QC.
Extract a JSON object with this exact shape (no markdown):
{
  "job_number": "",
  "beam_mark": "",
  "product_name": "",
  "twin_type": "i_beam or box_beam",
  "length_ft": 0,
  "depth_in": 0,
  "width_in": 0,
  "top_flange_width_in": 0,
  "bot_flange_width_in": 0,
  "web_thick_in": 0,
  "marked_end_id": "",
  "strands": [{"number":1,"size":"0.5in","detensioning":"straight|draped","debond_me_ft":0,"debond_ue_ft":0,"offset_in":0}],
  "hardware": [{"kind":"lift_loop|insert|tube|drain|downspout|tie_rod|hold_down|projecting_rebar|grout_groove|diaphragm|bearing_plate|bituminous_zone","name":"","type_code":"","size":"","station_ft":0,"height_from_soffit_in":0,"offset_in":0,"notes":""}],
  "notes": [],
  "special_finishes": []
}
Read EVERY lift loop, F-64/insert, drain, tube, tie-rod, hold-down, bearing plate,
bituminous/debond zone, diaphragm angle, grout groove, and marked-end stamp.
Stations are feet from the Marked End. Heights are inches from soffit.
"""


def _text_from_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        logger.info("pypdf unavailable or failed for %s", path.name)
        return ""


def _looks_like_l25390(filename: str, text: str) -> bool:
    blob = f"{filename} {text}".upper()
    keys = ("L25390", "255390", "LARUE", "LA RUE", "TYPE 2", "PC I BEAM TYPE 2", "NOLIN")
    return any(k in blob for k in keys)


def _heuristic_geometry(text: str, filename: str) -> dict:
    length = None
    m = re.search(r"(\d{2,3})\s*['’]\s*-?\s*(\d{1,2})?\s*[\"″]?", text)
    if m:
        feet = float(m.group(1))
        inches = float(m.group(2) or 0)
        length = feet + inches / 12.0
    twin = "box_beam" if re.search(r"box\s*beam", text, re.I) else "i_beam"
    return {
        "length_ft": length or 73.333,
        "twin_type": twin,
        "filename": filename,
    }


def _box_grout_grooves(length_ft: float, width_in: float) -> list:
    grooves = []
    for name, off in (("Grout groove left", -(width_in / 2) + 1.0), ("Grout groove right", (width_in / 2) - 1.0)):
        grooves.append(HardwareItem(
            kind="grout_groove",
            name=name,
            type_code="GG",
            size='1" x 1"',
            material="cast groove",
            position=StationRef(station_ft=0.0, offset_in=off, height_from_soffit_in=0.0, face="side"),
            end_station_ft=length_ft,
            notes="Longitudinal grout key for adjacent box beams.",
            tolerance_in=0.5,
        ))
    return grooves


def _spec_from_vision_json(data: dict, beam_id, job_id, pour_id, blueprint_id, beam_mark) -> BeamSpec:
    from beam_spec import StrandItem

    geo = data.get("geometry") or data
    spec = build_l25390_spec(beam_id, job_id, pour_id, blueprint_id, beam_mark or data.get("beam_mark") or "B1")
    spec.extractor = "openai_vision"
    spec.extractor_confidence = 0.7
    spec.job_number = data.get("job_number") or spec.job_number
    spec.product_name = data.get("product_name") or spec.product_name
    spec.marked_end_id = data.get("marked_end_id") or spec.marked_end_id
    g = spec.geometry
    spec.geometry = BeamGeometry(
        twin_type=data.get("twin_type") or g.twin_type,
        length_ft=float(data.get("length_ft") or geo.get("length_ft") or g.length_ft),
        depth_in=float(data.get("depth_in") or g.depth_in),
        width_in=float(data.get("width_in") or g.width_in),
        top_flange_width_in=float(data.get("top_flange_width_in") or g.top_flange_width_in),
        top_flange_thick_in=g.top_flange_thick_in,
        bot_flange_width_in=float(data.get("bot_flange_width_in") or g.bot_flange_width_in),
        bot_flange_thick_in=g.bot_flange_thick_in,
        web_thick_in=float(data.get("web_thick_in") or g.web_thick_in),
        product_name=spec.product_name,
    )
    if data.get("notes"):
        spec.notes = list(data["notes"]) + spec.notes
    if data.get("hardware"):
        extra = []
        for h in data["hardware"]:
            extra.append(HardwareItem(
                kind=h.get("kind") or "insert",
                name=h.get("name") or h.get("kind") or "item",
                type_code=h.get("type_code") or "",
                size=h.get("size") or "",
                position=StationRef(
                    station_ft=float(h.get("station_ft") or 0),
                    offset_in=float(h.get("offset_in") or 0),
                    height_from_soffit_in=float(h.get("height_from_soffit_in") or 0),
                ),
                notes=h.get("notes") or "vision extraction",
            ))
        if len(extra) >= 4:
            spec.hardware = extra
        else:
            spec.hardware = extra + spec.hardware
    if spec.geometry.twin_type == "box_beam" and not any(h.kind == "grout_groove" for h in spec.hardware):
        spec.hardware = spec.hardware + _box_grout_grooves(spec.geometry.length_ft, spec.geometry.width_in)
    if data.get("strands"):
        vision_strands = []
        for s in data["strands"]:
            vision_strands.append(StrandItem(
                number=int(s.get("number") or 0),
                size=s.get("size") or "0.5in",
                detensioning=s.get("detensioning") or "straight",
                debond_me_ft=float(s.get("debond_me_ft") or 0),
                debond_ue_ft=float(s.get("debond_ue_ft") or 0),
                offset_in=float(s.get("offset_in") or 0),
            ))
        if vision_strands:
            spec.strands = vision_strands
    return spec


def _extract_openai(files: List[Path], beam_id, job_id, pour_id, blueprint_id, beam_mark) -> Optional[BeamSpec]:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return None
    try:
        import base64
        import httpx

        content = [{"type": "text", "text": VISION_PROMPT}]
        for path in files[:8]:
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                b64 = base64.b64encode(path.read_bytes()).decode("ascii")
                mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
                content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        if len(content) == 1:
            text = "\n".join(_text_from_pdf(p) for p in files if p.suffix.lower() == ".pdf")
            content[0]["text"] += "\n\nPDF TEXT:\n" + text[:12000]
        model = os.environ.get("BEAMSPEC_VISION_MODEL", "gpt-4o-mini")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.1,
        }
        with httpx.Client(timeout=90.0) as client:
            res = client.post(
                os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            res.raise_for_status()
            raw = res.json()["choices"][0]["message"]["content"]
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
        data = json.loads(raw)
        return _spec_from_vision_json(data, beam_id, job_id, pour_id, blueprint_id, beam_mark)
    except Exception:
        logger.exception("openai vision extraction failed")
        return None


def extract_beam_spec(
    files: List[Path],
    *,
    beam_id: Optional[str] = None,
    job_id: Optional[str] = None,
    pour_id: Optional[str] = None,
    blueprint_id: Optional[str] = None,
    beam_mark: str = "B1",
) -> Tuple[BeamSpec, str]:
    """Return (spec, extractor_name). Never raises on missing AI keys."""
    mode = (os.environ.get("BEAMSPEC_EXTRACTOR") or "auto").lower()
    names = " ".join(p.name for p in files)
    text = "\n".join(_text_from_pdf(p) for p in files if p.suffix.lower() == ".pdf")

    if mode == "l25390" or (mode == "auto" and _looks_like_l25390(names, text)):
        spec = build_l25390_spec(beam_id, job_id, pour_id, blueprint_id, beam_mark)
        spec.extractor = "l25390_reference"
        spec.notes = [f"Matched Larue County / {JOB_NUMBER} shop-drawing fingerprint from '{names}'."] + spec.notes
        logger.info("extract used l25390_reference files=%s", names)
        return spec, spec.extractor

    if mode in ("auto", "openai"):
        vision = _extract_openai(files, beam_id, job_id, pour_id, blueprint_id, beam_mark)
        if vision:
            logger.info("extract used openai_vision files=%s", names)
            return vision, vision.extractor

    spec = build_l25390_spec(beam_id, job_id, pour_id, blueprint_id, beam_mark)
    heur = _heuristic_geometry(text, names)
    spec.geometry.length_ft = heur["length_ft"]
    spec.geometry.twin_type = heur["twin_type"]
    if heur["twin_type"] == "box_beam" and not any(h.kind == "grout_groove" for h in spec.hardware):
        spec.hardware = spec.hardware + _box_grout_grooves(heur["length_ft"], spec.geometry.width_in)
    spec.extractor = "heuristic_fallback"
    spec.extractor_confidence = 0.45
    spec.notes = [
        f"Vision model not configured; seeded from {PRODUCT_NAME} / {JOB_NUMBER} reference and filename heuristics.",
        "QC Supervisor must review and lock before the twin is treated as design-of-record.",
    ] + spec.notes
    logger.info("extract used heuristic_fallback files=%s", names)
    return spec, spec.extractor
