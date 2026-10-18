# VPS delivery

[compose.yaml](compose.yaml) owns the VPS application topology. It is separate
from [local Compose](../local/compose.yaml). API, migration and the native Taskiq
worker consume the same published image; the two API slots retain independent
digest references. Only Caddy publishes a host port, TCP 443.

The starting topology is **2 API containers / 1 worker execution process /
4 concurrent jobs per worker**. The controller checks and routes both API replicas
in each slot. Further tuning requires representative load measurements.
With two replicas per blue/green slot, API overlap is four containers.

Production is running at `https://api-pycil.qninhdt.com`, with the Vercel frontend
at `https://pycil.qninhdt.com`. Bootstrap on 18 October 2026 verified both APIs,
native worker startup, real Clerk-authenticated account reads, telemetry ingestion
and independent restoration of an encrypted production backup. Live two-replica
traffic switching and rollback passed with the same immutable application image;
this does not establish compatibility between different code revisions or drain
under job load. Automatic GitHub delivery remains disabled
until the reviewed controller/configuration is published on the trusted branch.

## Files and responsibilities

| File | Responsibility |
| --- | --- |
| `compose.yaml`, `postgresql.conf`, `init-application-role.sh` | Native services, quotas, private networks and a separate non-superuser application role |
| `Caddyfile`, `upstream.caddy` | Static origin TLS, ingress/streaming policy and initial blue upstream |
| `deploy.sh` | Host lock, immutable release validation, candidate checks, traffic switch and application rollback |
| `smoke.py` | Bounded HTTP readiness, reference search and authenticated profile checks |
| `observe.py` | Read existing Prometheus HTTP metrics during the observation window; no collector or SDK |
| `session-token.py` | Use Clerk's native token endpoint for an existing dedicated smoke session |
| `cd.sh` | SSH entry point; temporary registry authentication and fixed production paths |
| `tests/` | Repeatable smoke and metric-check regression tests; no running infrastructure required |

The Python HTTP checks execute inside the candidate image, using its existing
stdlib and network access. Token minting runs on the host. These are short-lived
deployment commands, not services or custom worker machinery.

## Host contract

Keep the operational files at `/opt/pycil` stable for bootstrap and operator commands. Require
Python 3, Docker with Compose v2, Bash, jq, GNU timeout, flock and sha256sum. Use
the existing SSH operator with sudo; do not expose Docker's API or application
store ports. Host firewall ingress remains SSH plus Cloudflare-restricted HTTPS.

Provision these private files/directories outside Git:

| Path | Ownership / purpose |
| --- | --- |
| `/etc/pycil/runtime.env` | Root-only canonical DB/Redis URLs, separate PostgreSQL admin password, Clerk/provider secrets, CORS origins and private OTLP destination; see [configuration](../../docs/backend/configuration.md) |
| `/etc/pycil/tls/{origin.crt,origin.key}` | Certificate matching `api-pycil.qninhdt.com`; root-readable key; Cloudflare Full (strict) |
| `/etc/pycil/smoke-session` | Root-only existing active Clerk session ID for an operator-controlled ordinary Pycil account; use a dedicated account for unattended delivery |
| `/opt/pycil/bin/aws_signing_helper` | Shared official host binary, mounted read-only only into AWS consumers |
| `/etc/pycil/aws/wal-g/{config,producer.crt,producer.key}` | WAL-G-specific Roles Anywhere identity and credential-process profile, UID/GID 999, private files mode 0400 |
| `/etc/pycil/walg-producer` | Backup database credentials and public encryption key, UID/GID 999; contains no recovery private key |
| `/srv/pycil/{postgres,redis}` | Durable store bind mounts; official entrypoints initialize ownership on an empty directory |
| `/srv/pycil/search` | Durable Tantivy directory, UID/GID 10001 |
| `/srv/pycil/reference.jsonl.gz` | Verified reference artifact, read-only in the migration container |
| `/srv/pycil/deploy` | Root-only deployment state, retained across checkouts |
| `/srv/pycil/backup/{verification.json,verification.sha256}` | Independent successful recovery evidence and its reviewed SHA-256 (hex only) |

The application DB role must differ from `pycil_admin`. Its password comes from
`DB_URL`; it owns the application database but has no superuser/create-role rights.
The initial role script runs only for an empty PostgreSQL data directory. Never
reinitialize an existing directory to repair roles or migrations.

Verify both Cloudflare edge coverage for the API hostname and origin TLS.
An origin certificate alone does not establish edge coverage. Caddy uses supplied
certificates; it does not obtain or renew them in this topology.

The backup image uses official PostgreSQL and WAL-G artifacts. The shared AWS
signing helper is installed on the host and mounted read-only into AWS consumers.
No locally maintained upstream fork is used. On 18 October 2026 the operator accepted
unresolved findings where no patched official artifact is available. The exact
CVE/package versions are recorded in the shared [Trivy policy](../../.trivyignore.yaml);
retain the unfiltered scan and reassess on every image or binary update. These
exceptions do not claim the affected code is fixed or unreachable. Both API and
backup scans use this policy; each entry is limited to exact package versions.

The installed helper is the official Linux x86-64 release 1.8.5, verified SHA-256
`beec9ed1c492d93db809890f16713e3556353294b823c2184ad4e891f1b2b54d`.
The AWS config uses native `credential_process`; the helper obtains temporary
credentials when requested. It is not a service or a custom refresh loop. A future
API/worker AWS consumer gets its own certificate/profile/role and the same binary
mount; Fargate instead uses the ECS task role with the unchanged application image.

WAL-G writes only the live cluster generation under `vps/<system_identifier>/pg18`
in the private backup bucket. The producer cannot delete objects. The native
`pycil-backup.timer` schedules a full backup at 02:30 UTC each day; PostgreSQL
archives WAL continuously. Inspect `systemctl status pycil-backup.timer`,
`journalctl -u pycil-backup.service`, and the provisioned backup dashboard.
Producer certificates require renewal independently of temporary credentials.
The CA key, encrypted recovery private key and its passphrase stay off the VPS
under the operator's private `~/.local/share/pycil/production-backup` directory;
maintain a separate protected custody copy. Current bootstrap proves recovery
from one encrypted base and its required WAL, not arbitrary-time PITR or a paid
model call. No production prune scheduler is active; retained storage will grow
until a separate reviewed maintenance identity and coherent WAL-G pruning are enabled.

Smoke authentication uses [Clerk's existing-session token endpoint](https://clerk.com/docs/reference/backend/sessions/get-token).
It mints immediately before the authenticated check and pipes the token over
stdin. Never save a bearer token in the release manifest, command arguments or
GitHub logs. An expired/revoked session blocks deployment until the operator
reauthenticates the controlled account and replaces its session ID. This route
does not create a production user or bypass application authentication.

## Bootstrap and subsequent releases

Bootstrap is an operator operation after the gates above pass, not an automatic
fallback when an active deployment is missing. Validate configuration with:

```sh
python3 scripts/compose.py --env-file /etc/pycil/runtime.env \
  --file infra/vps/compose.yaml config -q
```

Use one trusted `release.json` from successful publication. It must contain
`source_sha`, `platform`, `manifest_digest` and the matching GHCR digest reference.
Initialize `blue.json` and `green.json` in the state directory to this same
manifest, `active` to `blue`, and `upstream.caddy` from this directory's template.
Export both slot images and `RELEASE_IMAGE` from the manifest when invoking
Compose manually. Start stores, run the explicit migration/import command once
(`python -m pycil.app.migrate --reference /app/data/reference.jsonl.gz`), and only
then start blue, worker and Caddy. Prove readiness, authenticated smoke, telemetry
and backup/recovery before enabling CD. Never run a blanket `compose up` over
both slots or delete volumes as part of delivery.

For subsequent releases, export the host paths from [cd.sh](cd.sh), set
`VERIFIED_BACKUP_SHA256` to the reviewed evidence checksum, and run:

```sh
make vps-deploy RELEASE=/private/path/release.json
make vps-rollback
```

Make and the CD entry point impose a 30-minute deadline. Direct invocation of
`deploy.sh` must receive an equivalent outer deadline. Both commands need
authorized GHCR pull access. The CD entry point uses a scoped
job token through stdin and a temporary Docker config under `/run`, removed on
exit. A backup checksum only identifies the supplied evidence; the script does
not establish its freshness, provenance or recoverability. The operator must
verify that it covers this production database and the agreed recovery window.

Delivery performs these steps under a single host lock:

1. Validate the recorded active container, routing/config, digest/source/platform,
   telemetry reachability, and at least 2 GiB available RAM / 5 GiB free disk.
2. Pull the inactive digest and compare both images' Alembic heads. A different
   head is rejected: current application startup requires an exact head, so such
   a release needs a separately planned maintenance procedure. Matching heads
   still require review of queue payload/result, reference and index compatibility.
3. Run the bounded migration, start only the inactive API, require five ready
   responses, then check reference search and a real authenticated account.
4. Validate/reload Caddy, replace/drain the native worker, and perform HTTPS reads
   for five minutes. From minute two, check candidate metrics every minute using
   a trailing two-minute window. Require fresh, nonempty request observations;
   reject HTTP errors above 2% when at least 50 requests occurred in that window.
5. Commit slot/active/previous records and stop the retired API. Database contents
   and successful migrations are preserved on every failure/rollback path.

The RED check covers HTTP errors and reports mean duration; it does not enforce a
latency SLO or guarantee every request/long stream/job finishes. The existing
Uvicorn/Taskiq shutdown budgets remain authoritative. A failed stop after release
commit must not stop the new active API. Diagnose and stop the retired slot alone.

The CD entry point pins `COMPOSE_FILE` to the production manifest.

The controller refuses ingress policy changes until the mounted Caddyfile matches
the reviewed source. Apply ingress changes separately with validate/reload; bind
mounts belonging to stores/Caddy must come from the stable bootstrap checkout.

## Interrupted deployment recovery

Ordinary command failures before switch stop the candidate while the active
route/worker stay unchanged. Failures after switch restore the saved route and old
worker; the candidate stops only after restoration succeeds.

`pending` means the switch was attempted but acceptance was not committed. A host
crash/SIGKILL can bypass shell traps. Both deploy and rollback refuse to guess in
this state. Inspect `active`, `pending`, both slot manifests, container image IDs,
worker startup logs, and Caddy's private admin config **inside its container**.
Do not delete `pending` to bypass this investigation.

Using the stable operational files and recorded slot images, start/verify the recorded
active API, restore `previous.caddy` to `upstream.caddy` with an atomic rename,
validate/reload Caddy, and restore the worker using the recorded active digest.
Verify routed readiness/search/auth and native worker `Listening started.` before
removing `pending` and stopping the unsuccessful candidate. If restoration fails,
keep both APIs available and investigate; do not restore over live PostgreSQL or
downgrade Alembic. Retain failure logs and state for diagnosis.

## GitHub and frontend

The `vps` job in [Deploy](../../.github/workflows/deploy.yml) depends on successful
trusted-main publication. It uses the tested checkout and that run's release
artifact, pinned SSH host keys, and this controller. Configure repository variable
`VPS_DEPLOY_ENABLED=true` only after bootstrap acceptance; set `VPS_HOST`,
`VPS_USER` and environment `vps` secrets `VPS_SSH_KEY`, `VPS_SSH_KNOWN_HOSTS`.
The GitHub plan does not currently provide an independent required reviewer;
the environment name alone is not a human approval boundary. Native workflow
concurrency plus the host lock serialize delivery. AWS runtime delivery is separate.

Vercel deployment is also separate. Verify its production
`NEXT_PUBLIC_PYCIL_API_URL` and `NEXT_PUBLIC_DATA_MODE=live`, Clerk
instance and CORS origin, then deploy compatible backend before frontend. Keep
the previous frontend deployment available. HTTP API smoke here does not prove
browser parsing or Vercel configuration; those require the real frontend journey.

Run the reusable checks with
`python3 -m unittest discover -s infra/vps/tests -v`.
