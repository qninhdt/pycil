# Defect regression coverage — what is pinned, and what is not

Audited 2026-08-06, after all 26 defects were fixed. The question was not
"are they fixed" but "would a revert be caught". Phase 2 was meant to write one
failing test per defect *before* the fixes; it was skipped, and tests were
written inline with each fix instead. This is the check on what that left.

Method: locate each fix, then hunt for tests by behaviour rather than by defect
id (test names carry invariants, never plan references). Phase 7's verdicts were
established by **reverting each fix and re-running**; Lexi's L1–L5 by running the
post-fix tests against a pre-fix worktree.

## Counts

| Verdict | Count |
|---|---|
| COVERED | 18 |
| WEAK | 3 |
| UNCOVERED | 5 |

## Two findings that outranked every missing test

**1. Six tests that had never run anywhere.** The worker's reconciler tests skip
themselves unless a Postgres DSN is in the environment, and nothing supplied one
— not CI, whose worker job had no database service, and not the local baseline.
Those six stand between the 24h purge and a learner's typed answer: the purge
nulls `raw_answer`, and the defect was that it did so under a live grading lease,
destroying text a worker was already paying a model to judge. Reverting the fix
was green before this, and now fails two of them.

**Fixed** — the worker CI job gained a Postgres service and prints skip reasons;
the baseline creates a database of its own for them; the worker floor moved
38 → 44 so a future silent skip fails rather than passes.

**2. Tests never saw migrations.** `conftest.py` builds its schema with
`create_all()` from the ORM, so a delete rule differing between a migration and
the model was invisible to the whole suite — including the account-deletion test,
which reads back whatever the ORM declared. Root cause behind both weak schema
verdicts below.

**Fixed** — `scripts/extract-fk-delete-rules.py` records all 31 foreign keys and
their delete rules against a migrated database, and fails when one changes in
either direction. Runs in the `migration-head` CI job and as a baseline tier.

## L7 was a plan error, not a missing fix

The audit reported L7's fix as absent: `_prune_orphan_vectors` calls `ids()`
unfiltered while `embed_missing` beside it filters by model. Investigated, and
the unfiltered call is **correct**. A vector's id is the bare sense id and
`model` is metadata, so an upsert under a new model replaces the same row —
whether a sense is alive has nothing to do with which model embedded it.
Filtering would be a leak: a vector left by a retired model would match no filter
the current encoder passes, so it could never be reaped.

Pinned by `test_the_prune_reaps_an_orphan_left_by_a_retired_model`, which fails
if the filter is ever added. The plan's seventh Lexi defect should be struck.

## Still uncovered, and deliberately so

Each is a decision rather than an oversight, recorded so the choice is visible.

- **B12a / B12b (advisory locks).** Both were reclassified in the plan itself as
  robustness corrections rather than defects — correctness rests on the
  `SessionSenseAttempt` unique claim and `with_for_update()`, and the locks only
  reduce contention. Reverting either key leaves the suite green, which is
  consistent with that classification. A test would have to assert two known
  colliding pairs take distinct `pg_locks` entries; worth writing only if
  contention is ever observed.
- **B9 (tracked-sense ceiling).** `TRACKED_SENSE_CEILING = 20_000` with a
  deterministic ORDER BY. Untested because nearby tests seed three senses and the
  query-budget harness counts statements, which a missing LIMIT does not change.
  To pin: insert ceiling+5 rows, assert exactly the ceiling comes back and that
  they are the numerically smallest.
- **B14 (session-start plan bound).** Replacing the bound-exhaustion `raise` with
  a sentinel left 204 tests green — the path never executes, because no test
  makes the structural generation move mid-plan. To pin: monkeypatch the
  generation read so it always differs, POST a session, assert 409 after exactly
  `_PLAN_ATTEMPTS` planning calls.
- **Cache viewer-suffix invalidation.** The existing test writes its key at the
  *old* generation and asserts at the *new* one, which are different keys — so it
  reads back a key that was never written and passes regardless. It pins
  unreachability, which the generation bump already guarantees; the defect was
  the leak. To pin: write anonymous and per-viewer keys at the current
  generation, delete, then assert `scan_iter` on that prefix is empty.
- **B2 (interest row growth).** A premise mismatch rather than a gap. No
  retention sweep exists; the commit deliberately fixed authorization lifetime
  instead, stating "this is an authorization defect, not a leak", and that half is
  covered by three tests. Rows still accumulate. Whether that matters is a product
  call.

## Weak, with the reason

- **B13 delete rules** — now covered by the FK baseline above. The
  *account-deletion* half was already strong: the test enumerates foreign keys
  from `information_schema` at runtime, so a new table fails it automatically.
- **L6 (`senses.word_id` index)** — declared in the ORM and in a migration, but
  no test asserts the index exists. Borderline: the schema is generated from the
  ORM, so there is no divergence path, unlike the delete rules.
