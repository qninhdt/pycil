# Database setup and recovery

Pycil owns one static application migration,
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

The command applies the single application baseline, performs native checkpoint setup,
optionally imports reference JSONL and verifies the resulting schema. Omitting
`--reference` performs schema setup only; API startup still requires imported references.
There is no automatic reference download, SQLite import or mandatory generated-content seed.
Generated content is optional and may be imported manually later by operations.

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
