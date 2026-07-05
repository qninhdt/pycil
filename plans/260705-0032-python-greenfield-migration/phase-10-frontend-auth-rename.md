---
phase: 10
title: "Frontend Auth & Rename"
status: partial
priority: P2
effort: "1.5d"
dependencies: [3, 8]
---

# Phase 10: Frontend Auth & Rename

## Overview
Swap Next.js auth from Auth.js v5 to iron-session (holds the backend-signed JWT), point the API client at the Python backend, wire Centrifugo subscription, and rename frontend types `definitionId`→`senseId`. Content fields come from lexi-ai responses relayed by pycil.

## Requirements
- Functional: login via backend OAuth, session in iron-session cookie; API calls hit Python with bearer JWT; realtime via Centrifugo token.
- Non-functional: no shared AUTH_JWT_SECRET; `senseId` naming; masteryProgress maps to FSRS mastery (0-100); ELO fields removed from all contracts.

## Architecture
`apps/web`: replace `next-auth`/`@auth/core` with `iron-session`. Login redirects to backend `/auth/login`; callback lands with backend JWT sealed into the iron-session cookie. **The cookie is FE-side session storage only — every API call sends the JWT as `Authorization: Bearer`, never relies on the cookie reaching the API** (the API is bearer-only, so there is no CSRF surface). Centrifugo JS SDK subscribes to owner-scoped channels (`users:{uid}:...`) using `GET /realtime/token`.

## Related Code Files
- Modify: `apps/web/package.json` (drop next-auth, add iron-session, @centrifugo client), `apps/web/src/lib/api-client/*`, `apps/web/src/types/{learning,deck}.ts`, `apps/web/src/types/domain/learning.ts` (remove `elo_old/elo_new/elo_delta` + `mastery_level` from `TermReviewedResult`), `apps/web/src/lib/adapters/term-deck.ts`, `apps/web/src/lib/mock/handlers/learning.ts` (drop `mastery_level`), auth provider/middleware
- Modify/rewrite: `apps/web/src/lib/mock/schema-parity.test.ts` (hardcoded key list at :78-85 asserts `elo_old/elo_new/elo_delta/interval_seconds/mastery_level` — update to FSRS shape: `sense_id/mastery/stability/next_review_date` + `GradeResponse` fields)
- Delete: Auth.js config, `src/app/api/auth/[...nextauth]` route
- Reference (read-only): `notes.md` §3, current `apps/web/src/app/sign-in`, `packages/zod/src/pycil/frontend/learning/GradeResponse.ts` (contract shape)

## Implementation Steps
1. Remove Auth.js; add iron-session. Session helper seals/unseals the backend JWT in an encrypted cookie.
2. Sign-in flow: button → backend `/auth/login`; backend callback redirects back with JWT → Next route stores it in iron-session.
3. API client: attach JWT bearer; base URL → Python API; handle 401 → refresh via `/auth/refresh`.
4. Centrifugo: fetch subscription token from `/realtime/token`; subscribe to owner-scoped channels `users:{uid}:jobs:...`, `users:{uid}`, `users:{uid}:grading:...` for live updates (term gen, notifications, grading verdicts). Verdict also refetchable via `GET /responses/{id}` if a push is missed.
5. Rename `definitionId`→`senseId` in `types/learning.ts`, `deck.ts`, adapters; keep `masteryProgress` (maps FSRS mastery 0-100). **Remove ELO fields** `elo_old/elo_new/elo_delta` + `mastery_level` from `types/domain/learning.ts` `TermReviewedResult`; the review result now carries FSRS `mastery` + `next_review_date`. Update `GradeResponse` consumers to the `Score`-derived shape (is_correct/grade_status/grade_score/grade_feedback). Content display fields sourced from API responses (which relay lexi content).
6. Update `schema-parity.test.ts` (hardcoded ELO key list :78-85) to the FSRS shape; remove `mastery_level` from mock handlers.
7. Remove mock handlers + admin pages tied to removed surfaces.
8. Verify in browser: sign in, land on dashboard, trigger a word gen → live update; answer a card → mastery updates.

## Success Criteria
- [ ] Login works via backend OAuth; JWT held in iron-session (no next-auth)
- [ ] No shared AUTH_JWT_SECRET between FE and backend; API calls are bearer-only (cookie never sent to API)
- [ ] API client calls Python backend with bearer JWT + refresh on 401
- [ ] Centrifugo live updates received on owner-scoped channels (job/grading); verdict refetchable via `GET /responses/{id}`
- [ ] FE types use `senseId`; masteryProgress renders FSRS mastery; NO `elo_old/elo_new/elo_delta`/`mastery_level` remain
- [ ] `schema-parity.test.ts` updated to FSRS/GradeResponse shape and passes
- [ ] Browser smoke test passes (sign-in → dashboard → gen → answer)

## Risk Assessment
- iron-session vs Auth.js session-shape differences. Mitigation: thin session helper; store only the JWT + minimal claims.
- CORS/cookie domain between Vercel FE and API. Mitigation: configure CORS + SameSite; document in `.env.example`.
