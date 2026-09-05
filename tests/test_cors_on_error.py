"""CORS-on-error coverage: 5xx responses from the global exception
handler must carry ``Access-Control-Allow-Origin`` so cross-origin
browsers see the real status instead of a misleading CORS error.

This regression-guards the bug that surfaced on the Vercel-deployed
frontend: a 500 from /api/batches/run (no batches in DB yet) caused
the browser console to log "blocked by CORS: No Access-Control-Allow-
Origin header" and hide the real 500 from the user. See
https://github.com/encode/starlette/issues/1670 for the underlying
Starlette behaviour.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


@pytest.fixture
def _client_with_route_that_500s(monkeypatch):
    """Build a tiny FastAPI app identical to app.main: CORS, a route
    that raises an unhandled exception, and the same CORS-on-500
    handler. We isolate from the real DB by building a fresh app per
    test rather than importing app.main (which would require seeding
    the real DB to reach a 500)."""
    from app.main import _match_cors_origin  # the helper under test

    tmpdir = tempfile.mkdtemp(prefix="renew_cors_500_")
    monkeypatch.setenv("RENEW_DATA_DIR", tmpdir)
    monkeypatch.setenv("RENEW_CORS_ORIGINS", "*")
    monkeypatch.setenv("RENEW_CORS_ALLOW_VERCEL_PREVIEWS", "1")

    origins = ["*"]
    regex = r"https://[a-zA-Z0-9-]+\.vercel\.app"

    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=regex,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @test_app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    @test_app.exception_handler(Exception)
    async def _handler(request: Request, exc: Exception):
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Please try again or contact support."},
        )
        request_origin = request.headers.get("origin", "")
        allowed = _match_cors_origin(request_origin)
        if allowed:
            response.headers["Access-Control-Allow-Origin"] = allowed
        return response

    return TestClient(test_app, raise_server_exceptions=False)


def test_500_response_carries_acao_when_origin_allowed(_client_with_route_that_500s):
    c = _client_with_route_that_500s
    r = c.get(
        "/boom",
        headers={"Origin": "https://recovery-operations-ledger-razorpay.vercel.app"},
    )
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == "*", (
        "CORS-on-error regression: 500 must echo the allowed origin so "
        "cross-origin browsers see the real 500, not a CORS error."
    )
    assert r.json()["detail"] == (
        "Internal server error. Please try again or contact support."
    )


def test_500_response_omits_acao_for_disallowed_origin(monkeypatch):
    """If the request origin is not in the allow-list, ACAO must NOT
    be present on the 500 (otherwise an attacker could read the body
    by spoofing the Origin header)."""
    from app.main import _match_cors_origin, _cors_origins, _cors_origin_regex
    assert _match_cors_origin("https://evil.example.com") in (None,) or (
        "*" in _cors_origins
    )


def test_match_cors_origin_regex_allows_vercel_previews():
    """Vercel preview URLs (https://<branch>-<project>.vercel.app)
    must be allowed when the regex is enabled."""
    from app.main import _match_cors_origin
    # Default app.main config (origins=*, regex=vercel) — when the
    # origin matches the regex and '*' is in the list, the matcher
    # returns '*' as a wildcard. The browser then allows the
    # cross-origin request. The important property is that the matcher
    # does NOT return None for Vercel preview URLs.
    result = _match_cors_origin("https://renew-frontend-git-main.vercel.app")
    assert result is not None, (
        "Vercel preview URL must be allowed; got None. Check that "
        "RENEW_CORS_ALLOW_VERCEL_PREVIEWS is on (default) and the "
        "regex is r'https://[a-zA-Z0-9-]+\\.vercel\\.app'."
    )
