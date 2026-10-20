# VPS capacity and endpoint tuning

Status: stopped at the user's request on 21 October 2026; wrap-up only.
The measured configuration is retained. Full endpoint optimization is not complete.

## Outcome and acceptance

Use the dedicated 8-logical-CPU / 8-GiB VPS effectively for Pycil. Select API
instance count N, worker process count M and per-process async concurrency K
from comparable measurements, rather than retaining the provisional 2/1/4.
Cover each production endpoint family, including search, library, account,
study reads/writes/preparation, jobs and assistant streaming. Optimize proven
bottlenecks, validate correctness and deploy the accepted configuration.

Acceptance requires an endpoint coverage ledger, comparable topology/worker
results, measured latency/throughput/errors/CPU/RAM/pools/queue delay, passing
regression checks, production readiness, and a reproducible rollback/deploy path.
Highest tested capacity must not be described as an absolute maximum.

## Constraints and non-goals

- Preserve real authentication, ownership, schema, durability and user data.
- Only the dedicated performance account may receive benchmark writes/jobs.
- Native Compose, Caddy, Taskiq and existing k6 runner own their lifecycles.
- No replacement worker framework, new paid infrastructure, fabricated provider
  performance, or weakened thresholds. Separate cached preparation throughput
  from paid generation and provider latency.
- Stop a load on sustained SLO/resource failure; preserve failed evidence.
- Keep rollback and host/backup/monitoring headroom under the measured peak;
  do not size by adding idle RSS or by exhausting RAM intentionally.
- Preserve unrelated dirty work. Keep private fixtures and tokens ignored.

## Execution

1. Revalidate live source, limits, resource use, pools and all endpoint families.
2. Benchmark current cached release, then compare N=1/2/4/6 where memory and DB
   connection budgets permit. Equal workloads, warmups and route mixes; repeat
   close candidates. Record origin and edge separately where permitted.
3. Compare native worker M=1/2 and K=4/8/16, extending only if evidence warrants.
   Measure real cached preparation and bounded genuine generation separately;
   ensure no active task is interrupted when changing configuration.
4. Profile slow endpoints, fix causes with focused tests, and repeat equivalent
   measurements. Include API reads under worker contention.
5. Implement the selected topology in Compose and the existing deploy controller;
   validate blue-green overlap, authenticated smoke and sustained mixed load.
6. Update owning operational docs and retain sanitized measurements and the
   endpoint ledger. Revoke dedicated sessions and stop owned generators/tunnels.

## Evidence and rollback

The selected measured topology is six single-process API containers and two
single-process worker containers, each worker accepting four concurrent jobs.
Application/checkpoint pools remain 3/2 with no application overflow. The proposed
4/1 comparison was not activated. Raw lesson-21 comparator evidence remains
frozen; these cached-production capacity experiments do not replace it.

The 200-RPS mixed read plateau completed with zero errors/drops, but individual
read routes and concurrent library mutations missed the latency targets. Those
failures remain in the [endpoint ledger](reports/endpoint-coverage.json).
No claim of all-endpoint SLO compliance or absolute maximum capacity is made.
Further optimization, additional pool comparisons and rare-route load repetitions
are deferred by the user, rather than marked as passed.

Sanitized results: [measurements](reports/measurements.md). Execution detail:
`devops-course/lab/capacity-tuning/` (private data excluded).
Previous read-query experiment remains independently frozen in lesson21.
Initial release: source `1348e6c5346ebc905a5cdf16065b26f53366f627`, image
`sha256:79ca71d697a5edf51d090ddca558c11146746747c06f677784440c83c00b5a85`.
Initial routing: two green APIs; native worker 1 process / 4 async tasks.
Before experiments, retain original routing/config hashes. Validate Caddy before
atomic reload, restore routing on failure, drain worker tasks before replacement.
No database downgrade or production dataset restore is part of rollback.
