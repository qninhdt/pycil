# Phase 4 — Auth + Middleware Adversarial Bug Hunt

Scope: `auth.py`, `api/deps.py`, `middleware/{csrf,rate_limit,security_headers,body_size}.py`, `services/user_service.py`, `routes/auth.py`, Caddyfile. Conversion bugs excluded.

## Findings (P1 first)

| id | file:line | sev | claim | evidence | repro | status |
|----|-----------|-----|-------|----------|-------|--------|
| B1 | body_size.py:62-71 | P2 | Multi-chunk request bodies silently truncated to first chunk | `replay_receive` hardcodes `"more_body": False` on EVERY replayed chunk. Buffer loop (43-58) correctly collects all chunks into `chunks`, but replay emits chunk[0] with `more_body:False` → Starlette `Request.stream` yields chunk[0] then breaks. Bytes 2..N dropped. | POST `/me` (or any handler) a JSON body that uvicorn delivers in ≥2 `http.request` messages (large/slow body under 1MB cap). Downstream sees only first segment → JSON decode error / partial data. Tests pass because small bodies arrive single-chunk. | CONFIRMED |
| B2 | rate_limit.py:27-29 + Caddyfile:21,25 | P3 | `X-Real-IP` trust = rate-limit bypass / victim-IP DoS IF pycil-core reachable bypassing Caddy | `client_ip` trusts client `x-real-ip` verbatim. Caddy `header_up X-Real-IP {remote_host}` overwrites it on the public path, so spoofing blocked *through Caddy*. Risk only if `pycil-core:8000` hit directly (other container / SSRF / misconfig). | Direct request to `:8000` with rotating `X-Real-IP` → unlimited; or fixed victim IP → exhaust victim's 60/min. Not reachable on intended topology. | SUSPECTED |
| B3 | auth.py:9-12, user_service.py:7-10 | P3 | Docstrings claim a "60s Redis cache wraps get_with_token_version_check" — no such cache exists | grep finds no cache impl; `get_current_user` always hits DB. Functionally SAFE (revocation immediate). Risk: a future dev "restoring" the documented cache reintroduces a 60s token-revocation lag. | n/a — comment/behavior drift | SUSPECTED |
| B4 | user_service.py:62-76 | P3 | Hot-path `get_with_token_version_check` ignores `deleted_at` | Returns user even if soft-deleted, as long as `tv` matches. Not exploitable: `soft_delete_user` (97-108) bumps `token_version`, killing old tokens, and `upsert_user` blocks re-mint via `is_soft_deleted`. Defense-in-depth gap only. | n/a (no token with matching tv survives soft-delete) | SUSPECTED |
| B5 | rate_limit.py:45,50 | P3 | Rejected requests still ZADD'd → 429'd requests extend the sliding ban | `zadd` runs before `zcard`; member persists 60s even on 429. Arguably intended for sliding window; mild. | Hammer past limit; each blocked req refreshes window. | CONFIRMED (low impact) |

## Attacks REFUTED (auth core is solid)

- **Expired session reuse** — `exp` IS enforced: PyJWT verifies `exp` by default; `_REQUIRED_CLAIMS` forces presence; plus manual `now-iat > jwt_max_age` (auth.py:67). No DB `sessions` table — pure JWT, equivalent. Refuted.
- **token_version per request** — compared on every request, no cache, immediate revocation (user_service.py:69). Refuted.
- **JWT alg/sig** — `algorithms=["HS256"]` pinned, no `none`, signature verified; prev-secret fallback only on signature error, expired re-raised first (auth.py:51-61). Refuted.
- **`sub`/`tv` parsing** — malformed → 401 invalid_session_claims (auth.py:90-93). Refuted.
- **CSRF subdomain/port/case bypass** — `_normalize_origin` + exact set membership; subdomain/port differ as strings, won't match; missing Origin+Referer → 403 (csrf.py:46-59). `/auth/*` bypass gated by `hmac.compare_digest` internal secret AND Caddy 404s `/api/core/auth/*`. Refuted.
- **body_size Content-Length spoof** — counts actual bytes regardless of CL (body_size.py:43-56). Refuted.

## Recommended fix priority
1. **B1** (P2, real): replay must preserve `more_body` — emit `more_body=True` for all but last chunk, or coalesce into a single body message. Currently breaks legitimate multi-segment requests.
2. B3: delete the stale 60s-cache docstrings (or pin "no cache, intentional").
3. B4: add `User.deleted_at.is_(None)` to hot-path filter (cheap defense-in-depth).

## Unresolved questions
- B2: Is `pycil-core:8000` *only* reachable via Caddy in prod (no host port publish, no peer containers)? If yes, B2 is non-issue; if other services share the docker net, it's exploitable.
- B1: Confirm whether uvicorn config / typical payload sizes ever produce multi-chunk `http.request` for this API (raises B1 from latent to active).
