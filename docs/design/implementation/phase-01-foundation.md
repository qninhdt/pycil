---
phase: 1
title: "Foundation"
status: pending
priority: P1
effort: "2-3d"
dependencies: []
---

# Phase 1: Foundation

## Overview

Make the design folder the only authority, delete what it retires, and squash the
migration chain to **one baseline holding the final schema**. Almost entirely
deletion — which is why it is the cheapest phase to abandon if a later one proves a
design decision wrong.

## Requirements

**Functional**

- `pycil-redesign/` committed and the only design authority — rule R0 in
  [`../README.md`](../README.md).
- The five root design documents retired, with nothing load-bearing citing them.
- `docs/` and `plans/` **kept**, demoted from authority: superseded plans closed, and
  any document that contradicts the design either corrected or marked historical in
  place.
- One Alembic revision producing the **final** schema (`A6`): every new column,
  every rename, every drop.
- Dead layers gone: the BFF, the story gallery, the meta-tooling scripts, the
  second CI runner, the nightly workflow, coverage and count floors, twelve of
  thirteen browser specs.

**Non-functional**

- A tag exists before the phase starts, so every deletion in it is recoverable.
- `next build` succeeds — which it will, because the file that fails it is deleted
  here.
- No phase after this one needs a second migration for a table this baseline
  should have held.

## Architecture

Two independent movements that happen to share a phase, plus one that is neither.

**Demotion, not deletion.** `docs/` and `plans/` stay. They record what was built
and how, and a record that disagrees with the current design is still evidence about
how the code reached its present shape. What changes is precedence: the design folder
governs, everything else is history. Superseded plans are **closed** through the plan
CLI, which marks them without erasing them.

The five root design documents are the exception, and the reason is narrow: their
entire purpose was to *be* the authority. A retired authority left in place is a
document a reader will follow by mistake, because it reads like a specification
rather than like history.

**Deletion** applies to code, tooling, and CI — the BFF, the story gallery, the
meta-tooling scripts, the second CI runner, the nightly workflow, twelve browser
specs. All tracked, all recoverable from git.

**The squash** is the one piece of real design work. The current chain is 25
revisions and 1,805 lines, containing three verified churn cycles: a table created,
indexed, leased, then dropped (156 lines, zero remaining references); another
created then dropped (138 lines, zero references); and an expand/validate/enum-add
split (143 lines) whose entire purpose is zero-downtime rollout against live data
that does not exist. Fourteen of twenty-five downgrades are refuse-only.

The replacement is one revision written **from the design**, not derived from the
chain. It must hold:

| Change | From |
|---|---|
| `user_sense_stats.depth_level`, `.depth_streak` | `B4` |
| Drop `user_sense_stats.buried_until` | removed #3 |
| Drop table `session_sense_attempts` | removed #2 |
| Drop table `deck_attributes` | removed #24 |
| `external_identities (issuer, subject)` unique | `H7` |
| `user_credits`, `credit_debits` with `UNIQUE (kind, reference_id)` | `P8` |
| No `partial_output` column; an interrupted turn is recovered from the checkpoint | `E6` |
| Run row: `attempt`, `cancel_requested_at`, and a unique active-Run-per-Thread index | `G2`, `G4` |
| Run status vocabulary: `pending`, `running`, `interrupted`, `success`, `error`, `cancelled` | `G7` |
| Rename `async_*` → `job_*` | vocabulary |
| Drop `assistant_run_events`, `assistant_actions`, and `assistant_action_audit` | `Q4`, `Q5` |
| Drop the lease-exhaustion status value, `revoked_at` on interests, `schema_name` on events | removed #15-17 |

`db/models.py` is updated in the same commit (`A7`) — every model module imported,
because Alembic autogenerate needs it and this is the one file every schema change
touches.

## Related Code Files

**Create**

- `apps/api/alembic/versions/0001_baseline.py` — the single baseline
- `README.md` — rewritten, pointing at `pycil-redesign/`

**Delete**

- `notes.md`, `agent.md`, `learning-system.md`, `DESIGN.md`, `prompt.md` (5,195)
- `apps/api/alembic/versions/00*.py` — all 25, replaced by the baseline
- `apps/web/lib/actions/*.ts` — 11 files carrying `"use server"`
- `apps/web/proxy.ts`, `apps/web/lib/auth/session.ts`, `apps/web/lib/api/upstream.ts`
- `apps/web/app/api/**` (291 lines)
- `apps/web/stories/`, `apps/web/.storybook/`
- `apps/web/scripts/design-system-audit.mjs`
- `apps/web/tests/e2e/specs/*` except the one becoming the golden journey
- `scripts/check-doc-paths.py`, `check-module-cycles.py`, `extract-error-codes.py`,
  `extract-fk-delete-rules.py`, `extract-realtime-contracts.py`,
  `verify-baseline.sh`, `release-lexi.sh`, and both `*-baseline.json`
- `.github/workflows/nightly.yml`
- `apps/api/tests/architecture/`, `apps/api/tests/contracts/`,
  `apps/api/tests/integration/` (an empty package)
- `apps/api/tests/test_embedded_cutover_deployment.py` — asserts on deployment
  files by substring

**Keep, demoted**

- `docs/` — no longer authority. Correct or mark historical anything that
  contradicts the design; do not delete.
- `plans/` — no longer authority. Close the superseded plans; do not delete.

**Modify**

- `apps/api/pyproject.toml` — remove the nine import-linter contracts
- `.github/workflows/test.yml` — remove staleness gates, coverage floors, the three
  count assertions, the Storybook build, the design audit
- `apps/api/pycil/db/models.py` — the aggregator, matching the baseline
- `apps/web/package.json`, `pnpm-workspace.yaml` — drop the story runner and the
  seven lockfile-absent exclusions

**Keep, explicitly** — these look like part of the deletion and are not:

- `apps/api/tests/test_v1_contract.py` — the answer-safety substring scan (`C6`)
- `apps/api/tests/learning/test_delivery_payload_leak.py` (`C6`)
- `apps/web/tests/e2e/specs/bundle-hygiene.spec.ts` — the requirement survives any
  server-rendering architecture
- `packages/shared-py/shared/fsrs/` and its tests (`B2`)

## Implementation Steps

1. `git add pycil-redesign/ && git commit` — the authority exists before anything
   else moves.
2. `git tag pre-redesign` — the point every deletion in this phase can be recovered
   from.
3. `ak plan close` the ten superseded plans. `plans/` and `docs/` stay on disk.
4. Sweep `docs/` for documents that contradict the design: correct the ones worth
   correcting, mark the rest historical in their own first line. The two known
   contradictions are a document claiming the web app is a separate deployment, and a
   roadmap asserting a dependency bump that already landed.
5. Delete the five root design documents and sweep for anything load-bearing that
   cited them.
6. Write `README.md` pointing at `pycil-redesign/` as the design authority and at
   `docs/` as operational reference.
7. Write `alembic/versions/0001_baseline.py` from the design's schema tables, then
   delete the 25 existing revisions.
8. Update `db/models.py` to match, and update every model module for the renames
   and drops.
9. `alembic upgrade head` on an empty database; diff the result against the model
   metadata until `alembic revision --autogenerate` produces an empty migration.
10. Delete the BFF layer. Every page under `app/(app)/` that read through a server
    action becomes a client fetch or is temporarily stubbed — it cannot authenticate
    until phase 3, and that is expected.
11. Delete the story gallery, the design audit, the meta-tooling scripts, the
    nightly workflow, and twelve browser specs.
12. Trim `test.yml` to the steps that still have a subject.
13. Run every suite. Delete tests whose subject is gone; **do not** weaken a test
    whose subject remains.

## Todo

- [ ] Commit `pycil-redesign/`
- [ ] Tag `pre-redesign`
- [ ] Close the ten superseded plans; keep `plans/` on disk
- [ ] Sweep `docs/` for contradictions: correct or mark historical
- [ ] Delete the five root design documents
- [ ] Sweep for load-bearing citations of them
- [ ] Rewrite `README.md`
- [ ] Write the single baseline migration
- [ ] Delete the 25 existing revisions
- [ ] Update `db/models.py` and every model module
- [ ] Verify autogenerate produces an empty diff
- [ ] Delete the BFF layer
- [ ] Delete the story gallery and the design audit
- [ ] Delete six meta-tooling scripts and both baseline JSON files
- [ ] Delete `nightly.yml`
- [ ] Delete twelve browser specs
- [ ] Trim `test.yml`
- [ ] Remove the nine import-linter contracts
- [ ] Every remaining suite green

## Success Criteria

- [ ] `pycil-redesign/` committed; `pre-redesign` tag exists
- [ ] The ten superseded plans are closed and `plans/` is still on disk
- [ ] No document in `docs/` contradicts the design without being marked historical
- [ ] The five root design documents are gone and nothing load-bearing cites them
- [ ] Exactly one file in `alembic/versions/`
- [ ] `alembic upgrade head` on an empty database, then `--autogenerate`, yields an
      empty migration
- [ ] `grep -r "use server" apps/web` returns nothing
- [ ] `pnpm build` succeeds
- [ ] `pnpm typecheck`, `pnpm lint`, `pnpm test:unit` green
- [ ] The API, worker, and shared suites green
- [ ] The answer-safety tests still present and passing

## Risk Assessment

**A retired root document is still followed by a reader.** The five root documents
read like specifications, so leaving one in place invites a future reader to
implement from it. Signal: a decision justified by a document that no longer
describes the system. Response: they are deleted rather than demoted, which is the
one place this phase differs from how `docs/` and `plans/` are handled — and the
reason is exactly that difference in how a document reads.

**A document in `docs/` still contradicts the design after the sweep.** Signal: two
sources disagree and neither is marked. Response: the sweep's output is a mark, not a
deletion — a document marked historical is unambiguous, and it keeps the record of
what was true when it was written.

**The baseline omits a table a later phase needs.** Signal: a phase cannot express
its schema. Response: **edit the baseline**. Pre-production with no data, so this
is a one-file change. Adding revision 2 on top of a chain squashed hours ago is the
failure mode to avoid, and it is tempting precisely because it feels safer.

**Deleting the BFF leaves the web app unable to authenticate until phase 3.**
Signal: none — it is expected. Response: accept it. Patching CI to keep the old
path alive means deleting it twice.

**A deleted test was load-bearing.** Signal: a later phase breaks something no test
caught. Response: the invariant checklist is the backstop — if the behaviour matters
it is a named line in a design file, and phase 11 will not pass without it.
