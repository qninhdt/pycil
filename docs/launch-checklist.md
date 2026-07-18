# Backend deployment checklist

This repository ships the Pycil API and worker only. A future Next.js BFF is a
separate deployment; do not use this checklist as a frontend launch checklist.

## Prerequisites

- [ ] `lexi-ai` is running separately, has completed its Cambridge reference
  bootstrap, and exposes the internal `lexi-service` alias on `pycil-backend`.
- [ ] Both PostgreSQL databases have a tested backup; Pycil does not own
  Lexi's dictionary database.
- [ ] Production `.env` has non-placeholder values for JWT, internal,
  Centrifugo, Google OAuth, and Lexi service secrets; `DOMAIN`,
  `ALLOWED_ORIGINS`, and `OAUTH_REDIRECT_URIS` are exact production values.
- [ ] `ENVIRONMENT=production`; the API's fail-closed production validation
  succeeds before any traffic is admitted.

## Deploy and smoke test

- [ ] From the Pycil checkout, run `IMAGE_TAG=<sha12> bash scripts/deploy.sh`.
- [ ] Confirm `GET https://<domain>/health/live` and `/health/ready` return
  success. Readiness covers Pycil Postgres, Redis, worker heartbeat, Lexi, and
  Centrifugo.
- [ ] Run Google OAuth through the Next.js BFF callback; verify its stored
  bearer token can call `GET /v1/me` and cannot be read by browser JavaScript.
- [ ] Submit `POST /v1/word-generations` with an `Idempotency-Key`; poll its
  returned `/v1/jobs/{id}` until terminal state and verify duplicate submission
  returns the same job.
- [ ] Start a session, answer a deterministic question, and verify exactly one
  FSRS response/review update. For `use_in_sentence`, verify the pending
  response resolves through poll or the owner-scoped Centrifugo channel.
- [ ] Confirm anonymous reads work only for public nodes and a private node
  returns `404` to another user.

## Go / no-go

Do not admit frontend traffic if migration, readiness, Lexi fingerprint,
OAuth callback allow-list, durable job recovery, or owner-channel isolation
fails. Investigate, deploy a forward fix, then rerun the affected smoke test.
