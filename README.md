# AirPower — SIH26249

A working local advisory prototype for integrated predictive maintenance and fleet availability review. Includes the React application, FastAPI API, SQLite migration, four-domain evidence intake, deterministic ranking/feasibility, one fail-closed DecisionGate, versioned review history, optional Gemini explanations, frozen fixtures, tests and prebuilt frontend.

## Start on Windows

1. Extract the ZIP into a writable folder. Install **Python 3.12** (with the Python launcher).
2. Double-click **start_windows.bat**. It creates a virtual environment, installs pinned requirements, creates `.env` if absent, migrates the database and starts one local server.
3. Open **http://127.0.0.1:8000**. First startup may need internet to install Python packages. Node is not needed to run the included built interface.
4. Open **Evidence intake**, import **Development v1**, then open a case and choose **Evaluate evidence**. Record a disposition and inspect **View trace**. Verification & setup runs the locked policy suite.

Linux/macOS: with Python 3.12 installed, run `bash start.sh` from the extracted folder. Manual commands below also work in a virtual environment.

```bash
python -m pip install -r requirements-lock.txt
# Copy .env.example to .env, then edit it.
python -m alembic upgrade head
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Run commands from this project directory. Do not use multiple workers, public binding, or expose this demo as enterprise authentication.

## Replace the Gemini key

Copy `.env.example` to `.env` if the launcher has not already done it. Edit:

```dotenv
GEMINI_API_KEY=YOUR_ACTUAL_KEY_HERE
GEMINI_MODEL=gemini-flash-latest
```

Restart the server. Evaluate a case, then choose **Request Gemini explanation**. This explicitly sends that case’s saved evidence to Google; it is the only cloud feature. The server sends the key in the `x-goog-api-key` header, never to the frontend. A blank key returns a clear 503 configuration error. Provider timeout, quota/authentication failures, blocked/empty results and malformed responses return safe errors. Model name can be replaced with an available Gemini model for your account. See [Google's API reference](https://ai.google.dev/api).

Gemini provides a narrative explanation only. It cannot change decisions, approve maintenance, generate accepted RUL, or write to aircraft/work-order systems. Without a key, the entire core workflow works locally. A live paid/provider call was **NOT_RUN** because no user key was supplied. Controlled response tests cover successful output and failure handling.

## API

Interactive API documentation: **http://127.0.0.1:8000/api/docs**. Committed OpenAPI 3.1: `docs/openapi.json`; generated TypeScript: `frontend/src/api-types.ts`.

All mutations require a unique **Idempotency-Key** header. Case mutations also require **If-Match** with the current integer case version (for example `2` or `"2"`). Same key + identical body/version replays the committed result; changed input returns 409. Refresh a stale case version before a new request. Error shape is `{"error":{"code":"...","message":"..."}}`.

| Method | /api/v1 path | Purpose |
|---|---|---|
| GET | /live, /ready | Release and readiness |
| GET | /session, /demo/metadata | Startup persona and version names |
| GET | /cases | URL filters, fixed server ordering, cursor, limit 1–50 |
| GET | /cases/{caseId} | Current version and persisted evaluation |
| GET | /cases/{caseId}/events | Events, version snapshots and replay checks |
| POST | /import-runs | `{ "fixture": "development-v1" }` or `{ "bundles": [...] }` |
| GET | /import-runs/{runId} | Intake report |
| POST | /cases/{caseId}/evaluations | `{}`; the authoritative DecisionGate |
| POST | /cases/{caseId}/dispositions | Allowed disposition and optional note |
| POST | /cases/{caseId}/explanations | Optional question; Gemini narrative |
| POST | /evaluation-runs | `{ "suite": "frozen-v1" }` |
| GET | /evaluation-runs/{runId} | Suite status and verified report ID |
| POST / GET | /rul-runs, /simulation-runs | Bounded stub launch / recent stub runs |
| GET | /rul-runs/{runId}, /simulation-runs/{runId} | Explicit blocked/PENDING/NOT_RUN result |
| GET | /artifacts/{artifactId} | Checksum-verified report download by logical ID |

No `/health`, `/imports` or `/evaluate` API aliases. Domain examples are in `fixtures/development-v1.json`. Upload a pack containing `bundles` through the UI or send the bundles array via API. JSON upload is capped at 2 MB, 300 cases, 12 records per case. Invalid source records are quarantined with lineage and never become valid evidence. Fixture evidence is visibly SYNTHETIC.

## Roles and persistence

Set `AIRPOWER_PRINCIPAL` and `AIRPOWER_ROLE` in `.env`; missing/invalid startup identity fails startup. Planner has all demo capabilities; analyst reads/explains; reviewer also evaluates/disposes; evaluator imports/evaluates/launches runs. There is no client role switch. Denials create audit records. Browser mutation origins must match the local application.

Data lives in `data/airpower.db` and `data/artifacts`. SQLite foreign keys are enabled. Evidence changes invalidate the current evaluation. Evaluations and dispositions append a case version and audit event in the same transaction as the idempotency response. Persistence failure rolls back without returning a gate result. A saved evaluation is historical at its decision_time; refresh and re-evaluate when source evidence becomes stale. Local hashes/history do not claim to be tamper-proof.

## Tests and development

```bash
python scripts/check.py
cd frontend
npm ci
npm test
npm run build
npx playwright install chromium
cd ..
python scripts/browser_check.py
```

`browser_check.py` starts an isolated temporary database/server, exercises every OpenAPI operation, then tests the production interface in Chromium. Port 8000 must be free. The launcher must be stopped before this check. `reports/` contains the actual results from this delivery, including the endpoint matrix and browser report. The Gemini adapter's success cases use controlled transport responses, not a claim of a live provider call.

40 development + 240 frozen holdout cases are committed with SHA-256 checksums. Holdout has 120 valid and 120 invalid (20 each: identity/epoch, stale/time, schema/version, unit/type, duplicate/conflict, infeasible constraint). These verify policy mechanics, not predictive accuracy or real-world gains. Stateful tests separately cover transaction rollback, concurrency, reimport invalidation, idempotency, RBAC, artifact faults and restore. No holdout training or tuning is performed.

For frontend development, run `npm run dev` from `frontend` while the API runs on port 8000. Vite proxies the API on the same origin. Regenerate contracts after API changes: `python scripts/export_openapi.py`, then `npm run types` in frontend. Commit the resulting schema/types and run the OpenAPI comparison test.

## Backup and restore

Stop the server first. The utility expects the default database basename `airpower.db`.

```bash
python scripts/backup.py backup data backups/snapshot-01
python scripts/backup.py restore backups/snapshot-01 restored-data
```

Backup uses SQLite's backup API, copies artifacts, and writes a checksum manifest. Restore verifies all checksums and refuses an existing target. Preserve the old data directory; move the verified restored directory into place while the server is stopped. Custom database URLs require adapting the directory/basename. Never delete your current database to work around a migration or startup error.

## Scope and decisions

See `docs/decision-register.md` and `docs/traceability.json`. The supplied brief is retained in `docs/source-requirements.md`. Gate B numeric RUL and Gate C simulation are intentionally blocked stubs, exactly as the brief requires; no operational prediction/availability improvement is asserted. Automated tests ran on Linux/Python 3.12 and Chromium. Windows launcher execution and real Gemini credentials remain unverified on this host.
