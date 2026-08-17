"""QC narrative for a digital-tape run vs the twin. Works without an API key."""
import json
import logging
import os
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def heuristic_tape_summary(compare: dict) -> dict:
    matches = compare.get("matches") or []
    unshot = compare.get("unshot") or []
    rescan = compare.get("needs_rescan") or [m for m in matches if m.get("rescan")]
    labels: List[str] = []
    for row in rescan:
        name = row.get("element_name") or f"station {row.get('measured_station_ft')} ft"
        idx = row.get("station_index")
        label = f"#{idx} {name}" if idx is not None else str(name)
        labels.append(label)
    notes: List[str] = []
    if compare.get("pass_count"):
        notes.append(f"{compare.get('pass_count')} station(s) match the twin within tolerance.")
    if rescan:
        notes.append(f"{len(rescan)} station(s) need a rescan (off-level, forced snap, or outside the element's inch tolerance).")
    if compare.get("unmatched_count"):
        notes.append(f"{compare.get('unmatched_count')} shot(s) did not land near a blueprint station — confirm they were intended.")
    if unshot:
        notes.append(f"{len(unshot)} design point(s) on the twin have not been shot yet.")
    if not matches:
        notes.append("No stations in this run. Plot the header, walk the beam, snap on green.")
    summary = (
        f"One QC tech shot {compare.get('shot_count') or 0} station(s) from the header / marked end. "
        f"{compare.get('pass_count') or 0} passed against the digital twin / shop drawing. "
        f"{len(rescan)} flagged for rescan. "
        f"{len(unshot)} blueprint point(s) still unmeasured."
    )
    if labels:
        summary += " Rescan: " + ", ".join(labels[:12]) + "."
    return {
        "summary": summary.strip(),
        "rescan_labels": labels,
        "notes": notes,
        "source": "heuristic",
    }


def _compact_compare(compare: dict) -> dict:
    matches = []
    for row in (compare.get("matches") or [])[:80]:
        matches.append({
            "station_index": row.get("station_index"),
            "measured_ft": row.get("measured_station_ft"),
            "design_ft": row.get("design_station_ft"),
            "delta_in": row.get("delta_in"),
            "tolerance_in": row.get("tolerance_in"),
            "element": row.get("element_name"),
            "kind": row.get("element_kind"),
            "level": row.get("level"),
            "forced": row.get("forced"),
            "rescan": row.get("rescan"),
            "flag": row.get("flag"),
        })
    unshot = []
    for row in (compare.get("unshot") or [])[:40]:
        unshot.append({
            "name": row.get("name"),
            "kind": row.get("kind"),
            "station_ft": row.get("station_ft"),
            "tolerance_in": row.get("tolerance_in"),
        })
    return {"matches": matches, "unshot": unshot}


def ai_tape_review(compare: dict) -> dict:
    """Optional LLM narrative. Never invents numbers; falls back to the local matcher."""
    base = heuristic_tape_summary(compare)
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return base
    try:
        import httpx

        compact = _compact_compare(compare)
        prompt = (
            "You are a precast QC assistant. A tech used an iPhone digital tape "
            "(flashlight + self-leveling gauge). Origin is the header / marked end. "
            "Stations are feet from that origin. Compare measured stations to the "
            "shop-drawing / digital-twin design table.\n"
            "Use ONLY the numbers given. Do not invent measurements.\n"
            "Return JSON with keys: summary (2-4 sentences for the QC tech), "
            "rescan_labels (array of strings naming stations to reshoot), "
            "notes (short flags).\n\n"
            f"{json.dumps(compact)}"
        )
        model = os.environ.get("TAPE_REVIEW_MODEL") or os.environ.get("BEAMSPEC_VISION_MODEL") or "gpt-4o-mini"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        with httpx.Client(timeout=25.0) as client:
            res = client.post(
                os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            res.raise_for_status()
            raw = res.json()["choices"][0]["message"]["content"]
        raw = (raw or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
        data = json.loads(raw)
        summary = str(data.get("summary") or "").strip() or base["summary"]
        labels = data.get("rescan_labels")
        if not isinstance(labels, list) or not labels:
            labels = base["rescan_labels"]
        labels = [str(x)[:120] for x in labels][:20]
        notes = data.get("notes")
        if not isinstance(notes, list) or not notes:
            notes = base["notes"]
        notes = [str(x)[:240] for x in notes][:12]
        logger.info("tape ai review source=llm flags=%s", len(base["rescan_labels"]))
        return {
            "summary": summary[:2000],
            "rescan_labels": labels,
            "notes": notes,
            "source": "llm",
        }
    except Exception:
        logger.exception("tape ai review failed; using heuristic")
        return base
