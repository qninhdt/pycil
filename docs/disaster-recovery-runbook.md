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
