"""FastAPI application entrypoint for RENEW.

Step 1 of the build order: app skeleton + create_all DB setup + /health.
"""
from __future__ import annotations

import logging
import os
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import SessionLocal, init_db
from app.routes import router

logger = logging.getLogger("renew")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # No Alembic by design; schema is created from the models on startup.
    init_db()
    yield


app = FastAPI(
    title="RENEW",
    description=(
        "Failed subscription revenue recovery: diagnose -> score -> "
        "deterministic policy decision -> simulated intervention -> audit."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for the deployed Vercel frontend. The set of allowed origins is
# controlled by the RENEW_CORS_ORIGINS env var (comma-separated). Defaults
# to "*" so the demo works out of the box on any host; lock it down in
# production by setting the env var to the exact Vercel origin, e.g.
# "https://renew-frontend.vercel.app".
#
# Additionally, Vercel preview deployments get a fresh URL per branch/PR
# (https://<branch>-<project>.vercel.app), so we always also allow any
# `*.vercel.app` origin. Set RENEW_CORS_ALLOW_VERCEL_PREVIEWS=0 to
# disable the regex if you need a strict allow-list.
_default_origins = "*"
_cors_origins_env = os.environ.get("RENEW_CORS_ORIGINS", _default_origins)
_cors_origins: list[str] = (
    ["*"] if _cors_origins_env.strip() == "*"
    else [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
)
_allow_vercel_previews = os.environ.get("RENEW_CORS_ALLOW_VERCEL_PREVIEWS", "1") != "0"
_cors_origin_regex = r"https://[a-zA-Z0-9-]+\.vercel\.app" if _allow_vercel_previews else None
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
# Mirror all routes under `/api/*` for cross-origin deployments where the
# frontend lives on a different host (Vercel) and sends requests to
# `<backend>/api/<route>`. In local dev the Vite dev server strips the
# `/api` prefix before proxying, so both forms work everywhere.
app.include_router(router, prefix="/api")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Log full traceback server-side and return a clean JSON error body."""
    logger.error("Unhandled exception on %s\n%s", request.url.path, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again or contact support."},
    )


@app.get("/health")
def health() -> dict:
    """Liveness/readiness probe. Verifies the DB is reachable."""
    db_ok = True
    try:
        db = SessionLocal()
        from sqlalchemy import text

        db.execute(text("SELECT 1"))
        db.close()
    except Exception:  # pragma: no cover - health must never raise
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "service": "renew"}
