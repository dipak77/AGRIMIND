# OIDC / Identity Provider Integration

AGRIMIND supports **local HS256 JWTs** for development and **live OIDC** (RS256/ES256 via JWKS) for staging/production.

## Modes

| Mode | When | Token issue | Token validate |
|------|------|-------------|----------------|
| Local | `OIDC_ISSUER` and `OIDC_JWKS_URL` unset | `POST /v1/auth/token` (HS256) | `JWT_SECRET` HS256 |
| Live OIDC | `OIDC_ISSUER` and/or `OIDC_JWKS_URL` set | IdP only (or gateway code exchange) | JWKS + iss/aud/exp |

When OIDC is configured, `decode_token` **prefers the OIDC path** and fails loudly on bad signatures, wrong issuer, or expired tokens. Local HS256 issuance remains available only for non-prod (`ENV!=production`) unless `ALLOW_LOCAL_TOKEN_ISSUE=true`.

## Environment variables

```bash
# --- Required for live OIDC validation (one of issuer / jwks) ---
OIDC_ISSUER=https://keycloak.example.com/realms/agrimind
# Optional if discoverable from issuer:
OIDC_JWKS_URL=https://keycloak.example.com/realms/agrimind/protocol/openid-connect/certs

OIDC_AUDIENCE=agrimind-api          # validated when set
OIDC_CLIENT_ID=agrimind-gateway
OIDC_CLIENT_SECRET=                 # confidential clients only; omit for public/PKCE
OIDC_SCOPES=openid profile email
OIDC_REDIRECT_URI=http://localhost:3000/callback
OIDC_JWKS_TTL_SECONDS=3600

# Local JWT (always used when OIDC not configured)
JWT_SECRET=local-dev-secret-key-min-32-chars-long!
JWT_ALGORITHM=HS256
AUTH_REQUIRED=true                  # production: require Bearer token
```

## Gateway endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/v1/auth/oidc/config` | public | Issuer, client_id, authorize URL, scopes (no secrets) |
| `GET` | `/v1/auth/oidc/login` | public | 302 redirect to IdP authorize URL |
| `POST` | `/v1/auth/oidc/token` | public | Authorization-code exchange (server secret or PKCE) |
| `POST` | `/v1/auth/token` | public* | **Local-dev only** HS256 issue |
| `GET` | `/v1/auth/me` | Bearer | Current principal |

\* Disabled when `ENV=production` unless `ALLOW_LOCAL_TOKEN_ISSUE=true`.

### SPA / PKCE public client

1. `GET /v1/auth/oidc/config` → `client_id`, `authorization_endpoint`, `pkce_required: true`
2. Browser: authorize with `code_challenge` (S256)
3. App exchanges code at IdP **or** via `POST /v1/auth/oidc/token` with `{ "code", "code_verifier", "redirect_uri" }`
4. Call APIs with `Authorization: Bearer <access_token>`

### Confidential client (BFF)

1. Set `OIDC_CLIENT_SECRET` on the gateway
2. `GET /v1/auth/oidc/login?redirect_uri=...` (or build authorize URL client-side)
3. `POST /v1/auth/oidc/token` with `{ "code", "redirect_uri" }` — gateway attaches secret

## Claim mapping → Principal

| Principal field | Claim sources (first match) |
|-----------------|----------------------------|
| `subject` | `sub`, `user_id` |
| `tenant_id` | `tenant_id`, `tid`, `org_id`, `https://agrimind/tenant` |
| `roles` | `roles`, `role`, Keycloak `realm_access.roles`, or flattened `resource_access.*.roles` |
| `email` | `email` |

Unknown/custom IdP roles are kept as strings; RBAC recognizes `farmer`, `expert`, `admin`, `service`, `readonly` (admin implies all).

## Keycloak realm example

1. Create realm `agrimind`.
2. Create client `agrimind-gateway`:
   - Access type: confidential (or public + PKCE)
   - Valid redirect URIs: `http://localhost:3000/*`, `http://localhost:8000/*`
   - Web origins as needed
3. Client scopes / mappers:
   - Audience mapper → `agrimind-api` (or set `OIDC_AUDIENCE` to client id)
   - Optional protocol mapper for `tenant_id` (user attribute or group)
   - Realm roles: `farmer`, `expert`, `admin`
4. Env:

```bash
OIDC_ISSUER=https://auth.example.com/realms/agrimind
OIDC_CLIENT_ID=agrimind-gateway
OIDC_CLIENT_SECRET=<from Keycloak>
OIDC_AUDIENCE=account   # or dedicated audience; must match token aud
OIDC_SCOPES=openid profile email
AUTH_REQUIRED=true
ENV=production
```

JWKS is auto-discovered from:

`{OIDC_ISSUER}/.well-known/openid-configuration` → `jwks_uri`.

## Auth0 notes

```bash
OIDC_ISSUER=https://YOUR_TENANT.auth0.com/
OIDC_CLIENT_ID=...
OIDC_CLIENT_SECRET=...          # Regular Web App
OIDC_AUDIENCE=https://api.agrimind.local
OIDC_SCOPES=openid profile email
OIDC_REDIRECT_URI=http://localhost:3000/callback
```

- Create an API in Auth0; set Identifier = `OIDC_AUDIENCE`.
- Add Action/Rule to inject `https://agrimind/tenant` and `roles` into access tokens if multi-tenant RBAC is required.
- SPA apps should use PKCE and leave `OIDC_CLIENT_SECRET` unset on the gateway (or keep secret only on a BFF).

## Library surface

```python
from agrimind_kernel.security.oidc import (
    OIDCConfig,
    discover,
    JWKSCache,
    validate_oidc_token,
    exchange_code,
    build_authorize_url,
)
from agrimind_kernel.security.auth import decode_token, principal_from_claims
```

Unit tests mock discovery + JWKS and mint RSA JWTs with PyJWT — no live IdP required in CI.
