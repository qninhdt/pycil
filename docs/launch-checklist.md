# Backend deployment checklist

This repository ships the Pycil API, worker, and embedded Lexi domain library.
The Next.js BFF remains a separate deployment.

## Prerequisites

- [ ] An immutable reference artifact is available at
  `LEXI_REFERENCE_DATASET_PATH`, and its SHA-256 was checked during the fresh
  schema rehearsal.
- [ ] The shared PostgreSQL cluster has a tested backup covering `public` and
  `lexi` schemas.
- [ ] Production `.env` has non-placeholder values for JWT, internal,
  Centrifugo, Google OAuth, and the Lexi reference fingerprint; `DOMAIN`,
  `ALLOWED_ORIGINS`, and `OAUTH_REDIRECT_URIS` are exact production values.
- [ ] `ENVIRONMENT=production`; the API's fail-closed production validation
  succeeds before any traffic is admitted.

## Deploy and smoke test

- [ ] From the Pycil checkout, run `IMAGE_TAG=<sha12> bash scripts/deploy.sh`.
- [ ] Before production deployment, run `bash scripts/rehearse-fresh-schema.sh`
  against an empty local Compose project with the release artifact.
- [ ] Confirm `GET https://<domain>/health/live` and `/health/ready` return
  success. Readiness covers Postgres, Redis, worker heartbeat, and Centrifugo.
- [ ] Run Google OAuth through the Next.js BFF callback; verify its stored
  bearer token can call `GET /v1/me` and cannot be read by browser JavaScript.
- [ ] Submit `POST /v1/word-generations` with an `Idempotency-Key`; subscribe to
  its returned task ID through SSE and verify duplicate submission joins it.
- [ ] Start a session, answer a deterministic question, and verify exactly one
  FSRS response/review update. For `use_in_sentence`, verify the pending
  response resolves through its owner-authorized SSE task snapshot.
- [ ] Confirm anonymous reads work only for public nodes and a private node
  returns `404` to another user.

## Go / no-go

Do not admit frontend traffic if migration ordering, fresh-schema rehearsal,
readiness, reference fingerprint, OAuth callback allow-list, durable task
recovery, or owner-channel isolation fails. This checklist does not satisfy the
separate Phase 9 compatibility-observation gate. Investigate, deploy a forward
fix, then rerun the affected smoke test.
