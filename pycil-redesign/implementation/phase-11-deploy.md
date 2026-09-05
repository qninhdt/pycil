---
phase: 11
title: "Verify and Deploy"
status: pending
priority: P1
effort: "2-3d"
dependencies: [10]
---

# Phase 11: Verify and Deploy

## Outcome

Turn every design invariant into a named gate, build one immutable image digest,
rehearse full Postgres restore, and deploy the verified stack.

## Preconditions

- Supply CI's required session setting.
- Inject one Lexi artifact identity into API and domain worker.
- Declare `BACKUP_ID` on the backup/restore service.
- No Centrifugo, gateway secret, assistant worker, or publication relay remains.

## Implementation

1. Map each invariant in architecture, modules, cross-cutting concerns, testing,
   and operations to one named unit, integration, or golden-journey assertion.
2. Run unit checks, container-backed integration checks, generated-client checks,
   and the one-browser journey locally and in CI.
3. Build once, scan, and push by digest only after the gate is green.
4. Validate Compose and Caddy; verify assistant SSE is unbuffered and uncompressed.
5. Restore a coordinated dump of public, Lexi, and checkpointer schemas into an
   empty second Compose project and run integrity checks.
6. Snapshot production, run blocking migrations, health-gate domain worker and
   scheduler, then API, web, and Caddy.
7. Run smoke and golden journey against the deployed origin; record the digest.

## Success criteria

- [ ] Every named invariant has an executable assertion.
- [ ] A missing dependency fails rather than skips.
- [ ] Fresh Postgres reaches the expected Lexi/checkpointer/Alembic heads.
- [ ] The golden journey covers polled generation, synchronous grading, direct
  assistant SSE, reload at approval, and resume.
- [ ] Compose contains seven long-lived services and no gateway or assistant worker.
- [ ] Caddy preserves SSE framing without buffering or compression.
- [ ] Restore rehearsal proves all Postgres schemas and ownership links.
- [ ] Deploy uses the exact digest tested by CI and rollback uses the previous digest.
