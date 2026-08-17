"""Forge Coach — grounded prestress answers. Optional OpenAI; always a local fallback."""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SYSTEM_RULES = (
    "You are Forge Coach, a senior prestressed-concrete QC / production supervisor at a precast plant. "
    "Speak short, floor-ready English. Use plant examples. Never sound like a generic chatbot. "
    "Use ONLY the grounded notes. If they do not cover the question, say so and point the tech to the in-app tutorial. "
    "You cannot issue overrides, unlock beds, force QC passed, change users, or reveal secrets or other people's data. "
    "If asked to bypass the strand-roll gate, say: plant manager, Command → Overrides, bed number, written reason, audit log. "
    "Do not invent heat numbers, elongation values, or drawing stations."
)

OVERRIDE_ANSWER = (
    "I cannot issue an override, unlock a bed, or force QC. A plant manager does that in Command → Overrides: "
    "bed number (or beam mark), a written reason, and it is written to the audit log. "
    "If the mill tag is readable, log the roll instead — that is the real fix."
)


def is_override_ask(question: str) -> bool:
    q = (question or "").lower()
    needles = ("override", "unlock the bed", "unlock the gate", "unlock the spec", "bypass", "force pass", "turn off the gate")
    return any(n in q for n in needles)


def compose_local(grounded: List[dict], question: str) -> str:
    if is_override_ask(question):
        return OVERRIDE_ANSWER
    parts = []
    for row in grounded or []:
        title = (row or {}).get("title") or ""
        body = (row or {}).get("body") or ""
        if body:
            parts.append(f"{title}: {body}".strip() if title else body)
    if parts:
        return "\n\n".join(parts[:3])
    return (
        "Ask me about mill tags, tension, inspection, camber, finish, QR, or what to do when it goes wrong. "
        "Open Tutorial on this phone — it works with no signal."
    )


def _llm_answer(question: str, grounded: List[dict], route: str, role: str) -> Optional[str]:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return None
    notes = []
    for row in (grounded or [])[:6]:
        title = (row or {}).get("title") or ""
        body = str((row or {}).get("body") or "")[:1200]
        if body:
            notes.append(f"- {title}: {body}" if title else f"- {body}")
    grounded_text = "\n".join(notes) or "(no grounded notes)"
    payload = {
        "model": os.environ.get("COACH_MODEL") or os.environ.get("STRAND_ROLL_VISION_MODEL") or "gpt-4o-mini",
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_RULES + "\n\nGROUNDED NOTES:\n" + grounded_text},
            {
                "role": "user",
                "content": f"Role: {role or 'qc_tech'}\nScreen: {route or '/'}\nQuestion: {question}",
            },
        ],
    }
    try:
        import httpx

        with httpx.Client(timeout=25.0) as client:
            res = client.post(
                os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            res.raise_for_status()
            text = (res.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
        text = text.strip()
        return text or None
    except Exception:
        logger.exception("coach llm failed")
        return None


def answer_coach(question: str, *, grounded: Optional[List[dict]] = None, route: str = "/", role: str = "qc_tech") -> Dict[str, Any]:
    rows = list(grounded or [])
    if is_override_ask(question):
        return {"answer": OVERRIDE_ANSWER, "source": "local", "tutorial": "supervisors"}
    llm = _llm_answer(question, rows, route, role)
    if llm:
        tutorial = (rows[0] or {}).get("tutorial") if rows else None
        return {"answer": llm, "source": "llm", "tutorial": tutorial}
    return {
        "answer": compose_local(rows, question),
        "source": "local",
        "tutorial": (rows[0] or {}).get("tutorial") if rows else "what",
    }
