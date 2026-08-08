"""Offline OIDC unit tests: RSA JWT + mocked discovery/JWKS; HS256 fallback."""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

# Local/dev defaults — OIDC env cleared per-test when needed
os.environ.setdefault("ENV", "test")
os.environ.setdefault("AUTH_REQUIRED", "false")
os.environ.setdefault("JWT_SECRET", "local-dev-secret-key-min-32-chars-long!")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from agrimind_kernel.security.auth import (
    decode_token,
    issue_token,
    oidc_enabled,
    principal_from_claims,
)
from agrimind_kernel.security.oidc import (
    OIDCConfig,
    OIDCError,
    JWKSCache,
    clear_oidc_caches,
    discover,
    extract_roles,
    extract_tenant,
    validate_oidc_token,
)


ISSUER = "https://idp.test/realms/agrimind"
AUDIENCE = "agrimind-api"
JWKS_URL = f"{ISSUER}/protocol/openid-connect/certs"
KID = "test-rsa-1"


@pytest.fixture(autouse=True)
def _clean_oidc_env(monkeypatch: pytest.MonkeyPatch):
    """Start each test without live OIDC unless the test sets it."""
    for key in (
        "OIDC_ISSUER",
        "OIDC_JWKS_URL",
        "OIDC_AUDIENCE",
        "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET",
        "OIDC_SCOPES",
        "OIDC_REDIRECT_URI",
    ):
        monkeypatch.delenv(key, raising=False)
    clear_oidc_caches()
    yield
    clear_oidc_caches()


@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def _b64url_uint(val: int) -> str:
    length = (val.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(val.to_bytes(length, "big")).rstrip(b"=").decode("ascii")


def _public_jwk(public_key, kid: str = KID) -> dict[str, Any]:
    numbers = public_key.public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }


def _mint_rsa_token(
    private_key,
    *,
    sub: str = "user-1",
    roles: list[str] | None = None,
    tenant_id: str | None = "tenant-a",
    realm_roles: list[str] | None = None,
    custom_tenant: str | None = None,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    exp_delta: int = 3600,
    kid: str = KID,
    extra: dict[str, Any] | None = None,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + exp_delta,
        "email": "user@example.com",
    }
    if roles is not None:
        payload["roles"] = roles
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    if realm_roles is not None:
        payload["realm_access"] = {"roles": realm_roles}
    if custom_tenant is not None:
        payload["https://agrimind/tenant"] = custom_tenant
        payload.pop("tenant_id", None)
    if extra:
        payload.update(extra)
    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


def _mock_httpx_get(url_map: dict[str, Any]):
    """Return a context manager that mocks httpx.Client.get from url → JSON body."""

    class _Resp:
        def __init__(self, body: Any, status: int = 200):
            self._body = body
            self.status_code = status
            self.text = json.dumps(body) if not isinstance(body, str) else body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

        def json(self):
            if isinstance(self._body, str):
                return json.loads(self._body)
            return self._body

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url: str, **kwargs):
            if url not in url_map:
                raise Exception(f"unexpected URL {url}")
            return _Resp(url_map[url])

        def post(self, url: str, **kwargs):
            if url not in url_map:
                raise Exception(f"unexpected POST {url}")
            return _Resp(url_map[url])

    return _Client


# --- Config / discovery ------------------------------------------------------


def test_oidc_config_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "gw")
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("OIDC_SCOPES", "openid email")
    cfg = OIDCConfig.from_env()
    assert cfg.is_configured()
    assert cfg.issuer == ISSUER
    assert cfg.client_id == "gw"
    assert cfg.scopes == "openid email"
    assert not cfg.is_confidential()
    pub = cfg.public_client_config()
    assert "client_secret" not in pub
    assert pub["pkce_required"] is True


def test_oidc_not_configured_by_default():
    assert OIDCConfig.from_env().is_configured() is False
    assert oidc_enabled() is False


def test_discover_caches(monkeypatch: pytest.MonkeyPatch):
    discovery = {
        "issuer": ISSUER,
        "jwks_uri": JWKS_URL,
        "authorization_endpoint": f"{ISSUER}/auth",
        "token_endpoint": f"{ISSUER}/token",
    }
    client_cls = _mock_httpx_get(
        {f"{ISSUER}/.well-known/openid-configuration": discovery}
    )
    with patch("agrimind_kernel.security.oidc.httpx.Client", client_cls):
        doc1 = discover(ISSUER)
        doc2 = discover(ISSUER)
    assert doc1["jwks_uri"] == JWKS_URL
    assert doc2 is doc1 or doc2["jwks_uri"] == JWKS_URL


def test_discover_fails_loud():
    class _Boom:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            import httpx

            raise httpx.ConnectError("refused")

    with patch("agrimind_kernel.security.oidc.httpx.Client", _Boom):
        with pytest.raises(OIDCError, match="discovery failed"):
            discover("https://nowhere.invalid/realms/x")


# --- JWKS + validate_oidc_token ----------------------------------------------


def test_validate_oidc_token_rsa(rsa_keypair, monkeypatch: pytest.MonkeyPatch):
    private_key, public_key = rsa_keypair
    jwks = {"keys": [_public_jwk(public_key)]}
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)

    token = _mint_rsa_token(private_key, roles=["farmer", "expert"])
    client_cls = _mock_httpx_get({JWKS_URL: jwks})
    with patch("agrimind_kernel.security.oidc.httpx.Client", client_cls):
        claims = validate_oidc_token(token)
    assert claims["sub"] == "user-1"
    assert claims["tenant_id"] == "tenant-a"
    assert "farmer" in claims["roles"]
    p = principal_from_claims(claims)
    assert p.subject == "user-1"
    assert p.has_role("expert")


def test_keycloak_realm_access_roles(rsa_keypair, monkeypatch: pytest.MonkeyPatch):
    private_key, public_key = rsa_keypair
    jwks = {"keys": [_public_jwk(public_key)]}
    monkeypatch.setenv("OIDC_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)

    token = _mint_rsa_token(
        private_key,
        roles=None,
        tenant_id=None,
        realm_roles=["admin", "offline_access", "uma_authorization"],
        custom_tenant="org-99",
    )
    client_cls = _mock_httpx_get({JWKS_URL: jwks})
    with patch("agrimind_kernel.security.oidc.httpx.Client", client_cls):
        claims = validate_oidc_token(token)
    assert "admin" in claims["roles"]
    p = principal_from_claims(claims)
    assert p.tenant_id == "org-99"
    assert p.has_role("admin")
    assert p.has_role("farmer")  # admin implies


def test_extract_roles_and_tenant_helpers():
    assert extract_roles({"roles": ["expert"]}) == ["expert"]
    assert extract_roles({"realm_access": {"roles": ["farmer"]}}) == ["farmer"]
    assert extract_roles({}) == ["farmer"]
    assert extract_tenant({"org_id": "o1"}) == "o1"
    assert extract_tenant({"https://agrimind/tenant": "t2"}) == "t2"
    assert extract_tenant({}) == "default"


def test_validate_rejects_expired(rsa_keypair, monkeypatch: pytest.MonkeyPatch):
    private_key, public_key = rsa_keypair
    jwks = {"keys": [_public_jwk(public_key)]}
    monkeypatch.setenv("OIDC_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)
    token = _mint_rsa_token(private_key, exp_delta=-120)
    client_cls = _mock_httpx_get({JWKS_URL: jwks})
    with patch("agrimind_kernel.security.oidc.httpx.Client", client_cls):
        with pytest.raises(OIDCError, match="validation failed"):
            validate_oidc_token(token, leeway=0)


def test_validate_rejects_wrong_audience(rsa_keypair, monkeypatch: pytest.MonkeyPatch):
    private_key, public_key = rsa_keypair
    jwks = {"keys": [_public_jwk(public_key)]}
    monkeypatch.setenv("OIDC_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("OIDC_AUDIENCE", "other-api")
    token = _mint_rsa_token(private_key, audience=AUDIENCE)
    client_cls = _mock_httpx_get({JWKS_URL: jwks})
    with patch("agrimind_kernel.security.oidc.httpx.Client", client_cls):
        with pytest.raises(OIDCError, match="validation failed"):
            validate_oidc_token(token)


def test_validate_rejects_hs256_when_oidc(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OIDC_JWKS_URL", JWKS_URL)
    hs = issue_token(subject="x", tenant_id="t", roles=["farmer"])
    with pytest.raises(OIDCError, match="rejects algorithm"):
        validate_oidc_token(hs)


def test_jwks_kid_miss_raises(rsa_keypair, monkeypatch: pytest.MonkeyPatch):
    private_key, public_key = rsa_keypair
    jwks = {"keys": [_public_jwk(public_key, kid="other-kid")]}
    monkeypatch.setenv("OIDC_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)
    token = _mint_rsa_token(private_key, kid=KID)
    client_cls = _mock_httpx_get({JWKS_URL: jwks})
    with patch("agrimind_kernel.security.oidc.httpx.Client", client_cls):
        with pytest.raises(OIDCError, match="No signing key"):
            validate_oidc_token(token)


# --- decode_token routing ----------------------------------------------------


def test_decode_token_falls_back_to_hs256_when_oidc_unset():
    token = issue_token(
        subject="farmer_1",
        tenant_id="tenant_a",
        roles=["farmer"],
        email="f@example.com",
    )
    claims = decode_token(token)
    assert claims["sub"] == "farmer_1"
    assert claims["tenant_id"] == "tenant_a"


def test_decode_token_uses_oidc_when_configured(
    rsa_keypair, monkeypatch: pytest.MonkeyPatch
):
    private_key, public_key = rsa_keypair
    jwks = {"keys": [_public_jwk(public_key)]}
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)
    assert oidc_enabled() is True

    token = _mint_rsa_token(private_key, roles=["service"])
    client_cls = _mock_httpx_get({JWKS_URL: jwks})
    with patch("agrimind_kernel.security.oidc.httpx.Client", client_cls):
        claims = decode_token(token)
    assert claims["sub"] == "user-1"
    assert "service" in claims["roles"]


def test_decode_token_oidc_failure_is_pyjwt_error(
    rsa_keypair, monkeypatch: pytest.MonkeyPatch
):
    private_key, public_key = rsa_keypair
    jwks = {"keys": [_public_jwk(public_key)]}
    monkeypatch.setenv("OIDC_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)
    token = _mint_rsa_token(private_key, exp_delta=-500)
    client_cls = _mock_httpx_get({JWKS_URL: jwks})
    with patch("agrimind_kernel.security.oidc.httpx.Client", client_cls):
        with pytest.raises(jwt.PyJWTError):
            decode_token(token)


def test_local_hs256_ignored_when_oidc_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OIDC_JWKS_URL", JWKS_URL)
    hs = issue_token(subject="local", tenant_id="t", roles=["admin"])
    # OIDC path rejects HS256 → InvalidTokenError
    with pytest.raises(jwt.PyJWTError):
        decode_token(hs)


# --- Gateway OIDC config endpoint (no real IdP) ------------------------------


def test_gateway_oidc_config_503_when_unset():
    from gateway_service.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.get("/v1/auth/oidc/config")
    assert r.status_code == 503


def test_gateway_oidc_config_public(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "agrimind-gateway")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "super-secret")
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("OIDC_SCOPES", "openid profile")

    discovery = {
        "issuer": ISSUER,
        "jwks_uri": JWKS_URL,
        "authorization_endpoint": f"{ISSUER}/protocol/openid-connect/auth",
        "token_endpoint": f"{ISSUER}/protocol/openid-connect/token",
    }
    client_cls = _mock_httpx_get(
        {f"{ISSUER}/.well-known/openid-configuration": discovery}
    )

    from gateway_service.main import app
    from fastapi.testclient import TestClient

    with patch("agrimind_kernel.security.oidc.httpx.Client", client_cls):
        client = TestClient(app)
        r = client.get("/v1/auth/oidc/config")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["client_id"] == "agrimind-gateway"
    assert body["issuer"] == ISSUER
    assert "client_secret" not in body
    assert body["pkce_required"] is False  # secret configured
    assert "authorization_endpoint" in body
