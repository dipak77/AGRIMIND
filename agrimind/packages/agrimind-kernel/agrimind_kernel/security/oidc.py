"""Production OIDC client: discovery, JWKS cache, RS256/ES256 token validation.

Configure via env (see OIDCConfig.from_env). When OIDC_ISSUER or OIDC_JWKS_URL
is set, auth.decode_token prefers validate_oidc_token over local HS256.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import algorithms as jwt_algorithms

# Lazy Principal import avoided at module top to reduce circular risk;
# validate_oidc_token returns claims + principal via auth.principal helpers.


class OIDCError(Exception):
    """Raised for OIDC configuration, discovery, JWKS, or validation failures."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


DEFAULT_SCOPES = "openid profile email"
DEFAULT_JWKS_TTL_SECONDS = 3600
TENANT_CLAIM_URI = "https://agrimind/tenant"


@dataclass(frozen=True)
class OIDCConfig:
    """OIDC client settings loaded from environment."""

    issuer: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    audience: str | None = None
    jwks_url: str | None = None
    scopes: str = DEFAULT_SCOPES
    jwks_ttl_seconds: int = DEFAULT_JWKS_TTL_SECONDS
    redirect_uri: str | None = None

    @classmethod
    def from_env(cls) -> OIDCConfig:
        ttl_raw = os.getenv("OIDC_JWKS_TTL_SECONDS", str(DEFAULT_JWKS_TTL_SECONDS))
        try:
            ttl = int(ttl_raw)
        except ValueError:
            ttl = DEFAULT_JWKS_TTL_SECONDS
        return cls(
            issuer=_env_strip("OIDC_ISSUER"),
            client_id=_env_strip("OIDC_CLIENT_ID"),
            client_secret=_env_strip("OIDC_CLIENT_SECRET"),
            audience=_env_strip("OIDC_AUDIENCE"),
            jwks_url=_env_strip("OIDC_JWKS_URL"),
            scopes=_env_strip("OIDC_SCOPES") or DEFAULT_SCOPES,
            jwks_ttl_seconds=ttl,
            redirect_uri=_env_strip("OIDC_REDIRECT_URI"),
        )

    def is_configured(self) -> bool:
        """True when live IdP validation should be used."""
        return bool(self.issuer or self.jwks_url)

    def is_confidential(self) -> bool:
        """True when client_secret is set (authorization-code server exchange)."""
        return bool(self.client_secret)

    def public_client_config(self, discovery: dict[str, Any] | None = None) -> dict[str, Any]:
        """Safe config for SPA / mobile — never includes client_secret."""
        disc = discovery or {}
        authorize = disc.get("authorization_endpoint")
        token_ep = disc.get("token_endpoint")
        end_session = disc.get("end_session_endpoint")
        if not authorize and self.issuer:
            # Fallback convention if discovery not yet loaded
            base = self.issuer.rstrip("/")
            authorize = f"{base}/protocol/openid-connect/auth"
            token_ep = token_ep or f"{base}/protocol/openid-connect/token"
        return {
            "issuer": self.issuer,
            "client_id": self.client_id,
            "audience": self.audience,
            "scopes": self.scopes,
            "authorization_endpoint": authorize,
            "token_endpoint": token_ep,
            "end_session_endpoint": end_session,
            "redirect_uri": self.redirect_uri,
            "jwks_url": self.jwks_url or disc.get("jwks_uri"),
            "pkce_required": not self.is_confidential(),
            "response_type": "code",
        }


def _env_strip(name: str) -> str | None:
    v = os.getenv(name)
    if v is None:
        return None
    v = v.strip()
    return v or None


# --- Discovery cache ---------------------------------------------------------

_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_DISCOVERY_TTL = 3600.0


def clear_oidc_caches() -> None:
    """Clear discovery + JWKS caches (tests / config reload)."""
    _discovery_cache.clear()
    JWKSCache.clear_all()


def discover(issuer: str, *, force: bool = False, timeout: float = 10.0) -> dict[str, Any]:
    """
    Fetch OpenID Provider Metadata from ``{issuer}/.well-known/openid-configuration``.

    Results are cached in-process for one hour.
    """
    if not issuer:
        raise OIDCError("OIDC issuer is empty; set OIDC_ISSUER")
    base = issuer.rstrip("/")
    now = time.time()
    if not force and base in _discovery_cache:
        exp, doc = _discovery_cache[base]
        if now < exp:
            return doc

    url = f"{base}/.well-known/openid-configuration"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()
            doc = resp.json()
    except httpx.HTTPError as exc:
        raise OIDCError(
            f"OIDC discovery failed for {url}: {exc}",
            cause=exc,
        ) from exc
    except ValueError as exc:
        raise OIDCError(f"OIDC discovery returned non-JSON from {url}", cause=exc) from exc

    if not isinstance(doc, dict):
        raise OIDCError(f"OIDC discovery payload is not an object: {url}")
    if "jwks_uri" not in doc and "issuer" not in doc:
        raise OIDCError(f"OIDC discovery missing jwks_uri/issuer: {url}")

    _discovery_cache[base] = (now + _DISCOVERY_TTL, doc)
    return doc


# --- JWKS cache --------------------------------------------------------------


class JWKSCache:
    """Fetch and cache JWKS; resolve signing keys by ``kid``."""

    _instances: dict[str, JWKSCache] = {}

    def __init__(self, jwks_url: str, *, ttl_seconds: int = DEFAULT_JWKS_TTL_SECONDS) -> None:
        if not jwks_url:
            raise OIDCError("JWKS URL is empty")
        self.jwks_url = jwks_url
        self.ttl_seconds = ttl_seconds
        self._keys: dict[str, Any] = {}
        self._fetched_at: float = 0.0
        self._raw: dict[str, Any] | None = None

    @classmethod
    def for_url(
        cls,
        jwks_url: str,
        *,
        ttl_seconds: int = DEFAULT_JWKS_TTL_SECONDS,
    ) -> JWKSCache:
        existing = cls._instances.get(jwks_url)
        if existing is not None and existing.ttl_seconds == ttl_seconds:
            return existing
        cache = cls(jwks_url, ttl_seconds=ttl_seconds)
        cls._instances[jwks_url] = cache
        return cache

    @classmethod
    def clear_all(cls) -> None:
        cls._instances.clear()

    def _stale(self) -> bool:
        return time.time() - self._fetched_at >= self.ttl_seconds or not self._keys

    def fetch(self, *, force: bool = False, timeout: float = 10.0) -> dict[str, Any]:
        if not force and not self._stale() and self._raw is not None:
            return self._raw
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(self.jwks_url)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise OIDCError(
                f"JWKS fetch failed for {self.jwks_url}: {exc}",
                cause=exc,
            ) from exc
        except ValueError as exc:
            raise OIDCError(
                f"JWKS response is not JSON: {self.jwks_url}",
                cause=exc,
            ) from exc

        if not isinstance(data, dict) or "keys" not in data:
            raise OIDCError(f"JWKS document missing 'keys': {self.jwks_url}")

        keys: dict[str, Any] = {}
        for jwk in data["keys"]:
            kid = jwk.get("kid")
            if not kid:
                continue
            try:
                keys[str(kid)] = jwt_algorithms.RSAAlgorithm.from_jwk(jwk) if jwk.get(
                    "kty"
                ) == "RSA" else jwt_algorithms.ECAlgorithm.from_jwk(jwk)
            except Exception as exc:
                # Skip unusable keys but keep others
                if jwk.get("kty") not in ("RSA", "EC"):
                    continue
                raise OIDCError(
                    f"Failed to parse JWK kid={kid} kty={jwk.get('kty')}: {exc}",
                    cause=exc,
                ) from exc

        if not keys:
            raise OIDCError(f"No usable RSA/EC keys in JWKS: {self.jwks_url}")

        self._keys = keys
        self._raw = data
        self._fetched_at = time.time()
        return data

    def get_signing_key(self, kid: str | None, *, force_refresh: bool = False) -> Any:
        """Return cryptographic key for ``kid``. Refreshes once on miss."""
        self.fetch(force=force_refresh)
        if kid and kid in self._keys:
            return self._keys[kid]
        # One refresh on miss (key rotation)
        if not force_refresh:
            self.fetch(force=True)
            if kid and kid in self._keys:
                return self._keys[kid]
        if kid is None and len(self._keys) == 1:
            return next(iter(self._keys.values()))
        available = list(self._keys.keys())
        raise OIDCError(
            f"No signing key for kid={kid!r} in JWKS {self.jwks_url}; "
            f"available kids={available}"
        )


def _resolve_jwks_url(config: OIDCConfig) -> str:
    if config.jwks_url:
        return config.jwks_url
    if not config.issuer:
        raise OIDCError("Set OIDC_JWKS_URL or OIDC_ISSUER for OIDC validation")
    doc = discover(config.issuer)
    jwks_uri = doc.get("jwks_uri")
    if not jwks_uri:
        raise OIDCError(f"Discovery for {config.issuer} has no jwks_uri")
    return str(jwks_uri)


def extract_roles(claims: dict[str, Any]) -> list[str]:
    """Map IdP role claims: ``roles``, ``role``, or Keycloak ``realm_access.roles``."""
    roles = claims.get("roles") or claims.get("role")
    if roles is None:
        realm = claims.get("realm_access")
        if isinstance(realm, dict):
            roles = realm.get("roles")
    if roles is None:
        # resource_access.<client>.roles (Keycloak client roles) — flatten unique
        resource = claims.get("resource_access")
        if isinstance(resource, dict):
            collected: list[str] = []
            for _client, body in resource.items():
                if isinstance(body, dict):
                    r = body.get("roles") or []
                    if isinstance(r, list):
                        collected.extend(str(x) for x in r)
            if collected:
                roles = collected
    if roles is None:
        return ["farmer"]
    if isinstance(roles, str):
        return [roles]
    return [str(r) for r in roles]


def extract_tenant(claims: dict[str, Any]) -> str:
    """Tenant from standard or custom AGRIMIND claims."""
    tenant = (
        claims.get("tenant_id")
        or claims.get("tid")
        or claims.get("org_id")
        or claims.get(TENANT_CLAIM_URI)
        or claims.get("https://agrimind.ai/tenant")
    )
    if tenant is None:
        return "default"
    return str(tenant)


def claims_to_principal_fields(claims: dict[str, Any]) -> dict[str, Any]:
    """Normalize OIDC claims for Principal construction."""
    return {
        "subject": str(claims.get("sub") or claims.get("user_id") or "unknown"),
        "tenant_id": extract_tenant(claims),
        "roles": extract_roles(claims),
        "email": claims.get("email"),
        "claims": claims,
    }


def validate_oidc_token(
    token: str,
    *,
    config: OIDCConfig | None = None,
    leeway: int = 30,
) -> dict[str, Any]:
    """
    Validate an OIDC access/ID token (RS256 / ES256 / RS384 / ES384 / RS512 / ES512).

    Checks signature via JWKS, ``exp``, ``iss`` (when issuer configured),
    and ``aud`` (when audience configured).

    Returns decoded claims dict. Raises ``OIDCError`` or ``jwt.PyJWTError`` on failure.
    """
    cfg = config or OIDCConfig.from_env()
    if not cfg.is_configured():
        raise OIDCError(
            "OIDC is not configured; set OIDC_ISSUER and/or OIDC_JWKS_URL"
        )

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise OIDCError(f"Invalid JWT header: {exc}", cause=exc) from exc

    kid = header.get("kid")
    alg = header.get("alg", "RS256")
    if alg in ("HS256", "HS384", "HS512", "none"):
        raise OIDCError(
            f"OIDC path rejects algorithm {alg!r}; expected RS*/ES* signed tokens"
        )

    jwks_url = _resolve_jwks_url(cfg)
    cache = JWKSCache.for_url(jwks_url, ttl_seconds=cfg.jwks_ttl_seconds)
    try:
        key = cache.get_signing_key(kid)
    except OIDCError:
        raise
    except Exception as exc:
        raise OIDCError(f"Failed to resolve signing key: {exc}", cause=exc) from exc

    algorithms = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]
    options: dict[str, Any] = {
        "require": ["exp", "sub"],
        "verify_aud": bool(cfg.audience),
        "verify_iss": bool(cfg.issuer),
    }
    kwargs: dict[str, Any] = {
        "algorithms": algorithms,
        "options": options,
        "leeway": leeway,
    }
    if cfg.audience:
        kwargs["audience"] = cfg.audience
    if cfg.issuer:
        kwargs["issuer"] = cfg.issuer.rstrip("/")

    try:
        claims = jwt.decode(token, key, **kwargs)
    except jwt.PyJWTError as exc:
        raise OIDCError(f"OIDC token validation failed: {exc}", cause=exc) from exc

    # Normalize roles into claims for downstream principal_from_claims
    if "roles" not in claims:
        roles = extract_roles(claims)
        claims = {**claims, "roles": roles}
    if "tenant_id" not in claims:
        claims = {**claims, "tenant_id": extract_tenant(claims)}

    return claims


def build_authorize_url(
    config: OIDCConfig | None = None,
    *,
    state: str | None = None,
    nonce: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str = "S256",
    redirect_uri: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> str:
    """Build IdP authorization URL for browser redirect (optional PKCE)."""
    cfg = config or OIDCConfig.from_env()
    if not cfg.issuer and not cfg.client_id:
        raise OIDCError("OIDC_ISSUER and OIDC_CLIENT_ID required for login redirect")

    discovery: dict[str, Any] = {}
    if cfg.issuer:
        discovery = discover(cfg.issuer)
    pub = cfg.public_client_config(discovery)
    authorize = pub.get("authorization_endpoint")
    if not authorize:
        raise OIDCError("No authorization_endpoint from discovery or config")
    if not cfg.client_id:
        raise OIDCError("OIDC_CLIENT_ID is required for authorize URL")

    params: dict[str, str] = {
        "client_id": cfg.client_id,
        "response_type": "code",
        "scope": cfg.scopes,
    }
    redir = redirect_uri or cfg.redirect_uri
    if redir:
        params["redirect_uri"] = redir
    if state:
        params["state"] = state
    if nonce:
        params["nonce"] = nonce
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = code_challenge_method
    if extra_params:
        params.update(extra_params)
    return f"{authorize}?{urlencode(params)}"


def exchange_code(
    code: str,
    *,
    config: OIDCConfig | None = None,
    redirect_uri: str | None = None,
    code_verifier: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """
    Server-side authorization code exchange.

    Requires ``OIDC_CLIENT_SECRET`` for confidential clients, or ``code_verifier``
    for public PKCE clients.
    """
    cfg = config or OIDCConfig.from_env()
    if not cfg.issuer:
        raise OIDCError("OIDC_ISSUER required for code exchange")
    if not cfg.client_id:
        raise OIDCError("OIDC_CLIENT_ID required for code exchange")

    discovery = discover(cfg.issuer)
    token_url = discovery.get("token_endpoint")
    if not token_url:
        raise OIDCError("Discovery missing token_endpoint")

    redir = redirect_uri or cfg.redirect_uri
    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": cfg.client_id,
    }
    if redir:
        data["redirect_uri"] = redir
    if cfg.client_secret:
        data["client_secret"] = cfg.client_secret
    if code_verifier:
        data["code_verifier"] = code_verifier
    if not cfg.client_secret and not code_verifier:
        raise OIDCError(
            "Code exchange requires OIDC_CLIENT_SECRET (confidential client) "
            "or code_verifier (PKCE public client)"
        )

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code >= 400:
                detail = resp.text[:500]
                raise OIDCError(
                    f"Token endpoint returned {resp.status_code}: {detail}"
                )
            return resp.json()
    except OIDCError:
        raise
    except httpx.HTTPError as exc:
        raise OIDCError(f"Token exchange request failed: {exc}", cause=exc) from exc
    except ValueError as exc:
        raise OIDCError("Token endpoint returned non-JSON", cause=exc) from exc
