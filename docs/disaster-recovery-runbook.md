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

The coordinator stops the Pycil stack, restores the shared dump, then starts the
Lexi-domain and Pycil migration gates before API/worker. Before routing traffic,
verify Pycil's `/health/ready`, perform one authenticated read, and record the
drill result and recovery time.

## Recovery objective

The coordinated backup timestamp is the practical RPO. RTO depends on the
database size and Restic repository throughput; measure it in a scheduled
restore drill rather than treating it as a guaranteed constant.
