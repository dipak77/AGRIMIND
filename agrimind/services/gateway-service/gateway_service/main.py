"""Gateway — auth (JWT/OIDC claims), RBAC, rate limit, trace, proxy (Phase F)."""

from __future__ import annotations

import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from agrimind_kernel.config.settings import get_settings
from agrimind_kernel.security.auth import (
    Principal,
    Role,
    get_principal,
    issue_token,
    require_roles,
    tenant_headers,
)
from agrimind_kernel.security.oidc import (
    OIDCConfig,
    OIDCError,
    build_authorize_url,
    discover,
    exchange_code,
)
from agrimind_kernel.security.rate_limiter import InMemoryRateLimiter
from agrimind_kernel.telemetry.otel import instrument_fastapi, setup_otel

logger = structlog.get_logger()
settings = get_settings()
limiter = InMemoryRateLimiter(max_requests=settings.rate_limit_per_minute, window_seconds=60)


class TokenRequest(BaseModel):
    subject: str = Field(..., min_length=1)
    tenant_id: str = Field(default="default")
    roles: list[str] = Field(default_factory=lambda: ["farmer"])
    email: str | None = None
    expires_minutes: int = 60


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_minutes: int
    tenant_id: str
    roles: list[str]


class OIDCCodeExchangeRequest(BaseModel):
    """Authorization-code exchange (server-side confidential client or PKCE)."""

    code: str = Field(..., min_length=1)
    redirect_uri: str | None = None
    code_verifier: str | None = Field(
        default=None,
        description="Required for public/PKCE clients when OIDC_CLIENT_SECRET is unset",
    )
    state: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_otel(
        "gateway-service",
        otlp_endpoint=os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", settings.otel_exporter_otlp_endpoint
        ),
    )
    logger.info("gateway-service starting", assistant=settings.assistant_api_url)
    app.state.http = httpx.AsyncClient(timeout=60.0)
    yield
    await app.state.http.aclose()
    logger.info("gateway-service stopped")


app = FastAPI(title="AGRIMIND Gateway", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
instrument_fastapi(app, "gateway-service")


@app.middleware("http")
async def edge_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    client_key = request.client.host if request.client else "unknown"
    # tenant-aware rate key when present
    tenant = request.headers.get("X-Tenant-ID", "")
    rate_key = f"{tenant}:{client_key}" if tenant else client_key

    if not limiter.is_allowed(rate_key):
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded",
                "retry_after": limiter.retry_after(rate_key),
            },
            headers={
                "X-Request-ID": request_id,
                "Retry-After": str(int(limiter.retry_after(rate_key))),
            },
        )

    start = time.time()
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("X-Response-Time", f"{time.time() - start:.3f}s")
    logger.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        request_id=request_id,
    )
    return response


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "gateway-service", "version": "0.2.0"}


@app.get("/ready")
async def ready():
    return {"status": "ready", "upstream": settings.assistant_api_url}


@app.post("/v1/auth/token", response_model=TokenResponse)
async def auth_token(body: TokenRequest):
    """
    Local/dev token issuance (HS256 only).

    Production should use a real OIDC IdP:
    - ``GET /v1/auth/oidc/config`` + browser authorize / PKCE, or
    - ``POST /v1/auth/oidc/token`` code exchange when ``OIDC_CLIENT_SECRET`` is set.
    Disabled in production/prod unless ``ALLOW_LOCAL_TOKEN_ISSUE=true``.
    """
    # In production, disable local issuance unless explicitly allowed
    if os.getenv("ENV", "local").lower() in ("production", "prod"):
        if os.getenv("ALLOW_LOCAL_TOKEN_ISSUE", "").lower() not in ("1", "true", "yes"):
            raise HTTPException(status_code=403, detail="local token issue disabled")
    allowed = {r.value for r in Role}
    roles = [r for r in body.roles if r in allowed] or ["farmer"]
    token = issue_token(
        subject=body.subject,
        tenant_id=body.tenant_id,
        roles=roles,
        email=body.email,
        expires_minutes=body.expires_minutes,
    )
    return TokenResponse(
        access_token=token,
        expires_minutes=body.expires_minutes,
        tenant_id=body.tenant_id,
        roles=roles,
    )


@app.get("/v1/auth/oidc/config")
async def oidc_public_config() -> dict[str, Any]:
    """
    Public OIDC client config for SPAs (no secrets).

    Includes issuer, client_id, authorize/token endpoints, scopes, and whether PKCE
    is required. Returns 503 when OIDC is not configured.
    """
    cfg = OIDCConfig.from_env()
    if not cfg.is_configured():
        raise HTTPException(
            status_code=503,
            detail="OIDC not configured; set OIDC_ISSUER and/or OIDC_JWKS_URL",
        )
    discovery: dict[str, Any] = {}
    if cfg.issuer:
        try:
            discovery = discover(cfg.issuer)
        except OIDCError as exc:
            logger.warning("oidc_discovery_failed", error=str(exc))
            # Still return static config so clients can use JWKS-only setups
            discovery = {}
    pub = cfg.public_client_config(discovery)
    pub["configured"] = True
    return pub


@app.get("/v1/auth/oidc/login")
async def oidc_login(
    redirect_uri: str | None = Query(default=None),
    state: str | None = Query(default=None),
    code_challenge: str | None = Query(
        default=None,
        description="PKCE S256 challenge (required for public clients)",
    ),
):
    """Redirect browser to IdP authorization endpoint."""
    cfg = OIDCConfig.from_env()
    if not cfg.issuer or not cfg.client_id:
        raise HTTPException(
            status_code=503,
            detail="OIDC_ISSUER and OIDC_CLIENT_ID required for login redirect",
        )
    try:
        url = build_authorize_url(
            cfg,
            state=state or secrets.token_urlsafe(16),
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
        )
    except OIDCError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse(url=url, status_code=302)


@app.post("/v1/auth/oidc/token")
async def oidc_token_exchange(body: OIDCCodeExchangeRequest) -> dict[str, Any]:
    """
    Exchange authorization ``code`` for tokens at the IdP token endpoint.

    - **Confidential client:** set ``OIDC_CLIENT_SECRET``; body needs ``code``
      (+ ``redirect_uri`` if not in env).
    - **Public / PKCE:** omit secret; send ``code_verifier`` with the code.

    Returns the IdP token response (access_token, id_token, refresh_token, …).
    """
    cfg = OIDCConfig.from_env()
    if not cfg.is_configured() or not cfg.issuer:
        raise HTTPException(
            status_code=503,
            detail="OIDC not configured; set OIDC_ISSUER (and client credentials)",
        )
    try:
        tokens = exchange_code(
            body.code,
            config=cfg,
            redirect_uri=body.redirect_uri,
            code_verifier=body.code_verifier,
        )
    except OIDCError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Never echo client_secret; IdP response is already safe
    return tokens


@app.get("/v1/auth/me")
async def auth_me(principal: Principal = Depends(get_principal)):
    return {
        "subject": principal.subject,
        "tenant_id": principal.tenant_id,
        "roles": principal.roles,
        "email": principal.email,
        "token_type": principal.token_type,
    }


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_v1(
    path: str,
    request: Request,
    principal: Principal = Depends(get_principal),
):
    """Proxy /v1/* to assistant-api with tenant identity headers."""
    # farmers+ can chat; admin/expert also allowed
    if path.startswith("admin"):
        principal.require_role(Role.ADMIN)
    return await _proxy(
        request,
        f"{settings.assistant_api_url}/v1/{path}",
        principal,
    )


@app.post("/ask")
async def proxy_ask(
    request: Request,
    principal: Principal = Depends(require_roles(Role.FARMER, Role.EXPERT, Role.ADMIN)),
):
    """Convenience alias → assistant /v1/chat."""
    body = await request.body()
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    headers = {
        "Content-Type": request.headers.get("content-type", "application/json"),
        **tenant_headers(principal, request_id),
    }
    # forward auth if present
    auth = request.headers.get("authorization")
    if auth:
        headers["Authorization"] = auth
    client: httpx.AsyncClient = request.app.state.http
    try:
        resp = await client.post(
            f"{settings.assistant_api_url}/v1/chat",
            content=body,
            headers=headers,
        )
    except httpx.RequestError as exc:
        logger.error("upstream_unreachable", error=str(exc))
        raise HTTPException(status_code=502, detail=f"assistant-api unreachable: {exc}") from exc
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type="application/json",
        headers={"X-Request-ID": request_id, "X-Tenant-ID": principal.tenant_id},
    )


async def _proxy(request: Request, url: str, principal: Principal) -> Response:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    client: httpx.AsyncClient = request.app.state.http
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }
    headers.update(tenant_headers(principal, request_id))
    body = await request.body()
    try:
        resp = await client.request(request.method, url, content=body, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"upstream error: {exc}") from exc
    out_headers = {
        "X-Request-ID": request_id,
        "X-Tenant-ID": principal.tenant_id,
    }
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
        headers=out_headers,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
