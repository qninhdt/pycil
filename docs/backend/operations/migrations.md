# Database setup and recovery

The application head is `20261012_profile` (baseline `20261009_baseline`); the native Lexi baseline is
`20261009_base`. Historical migration revisions and upgrade transformations have been
removed. These baselines initialize fresh schemas; they do not adopt an old database.

Application startup only verifies schemas. Run the explicit gate from `apps/api`:

```sh
uv run --locked --env-file /absolute/path/to/approved.env python -m pycil.migrate
```

The gate applies native Lexi migrations, then Pycil migrations, imports the required
reference into `lexi_reference`, imports the bundled `vendor/lexi-ai/content.sqlite`
into `lexi`, sets up native checkpoints, and verifies all owners.
The default reference is downloaded and cached from the pinned GitHub release.
`--reference /path/reference.sqlite` supplies a standalone offline snapshot.
Repeated setup reuses the installed reference without downloading it again.
The content snapshot ships in the same API image and requires no release download or
sibling Lexi checkout. `--content /path/content.sqlite` overrides it. Lexi preserves
identities, skips an unchanged installed snapshot, and rolls back conflicting imports;
setup does not invoke inference or overwrite runtime-generated content.

The packaged Lexi head is `20261012_word_refs`, which renames `word_sources` to
`word_references` and its Word lookup index without changing rows or IDs. This rename
is reversible. The preceding `20261011_artifacts` migration replaces old question storage
and intentionally removes old question rows; Word/Sense and their lexical content remain.
The application profile migration normalizes padded/blank legacy display names and
adds the display-name shape check; display-name/handle/bio columns already exist.
Missing profile identity is initialized from Clerk on first authenticated access,
without external calls during migration. Downgrade removes the check, not normalization.
The application learning migration replaces last rating with Elo and last exposure,
removes obsolete preferences and clamps N/K to the new limits. Both learning replacements
require a backup restore to reverse.

The local native `data/content.sqlite` was migrated with a pre-migration backup and lexical table hash/count comparison. This does not migrate a deployed PostgreSQL database.

Fresh baselines require empty owned schemas apart from their version tables. Supported recorded versions upgrade through their packaged chain; unknown revisions fail rather than resetting data. Existing installations need a separately reviewed data transfer
or a verified backup restored with their matching old release.

Each Alembic owner uses transactional DDL, but native checkpoint setup uses autocommit;
the whole gate is not one transaction. A later failure can leave earlier stages complete.
Read-only runtime checks detect mismatched versions, missing tables and reference markers.

Downgrade through the learning replacement is rejected. For populated data:
restore a verified backup with the code that matches that backup. No production database
was reset or migrated during this change.

- [Gate](../../../apps/api/pycil/migrate.py) and [migration environment](../../../apps/api/migrations/env.py)
- [Current baseline](../../../apps/api/migrations/versions/20261009_baseline.py)
- [Fresh schema checks](../../../apps/api/tests/integration/test_fresh_schema.py) and [bootstrap checks](../../../apps/api/tests/integration/test_bootstrap.py)
