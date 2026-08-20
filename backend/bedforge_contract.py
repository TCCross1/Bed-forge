"""BedForge product expectation matrix — single source of truth for Ask Expert.

This is the contract the plant must meet. It is not marketing copy. Ask Expert
loads CONTRACT_TEXT on every request and scores live plant APIs against it.
"""
from __future__ import annotations

from typing import Any, Dict, List

CONTRACT_VERSION = "2026-08-20"

ROUTES = {
    "job_specs": "/job-specs",
    "blueprints": "/blueprints",
    "open_job": "/jobs",
    "dashboard": "/",
    "batch": "/batch",
    "command_tv": "/command-tv",
    "ncr": "/ncr",
    "tension": "/tension",
    "inspection": "/inspection",
    "camber": "/camber",
    "finish": "/finish",
    "release": "/release",
}

APIS = {
    "auth_me": "GET /api/auth/me",
    "jobs": "GET /api/jobs",
    "jobs_open": "GET /api/jobs/open",
    "jobs_open_put": "PUT /api/jobs/open",
    "blueprints": "GET /api/blueprints",
    "blueprint_assessment": "GET /api/blueprints/{document_id}/extraction-report.pdf",
    "beam_specs": "GET /api/beam-specs",
    "beam_spec_twin": "GET /api/beam-specs/{spec_id}/twin",
    "batches": "GET /api/batches",
    "batch_recommend": "POST /api/batch-intelligence/recommend",
    "command_board": "GET /api/command-board",
}

# Shop-drawing expectations used when a named mark has no live Spec row.
# Never treat this as live Pass. Counts come from locked L25390 extraction, not invention.
REFERENCE_MARKS = {
    ("L25390", "205"): {
        "inserts": 1,
        "insert_type": "F-64",
        "station": "unconfirmed",
        "note": "Type 2 length family. Panel Inserts must equal visible mesh or an UNCONFIRMED placeholder — never silent omit.",
    },
}

SECTIONS: List[Dict[str, Any]] = [
    {
        "id": "A",
        "title": "Blueprint Intelligence",
        "must": [
            "Upload shop PDF → extract → review → lock on /blueprints.",
            "No invented values. Unconfirmed stays unconfirmed.",
            "Assessment PDF download for the verification loop (GET /api/blueprints/{id}/extraction-report.pdf).",
            "Multi-mark jobs (e.g. L25390 201–209) with length families.",
        ],
    },
    {
        "id": "B",
        "title": "Spec DNA",
        "must": [
            "Locked extraction is the DNA of each beam Spec.",
            "Job + mark identity, geometry, strand, hardware, finishes.",
            "Spec drives the twin. Twin must not hardcode demo geometry when Spec exists.",
        ],
    },
    {
        "id": "C",
        "title": "JOB SPECS / DRAWINGS (Digital Twin)",
        "must": [
            "Open job context at /job-specs. Plant Manager edits with auth; others read-only / verify.",
            "Pre-Pour: cage, strands, hold-downs, hardware — no concrete fill.",
            "Post-Pour: concrete + tip pattern + end treatment only when Spec has it.",
            "Layers: dimensions, stations, hardware, strands, stirrups/rebar, anomalies.",
            "Panel embed counts MUST match visible mesh (or an explicit UNCONFIRMED placeholder) — never silent omit.",
            "Engineered strand paths; tip pattern; OAL label; raise/lower framing.",
            "Responsive / not cluttered.",
        ],
    },
    {
        "id": "D",
        "title": "Open Job / Job Cabinet",
        "must": [
            "Plant Admin can open a job from the dashboard without a generic failure.",
            "Open job scopes Tags, Tension/Strands, photos, QC work to that job.",
            "Master file cabinet for jobs + blueprints + specs + reports (GET/PUT /api/jobs/open).",
        ],
    },
    {
        "id": "E",
        "title": "Roles & menus",
        "must": [
            "Plant Admin / QC Supervisor / QC Tech / Production see only tools for their work.",
            "QC tech: verify build + tests vs Spec — not global plant planning tools.",
            "Passcode/proof path for supervisor edits when required.",
        ],
    },
    {
        "id": "F",
        "title": "QC production",
        "must": [
            "QIR, tension (strand end twin + elongation), camber, finish, pre-delivery.",
            "Cylinder/crush with photo timestamp when implemented; link to beam/pour.",
            "NCR workflow linked to beam/pour/batch.",
        ],
    },
    {
        "id": "G",
        "title": "Batch Plant",
        "must": [
            "Extend existing Batch Plant only (/batch). No parallel mix product.",
            "Live weather for current conditions.",
            "Suggestion-first mix card; “Why this mix?” shows history on demand.",
            "Full lab suite feeds recommendations; multi-year append-only vault.",
            "Never invent admixture doses when lab history is thin.",
        ],
    },
    {
        "id": "H",
        "title": "Command Board",
        "must": [
            "TV kiosk: beds, status, analytics, ticker, env; read-only plant wall.",
            "GET /api/command-board. Weather must not block the kiosk payload.",
        ],
    },
    {
        "id": "I",
        "title": "Security / licensing / exports",
        "must": [
            "Role auth on every plant API.",
            "License gates for digital twin, batch, command board, packages.",
            "State package PDFs; PRESTRESS header / BedForge footer rules as already specified.",
            "Ask Expert cannot issue overrides, unlock beds, or force QC.",
        ],
    },
]


def _section_markdown(section: Dict[str, Any]) -> str:
    lines = [f"{section['id']}) {section['title']}"]
    for item in section.get("must") or []:
        lines.append(f"- {item}")
    return "\n".join(lines)


CONTRACT_TEXT = (
    f"BEDFORGE PRODUCT CONTRACT v{CONTRACT_VERSION}\n"
    "Ask Expert is the Product Auditor + Operator Guide for this contract.\n"
    "Never invent Spec numbers, mix doses, or claim a required feature works if it is missing.\n"
    "Prefer concrete routes: /job-specs, /blueprints, GET/PUT /api/jobs/open, GET /api/beam-specs/{id}/twin.\n\n"
    + "\n\n".join(_section_markdown(section) for section in SECTIONS)
)


def contract_prompt_block() -> str:
    return CONTRACT_TEXT


def section_titles() -> Dict[str, str]:
    return {item["id"]: item["title"] for item in SECTIONS}
