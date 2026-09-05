---
phase: 4
title: "Direct Delivery"
status: pending
priority: P1
effort: "1-2d"
dependencies: [1, 2, 3]
---

# Phase 4: Direct Delivery

## Outcome

Remove the realtime gateway and expose two delivery paths: owner-authorized
polling for durable jobs and same-origin SSE for inline assistant Runs.

## Requirements

- Delete Centrifugo configuration, token minting, channel authorization,
  publication adapters, and gateway dependencies.
- `GET /v1/jobs/{jobId}` returns the canonical owner-authorized snapshot.
- Assistant create and resume endpoints use a shared SSE framing contract.
- A dropped SSE connection changes no durable result; Run and Thread reads repair
  the UI.
- Caddy disables buffering and compression only for assistant SSE paths.

## Implementation

1. Delete the gateway service, configuration, secrets, and API integration.
2. Add the job read route through `job_interests` authorization.
3. Centralize assistant SSE frame encoding, heartbeat, error, and terminal events.
4. Configure and validate the Caddy route timeout, buffering, and compression.
5. Add contract and integration tests with a real HTTP stream and Postgres.

## Success criteria

- [ ] Another learner cannot read a job by guessing its id.
- [ ] Job state reaches the client through polling without a publication row.
- [ ] Assistant SSE frames parse across arbitrary transport chunk boundaries.
- [ ] Disconnect does not mark a Run successful or duplicate an effect.
- [ ] Canonical reads recover terminal and interrupted state.
- [ ] No Centrifugo service, secret, token, channel, or outbox publication remains.
- [ ] SSE is unbuffered and uncompressed through Caddy.
