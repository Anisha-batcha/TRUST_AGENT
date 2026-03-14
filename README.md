# TrustAgent

TrustAgent is an explainable digital trust scoring system (FastAPI backend + React frontend). It takes a target URL/handle + category and returns a trust score, risk level, red flags, evidence, confidence, and XAI breakdown.

## Quick Start (Recommended)

1) Create `.env`

- Copy `.env.example` → `.env`
- (Optional) set `GROQ_API_KEY` and `SERPER_API_KEY`

2) Start backend (FastAPI)

```powershell
.\run_backend.ps1
```

Open:
- `http://127.0.0.1:8001/` (health)
- `http://127.0.0.1:8001/docs` (Swagger)

3) Start frontend (React/Vite)

```powershell
.\run_frontend.ps1
```

Open:
- `http://127.0.0.1:5173/`

### Default demo login

- Username: `admin`
- Password: `admin123`

## Scraping modes

Configure in `.env`:

- `TRUSTAGENT_SCRAPE_MODE=auto` (default): Selenium when possible, otherwise HTTP fallback.
- `TRUSTAGENT_SCRAPE_MODE=selenium`: Try Selenium first.
- `TRUSTAGENT_SCRAPE_STRICT=1`: “Real scraping only” — if Selenium is blocked/login/captcha, the request fails (no fallback).

Selenium dependency install:

- Manual:
  - `python -m pip install --upgrade --target .deps-scrape -r requirements-scrape.txt`
- Auto-install once:
  - set `TRUSTAGENT_SELENIUM_INSTALL=1` and restart backend.

## Optional: Streamlit dashboard

```powershell
.\run_dashboard.ps1
```

## Dependency files

- Backend: `requirements.txt` (installs into `.deps-backend-v2`)
- Groq (optional): `requirements-ai.txt` (installs into `.deps-ai`)
- Selenium (optional): `requirements-scrape.txt` (installs into `.deps-scrape`)
- Streamlit UI: `requirements-ui.txt`
- Extras: `requirements-optional.txt`

