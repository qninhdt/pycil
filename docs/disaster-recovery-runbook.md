# Product backup and restore runbook

Pycil and Lexi have separate PostgreSQL databases. Back up and restore them as
one product unit because Pycil stores opaque IDs owned by Lexi.

## One-time host setup

On the deployment host, create a Restic password file for each compose project
outside source control (for example, `infra/backup/restic.password`) with mode
`0600`. Configure the same durable `RESTIC_REPOSITORY` and password material
for the scheduled backup environment. Set `LEXI_PROJECT_DIR` to the absolute
Lexi checkout path when it is not `/opt/lexi-ai`.

Do not commit either password file or cloud credentials. The compose backup
profiles deliberately require them at runtime.

## Backup

Run from the Pycil checkout:

```sh
RESTIC_REPOSITORY='b2:bucket/product' ./scripts/backup-product.sh
```

The coordinator temporarily stops both API/worker write paths, assigns one
UTC `BACKUP_ID`, then writes `lexi-<id>.dump` and `pycil-<id>.dump` to Restic.
It restarts the services even if a backup command fails. Schedule this command
from the host scheduler with a monitored failure alert; Restic retention is
applied by the Pycil backup container (7 daily, 4 weekly, 6 monthly).

## Restore drill

Restores are destructive and must be performed in an isolated environment
first. Select the exact coordinated ID, then run:

```sh
BACKUP_ID=20260722T000000Z \
RESTIC_REPOSITORY='b2:bucket/product' \
./scripts/restore-product.sh
```

The coordinator stops both stacks, restores Lexi first, runs its migrations,
then restores Pycil and starts its migrations/API/worker. Before routing
traffic, verify Lexi's readiness endpoint and Pycil's `/health/ready`, perform
one authenticated read, and record the drill result and recovery time.

## Recovery objective

The coordinated backup timestamp is the practical RPO. RTO depends on the
database size and Restic repository throughput; measure it in a scheduled
restore drill rather than treating it as a guaranteed constant.
