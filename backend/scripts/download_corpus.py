#!/usr/bin/env python3
"""Download public DOT prestressed-beam standard drawings into training-data/.

Sources are state DOT / government publications. Never log file bytes.
"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "training-data"
I_BEAMS = DATA / "i-beams"
BOX = DATA / "box-beams"
GUIDES = DATA / "guides"
UA = "BedForgeQC/1.0 (training corpus; public DOT standards)"

DOWNLOADS = [
    # NYSDOT I-beam / NEBT metric set
    {
        "url": "https://www.dot.ny.gov/main/business-center/engineering/cadd-info/bridge-details-sheets-repostitory/bdos_r1.zip",
        "dest": I_BEAMS / "nysdot" / "bdos_r1.zip",
        "kind": "i_beam",
        "agency": "NYSDOT",
    },
    # NYSDOT USC PC beams + slab/box complete set
    {
        "url": "https://www.dot.ny.gov/main/business-center/engineering/cadd-info/bridge-details-sheets-repostitory-usc/BD-PC_SET_USC-03-22.pdf",
        "dest": I_BEAMS / "nysdot" / "BD-PC_SET_USC-03-22.pdf",
        "kind": "mixed",
        "agency": "NYSDOT",
    },
    {
        "url": "https://www.dot.ny.gov/main/business-center/engineering/cadd-info/bridge-details-sheets-repostitory-usc/BD-PC_SET.zip",
        "dest": I_BEAMS / "nysdot" / "BD-PC_SET.zip",
        "kind": "mixed",
        "agency": "NYSDOT",
    },
    {
        "url": "https://www.dot.ny.gov/main/business-center/engineering/cadd-info/bridge-details-sheets-repostitory-usc/BD-PC_01-26.pdf",
        "dest": BOX / "nysdot" / "BD-PC_01-26.pdf",
        "kind": "box_beam",
        "agency": "NYSDOT",
    },
    # TDOT
    {
        "url": "https://www.tn.gov/content/dam/tn/tdot/structures/SDG-5-Precast_Prestressed_Beams-V12082023.pdf",
        "dest": GUIDES / "tdot" / "SDG-5-Precast_Prestressed_Beams-V12082023.pdf",
        "kind": "i_beam",
        "agency": "TDOT",
    },
    # SCDOT instructional memos + FIB
    {
        "url": "https://www.scdot.org/content/dam/scdot-legacy/business/structuraldrawings/aashto-bms/IM704_AASHTO_BM.pdf",
        "dest": GUIDES / "scdot" / "IM704_AASHTO_BM.pdf",
        "kind": "i_beam",
        "agency": "SCDOT",
    },
    {
        "url": "https://www.scdot.org/content/dam/scdot-legacy/business/structuraldrawings/abb/IM704-ABB.pdf",
        "dest": GUIDES / "scdot" / "IM704-ABB.pdf",
        "kind": "box_beam",
        "agency": "SCDOT",
    },
    {
        "url": "https://www.scdot.org/content/dam/scdot-legacy/business/structuraldrawings/fibs/IM704_FIBs.pdf",
        "dest": GUIDES / "scdot" / "IM704_FIBs.pdf",
        "kind": "i_beam",
        "agency": "SCDOT",
    },
    {
        "url": "https://www.scdot.org/content/dam/scdot-legacy/business/structuraldrawings/aashto-bms/704-AASHTO-BM.pdf",
        "dest": I_BEAMS / "scdot" / "704-AASHTO-BM.pdf",
        "kind": "i_beam",
        "agency": "SCDOT",
    },
    {
        "url": "https://www.scdot.org/content/dam/scdot-legacy/business/structuraldrawings/abb/704-ABB-GD.pdf",
        "dest": BOX / "scdot" / "704-ABB-GD.pdf",
        "kind": "box_beam",
        "agency": "SCDOT",
    },
    {
        "url": "https://www.scdot.org/content/dam/scdot-legacy/business/structuraldrawings/abb/704-ABB-TYPSEC.pdf",
        "dest": BOX / "scdot" / "704-ABB-TYPSEC.pdf",
        "kind": "box_beam",
        "agency": "SCDOT",
    },
    {
        "url": "https://www.scdot.org/content/dam/scdot-legacy/business/structuraldrawings/fibs/704-FIB.pdf",
        "dest": I_BEAMS / "scdot" / "704-FIB.pdf",
        "kind": "i_beam",
        "agency": "SCDOT",
    },
    # Oregon compiled girder + box sets
    {
        "url": "https://www.oregon.gov/odot/engineering/202307/br300s_all.pdf",
        "dest": I_BEAMS / "odot" / "br300s_all.pdf",
        "kind": "i_beam",
        "agency": "ODOT",
    },
    {
        "url": "https://www.oregon.gov/odot/engineering/202307/br400s_all.pdf",
        "dest": BOX / "odot" / "br400s_all.pdf",
        "kind": "box_beam",
        "agency": "ODOT",
    },
    {
        "url": "https://www.oregon.gov/odot/Engineering/202207/br300s_all.pdf",
        "dest": I_BEAMS / "odot" / "br300s_all-202207.pdf",
        "kind": "i_beam",
        "agency": "ODOT",
    },
    # NCDOT girder + box + design data
    {
        "url": "https://connect.ncdot.gov/resources/Structures/Structure%20Specs/pcg1_24.pdf",
        "dest": I_BEAMS / "ncdot" / "pcg1_24.pdf",
        "kind": "i_beam",
        "agency": "NCDOT",
    },
    {
        "url": "https://connect.ncdot.gov/resources/Structures/Structure%20Specs/pcg2_24.pdf",
        "dest": I_BEAMS / "ncdot" / "pcg2_24.pdf",
        "kind": "i_beam",
        "agency": "NCDOT",
    },
    {
        "url": "https://connect.ncdot.gov/resources/Structures/Structure%20Specs/pcg3_24.pdf",
        "dest": I_BEAMS / "ncdot" / "pcg3_24.pdf",
        "kind": "i_beam",
        "agency": "NCDOT",
    },
    {
        "url": "https://connect.ncdot.gov/resources/Structures/Structure%20Specs/pcg10_24.pdf",
        "dest": I_BEAMS / "ncdot" / "pcg10_24.pdf",
        "kind": "i_beam",
        "agency": "NCDOT",
    },
    {
        "url": "https://connect.ncdot.gov/resources/Structures/Structure%20Design%20Manual/FIG066%20Dimensions,%20Area,%20and%20Design%20Data%20for%20Prestressed%20Concrete%20Girders%20AASHTO%20Types%20II%20through%20IV.pdf",
        "dest": GUIDES / "ncdot" / "FIG066-AASHTO-II-IV.pdf",
        "kind": "i_beam",
        "agency": "NCDOT",
    },
    {
        "url": "https://connect.ncdot.gov/resources/Structures/Structure%20Specs/pcbb1_24.pdf",
        "dest": BOX / "ncdot" / "pcbb1_24.pdf",
        "kind": "box_beam",
        "agency": "NCDOT",
    },
    {
        "url": "https://connect.ncdot.gov/resources/Structures/Structure%20Specs/pcbb2_24.pdf",
        "dest": BOX / "ncdot" / "pcbb2_24.pdf",
        "kind": "box_beam",
        "agency": "NCDOT",
    },
    {
        "url": "https://connect.ncdot.gov/resources/Structures/Structure%20Specs/pcbb4_24.pdf",
        "dest": BOX / "ncdot" / "pcbb4_24.pdf",
        "kind": "box_beam",
        "agency": "NCDOT",
    },
    {
        "url": "https://connect.ncdot.gov/resources/Structures/Structure%20Specs/pcbb6_24.pdf",
        "dest": BOX / "ncdot" / "pcbb6_24.pdf",
        "kind": "box_beam",
        "agency": "NCDOT",
    },
    {
        "url": "https://connect.ncdot.gov/resources/Structures/Stucture%20Spec%20Memos/Box%20Beam%20Guidelines%20and%20Standards.pdf",
        "dest": GUIDES / "ncdot" / "Box-Beam-Guidelines-and-Standards.pdf",
        "kind": "box_beam",
        "agency": "NCDOT",
    },
    # TxDOT adjacent / spread boxes (representative)
    {
        "url": "https://ftp.txdot.gov/pub/txdot-info/cmd/cserve/standard/bridge/BB-B28-12.pdf",
        "dest": BOX / "txdot" / "BB-B28-12.pdf",
        "kind": "box_beam",
        "agency": "TxDOT",
    },
    {
        "url": "https://ftp.txdot.gov/pub/txdot-info/cmd/cserve/standard/bridge/BB-B34-12.pdf",
        "dest": BOX / "txdot" / "BB-B34-12.pdf",
        "kind": "box_beam",
        "agency": "TxDOT",
    },
    {
        "url": "https://ftp.txdot.gov/pub/txdot-info/cmd/cserve/standard/bridge/BB-ABB28-06.pdf",
        "dest": BOX / "txdot" / "BB-ABB28-06.pdf",
        "kind": "box_beam",
        "agency": "TxDOT",
    },
    {
        "url": "https://ftp.txdot.gov/pub/txdot-info/cmd/cserve/standard/bridge/BB-table-24.pdf",
        "dest": GUIDES / "txdot" / "BB-table-24.pdf",
        "kind": "box_beam",
        "agency": "TxDOT",
    },
    # VDOT adjacent-member standards index / manual
    {
        "url": "https://www.vdot.virginia.gov/media/vdotvirginiagov/doing-business/technical-guidance-and-support/technical-guidance-documents/structure-and-bridge/manuals-of-structure-and-bridge-acc/part5/Part5.pdf",
        "dest": GUIDES / "vdot" / "Part5-Prestressed-Adjacent-Member-Standards.pdf",
        "kind": "box_beam",
        "agency": "VDOT",
    },
]


def _ctx():
    ctx = ssl.create_default_context()
    return ctx


def fetch(url: str, dest: Path) -> tuple[bool, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1024:
        return True, "exists"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=90, context=_ctx()) as resp:
            data = resp.read()
            ctype = (resp.headers.get("Content-Type") or "").lower()
        if len(data) < 800:
            return False, f"too small ({len(data)} bytes)"
        if dest.suffix.lower() == ".pdf" and not data.startswith(b"%PDF") and "pdf" not in ctype:
            return False, f"not a pdf ({ctype[:60]})"
        dest.write_bytes(data)
        return True, f"{len(data)} bytes"
    except Exception as exc:
        return False, str(exc)


def unzip_if_needed(path: Path) -> None:
    if path.suffix.lower() != ".zip" or not path.exists():
        return
    out = path.with_suffix("")
    out.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(path) as zf:
            zf.extractall(out)
    except Exception as exc:
        print(f"  unzip failed {path.name}: {exc}")


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    I_BEAMS.mkdir(parents=True, exist_ok=True)
    BOX.mkdir(parents=True, exist_ok=True)
    GUIDES.mkdir(parents=True, exist_ok=True)
    (DATA / "extracted-json").mkdir(parents=True, exist_ok=True)

    results = []
    for item in DOWNLOADS:
        dest: Path = item["dest"]
        ok, msg = fetch(item["url"], dest)
        status = "ok" if ok else "fail"
        print(f"[{status}] {item['agency']} {dest.relative_to(DATA)} — {msg}")
        results.append({
            "agency": item["agency"],
            "kind": item["kind"],
            "url": item["url"],
            "path": str(dest.relative_to(ROOT)),
            "ok": ok,
            "detail": msg,
            "bytes": dest.stat().st_size if dest.exists() else 0,
        })
        if ok:
            unzip_if_needed(dest)

    manifest = DATA / "download-manifest.json"
    manifest.write_text(json.dumps({"files": results}, indent=2))
    ok_n = sum(1 for r in results if r["ok"])
    print(f"\nDownloaded {ok_n}/{len(results)} files. Manifest: {manifest}")
    return 0 if ok_n else 1


if __name__ == "__main__":
    sys.exit(main())
