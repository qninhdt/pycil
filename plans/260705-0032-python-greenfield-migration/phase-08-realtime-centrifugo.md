---
phase: 8
title: "Realtime Centrifugo"
status: complete
priority: P2
effort: "1d"
dependencies: [1, 3]
---

# Phase 8: Realtime Centrifugo

## Overview
Centrifugo integration replacing ad-hoc SSE + Redis Pub/Sub. API publishes events + signs JWT subscription tokens; worker publishes job/grading completion. Frontend subscribes via Centrifugo SDK (Phase 10).

## Requirements
- Functional: API signs per-user subscription tokens; publish to owner-scoped channels `users:{uid}:jobs:{job_id}`, `users:{uid}` (notifications), `users:{uid}:grading:{response_id}`; worker publishes on job completion.
- Non-functional: no per-conn goroutine/loop in app code; **private channels namespaced by owner so a token authorizes ONLY the caller's own ids**; reconnection recovery handled by Centrifugo.

## Architecture
`realtime/` domain: `client.py` (Centrifugo HTTP API publish + JWT subscription-token signer), `channels.py` (channel-name constants + payload schemas, shared via `packages/shared-py/shared/realtime`). Centrifugo runs as a compose container (Phase 1). Shared secret signs subscription tokens. **All private channels are prefixed `users:{uid}:...` so Centrifugo's per-user channel-permission (namespace + subscribe-only-own) prevents a user from subscribing to another user's job/grading stream — `jobs`/`grading` ids are enumerable bigints, so unprefixed channels would leak cross-user.**

## Related Code Files
- Create: `apps/api/pycil/realtime/{client,channels,router}.py`
- Create: `packages/shared-py/shared/realtime/{channels,payloads}.py` (worker + api share)
- Modify: `docker-compose.yml` (centrifugo config), `.env.example` (CENTRIFUGO_* secrets)
- Reference (read-only): `notes.md` §1-2

## Implementation Steps
1. `channels.py` (shared): owner-scoped channel builders `user_jobs(uid, job_id)` → `users:{uid}:jobs:{job_id}`, `user_notifications(uid)` → `users:{uid}`, `user_grading(uid, response_id)` → `users:{uid}:grading:{response_id}`; typed payload dataclasses per event. Every private channel embeds the owner uid.
2. `client.py`: `publish(channel, payload)` via Centrifugo HTTP API (httpx); `sign_subscription_token(user_id)` (JWT with Centrifugo secret, short TTL) that authorizes ONLY the caller's `users:{uid}...` namespace.
3. `router.py`: `GET /realtime/token` (authed) → subscription token scoped to the caller's own channels only.
4. `docker-compose.yml`: centrifugo service — namespace config enforcing subscribe-only-own-channel (user-scoped namespace permission), JWT HMAC secret from env, history/recovery on.
5. Worker side (Phase 9 consumes): worker imports `shared/realtime` to publish job-done to the owner-scoped channel (needs the target user's uid in the job payload).
6. Tests: token signing/verification, publish payload shape, channel naming, **user A's token cannot subscribe to user B's `users:{B}:...` channel**.

## Success Criteria
- [ ] `GET /realtime/token` returns a valid Centrifugo subscription token for the user
- [ ] API publishes to `jobs:`/`users:`/`grading:` channels
- [ ] Centrifugo container runs in compose with recovery enabled
- [ ] No per-connection goroutine/subscribe-loop in app code
- [ ] Shared channel/payload module imported by both api + worker

## Risk Assessment
- Shared secret handling. Mitigation: env-driven, never committed; documented in `.env.example`.
- Centrifugo config drift. Mitigation: pin image version; minimal channel-namespace config.
