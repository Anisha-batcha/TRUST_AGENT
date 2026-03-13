# TrustAgent React Frontend

## Setup

1. Open terminal in `frontend-react`
2. Install dependencies:

```bash
npm install
```

3. Run dev server:

```bash
npm run dev
```

Frontend runs on `http://127.0.0.1:5173`.

Backend should run on `http://127.0.0.1:8001` (or set `VITE_BACKEND_URL` to point the dev proxy to another port).

## Notes

- Includes slow Framer Motion loader on app boot and during API operations.
- Uses the same FastAPI auth/investigation endpoints.
