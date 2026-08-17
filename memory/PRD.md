# BedForge QC — Product Requirements Document

## Original Problem Statement
Build BedForge QC — a production-grade, paperless quality-control and digital-twin platform for prestressed concrete beam manufacturing at Prestress Services Industries LLC. Replace all paper forms (QIR 2026.6.1, Tension Report, Crack Map, Finish Sheet, Camber/Strength, Pre-Delivery) with a digital system that generates interactive 3D digital twins of I-beams and box beams, tracks 8 beds and every beam in real time, enforces multi-state tolerances/inspection gates, auto-calculates strand elongation & tension (±5% validation), captures measurements/photos/anomalies on the 3D twin, produces digital versions of plant Excel forms, and works offline-first on rugged iPads.

## Stack Decision
Requested stack was Next.js 15 / Prisma / PostgreSQL / NextAuth. The Emergent environment runs a fixed **React + FastAPI + MongoDB** stack; user accepted building the same platform on it. 3D via react-three-fiber + drei; Excel via openpyxl; JWT email/password auth.

## User Personas
- **QC Tech** — records inspections, tension, anomalies on the floor (iPad).
- **QC Supervisor** — reviews, gates holds/failures, sees all users.
- **Production** — monitors bed/beam status and throughput.
- **Admin** — full access; owner account (tccrossmusic@gmail.com).

## Architecture
- Backend modular: `db.py`, `models.py`, `auth.py`, `tension.py`, `excel_export.py`, `seed.py`, `server.py`. All routes under `/api`. UUID string ids (field `id`). Datetimes ISO strings.
- Auth: JWT Bearer (7-day access token) stored in localStorage `bf_token`; idempotent admin + demo seeding; role gate helper.
- Frontend: React Router, AuthContext, tactical-industrial dark theme (Barlow/IBM Plex/JetBrains Mono), shadcn + sonner.

## Implemented (2026-06)
- JWT auth (login/register/me/users) with 4 roles + idempotent seed of admin & 3 demo users.
- Data models: Users, ProductTypes, Jobs, Pours, Beds, Beams, Inspections, TensionReports, CamberReadings, Anomalies/CrackMaps.
- Seed: 8 beds, 5 product types, 1 job/pour, 11 beams, anomalies, camber, tension reports.
- Multi-bed live dashboard (`/api/dashboard`) with 6 stat cards + 8 bed cards, 15s auto-refresh.
- Digital Twin 3D viewer (I-beam & box-beam geometry) with tap-to-place anomaly capture.
- Guided QIR inspection flow: 6 sections with PASS/FAIL/HOLD gates updating beam qc_state.
- Tension calculator: ΔL=(P·L)/(A·E) with ±5% tolerance verdict.
- Forms export to .xlsx: QIR, Tension, Camber/Strength, Crack Map.
- Verified: testing agent 100% backend (20/20) + 100% frontend flows.

## Backlog / Remaining
### P1
- True offline-first support (Service Worker + IndexedDB) for iPad field use.
- Photo upload for anomalies (object storage) instead of note-only.
- Exact QIR 2026.6.1 / Tension Report layout match from real templates.
- Finish Sheet & Pre-Delivery dedicated forms + PDF export.

### P2
- Upload shop drawings to auto-generate twin geometry & strand patterns.
- Role-based UI gating (hide edit actions for Production).
- Bed timeline / pour scheduling views and camber-vs-time sparklines.
- Explicit CORS origins + httpOnly cookie auth path (currently Bearer only).

## Next Tasks
1. Confirm GitHub push (routed via support) and continue in Cursor.
2. Add anomaly photo capture with object storage.
3. Offline-first (Service Worker + IndexedDB) sync layer.
