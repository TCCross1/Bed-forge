"""Ask Expert (Forge Coach) — BedForge Product Auditor + Operator Guide.

Loads bedforge_contract on every request. Optional OpenAI; always a local
fallback. Audit questions score live read APIs as Fail / Warn / Pass.
Cannot issue overrides.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from bedforge_contract import CONTRACT_VERSION, contract_prompt_block
from coach_audit import compose_audit_answer, is_audit_ask

logger = logging.getLogger(__name__)

SYSTEM_RULES = (
    "You are BedForge Ask Expert — Product Auditor + Operator Guide. "
    "Always ground answers in the BedForge product contract and current software behavior. "
    "Speak short, floor-ready English. Never sound like a generic chatbot. "
    "When asked what needs to be fixed, return prioritized gaps: Fail / Warn / Pass by contract section, "
    "short evidence, then Suggested order of work. Structure: Summary → Failures → Warnings → Suggested order of work. "
    "Never invent Spec numbers, mix doses, heat numbers, elongation values, or drawing stations. "
    "Never claim a required feature works if the contract says it is required and implementation is missing. "
    "If a live API is down, report cannot verify — do not guess Pass. "
    "Prefer concrete routes: /job-specs, /blueprints, GET/PUT /api/jobs/open, GET /api/beam-specs/{id}/twin, /batch, GET /api/command-board. "
    "You cannot issue overrides, unlock beds, force QC passed, change users, or reveal secrets or other people's data. "
    "If asked to bypass the strand-roll gate, say: plant manager, Command → Overrides, bed number, written reason, audit log."
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
    if is_audit_ask(question):
        return compose_audit_answer(question, None)
    parts = []
    for row in grounded or []:
        title = (row or {}).get("title") or ""
        body = (row or {}).get("body") or ""
        if body:
            parts.append(f"{title}: {body}".strip() if title else body)
    if parts:
        return "\n\n".join(parts[:3])
    return (
        "Ask me about mill tags, tension, inspection, camber, finish, QR, Spec DNA, or what needs to be fixed. "
        "I score the plant against the BedForge contract. Open Tutorial on this phone — it works with no signal."
    )


def _llm_answer(question: str, grounded: List[dict], route: str, role: str, live_notes: str = "") -> Optional[str]:
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
    contract = contract_prompt_block()
    extra = f"\n\nLIVE AUDIT SNAPSHOT:\n{live_notes}" if live_notes else ""
    payload = {
        "model": os.environ.get("COACH_MODEL") or os.environ.get("STRAND_ROLL_VISION_MODEL") or "gpt-4o-mini",
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"{SYSTEM_RULES}\n\nCONTRACT v{CONTRACT_VERSION}:\n{contract}\n\n"
                    f"GROUNDED NOTES:\n{grounded_text}{extra}"
                ),
            },
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


def answer_coach(
    question: str,
    *,
    grounded: Optional[List[dict]] = None,
    route: str = "/",
    role: str = "qc_tech",
    live: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rows = list(grounded or [])
    if is_override_ask(question):
        return {"answer": OVERRIDE_ANSWER, "source": "local", "tutorial": "supervisors"}
    if is_audit_ask(question):
        answer = compose_audit_answer(question, live)
        logger.info(
            "ask expert audit live_ok=%s findings=%s q=%s",
            (live or {}).get("live_ok"),
            len((live or {}).get("findings") or []),
            (question or "")[:80],
        )
        return {"answer": answer, "source": "audit", "tutorial": None, "live_ok": bool((live or {}).get("live_ok"))}
    llm = _llm_answer(question, rows, route, role)
    if llm:
        tutorial = (rows[0] or {}).get("tutorial") if rows else None
        return {"answer": llm, "source": "llm", "tutorial": tutorial}
    return {
        "answer": compose_local(rows, question),
        "source": "local",
        "tutorial": (rows[0] or {}).get("tutorial") if rows else "what",
    }
