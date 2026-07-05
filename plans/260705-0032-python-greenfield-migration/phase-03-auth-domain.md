---
phase: 3
title: "Auth Domain"
status: complete
priority: P1
effort: "1.5d"
dependencies: [1, 2]
---

# Phase 3: Auth Domain

## Overview
Backend-driven OAuth 2.1 (Google, PKCE) with backend-signed JWTs, token_version revocation, and a `current_user` dependency. Frontend iron-session wiring lands in Phase 10.

## Requirements
- Functional: `/auth/login` → Google consent; `/auth/callback` exchanges code, upserts user, issues JWT; `/auth/refresh`; `/auth/logout`.
- Non-functional: PKCE mandatory, exact redirect-URI match, no implicit grant, JWT secret backend-only.

## Architecture
`auth/` domain owns oauth flow, token sign/verify, deps. JWT claims: `sub`, `role`, `tv` (token_version), `exp`, `iat`. `role` + `token_version` + `banned_at` re-read server-side on every authed request (JWT claims edge-convenience only). **Auth transport is bearer-header ONLY** — the API never reads a session cookie, so CSRF is out of scope by design (the "cookie handoff" is the FE's iron-session concern, Phase 10, not an API auth input). Internal upsert endpoint guarded by `X-Internal-Secret` (constant-time compare, fail-closed).

## Related Code Files
- Create: `apps/api/pycil/auth/{router,oauth,tokens,deps,schemas}.py`
- Modify: `apps/api/pycil/auth/models.py` (User only — no Session table, stateless JWT)
- Reference (read-only): `main:apps/pycil-core/pycil_core/auth.py` (banned check :103-104, alg pin :51/:62), Go `apps/api/internal/auth/jwt.go:50` (HMAC method assert), `apps/api/internal/handler/auth_handler.go:75-81` (constant-time internal secret), `~/projects/openlet` OAuth flow (per notes.md §3)

## Implementation Steps
1. `oauth.py`: build Google authorize URL with PKCE `code_challenge` + `state`; store verifier+state in short-lived Redis key. Callback: validate state, exchange code+verifier, fetch userinfo.
2. `tokens.py`: `sign_access(user)` / `verify(token)` with pyjwt. **Pin `algorithms=["HS256"]` and `options={"require": ["sub","tv","exp","iat"]}` on every `decode`** (reject alg-confusion/`alg:none`). Embed `tv` (token_version); short access TTL + refresh. `bump_token_version(user)` for logout-all. Forbid `jwt.decode` outside `tokens.py`.
3. `router.py`: `/auth/login`, `/auth/callback` (upsert user in same DB tx, issue JWT, return it for the FE to seal into iron-session — API itself is bearer-only), `/auth/refresh` (reissue JWT, no server session), `/auth/logout` (bump token_version).
4. `deps.py`: `current_user` verifies JWT (pinned alg) + re-reads `users.role`, `token_version`, **and `banned_at` from DB → reject with 403 `account_banned` if `banned_at IS NOT NULL`** (matches pycil-core/auth.py:103-104). `require_admin` checks re-read role.
5. `common/middleware.py`: `X-Internal-Secret` guard using `secrets.compare_digest` (constant-time); **reject when configured secret is empty/unset AND when provided header is empty**; fail closed at startup if unset in production (matches auth_handler.go:75-81).
6. Tests: PKCE state validation, token_version revocation, expired token, role re-read, **banned-user 403, alg-pin rejects `alg:none`/HS-confusion, internal-secret rejects empty/mismatched header**.

## Success Criteria
- [ ] Google OAuth round-trip issues a backend-signed JWT
- [ ] PKCE + state validated; invalid state rejected
- [ ] `current_user` re-reads role/token_version + rejects banned users (403)
- [ ] `token_version` bump invalidates old tokens
- [ ] JWT decode pins `algorithms=["HS256"]` + required claims; `alg:none`/HS-confusion rejected
- [ ] `X-Internal-Secret` uses constant-time compare; empty/unset secret fails closed
- [ ] API is bearer-only (never reads a session cookie); no `sessions` table

## Risk Assessment
- OAuth callback edge cases (state replay, code reuse). Mitigation: single-use Redis state key with TTL; reference openlet's verified flow.
- Secret handling. Mitigation: JWT + Centrifugo + internal secrets all env-driven, never committed.
