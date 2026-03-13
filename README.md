# TrustAgent

TrustAgent is an explainable digital trust scoring system (FastAPI backend + React frontend) that takes a target URL/handle + category and returns a trust score, risk level, red flags, evidence, and confidence.

## Quick Start (React)

### 1) Backend (FastAPI)

From repo root:

```powershell
python -m venv runvenv
.\runvenv\Scripts\python.exe -m pip install -r requirements.txt
.\runvenv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
```

Open health check:
- `http://127.0.0.1:8001/`

Optional (faster demo mode; avoids Selenium):
```powershell
$env:TRUSTAGENT_SCRAPE_MODE="http"
$env:TRUSTAGENT_SCRAPE_TIMEOUT_SEC="6"
.\runvenv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
```

Strict accuracy mode (no synthetic fallback scoring):
```powershell
$env:TRUSTAGENT_STRICT_DATA="1"
.\runvenv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
```

Tip: Real scraping can be slower than synthetic mode. The React UI sets a higher timeout for investigations to avoid client-side timeouts.

If you are on a corporate network (MITM proxy), HTTPS verification may fail in Python `requests`. This repo includes `truststore` to use the OS trust store automatically.

### 2) Frontend (React/Vite)

In a new terminal:

```powershell
cd frontend-react
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:
- `http://127.0.0.1:5173/`

## Default Demo Login

This project seeds a dev admin user in SQLite on first run:
- Username: `admin`
- Password: `admin123`

## Notes

- The React dev proxy defaults to backend `http://127.0.0.1:8001` (change via `VITE_BACKEND_URL` if needed).
- Data is persisted in `backend/data/trustagent.db` (ignored by git).
