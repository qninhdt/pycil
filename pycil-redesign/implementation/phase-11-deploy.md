---
phase: 11
title: "Deploy"
status: pending
priority: P1
effort: "2-3d"
dependencies: [10]
---

# Phase 11: Deploy

## Overview

Close the three preconditions, turn the gate green, and ship. This is where a red
gate stops being acceptable — `N8` blocks a deploy on a red gate, and this phase is
the deploy.

The two boot-blocking preconditions live here rather than in phase 1 because nothing
is deployable until the phases in between are done, and fixing a boot variable months
before a boot is fixing it twice.

## Requirements

**Functional**

- `P0.1` — the gate green. The file whose import-time validation failed the build was
  deleted in phase 1, so this is verification plus whatever the intervening phases
  broke.
- `P0.2` — the two production-required variables reach both containers: one artefact
  identity (`O5`) and the realtime proxy secret, documented in the template.
- `P0.3` — `BACKUP_ID` declared on the backup service, because `docker compose run`
  does not forward an undeclared host variable.
- One variable names the artefact identity (`O5`); the second name is gone.
- Every invariant line in the eleven design files has a **named test**.
- The golden journey passes on a real stack.
- Restore **rehearsed**, not assumed (`O10`).
- The runbook (`O12`) reflects what was learned in phases 2–10.

**Non-functional**

- A missing required variable fails the boot naming **every** missing one (`O6`).
- `stop_grace_period` per worker exceeds its longest acceptable drain (`O9`).
- Build once, promote by digest (`N8`).

## Architecture

```text
1  resolve the digests built by the PR pipeline
2  push them
3  on the host: pull those exact digests
4  migrate to completion                    ← BLOCKS
5  workers + gateway, health-gated
6  api, health-gated
7  web + edge
8  smoke: the golden journey
9  on failure: previous digest, up again
```

**Workers before the API** because jobs are written by the API and consumed by a
worker; starting the API first opens a window where work is enqueued that nothing can
consume at the current schema version.

**Migration blocks**, and it runs in the **new** image before anything swaps — so a
failure costs nothing and the old containers are untouched.

**The invariant sweep** is the substantive work here, not the deploy script. Eleven
design files end with a checklist; each line needs a named test. Some already exist
from their own phase, some do not, and the gap is the deliverable:

| Source | Lines |
|---|---|
| `modules/learning.md` §12 | 10 |
| `modules/agent.md` §13 | 14 |
| `modules/hierarchy.md` §9 | 15 |
| `modules/content.md` §9 | 14 |
| `modules/account.md` §9 | 17 |
| `modules/web.md` §10 | 14 |
| `cross-cutting/auth.md` §12 | 20 |
| `cross-cutting/realtime.md` §12 | 11 |
| `cross-cutting/messaging.md` §11 | 12 |
| `cross-cutting/security.md` §10 | 16 |
| `ops/devops.md` §13 | 12 |

## Related Code Files

**Modify**

- `docker-compose.yml` — the artefact identity variable on `api` and `worker`; the
  proxy secret; `BACKUP_ID` on the backup service; `stop_grace_period` per worker
- `.env.example` — every variable, documented, including the two that were missing
- `apps/api/pycil/config.py` — the required set collapses to one artefact-identity
  name; the boot error names every missing variable at once
- `scripts/deploy.sh` — start `web`; export the web image alongside the others; delete
  the stale header claiming an API-only stack
- `infra/backup/restore.sh` — reachable `BACKUP_ID`
- `.github/workflows/test.yml` — the final gate shape (`ops/cicd.md` §2)
- `../ops/devops.md` §10 — the runbook, updated with what phases 2–10 taught

**Create**

- whatever invariant tests the sweep finds missing

## Implementation Steps

1. Collapse the two artefact-identity variables to one; update the required set, the
   deploy preflight, the work-key builder, and the template.
2. Add the proxy secret to the template and confirm it reaches both the API and the
   gateway.
3. Declare `BACKUP_ID` on the backup service. Verify by running restore in a second
   compose project — the failure mode is that `restic` resolves an empty id, which
   looks like a missing snapshot rather than a missing variable.
4. Make the boot error collect **every** missing name. Fixing one variable per restart
   turns a ten-minute deploy into an hour.
5. Set `stop_grace_period` per worker: the agent one above the run deadline, the domain
   one above its longest job.
6. Fix `deploy.sh`: start `web`, export its image, delete the stale header.
7. Trim `test.yml` to the final shape: lint, typecheck, unit, integration, agent
   contract, golden journey, build. Nothing else.
8. **Walk all eleven checklists.** For each line, find its named test or write it.
   This is the phase's main body of work.
9. Run the golden journey against a real stack.
10. Rehearse restore: a second compose project, restoring into an empty database, and
    confirm a working stack comes out. An unverified backup of the only stateful
    component is the largest single operational risk here.
11. Update the runbook with what phases 2–10 actually taught — the entries written from
    the design are predictions until they have been used.
12. Deploy.

## Todo

- [ ] One artefact-identity variable; the second name gone
- [ ] Proxy secret in the template and reaching both processes
- [ ] `BACKUP_ID` declared and verified by a real restore
- [ ] Boot error names every missing variable
- [ ] `stop_grace_period` per worker
- [ ] `deploy.sh` starts `web`; stale header deleted
- [ ] `test.yml` at its final shape
- [ ] All eleven checklists walked; every line has a named test
- [ ] Golden journey green on a real stack
- [ ] Restore rehearsed end to end
- [ ] Runbook updated from experience
- [ ] Deployed

## Success Criteria

- [ ] The gate is green on `main`
- [ ] A missing required variable fails the boot, naming every missing one
- [ ] A placeholder value is rejected as if absent
- [ ] Production boots
- [ ] Migration blocks; nothing takes traffic against an unmigrated schema
- [ ] The migration asserts the dictionary schema head first
- [ ] Readiness fails on a stale worker heartbeat
- [ ] The heartbeat threshold exceeds the slowest legitimate task
- [ ] SIGTERM drains rather than dropping in-flight work
- [ ] The realtime path is neither compressed nor buffered at the edge
- [ ] One dump restores both schemas to a consistent state
- [ ] **Restore into an empty database reproduces a working stack** — rehearsed
- [ ] A deploy aborts before swapping when migration fails
- [ ] Every invariant line in the eleven design files has a named test
- [ ] The golden journey passes on a real stack
- [ ] `deploy.sh` runs to completion

## Risk Assessment

**The invariant sweep will find gaps, and some will be phases' worth of work.** A
line like "two workers on one queue: no Run executes twice" needs real concurrency,
not a mock. Signal: a checklist line with no plausible test. Response: that is the
signal the behaviour was never built, not that the test is hard — treat it as a defect
found late rather than a test to skip.

**Restore has never run.** The failure mode is quiet: the id resolves empty, `restic`
reports no such snapshot, and it reads as a missing backup rather than a missing
variable. Signal: the rehearsal in step 10. Response: this is the one step in the plan
whose absence would be discovered at the worst possible moment, which is why it is a
criterion and not a note.

**The gate may be red for reasons phases 2–10 introduced and nobody noticed.** Direct
commits to `main` with an accepted red gate means no phase was forced to prove itself
against the whole suite. Signal: step 7's first full run. Response: each phase ended
with its own suite green, so the failures should be integration-shaped rather than
unit-shaped — and integration-shaped failures at this point are what the golden journey
exists to surface.

**The runbook is prediction until used.** Signal: an entry whose first move does not
help. Response: step 11 rewrites from experience, and an entry that was never needed is
better deleted than kept as decoration.
