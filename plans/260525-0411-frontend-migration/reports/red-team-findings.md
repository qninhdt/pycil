# Red-Team Findings + Triage

Run: 2026-05-25. Reviewers: Security Adversary, Failure Mode Analyst, Assumption Destroyer, Scope & Complexity Critic. 47 findings → triaged below per `.claude/rules/review-audit-self-decision.md` §3 (no silent reversal of user-confirmed decisions).

## Top three blockers (must fix before phase 2 starts)

1. **Auth.js v5 JWT is JWE, not HS256** (Assumption Destroyer #1) — Auth.js v5 defaults to encrypted JWE with HKDF-derived key, NOT a HS256 JWS PyJWT can decode. Without an explicit `jwt: { encode, decode }` override in `auth.ts`, the entire FastAPI auth path is broken on first request.
2. **`/auth/upsert-user` reachable via Caddy** (Security #2) — `handle_path /api/core/*` strips and forwards everything; `POST /api/core/auth/upsert-user` resolves on the same FastAPI app. Plan's verification ("→ 404") is wrong.
3. **`AUTH_SECRET` vs `AUTH_JWT_SECRET` divergence** (Failure #3) — phase-10 docker-compose lists both as separate env vars. Auth.js will sign with `AUTH_SECRET`; FastAPI verifies with `AUTH_JWT_SECRET`; every request 401.

## Apply

**Phase 2 (auth):**
- Override Auth.js `jwt.encode`/`jwt.decode` to emit HS256 JWS that PyJWT can verify. Use the `jose` lib in Auth.js; verify symmetric output.
- Separate `INTERNAL_API_SECRET` (64 bytes) for `/auth/upsert-user`. Never reuse JWT signing key.
- Mount `/auth/upsert-user` on a sub-router blocked by Caddy: add `respond /api/core/auth/* 404` rule before `handle_path`. Verify with curl.
- Single decode helper `decode_session(token)` in `pycil_core/auth.py`; lint-rule banning raw `jwt.decode` outside that file.
- `secrets.compare_digest` (or `hmac.compare_digest`) for `X-Internal-Secret` check.
- Pin OAuth `checks: ["pkce", "state"]` on the Google provider explicitly.
- `get_current_user` always re-reads `users` row (60s Redis cache) — JWT claims alone do not authoritatively identify the user. Catches user-deleted/banned mid-token-life.
- Add `users.token_version` SMALLINT column; embed `tv` claim; reject mismatch (lightweight revocation).
- `AUTH_SECRET = AUTH_JWT_SECRET` unification at compose layer (single env, two refs).
- Forbid wildcard `ALLOWED_ORIGINS` at FastAPI startup (fail-fast on `*` or `null`).
- Always return 404 for "not yours" job lookups (no 403 timing oracle).

**Phase 3 (BFF removal):**
- Drop FastAPI `CORSMiddleware` entirely. Same-origin via Caddy (prod) and Next.js `rewrites` (dev). One mechanism. (Cut #1.)
- Place SSE matcher INSIDE `handle_path /api/core/*` block with post-strip path `/jobs/*/stream`. Add curl test.
- SSE handler reads `jobs` row first; if `status in ('completed','failed')`, emit terminal frame and close BEFORE subscribing to pubsub (avoids missed events on reconnect).
- Re-validate session every heartbeat OR cap SSE max-duration to 60s and rely on client reconnect. Pick 60s cap (simpler).
- Verify worker publishes to `results:{term_id}` exactly; add `redis-cli psubscribe 'results:*'` smoke step.
- Dev: cookie path MUST go through Caddy.local, NOT raw `localhost:3000` → `localhost:8000`. Update phase-3 architecture diagram.
- Cut SSE-per-row in term-table; rows poll `useJob` every 5s with backoff. SSE only in `<TermAddDialog>` modal. (Cut #5.)

**Phase 4 (api client):**
- `lib/api-client/query-keys.ts` factory module — single source of truth for all queryKeys.
- 401 interceptor: `queryClient.clear() + redirect /sign-in?reason=expired`.
- Drop `react-hook-form` + `zod` + `@hookform/resolvers`. Native `<form>` + `required`/`minLength`/`maxLength` for the two dialogs. (Cut #10.)

**Phase 6 (mutate + SSE):**
- Explicit `useEffect` cleanup `return () => es.close()` for every EventSource.
- Polling fallback `refetchInterval` returns `false` on terminal status; treat 404 as terminal "timed out".
- Sign-out: `await signOut({redirect:false}); queryClient.clear(); router.push('/sign-in')` — prevents cache leak across users on shared browser.
- Onboarding seed: BE `INSERT ... ON CONFLICT DO NOTHING` on a unique `nodes_user_seed_unique(user_id, name)` partial index; phase-09 ships the index.

**Phase 7 (study):**
- Delete `use-learning-session.ts` outright in this phase. No `__legacy_` rename. (Cut #3.)

**Phase 8 (profile/dead-links):**
- Drop `NEXT_PUBLIC_SHOW_UNIMPLEMENTED` flag. Delete Group B `<Link>`s outright; v0.2 restores each link in the same PR that ships its endpoint. (Cut #4.)

**Phase 9 (migration):**
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` on both columns (rerun-safe).
- **Drop `term_count` column** entirely. Compute `(SELECT COUNT(*) FROM deck_terms WHERE deck_id = …)` at SELECT time. Delete the broken UPDATE in `onboarding_service`. (Cut #7.)
- `canonical_meaning` backfill: inspect first via `SELECT notes[1] FROM definitions LIMIT 50` BEFORE migration. If mixed/non-canonical, drop the backfill UPDATE; accept NULL until re-enrich.
- `PATCH /me`: NFC-normalize input; strip `\p{Cf}` (BiDi/format chars); reject non-`\p{L}\p{N}\p{P}\p{Zs}`; cap on grapheme clusters not bytes.
- Add `users.token_version` column.
- Add `nodes_user_seed_unique` partial index.

**Phase 10 (infra):**
- Caddy: SSE matcher inside `handle_path` block.
- Block `/api/core/auth/*` at Caddy with explicit 404 rule before `handle_path`.
- `AUTH_SECRET: ${AUTH_JWT_SECRET}` unification in compose.
- `INTERNAL_API_SECRET: ${INTERNAL_API_SECRET}` shared between web and core.
- Worker explicit `environment:` block — only `OPENROUTER_*`, `DATABASE_URL`, `REDIS_URL`. NOT `AUTH_JWT_SECRET`, NOT `INTERNAL_API_SECRET`.
- Healthcheck: `curl -fsS /api/auth/csrf` (500s if `AUTH_SECRET` missing). Or `/api/healthz` route that decodes a self-signed test JWT.
- Single-stage Dockerfile, drop `output: "standalone"`. `CMD ["npm","start"]`. Eats ~80MB; saves runtime-files class of bug. (Cut #11.)
- Split env: `PYCIL_CORE_INTERNAL_URL=http://pycil-core:8000` (compose only) vs `NEXT_DEV_PROXY_TARGET=http://localhost:8000` (dev `.env.local`). next.config.ts uses the dev variant.
- Pin exact origins per env in CI; forbid wildcards at config load.
- Mock-data deleted in **phase 1**, not phase 11. (Cut #2.)

**Phase 11 (smoke):**
- Reduce manual smoke to critical-path 6: sign-in → onboarding seed → add-term (SSE delivers) → flashcard renders → learn session to completion → sign-out. Move full 42-item walk to v0.2 Playwright. (Cut #12.)

**plan.md:**
- Update Hard Decisions Locked: add JWT-format override, separate internal secret, term_count computed, Caddy auth block.
- Update Risks table.

## Defer / Reject (preserves user-confirmed decisions)

Per `.claude/rules/review-audit-self-decision.md` §3: user said "don't remove features".

- **Reject Cut #6 (reduce themes to 1 + dark)** — legacy ships 6 themes × 3 fonts × dark; this is a feature the user explicitly preserved. Keep.
- **Reject Cut #8 (strip gamification fields from User)** — legacy Profile renders level/streak/coins/badges; layout-preserve with zero placeholders is the user's "don't remove features" stance. v0.2 wires real values.
- **Defer Cut #9 (drop adapter layer)** — adapters are thin (one function per type); collapsing the type tree adds component churn for marginal simplification. Keep.
- **Defer Security #4 (full revocation set)** — `token_version` column gives lightweight per-user revocation; full Redis JTI set deferred to v0.2.
- **Defer Security #15 (re-validate session every SSE heartbeat)** — instead, cap SSE duration to 60s and rely on client reconnect. Cheaper.
- **Defer Failure #14 (long-lived session JWT exp mid-flow)** — accept user-visible 401 at 7d boundary; v0.2 adds refresh-on-use.

## Open Questions Surfaced (no decision yet)

- Auth.js v5 `jwt.encode/decode` override: confirm it's a documented v5 API (not v4 holdover). VERIFY via context7 before phase-2 implementation.
- `next.config.ts` `output: "standalone"` decision — dropping it costs ~80MB image size; benefit is class-of-bug elimination (font copying, server.js placement). Final call deferred to phase-10 implementation; document either way.
- Should `signIn` callback's POST to `/auth/upsert-user` be retried on transient 502? If pycil-core boots slower than web on cold start, first sign-in fails. Add 3-retry with backoff in `auth.ts` callback.
