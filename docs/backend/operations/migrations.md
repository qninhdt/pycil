# Migrations, upgrades, and recovery

## Rules

Application startup never migrates. Use the explicit finite gate against an approved,
identified database. Do not rewrite an applied historical revision, reset populated
data, infer a target from a test fixture, or delete tables to bypass a mismatch.

The current application history is:

```text
0001_baseline -> 0002_nodes_spaces_paths -> 0003_learning_batches_activity
              -> 0004_node_search -> 0005_profile_handle_bio
```

The baseline is retained unchanged. Schema/version ownership is described in
[data model](../data-model.md). Only appended revisions implement new transformations;
the historical baseline and placement upgrade stay unchanged.

## Gate and validation

From `apps/api`, with an explicit chosen environment:

```sh
uv run --locked --env-file /absolute/path/to/approved.env python -m pycil.migrate
```

The module also accepts `--database-url`, but putting a credential-bearing URL into
command history/process arguments is not preferred. It requires PostgreSQL async URL
syntax and executes in order:

1. Native Lexi `upgrade_to_head(..., db_schema="lexi")`.
2. Pycil Alembic upgrade to head, managing `public` only.
3. Native checkpoint schema creation/setup using its own connection.
4. Read-only verification of all version rows and required tables.

Native checkpoint setup uses autocommit, including native concurrent-index operations.
The whole gate is therefore not a single all-or-nothing transaction. Application Alembic
uses PostgreSQL transactional DDL for its own upgrade. A failure in a later stage can
leave earlier stages completed; inspect each owner instead of assuming complete rollback.

The gate's command-line error is intentionally redacted. Investigate using controlled
diagnostics that identify revisions/stages without exposing passwords or raw user content.
Runtime schema checks refuse mismatched versions or missing required tables; they do not repair.

## Fresh baseline

`0001_baseline` requires an empty application `public` schema apart from Alembic's own
version table. Lexi's separate schema may already have been created by the preceding
gate stage. An unrelated or previous application schema is not automatically adopted.
Do not label a destructive reset of that schema a normal upgrade.

## Placement upgrade: `0002_nodes_spaces_paths`

This data-preserving, breaking migration uses frozen SQL rather than importing current
ORM models or policy. Writers must be stopped while it runs.

### Preflight

- Validate parent ownership and folder parent type.
- Reject reference targets that are not folders/decks.
- Walk old physical roots and fail if any node is unreachable due to cyclic/detached ancestry.
- Capture effective old PUBLIC behavior before changing placement: a live PUBLIC ancestor
  made descendants readable even when their own old flag was PRIVATE.

Corruption aborts the upgrade with an actionable identifier. The migration does not
delete corrupt rows to claim success. Repair requires its own reviewed data operation.

### Transformation

1. Rename `collection_nodes` to `nodes` and adjust constraints/index names/FKs.
2. Add role/space and create Library, Personal, Published for every user.
3. Put old top-level normal content under Personal.
4. Identify minimal effective-public frontiers and move those existing identities under Published.
5. Retain private organizational references for moved folder/deck frontiers, without copying memberships.
6. Complete placement across owners before deciding cross-owner reference availability.
7. Move unavailable/private-target Published references into Personal and warn with counts.
8. Preserve inactivity of descendants under deleted old ancestors so content is not resurrected.
9. Recompute derived space from final placement, remove editable visibility, add owner/role/root constraints.
10. Build active physical closure and report existing over-limit depth/nodes/children/memberships.

Private ancestor names are not exposed as public navigation. Canonical IDs, direct deck
memberships, and existing personal scheduling state are preserved. No learning-state
rename or review-log transformation happens in this revision.

Existing over-limit data is preserved, not silently reduced. Runtime allows relevant
reductions/repairs while rejecting growth. Warnings use frozen initial thresholds and
are not a promise that every deployment's future policy is identical.

### Learning/search/profile upgrade

0003 renames scheduling state/constraints/indexes without recomputing FSRS, converts
each old event into an original one-item batch receipt, and backfills daily activity
without current membership filtering. SHA-256 JSON rules are frozen in the migration.
Old event timezone-at-acceptance was absent: use the user's validated upgrade-time
timezone, documenting that historical approximation; all new dates are frozen.

Saved max senses becomes floor(effective Q/K), including K-only overrides. Frozen
old defaults are Q=30, K=3. Verify target policy matches before migrating; invalid
legacy combinations abort transactionally. Old budget keys/scalar columns/mastery
and history indexes are removed. 0004 adds generated weighted FTS and indexes; 0005
adds nullable handle/bio (no invented handle backfill). Schema drift check verifies
current metadata. 0003 refuses a lossy scalar downgrade; restore a verified pre-upgrade
backup with a compatible old release instead.

Quiesce assistant in-flight tools and all API/worker writers before breaking cutover.
The new cache namespace does not consume old payloads or flush unrelated Redis keys.
Matching clients use batch bodies and opaque cursors, not compatibility parsers.

## Upgrade checklist

Before production use:

- Verify a complete pre-upgrade backup by restoring it into an isolated database.
- Record exact old/new image digests, application revisions, external migration heads,
  reference artifact and product policy.
- Rehearse the upgrade on populated representative data, including deleted ancestry,
  publication frontiers, foreign references, and already-over-limit accounts.
- Run fresh/populated tests and schema comparison; verify no unintended external DDL.
- Quiesce API and worker writers, including any separate maintenance writer.
- Run the gate once against the identified target and capture stage/revision results.
- Confirm private/public read behavior, complete editor membership, and personal state preservation.
- Start matching API/worker/client versions; check readiness and worker bootstrap.

The operator sequence is in [deployment](deployment.md). Do not keep old visibility
clients running through a dual parser or route alias; the compatibility contract has been removed.

## Rollback and restore

`0002_nodes_spaces_paths.downgrade()` deliberately raises an error. Placement changes,
retained references, and retired visibility are not inverted by pretending the old
publication semantics are recoverable from the new tree.

Recovery requires an independently verified pre-upgrade backup:

1. Stop writers and preserve the failed/new database for diagnosis under the agreed
   retention/security policy; do not overwrite it reflexively.
2. Identify which schema owners completed and which image/client versions were running.
3. Choose approved forward repair or restore; do not alternate image versions blindly.
4. Restore the complete backup into the selected recovery target using the rehearsed process.
5. Restore matching reference/configuration/artifact versions and check all schema owners.
6. Start the matching old code only after schema compatibility is established.
7. Verify access, memberships, scheduling state, receipts, conversations, usage, and jobs
   before reopening writes.

Any work accepted after the backup has a data-loss/reconciliation implication. The
repository does not implement backup creation, point-in-time recovery, an automatic
restore command, or a zero-data-loss rollback guarantee. A checksum verifies bytes,
not successful restore. Do not substitute a newly created empty database for recovered data.

## Verification evidence

- Fresh gate repeat plus Alembic `command.check` validates current ORM/schema alignment.
- Populated baseline tests exercise inherited publication, retained references, foreign
  target repairs, hidden deleted descendants, and preserved memory fields.
- Invalid old ancestry tests verify failed application migration leaves old table and revision intact.
- Bootstrap tests verify independent external schema ownership and refusal of a lossy downgrade.
- Production-specific backup restore and scale query-plan verification remain operational obligations.

## Sources

- [Gate](../../../apps/api/pycil/migrate.py), [Alembic environment](../../../apps/api/migrations/env.py)
- [Baseline](../../../apps/api/migrations/versions/0001_baseline.py), [placement upgrade](../../../apps/api/migrations/versions/0002_nodes_spaces_paths.py)
- [Native checkpoint setup](../../../apps/api/pycil/assistant/checkpoints.py), [schema verification](../../../apps/api/pycil/database.py)
- [Populated upgrade tests](../../../apps/api/tests/integration/test_nodes_migration.py), [fresh tests](../../../apps/api/tests/integration/test_fresh_schema.py), [bootstrap tests](../../../apps/api/tests/integration/test_bootstrap.py)
