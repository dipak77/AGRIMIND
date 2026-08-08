"""OIDC/JWT auth + tenant RBAC (Phase F1 + live OIDC).

Local/dev: HS256 JWT issued by gateway (``issue_token``).
Production: when ``OIDC_ISSUER`` or ``OIDC_JWKS_URL`` is set, validate RS256/ES256
tokens via discovery + JWKS (see ``agrimind_kernel.security.oidc``).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agrimind_kernel.config.settings import get_settings


class Role(StrEnum):
    FARMER = "farmer"
    EXPERT = "expert"
    ADMIN = "admin"
    SERVICE = "service"
    READONLY = "readonly"


# Role inheritance: higher includes lower for coarse checks
ROLE_RANK = {
    Role.READONLY: 1,
    Role.FARMER: 2,
    Role.EXPERT: 3,
    Role.SERVICE: 4,
    Role.ADMIN: 5,
}


@dataclass
class Principal:
    """Authenticated caller identity."""

    subject: str
    tenant_id: str
    roles: list[str] = field(default_factory=list)
    email: str | None = None
    token_type: str = "bearer"
    claims: dict[str, Any] = field(default_factory=dict)

    def has_role(self, role: str | Role) -> bool:
        want = Role(role) if not isinstance(role, Role) else role
        mine = [Role(r) if r in Role._value2member_map_ else None for r in self.roles]
        mine_r = [r for r in mine if r is not None]
        if want in mine_r:
            return True
        # admin implies all
        if Role.ADMIN in mine_r:
            return True
        return any(ROLE_RANK.get(r, 0) >= ROLE_RANK.get(want, 99) for r in mine_r)

    def require_role(self, *roles: str | Role) -> None:
        if not any(self.has_role(r) for r in roles):
            raise HTTPException(
                status_code=403,
                detail=f"requires one of roles: {[str(r) for r in roles]}",
            )


def _jwt_secret() -> str:
    settings = get_settings()
    return os.getenv("JWT_SECRET") or settings.jwt_secret


def _jwt_alg() -> str:
    settings = get_settings()
    return os.getenv("JWT_ALGORITHM") or settings.jwt_algorithm or "HS256"


def issue_token(
    *,
    subject: str,
    tenant_id: str,
    roles: list[str],
    email: str | None = None,
    expires_minutes: int = 60,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Issue local HS256 access token (dev / gateway login)."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "roles": roles,
        "iat": now,
        "exp": now + expires_minutes * 60,
        "iss": os.getenv("OIDC_ISSUER", "agrimind-local"),
    }
    if email:
        payload["email"] = email
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_alg())


def oidc_enabled() -> bool:
    """True when live IdP validation should be preferred over local HS256."""
    from agrimind_kernel.security.oidc import OIDCConfig

    return OIDCConfig.from_env().is_configured()


def decode_token(token: str) -> dict[str, Any]:
    """
    Validate and decode JWT.

    - If ``OIDC_ISSUER`` or ``OIDC_JWKS_URL`` is set: OIDC path (RS256/ES256, JWKS,
      issuer + audience + exp). Failures raise ``jwt.PyJWTError`` / OIDCError-wrapped
      as InvalidTokenError for a consistent surface.
    - Else: HS256 with ``JWT_SECRET`` (local OIDC-compatible claims).
    """
    from agrimind_kernel.security.oidc import OIDCConfig, OIDCError, validate_oidc_token

    cfg = OIDCConfig.from_env()
    if cfg.is_configured():
        try:
            return validate_oidc_token(token, config=cfg)
        except OIDCError as exc:
            # Surface as PyJWTError so get_principal / callers stay stable
            raise jwt.InvalidTokenError(str(exc)) from exc

    options = {"require": ["exp", "sub"]}
    audience = os.getenv("OIDC_AUDIENCE")
    kwargs: dict[str, Any] = {
        "algorithms": [_jwt_alg()],
        "options": options,
    }
    if audience:
        kwargs["audience"] = audience
    return jwt.decode(token, _jwt_secret(), **kwargs)


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    """Map JWT/OIDC claims to Principal (Keycloak + custom tenant claims)."""
    from agrimind_kernel.security.oidc import extract_roles, extract_tenant

    roles = extract_roles(claims)
    tenant = extract_tenant(claims)
    return Principal(
        subject=str(claims.get("sub") or claims.get("user_id") or "unknown"),
        tenant_id=str(tenant),
        roles=[str(r) for r in roles],
        email=claims.get("email"),
        claims=claims,
    )


_bearer = HTTPBearer(auto_error=False)


def auth_required() -> bool:
    """When false (local default), anonymous principal is allowed."""
    env = os.getenv("ENV", "local").lower()
    flag = os.getenv("AUTH_REQUIRED")
    if flag is not None:
        return flag.lower() in ("1", "true", "yes")
    return env in ("production", "staging", "prod")


async def get_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal | None:
    """Extract principal from Authorization header; optional when AUTH_REQUIRED=false."""
    if creds is None or not creds.credentials:
        if auth_required():
            raise HTTPException(status_code=401, detail="missing bearer token")
        # anonymous local principal
        tenant = request.headers.get("X-Tenant-ID", "default")
        return Principal(
            subject="anonymous",
            tenant_id=tenant,
            roles=["farmer"],
            token_type="anonymous",
        )
    try:
        claims = decode_token(creds.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc
    principal = principal_from_claims(claims)
    # header tenant override only if admin/service
    hdr_tenant = request.headers.get("X-Tenant-ID")
    if hdr_tenant and hdr_tenant != principal.tenant_id:
        if not principal.has_role(Role.ADMIN) and not principal.has_role(Role.SERVICE):
            raise HTTPException(status_code=403, detail="tenant mismatch")
        principal.tenant_id = hdr_tenant
    request.state.principal = principal
    return principal


def require_roles(*roles: str | Role) -> Callable:
    """FastAPI dependency factory for RBAC."""

    async def _dep(principal: Principal | None = Depends(get_principal)) -> Principal:
        if principal is None:
            raise HTTPException(status_code=401, detail="unauthenticated")
        principal.require_role(*roles)
        return principal

    return _dep


def tenant_headers(principal: Principal, request_id: str | None = None) -> dict[str, str]:
    """Propagate identity to downstream services."""
    h = {
        "X-Tenant-ID": principal.tenant_id,
        "X-User-ID": principal.subject,
        "X-Roles": ",".join(principal.roles),
    }
    if request_id:
        h["X-Request-ID"] = request_id
    return h
