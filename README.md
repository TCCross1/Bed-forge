# BedForge QC

Paperless prestress plant QC: mill tags, tension twin, fresh concrete at the truck, batch plant tickets, cylinders, beam QR, owner packages.

## Local run

Workspace path has a space: `/Users/anthonycross/Desktop/Bed Forge`

Backend (venv):

```bash
cd backend
source venv/bin/activate
uvicorn server:app --reload --port 8000
```

Frontend:

```bash
cd frontend
# CRA reads REACT_APP_BACKEND_URL at build/start time
REACT_APP_BACKEND_URL=http://localhost:8000 npm start
```

## Environment (set these on Emergent)

Copy `.env.example` to `backend/.env`. **Never commit real secrets.**

| Variable | Required | Notes |
|---|---|---|
| `MONGO_URL` | yes | Mongo connection string |
| `DB_NAME` | yes | Database name |
| `JWT_SECRET` | yes | ≥32 random characters |
| `FILE_ENCRYPTION_KEY` | yes | Separate key for drawings / mill photos at rest |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | first boot | Seeds the plant manager if that email does not exist. Never overwrites an existing password. |
| `CORS_ORIGINS` | production | Comma-separated **explicit** origins. `*` is refused in production. |
| `PUBLIC_APP_URL` | QR links | Public frontend origin, e.g. `https://your-app.emergent.sh` |
| `BEDFORGE_ENV` | production | Set to `production` |
| `BEDFORGE_DEMO_USERS` | production | Set to `0` so demo logins and seed demo accounts stay off |
| `BEDFORGE_ALLOW_REGISTER` | production | Keep `0` |
| `REACT_APP_BACKEND_URL` | frontend build | API origin. **Leave empty** if FastAPI serves `frontend/build` (same origin `/api`). Set only when the UI is on a different host. |
| `OPENAI_API_KEY` | optional | Forge Coach / mill-tag OCR polish. App works without it. |

## Emergent deploy

1. Set the table above on the **backend**. `BEDFORGE_ENV=production`, `BEDFORGE_DEMO_USERS=0`, explicit `CORS_ORIGINS` (the public app URL).
2. Build the UI **with** the API origin if the frontend is a separate host: `REACT_APP_BACKEND_URL=https://your-api.example npm run build` in `frontend`.
3. If Emergent is a single service: build the frontend, then start uvicorn. FastAPI serves `frontend/build` when that folder exists. Start command: `cd backend && python -m uvicorn server:app --host 0.0.0.0 --port $PORT` (see `Procfile`).
4. Demo role buttons only appear when `BEDFORGE_DEMO_USERS=1` **and** the app is not production. Passwords are seeded on the server, never bundled in the UI.

## Roles

- **QC Tech** — Fresh Test, QIR, sheets. Read-only on confirmed batches.
- **Production** — mixer drafts, tension, planner. Cannot confirm a batch.
- **QC Supervisor** — lock specs, review. Cannot confirm a batch.
- **Plant Manager / Executive (`admin`, `executive`)** — confirm batches, overrides, users, packages.

Confirmed batch tickets are immutable. Amendments create a new revision with a written reason.

## Field vs desk

- iPhone field: bottom nav — Board, Rolls, **Fresh**, Twin, Tension, More (Batch Plant is first tools after Fresh).
- iPad/Mac desk: sidebar includes Fresh Test and Batch Plant.

## Verify

```bash
cd backend && ./venv/bin/pytest tests/ --ignore=tests/backend_test.py
cd frontend && npm run build
```
