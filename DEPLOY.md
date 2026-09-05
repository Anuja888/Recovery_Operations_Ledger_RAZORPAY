# Deploying RENEW

RENEW is a two-service app: a **FastAPI backend** (Python + scikit-learn + SQLite) and a **Vite React frontend**. The two are deployed independently and the frontend is pointed at the backend at build time.

```
┌───────────────────────┐         ┌───────────────────────┐
│  Vercel (frontend)    │  HTTPS  │  Render (backend)     │
│  Vite static build    │ ──────► │  FastAPI + uvicorn   │
│  VITE_API_BASE=…      │  /api/* │  SQLite + scikit-learn│
└───────────────────────┘         └───────────────────────┘
```

> Vercel does not support long-running Python processes with scikit-learn + SQLite in a way that fits a 250 MB serverless bundle. We deploy the frontend on Vercel and the backend on a Python host that supports persistent disks and a real process (Render / Railway / Fly / a plain VM).

---

## 1. Backend on Render (recommended)

1. Push this repo to GitHub.
2. Sign in to <https://render.com> with GitHub.
3. Click **New +** → **Blueprint** → select this repo. Render reads `render.yaml` and creates the `renew-api` web service with a 1 GB persistent disk mounted at `/data`.
4. After the first deploy finishes, copy the public URL (e.g. `https://renew-api.onrender.com`).
5. Open the service's **Environment** page and set:
   - `RENEW_CORS_ORIGINS` = `https://<your-vercel-app>.vercel.app` (your exact frontend origin, no trailing slash)
6. Smoke-test: `curl https://renew-api.onrender.com/health` → `{"status":"ok",…}`.
7. Trigger a seed: `curl -X POST https://renew-api.onrender.com/admin/seed?force=true` — this generates 2,000 synthetic cases, trains the scorer, and runs the failure-story batches. It takes ~20–30 s on Render's starter plan.

> The persistent disk keeps `renew.db`, `scorer.pkl`, and `failure_demo.json` across deploys. If you change the model code you must run `/admin/seed?force=true` again to retrain.

### Backend on Railway (alternative)

1. Sign in to <https://railway.app> with GitHub.
2. **New Project** → **Deploy from GitHub repo** → pick this repo.
3. Add a **Volume** mounted at `/data` (1 GB).
4. Set environment variables:
   - `RENEW_DATA_DIR=/data`
   - `RENEW_MODELS_DIR=/data/models`
   - `RENEW_CORS_ORIGINS=https://<your-vercel-app>.vercel.app`
5. The build runs `pip install -r requirements.txt` automatically (Nixpacks); the start command comes from `railway.json` (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`).
6. Visit the generated `*.up.railway.app` URL for `/health` to verify.

### Backend on Fly.io / a VM

`Dockerfile.backend` is production-ready. Mount a persistent volume at `/data` and set the same three env vars above.

---

## 2. Frontend on Vercel

1. Sign in to <https://vercel.com> with GitHub.
2. **Add New…** → **Project** → import this repo.
3. In **Environment Variables** add:
   - `VITE_API_BASE` = your Render backend origin (e.g. `https://renew-api.onrender.com`) — no trailing slash, no `/api` suffix; the client appends `/api/...` automatically.
4. Leave the other settings at defaults (framework: Vite; build command: `cd frontend && npm install && npm run build`; output: `frontend/dist`).
5. Deploy. The first build takes ~1 min.
6. Open the generated `*.vercel.app` URL — you should see the full RENEW UI, populated with the seeded data from step 1.

> After the first deploy, copy the exact Vercel origin and go back to step 1.5 / 1.4 to set `RENEW_CORS_ORIGINS` to that origin. Then redeploy the backend (Render auto-redeploys on env change).

---

## 3. Local development

```bash
# Backend
python -m venv .venv && . .venv/Scripts/activate   # or `source .venv/bin/activate`
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                                          # http://localhost:5173
```

`vite.config.ts` proxies `/api/*` from `http://localhost:5173` to `http://127.0.0.1:8010`, so the frontend uses **same-origin** URLs in dev. Leave `VITE_API_BASE` empty in `frontend/.env`.

To run the frontend against a deployed backend from your laptop, set `VITE_API_BASE=https://renew-api.onrender.com` in `frontend/.env` and `npm run dev`.

---

## 4. Environment variables reference

| Variable                    | Where          | Default                              | Purpose                                                   |
|-----------------------------|----------------|--------------------------------------|-----------------------------------------------------------|
| `VITE_API_BASE`             | Vercel / build | (empty)                              | Frontend → backend origin. Empty uses same-origin dev proxy. |
| `RENEW_DATA_DIR`            | Backend        | `<repo>/data`                        | Directory for `renew.db` and `failure_demo.json`.         |
| `RENEW_MODELS_DIR`          | Backend        | `<repo>/models`                      | Directory for `scorer.pkl`.                                |
| `RENEW_DATABASE_URL`        | Backend        | `sqlite:///$RENEW_DATA_DIR/renew.db` | SQLAlchemy URL. Override for Postgres if you want.        |
| `RENEW_CORS_ORIGINS`        | Backend        | `*`                                  | Comma-separated allowed origins. Set to your Vercel URL.  |
| `RENEW_LLM_PROVIDER`        | Backend        | `mock`                               | `mock` (offline, deterministic), or a real LLM provider.  |
| `ANTHROPIC_API_KEY`         | Backend        | (empty)                              | Required if `RENEW_LLM_PROVIDER=anthropic`.               |
| `OPENAI_API_KEY`            | Backend        | (empty)                              | Required if `RENEW_LLM_PROVIDER=openai`.                  |
| `RENEW_BATCH_BUDGET_CAP`    | Backend        | `5000`                               | Hard cap on per-batch outreach spend (₹).                 |
| `PORT`                      | Backend host   | `8000`                               | Provided automatically by Render / Railway.               |

---

## 5. Verifying a fresh deploy

```bash
# 1. Health
curl -fsS https://renew-api.onrender.com/health

# 2. Seed (only on first deploy or after a model change)
curl -X POST 'https://renew-api.onrender.com/admin/seed?force=true'

# 3. Confirm the failure story is populated
curl -fsS https://renew-api.onrender.com/api/failure-story | head -c 400

# 4. Run a batch from the deployed UI's "Run batch" tab — numbers appear
#    in the Ledger tab.
```

If `/api/failure-story` returns 404, the seed step was skipped or timed out; re-run the `POST /admin/seed?force=true` and check the Render logs.

---

## 6. CORS — the #1 cause of "net::ERR_FAILED" in the browser console

The browser blocks cross-origin `fetch` calls unless the backend's CORS headers explicitly allow the frontend's origin. The `app/main.py` middleware is configured to allow:

- any origin listed in the `RENEW_CORS_ORIGINS` env var (comma-separated, e.g. `https://recovery-operations-ledger-razorpay.vercel.app`).
- any `https://*.vercel.app` URL — this covers Vercel preview deployments (one URL per branch / PR). Disable with `RENEW_CORS_ALLOW_VERCEL_PREVIEWS=0` if you want a strict allow-list.
- `*` (the default) — open to anything, fine for a demo, set `RENEW_CORS_ORIGINS` to a real origin list for production.

After changing the env var, **restart the Render service** so the new CORS config is loaded.

## 7. Pre-demo checklist (operational risks, not code)

- **Cold start (free / starter Render plan).** If the Render service is on a plan that spins down after idle, the first request to the backend after a quiet period takes 30–50+ seconds to wake up. The frontend's fetch will appear to hang. **Mitigation:** open the Vercel URL yourself 1–2 minutes before any live demo or panel to warm the backend; the page will load normally thereafter.
- **Persistence.** The Render service has a 1 GB persistent disk mounted at `/data` (declared in `render.yaml`). `renew.db` and `scorer.pkl` survive restarts. If you delete the disk or move to a plan that doesn't allow disks, you'll need to re-seed via `POST /admin/seed?force=true` after every restart.
- **`VITE_API_BASE_URL` / `VITE_API_BASE` is set in the Vercel project environment, not in the source.** It's a build-time variable, so changing it in the Vercel dashboard only takes effect after a redeploy. The deployed JS bundle should contain the Render origin; if it doesn't, every API call returns a Vercel 404 instead of a backend response.
