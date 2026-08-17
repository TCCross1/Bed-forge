# BedForge training corpus

Public prestressed I-beam and box-beam standard drawings used to train and evaluate BeamSpec extraction.

## Layout

- `i-beams/` — AASHTO I / NEBT / FIB / bulb-tee standard PDFs (and NYSDOT CADD zip)
- `box-beams/` — adjacent and spread box-beam standards
- `guides/` — design memos and section-property sheets (SCDOT IM704, TDOT SDG-5, NCDOT FIG 6-66, VDOT Part 5)
- `extracted-json/` — gold-standard BeamSpec JSON, one file per catalog entry
- `download-manifest.json` — last download attempt

Rebuild gold JSON:

```
cd backend && PYTHONPATH=. python scripts/export_gold.py
```

Re-download public PDFs:

```
python backend/scripts/download_corpus.py
```

## Sources (public DOT)

| Agency | What | URL |
| --- | --- | --- |
| NYSDOT | BD-PC1E–PC39E USC (I-beam, NEBT, PCEF, NEXT, 3'/4' box) | https://www.dot.ny.gov/main/business-center/engineering/cadd-info/drawings/bridge-detail-sheets-usc/PC-Prestressed-Concrete-Beams-and-Slab-Units-USC |
| NYSDOT | BD-PS metric I-beam / NEBT | https://www.dot.ny.gov/main/business-center/engineering/cadd-info/drawings/bridge-detail-sheets/ps-prestressed-concrete |
| SCDOT | AASHTO I Types I Mod–IV, FIB, Adjacent Box (ABB) | https://www.scdot.org/business/structural-drawings-704.html |
| NCDOT | PCG1–3 Type II/III/IV, PCBB 3'-0" boxes, PCG10 diaphragms | https://connect.ncdot.gov/resources/Structures/Pages/Structure-Standards.aspx |
| ODOT | BR325–BR340 girders, BR425–BR445 boxes (`br300s_all.pdf`, `br400s_all.pdf`) | https://www.oregon.gov/odot/engineering/pages/drawings-bridge.aspx |
| TDOT | SDG-5 Precast Prestressed Beams | https://www.tn.gov/content/dam/tn/tdot/structures/SDG-5-Precast_Prestressed_Beams-V12082023.pdf |
| TxDOT | Box beam standards BB-B28, BB-B34, BB-ABB28 | https://ftp.txdot.gov/pub/txdot-info/cmd/cserve/standard/bridge/ |
| VDOT | Part 5 Prestressed Adjacent Member Standards | https://www.vdot.virginia.gov/media/vdotvirginiagov/doing-business/technical-guidance-and-support/technical-guidance-documents/structure-and-bridge/manuals-of-structure-and-bridge-acc/part5/Part5.pdf |

These are government standard drawings published for public use. They are **not** project shop drawings. A QC supervisor must still lock a BeamSpec against the job print.

## Extraction order

1. Larue County / L25390 fingerprint
2. Gold corpus fingerprint (drawing number, agency, type)
3. Vision model (if `OPENAI_API_KEY` / `EMERGENT_LLM_KEY` is set)
4. AASHTO section heuristic (Type I–IV, FIB, NEBT, box)
5. Type 2 fallback for supervisor review
