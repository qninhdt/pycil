# Product backup and restore runbook

Pycil uses one PostgreSQL database with two ownership boundaries: Pycil's
application tables live in `public`, while embedded Lexi owns the isolated `lexi`
schema. The single custom-format dump therefore backs up both schemas as one
product unit; Pycil stores opaque IDs owned by Lexi.

## One-time host setup

On the deployment host, create the Restic password file for this Compose project
outside source control (for example, `infra/backup/restic.password`) with mode
`0600`. Configure the same durable `RESTIC_REPOSITORY` and password material for
the scheduled backup environment.

Do not commit the password file or cloud credentials. The Compose backup
profiles deliberately require them at runtime.

## Backup

Run from the Pycil checkout:

```sh
RESTIC_REPOSITORY='b2:bucket/product' ./scripts/backup-product.sh
```

The coordinator temporarily stops API/worker writes, assigns one UTC
`BACKUP_ID`, and streams a custom-format dump containing both `public` and
`lexi` to Restic as `pycil-<id>.dump`. It restarts the services even if a backup
command fails. Schedule this command from the host scheduler with a monitored
failure alert; Restic retention is applied by the Pycil backup container (7
daily, 4 weekly, 6 monthly).

## Restore drill

Restores are destructive and must be performed in an isolated environment
first. Select the exact coordinated ID, then run:

```sh
BACKUP_ID=20260722T000000Z \
RESTIC_REPOSITORY='b2:bucket/product' \
./scripts/restore-product.sh
```

The coordinator stops the Pycil stack, restores the shared dump, then runs the
migration gate before the worker and API start. Before routing traffic, verify
Pycil's `/health/ready`, perform one authenticated read, and record the drill
result and recovery time.

## Planned replacement

The accepted design moves to WAL-G base backups plus continuous WAL archiving to
S3-compatible storage, which recovers within the actually archived window rather
than to the last dump. **This runbook is still the operational route** and stays
until a WAL-G restore has been rehearsed in isolation; a backup route is not
replaced by a plan to replace it. See `pycil-redesign/ops/devops.md` §7.

## WAL-G: base backup, WAL archiving and point-in-time restore

The WAL-G route is **rehearsed and passing** against an isolated cluster, but it is
not yet the deployed route — the deployed Postgres still runs the stock image with
no archiving. What follows is the mechanism, and what has been proven about it.

### How it is built

| Piece | Path | Purpose |
|---|---|---|
| `infra/postgres-walg/Dockerfile` | PostgreSQL 16 (Debian) plus WAL-G `v3.0.9`, checksum-verified at build time | The image a deployment would run |
| `infra/postgres-walg/entrypoint-walg.sh` | Validates `WALG_S3_PREFIX` and its reachability, then hands off to the stock entrypoint | A cluster that cannot archive refuses to start rather than looking healthy |
| `docker-compose.walg-rehearsal.yml` | Isolated source cluster, restore target and MinIO | The rehearsal, on loopback port 5499 |
| `scripts/rehearse-walg-restore.sh` | The rehearsal itself, with assertions | Proves recoverability rather than assuming it |

Archive settings are passed as `-c` flags from the compose file. They are **not**
a mounted `config_file`: pointing `config_file` at a file of your own *replaces*
the generated `postgresql.conf` instead of extending it, which silently drops
`listen_addresses = '*'` and leaves the container reachable from inside the compose
network and resetting every connection from the host. That failure was hit while
building this and is why the flags are used.

### The rehearsal

```sh
docker compose -f docker-compose.walg-rehearsal.yml up -d postgres
./scripts/rehearse-walg-restore.sh
docker compose -f docker-compose.walg-rehearsal.yml --profile restore down -v
```

It asserts, in order: archiving is live; Pycil's real migration chain applies;
a known row exists in each of the three schemas; a base backup is written; a
post-backup row is written and a recovery target recorded; the archiver reports
zero failures and `wal-verify integrity` is OK; the backup fetches into fresh
PGDATA; replay reaches the target; and finally that the pre-target rows are present
while the post-target row is absent. That last pair is what makes it a
point-in-time restore rather than a restore of whatever was latest.

**Measured result (2026-09-25):** 13 public tables restored, `alembic_version` at
`0008_credit_debit_usage_snapshot`, `lexi` and the checkpoint table both present,
`archived_count=6`, `failed_count=0`, `wal-verify integrity: OK`, and archive lag
at the end of the run of 20s.

**RPO** is bounded by `archive_timeout = 60s`, which is what caps how long a
committed change can wait to reach the bucket on a quiet database. **RTO** was not
measured: the rehearsal data is a few megabytes, so its restore time says nothing
about a production-sized cluster. Measure RTO against real data volume before
relying on a number.

### Two things that must be configured before this replaces Restic

1. **WAL-G reads libpq's own variables.** Without `PGUSER`/`PGHOST` it defaults to
   the OS user — usually `root`, which is not a database role — and the failure
   appears as a broken `archive_command`, not as a startup error. The entrypoint
   sets them from `POSTGRES_USER`/`POSTGRES_DB`.
2. **A private prefix and credentials.** `WALG_S3_PREFIX`, `AWS_ACCESS_KEY_ID`,
   `AWS_SECRET_ACCESS_KEY` and `AWS_ENDPOINT`. The rehearsal uses a local MinIO with
   throwaway credentials; a deployment needs a bucket restricted to backup use.

Do not delete `infra/backup/` or the Restic scripts until a WAL-G restore has been
rehearsed against production-sized data in the real bucket.

## Where to read logs

Every service writes to its own stdout and Docker captures it, so `docker compose
logs` on the deployment host is the log source. There is no log shipper and no
external log service: nothing survives `docker compose down`, and a removed
container takes its history with it.

```sh
docker compose logs --since 30m api        # one service, recent window
docker compose logs --since 30m worker
docker compose logs --since 30m -f caddy   # follow, for a live incident
```

The API's `uvicorn` access log and its application loggers both go to stdout. The
worker configures `logging.basicConfig` in `main()` and logs `worker_started`,
`job_failed` and `worker_heartbeat_failed` there. Caddy logs to stdout too.

Two consequences worth knowing before an incident:

- **No rotation is configured.** `docker-compose.yml` sets no `logging` driver or
  `max-size`, so logs accumulate in Docker's default `json-file` store until the
  disk fills. A long-lived deployment needs a `logging` block with `max-size` and
  `max-file`, or a host-level rotation — neither is in place today.
- **Nothing is shipped off the host.** A host that is lost takes its logs with it,
  which is the case where they matter most. This runbook can recover the database;
  it cannot recover a log.

## Recovery objective

The coordinated backup timestamp is the practical RPO. RTO depends on the
database size and Restic repository throughput; measure it in a scheduled
restore drill rather than treating it as a guaranteed constant.
