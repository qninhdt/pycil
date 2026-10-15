# Database setup and recovery

Pycil owns an application migration history rooted at
[initial.py](../../../apps/api/migrations/versions/initial.py). Application tables and
native checkpoint tables live in PostgreSQL `public`. Checkpoint setup uses the installed
library's native migration history; it is not copied into application Alembic revisions.

This baseline initializes a fresh database. It does not upgrade databases created by
retired migration histories. Existing data needs an explicit separately reviewed transfer
or a matching backup/release; do not reset a populated database to make startup pass.

## Explicit setup

From `apps/api`, using an explicitly selected environment:

```sh
uv run --locked --env-file /absolute/path/to/approved.env python -m pycil.app.migrate \
  --reference /absolute/path/to/reference.jsonl
```

`DB_URL` must be a PostgreSQL async URL. `--database-url` can explicitly select the target
instead. Treat command-line credentials according to the installation's secret policy.

The command upgrades application migrations to the current head, performs native checkpoint setup,
optionally imports reference JSONL and verifies the resulting schema. Omitting
`--reference` performs schema setup only; API startup still requires imported references.
There is no automatic reference download, SQLite import or mandatory generated-content seed.
Generated content is optional and may be imported manually later by operations.

## Identity and content-history adoption

The additive `user_identity` migration renames `users.clerk_subject` to `clerk_id` and
its unique constraint without replacing user rows. Coordinate application rollout:
old application versions expecting the old column cannot share this schema.
The following `content_revisions` migration adds retained history and its `CACHE 1` sequence.

For a populated installation, pause **all content writers**, back up the database and
run the migration command with `--baseline-content`. It records one adoption-time snapshot
per existing word/theme/artifact in bounded, idempotent transactions. It cannot recover
pre-adoption history. Finish the baseline before resuming only revision-aware writers.
Fresh empty installations need no content backfill. API startup never backfills history.
An edit of legacy content without a baseline fails and rolls back rather than inventing history.
Manual generated-content imports require the same paused baseline procedure before use.

Content-history downgrade is deliberately refused because dropping history loses replay data.
Restore a compatible release/backup through an explicit recovery decision instead. Do not prune
the revision chain on a timer. A resumed baseline is safe after interruption.

Search schema v3 uses its own derived directory, separate from cache payload versions and
required Redis coordination namespaces. For reference replacement or older-DB restore,
pause writes, stop every worker owning the affected directory, invalidate only derived index
directories, then restart compatible workers and wait for readiness/catch-up. An index cursor
ahead of the restored database is rejected. No user/content/history tables are reset by this
procedure; old schema directories are not automatically deleted. Backups/restores and deploy
commands remain operator actions, not API startup behavior.

## Reference artifact

[reference.jsonl](../../../data/reference.jsonl) contains one retained word and its
ordered senses per line. [Its manifest](../../../data/reference.manifest.json) records
counts and checksum. Imported identities are retained for sense citations; unused source
fields are excluded. Runtime reads use `reference_words` and `reference_senses`.

The importer validates rows and publishes the artifact transactionally with a source
lock. Reimporting identical data is idempotent. Conflicting identities, duplicate rows
or malformed content fail without partially publishing that import. No provider is
called during setup.

## Failure and recovery

Application DDL is transactional. Native checkpoint setup requires autocommit, so the
whole setup command is not one global transaction; earlier stages can remain complete
when a later import fails. Correct the input/connectivity failure and rerun the explicit
command. Do not silently replace conflicting reference rows.

Runtime startup checks versions, tables and reference presence without repairing them.
Back up populated installations and restore with a matching release when recovery is
needed. This consolidation has not reset or migrated a production database.

- [Setup command](../../../apps/api/pycil/app/migrate.py)
- [Migration environment](../../../apps/api/migrations/env.py)
- [Schema comparison](../../../apps/api/tests/integration/infrastructure/test_schema.py)
- [Reference import tests](../../../apps/api/tests/integration/vocabulary/test_reference_import.py)
