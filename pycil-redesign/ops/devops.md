# ops/devops

Docker Compose, one VPS, one environment. Decisions `O1`–`O12`.

## 1. Shape

```text
infra/
├── compose.yml          the stack
├── compose.prod.yml     override: images by digest, restart policy, limits
├── .env.example         every variable, documented, no real values
└── caddy/ · centrifugo/ configuration, mounted read-only
```

One compose file plus a production override (`O1`). No staging stack (`A8`) — a
second environment nobody operates loses to one that is, and it costs a second way
for the stack to boot.

A second compose **project** on the same host is how a fresh-schema rehearsal runs
beside the live stack. That is why every host port is parameterised (§4): a
hardcoded port makes the rehearsal and the live stack mutually exclusive.

## 2. Services

```text
caddy            80 · 443       TLS · routing · the only published ports
web              internal       Next.js, UI only
api              internal       FastAPI + outbox relay
agent-worker     internal       agent runs, own queue, long drain
domain-worker    internal       jobs, own queue, short drain
scheduler        internal       periodic only
centrifugo       internal       realtime
postgres         internal       volume · public + lexi schemas
redis            internal       volume · broker, cache, coordination, engine
migrate          one-shot       blocking gate, not a long-lived service

profile: backup  on demand      coordinated dump and restore
```

Only the edge publishes ports; everything else is reachable on the internal network
only. That is part of the trust argument in
[../cross-cutting/security.md](../cross-cutting/security.md) §6.

**The web app is deployed here** (`O3`), behind the edge, sharing the API origin.
Any document claiming an API-only stack is stale — same-origin is required by `H1`.

Four processes share one image (`api`, both workers, `scheduler`): same code,
different entrypoint and queue.

## 3. Volumes

```text
postgres-data
redis-data          append-only persistence on: the broker's queue is durable work
caddy-data          certificates
```

Postgres is the only stateful component that matters. Redis holds nothing canonical
(`A4`), but its persistence is on because a broker queue is durable work in flight
— losing it means losing dispatch, and the reconcilers then have to re-derive
everything.

## 4. Configuration

Every value from the environment (`R1`). Nothing derived from a hostname, a
container name, or a replica index — that is what keeps "an orchestrator is a
config change" true rather than aspirational.

**A service with a missing required variable fails to boot** (`O6`), reporting
**every** missing name at once. A container that starts and then rejects every
request looks healthy while doing nothing, and fixing one variable per restart is
how a ten-minute deploy becomes an hour.

A **placeholder value is rejected as if absent.** A copied template must not reach
production silently.

Host ports are parameterised and loopback-bound: the database, cache, API, and web
debug ports exist for a shell on the host, not for the internet.

Two configuration traps worth writing down because both fail **silently**:

| Trap | Consequence |
|---|---|
| The realtime gateway **warns rather than fails** on an unrecognised configuration variable | A misspelt key is inert and the default applies. A wrong subscribe-proxy secret means the API rejects every authorization call and **no channel can be subscribed at all** — with nothing in the failure path saying why. After any rename, read the startup log for unknown-variable warnings |
| The gateway does not interpolate variables inside its own config file | Its secrets must arrive as mapped environment variables, not as placeholders in the mounted file |

## 5. Secrets

Injected by environment or file secret; never in an image, never in the repository.
Which process holds what is the control (`O6`, security §6):

```text
api              token signing + previous, refresh pepper, OAuth client secret,
                 realtime signing secret, internal proxy secret
centrifugo       realtime signing secret, internal proxy secret
workers          model provider keys
scheduler        neither credentials nor provider keys
```

The API cannot spend money; a worker cannot mint a session.

## 6. Deploy

```text
1  build once in CI, push by digest                          (N8)
2  on the host: pull those exact digests
3  run migrations to completion                              ← BLOCKS
4  start the workers and the realtime gateway, health-gate them
5  start the API, health-gate it
6  start web and the edge
7  smoke: the golden journey
8  on failure: previous digest, up again
```

**Build once, promote by digest.** Rebuilding at deploy means the artefact tested is
not the artefact deployed. A tag can be moved; a digest cannot.

**Migration blocks** (`O4`). It applies the dictionary library's schema, **asserts
the installed head matches the expected one**, then applies the application schema.
That assertion is what stops a half-migrated database from booting. Nothing takes
traffic against an unmigrated schema — a healthy database is not a migrated
database.

The chain starts from **one squashed baseline** (`A6`): pre-production with no data
to preserve, and the previous chain had accumulated three churn cycles plus fourteen
refuse-only reversals. Normal incremental migrations resume from it. Every schema
change also touches the model aggregator (`A7`) — that is a step in the procedure,
not a surprise.

The migration runs in the **new** image **before** anything swaps, so a failure
costs nothing and the old containers are untouched.

**Workers start before the API** (step 4). Jobs are written by the API and consumed
by a worker, so starting the API first opens a window where work is enqueued that
nothing can consume at the current schema version.

A pre-deploy database snapshot is taken and a small number retained.

Two preflight checks run before anything swaps: the realtime configuration and the
edge configuration are both validated by their own tools. Both are mounted files
that fail at runtime rather than at parse time otherwise.

Rollback is the previous digest. A migration that cannot be reversed is written to
be **forward-compatible with the previous image**, so a rollback does not require a
schema reversal. Pre-production this is trivial; it stops being trivial the moment
there is data, which is why the habit starts now.

## 7. Health

```text
liveness    the process is alive
readiness   dependencies reachable AND required configuration present
```

Distinct, because they answer different questions (`O8`). A process alive but
unable to reach the database must not receive traffic.

API readiness checks: database, cache, **a live worker heartbeat**, and the realtime
gateway. The heartbeat is what makes "the API is up but nothing is being processed"
visible.

**The heartbeat threshold must exceed the slowest legitimate task plus the poll
interval** (`O8`), or a slow-but-healthy worker is killed mid-task. This is also
why periodic work runs outside the worker pool (`F9`): a heartbeat that cannot get
a slot reports a failure that is not happening.

## 8. Graceful drain

```text
SIGTERM
├── stop claiming new work
├── in flight: finish, or checkpoint and release the lease
├── the outbox relay finishes its current batch
└── exit
```

`stop_grace_period` **exceeds the longest acceptable drain** (`O9`). The two workers
differ by an order of magnitude here — an agent run may take minutes, a domain job
seconds — which is one of the reasons they are separate processes (`G3`). One
process would force one window for both, and the window would have to be the long
one.

Lease and fence recovery exists as the **failure** path, never as normal load
balancing. Drain is what keeps a deploy from looking like a fleet of crashes.

## 9. Backup

```text
postgres       scheduled dump, retained, restore REHEARSED not assumed
```

One dump covers **both schemas** (`O10`). Pycil stores opaque ids owned by the
dictionary schema with no foreign key across (`A5`), so a schema-selective dump
restores to a broken referential state — rows pointing at senses that no longer
exist.

The dump is taken with the **write path stopped** so it is one consistent point,
and the services are restored afterwards **even if the dump failed**.

**Restore is rehearsed, not assumed.** An unverified backup of the only stateful
component is the largest single operational risk in this deployment, and a restore
path that has never run is a restore path that does not work. The rehearsal is a
second compose project on the same host restoring into an empty database — which is
what all those parameterised ports are for.

Any schema or data change is taken **after** a verified backup.

## 10. Runbook

`O12`. Situation → first move. This table is the knowledge that disappears when it
is not written down.

| Situation | First move |
|---|---|
| Jobs queued, none running | A worker is down, or every worker is at its concurrency limit |
| Jobs stuck running | Lease expiry and the reaper. **If the reaper is not running, nothing recovers** |
| Realtime silent, HTTP fine | Is the gateway up? Is its Redis engine reachable? Is realtime-token minting working? Check the gateway's startup log for unknown-variable warnings |
| Nothing arriving over realtime, jobs completing | The outbox relay. Query the oldest unpublished row: a relay that died leaves them accumulating with the API still committing |
| Readiness failing, everything looks fine | The worker heartbeat. Either a worker is down, or periodic work cannot get a slot |
| A learner reports a wrong verdict on free text | The rubric grader. This is also the measurement `P12` is waiting for — record it |
| Credit balance looks wrong | The period may not have rolled: it rolls **lazily on the next debit** (`P9`), so an idle account shows last period's usage until it spends |
| Agent replies are slow, grading is fine | The agent worker's concurrency limit, or a provider. They are separate queues on purpose (`G3`) |
| Model cost rising with no traffic rise | Cache reads. Always-zero means the prompt prefix broke — a timestamp in the system prompt, a changed tool list, non-deterministic serialisation (`G14`) |
| Disk filling | Which volume: Postgres, Redis persistence, or certificates |
| Deploy aborted at migration | Correct behaviour. The old containers are untouched; read the migration output |
| Production refuses to start | A required variable or a placeholder value. The boot error names **every** missing one (`O6`) |

## 11. Observability

There is none (`O7`). Structured logs to stdout, and stable error codes inside
them.

Stated as a cost rather than a gap:

- three values in this folder stay `uncalibrated` (`P12`);
- a dead outbox relay is invisible until a client notices missing updates — the
  runbook query above is the mitigation, not a metric;
- concurrency limits are set by judgment, not by queue depth (`G4`).

The seam is logs to stdout plus stable codes: a scraper, a trace backend, or an
error tracker attaches without a code change. Seven processes for one operator is
the cost that was refused, not observability itself.

## 12. Toward an orchestrator

Not used (`O1`). What keeps it a configuration change rather than a rewrite:

```text
every value from the environment
no host paths
no state inside a container
logs to stdout
readiness distinct from liveness
graceful SIGTERM drain
one process per container
no dependency on container names or start order beyond declared gates
```

Every item is already required by `R1`, so orchestrator readiness is a
**consequence** rather than separate work.

## 13. Invariants for the checklist

```text
a missing required variable fails the boot, naming every missing one
a placeholder value is rejected as if absent
migration blocks: no container takes traffic against an unmigrated schema
the migration asserts the dictionary schema head before applying the application schema
readiness fails when the worker heartbeat is stale
readiness fails when a dependency is unreachable
the heartbeat threshold exceeds the slowest legitimate task
SIGTERM drains in flight work rather than dropping it
the realtime path is neither compressed nor buffered at the edge
one dump restores both schemas to a consistent state
restore into an empty database reproduces a working stack   ← rehearsed
a deploy aborts before swapping when migration fails
```
