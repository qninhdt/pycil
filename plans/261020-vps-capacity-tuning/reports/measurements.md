# Capacity measurements — 20 October 2026

Status: topology selected and applied; further endpoint tuning stopped at the user's request.
Source `1348e6c5346ebc905a5cdf16065b26f53366f627`, application image
`sha256:79ca71d697a5edf51d090ddca558c11146746747c06f677784440c83c00b5a85`.
Use the [execution plan](../plan.md) for full acceptance scope. Private raw evidence
is retained in ignored `devops-course/lab/capacity-tuning/private/`; it contains
credentials/account identifiers and must not be committed or archived publicly.

## Read capacity

Authenticated real 60/20/20 word/account/progress workload, real Cloudflare HTTPS
path, native k6 2.3.0 on an independent machine. Identical rate executors isolate
50/100/200/400 RPS, 15-second ramps then two-minute plateaus. Abort thresholds
remain p95 <300 ms, p99 <800 ms, errors <1%, with zero drops required. Failed
runs remain failed; the aggregate percentile can hide a failing stage.

| Run | APIs / Caddy CPU ceiling | Full 200-RPS plateau | 400-RPS observation | Whole run |
| --- | --- | --- | --- | --- |
| `n2-read-guarded` | 2 / 0.25 | Aborted: p95 314.63 ms including ramp | Not started | Exit 99 |
| `n2-caddy1-read` | 2 / 1 | 23,998 requests; p95 269.86, p99 426.13 ms; zero errors/drops | 2,761 errors in 7,038 completed requests; 1,726 drops; aborted | Exit 99 |
| `n4-caddy1-read` | 4 / 1 | 23,997 requests; p95 224.17, p99 362.31 ms; zero errors/drops | 27,377 correct responses; stage p95 329.94 ms including ramp; 135 drops; aborted | Exit 99 |
| `n6-caddy1-read` | 6 / 1 | 23,987 requests; p95 235.32, p99 437.12 ms; zero HTTP errors, 10 drops | Full 47,997-request plateau; p95 222.11, p99 319.94 ms; zero HTTP errors/drops | Exit 99: drops at 200 RPS |

Original Caddy cgroups showed average 0.225 core against a 0.25-core quota and
49.96 seconds throttled in a 173-second late-100/200-RPS interval. Its 1-core
ceiling is now persisted in the owning Compose locally and on the VPS. It is a
ceiling, not a reservation. Four-API measurement sampled at least 58.28% host
available memory; generator peak sampled CPU was 30.13% of one core against a
1.5-core quota. This rules out sustained generator resource saturation, not every
possible brief scheduling/network stall. Highest passing plateau is not an
absolute server maximum.

The six-API run completed 99,061 correct business requests and recovery without
interruptions. Its ten dropped iterations occurred within 170 ms at
01:18:53–54 UTC during the 200-RPS stage. All latency/error thresholds passed,
but the whole run remains failed because the zero-drop gate did not. A repeat
must resolve that transient; a passing 400-RPS segment cannot erase it. In an
86-second steady-400 native cgroup interval the six APIs together used 4.03
cores, Caddy 0.484 and PostgreSQL 0.448. This is evidence for testing six APIs
with a safe connection budget, not final rollout approval.

The six-API routing window was explicitly stopped after the run. Native Caddy
admin configuration confirmed exactly the original two upstreams, the on-disk
SHA matched the original, and the routing helper exited 143 through its restore
trap. No source/image/worker changes occurred during the comparison.

Historical telemetry during the two-API 400-RPS overload shows failed application
pool acquisitions while executed queries remained successful. Native k6 recorded
231 HTTP 500, 2,518 HTTP 503 and 12 transport failures in that stage. Pool failure
is a verified part of the overload; the existing production logs still do not
prove the exception type behind every HTTP 500. Do not blanket-remap all errors.

Temporary routing restored the exact original two-API upstream SHA
`45734337dc5502cb816a55536f02fc8bd51af2816f04b888898e06adc20e3707` after the
four-API run. Public readiness was 200. Additional replicas remain temporary.

The first one-API comparison was stopped by the resource guard after 10,700
correct responses: Tempo exceeded 90% of its 384-MiB quota for 30 seconds while
host available memory remained above 50%. Its full 50-RPS plateau had p95
183.87 ms / p99 289.43 ms; 100 RPS was incomplete. This is an aborted run, not
an API capacity result. Tempo 3.1.0's native configuration verifier accepted
`memory.automemlimit_enabled: true` under the same 384-MiB quota and reported
GOMEMLIMIT 322,122,547 bytes (default 0.8 ratio). The production Tempo restart
confirmed that value and readiness. A repeated one-API run then reached its
native latency abort at 100 RPS, not the memory guard: full 50-RPS plateau
p95 174.90 / p99 264.27 ms, incomplete 100-RPS plateau p95 459.21 / p99
1,056.80 ms. All 13,416 completed responses include ten HTTP failures; zero
drops and 22 interrupted iterations. Tempo peaked at 36.48% of its quota,
with minimum host available memory 53.08%.

The previous six-API ten-drop interval was investigated separately. Between
01:18:51–57 UTC, the generator saw waiting/receiving delays over one second;
992 retained backend completion logs in that window had p95 26.39 ms and
maximum 59.59 ms. These independently filtered samples do not identify every
request end to end, but rule out a sustained multi-second application stall
across that window. Network/edge/generator stalls remain possible; the run
still fails the zero-drop gate.

A new six-API comparison uses application pool size 3 and checkpoint maximum
2, with the same source/image, zero overflow and timeouts unchanged. This
bounds twelve API processes during blue-green to 60 connections, rather than
96 under the previous 5+3 pool sizes; worker, monitoring, administration and
PostgreSQL reserves still need their separate budget. Both host policy files
were backed up privately, all six APIs restarted sequentially and readiness
verified before starting the new run. Original hash `55e8b3885a0b9093bdcfe8b1ac24a083053eae468227bd2474b4cdd1663e27bf`;
candidate hash `6bdf9e9acfddd0241aa61e865fc3e0cd5aff4a5e0b0c6e45cd37321e3de652d8`.
Selection remains pending its results and overlap proof.

## Worker comparison

Only native Taskiq CLI flags and Docker CPU quotas changed. Cached jobs each
prepare 16 real senses, one question per sense. Each batch uses 32 independent
owned decks; process caches are warmed before the comparable batch. Polling is
at two seconds, so client makespan includes API/poll delay. Queue and execution
measurements come directly from native Taskiq result labels/execution_time.

| Processes × concurrency | Total CPU quota | Cached batch observed seconds | Median queue seconds | Median execution seconds | Failures |
| --- | --- | --- | --- | --- | --- |
| 1 × 4 | 1 | 5.128 | 1.160 | 0.260 | 0/32 |
| 1 × 8 | 1 | 5.322 | 1.424 | 0.530 | 0/32 |
| 1 × 8 | 2 | 3.232 | 0.858 | 0.455 | 0/32 |
| 2 × 4 | 2 | 3.083 | 0.220 | 0.240 | 0/32 |

The one-process CPU-2 test retained the same warm process; paired cgroups showed
no additional throttled periods/time during that interval. The two-process
container used 460.9 MiB after warmup with no memory-limit/OOM events. These are
bounded batch observations, not a sustained jobs/second maximum. Repeat close
candidates and validate mixed load before final selection.

Each genuine-generation job required new artifacts for a different real sense;
provider/model/quality/timeout policy stayed unchanged. Prompts differ between
batches, so provider execution variance is not a causal process-count comparison.

| Processes × concurrency | CPU | Batch observed seconds | Median queue seconds | Median execution seconds | Failures |
| --- | --- | --- | --- | --- | --- |
| 1 × 4 | 1 | 107.909 | 13.206 | 50.785 | 0/8 |
| 1 × 8 | 1 | 116.343 | 0.196 | 56.335 | 0/8 |
| 2 × 4 | 2 | 120.816 | 0.005 | 73.315 | 1/8 |

The failed job logged `ProviderTimeoutError` at the existing 120-second deadline;
all jobs settled, fixture parents were removed and learning preferences restored.
No automatic paid retries or model/quality reductions were introduced. Higher
provider concurrency is not justified by a failed batch. Singleflight source
verification confirms completed successes/failures permit a fresh submission;
only in-flight matching jobs are reused.

## Application read calibration

Ten equally weighted real reads cover node detail/senses/listing with summaries,
discovery, public profile, usage, activity/schedule, assistant models/conversations.
Both native two-minute 1-RPS smoke runs passed 121 correct requests, zero HTTP
failures, drops or interruptions. With 12–13 samples per endpoint these calibrate
contracts and latency, not high-load capacity or statistically strong p99.

- After the 1/4 job batch: p95 216.34 ms, p99 310.36 ms.
- Overlapping the 1/8 batch: p95 215.62 ms, p99 428.03 ms; monitor observed up to
  eight outstanding jobs, at least 58.31% available host memory.

## Owned mutation workflow baseline

With normal two-API routing and native worker 1/4 idle, a calibration cycle and
32 cycles at concurrency four passed real library create/rename/membership/
copy/move/scoped-search/provenance/delete assertions. The concurrent run validated
299 HTTP responses; its cycle/cleanup interval was 13.43 seconds. Every new
fixture subtree and empty assistant conversation was removed. Account settings
and bio were round-tripped without changing their values; those and vocabulary
batch/context/public-lookup/checkpoint operations are smoke checks, not sustained
write-capacity measurements.

Client p95 was 566.84 ms for membership updates, 436.14 ms for scoped search,
300.09 ms for copying and 277.27 ms for moving. Other repeated mutation/provenance
routes were below 240 ms. These slow paths require further investigation.
One native sampled membership trace took 484.53 ms: its ten SQL spans totaled
under 16 ms, with a roughly 445-ms gap before the third query. The trace rules
out SQL execution occupying that whole gap, but does not by itself distinguish
Python work, event-loop scheduling or connection acquisition. No owner/visibility
lock or security check has been removed based on this observation.

## Memory and profiler checks

The existing representative cache-capacity benchmark passed: configured user-ID,
word-metadata, sense and artifact entries used about 51.15 MiB per process with
independently decoded DTOs. This is not a bound on arbitrary content size.
A separate native py-spy diagnostic had 343 valid stacks and 314 nonblocking
unwind errors; it is qualitative only and does not justify rewriting native
SQLAlchemy/asyncpg or Pydantic serialization. No profiler ran during comparisons.

## Six APIs with bounded rollout connection budget

Run `20261020T031949Z-db-read` completed all stages and recovery with the
same production image. Application pool size was 3, overflow 0, checkpoint
maximum 2 per API process. Native k6 exited 0, with zero dropped or interrupted
iterations. There were 99,072 business requests: 99,071 HTTP 200 and one
5,000.85-ms transport timeout (status 0, error code 1050) during the 100-RPS stage.
The failure remains part of the result; this is not a zero-error whole run.

| RPS | Full plateau requests | p95 ms | p99 ms | Non-200 | Drops |
| --- | --- | --- | --- | --- | --- |
| 50 | 5,992 | 174.66 | 269.33 | 0 | 0 |
| 100 | 11,992 | 189.08 | 355.94 | 1 | 0 |
| 200 | 23,997 | 210.49 | 318.50 | 0 | 0 |
| 400 | 47,998 | 222.52 | 318.29 | 0 | 0 |

All 751 recovery requests returned correct HTTP 200. Across 57 resource samples,
minimum available host memory was 54.52%; Tempo peaked at 53.50% of its 384-MiB
limit with its native automatic Go memory limit enabled. No monitoring guard
fired. The original two-upstream Caddy file hash and live admin configuration
were verified after explicitly ending the temporary routing window; its lock
was released. This supports six APIs as a candidate, pending mixed endpoints,
worker contention, rollout headroom and final-image verification.

## Bounded database overload rejection

A real PostgreSQL integration case held the only connection in a size-one,
zero-overflow pool. `/v1/me` returned generic HTTP 500 before the fix. A typed
SQLAlchemy pool-timeout handler now returns sanitized HTTP 503 `database_busy`,
with request correlation retained; releasing the connection restores HTTP 200.
Both account dependency sessions and direct word-read sessions are covered.
Other exception types retain their existing handling. This improves failure
semantics; it does not increase database throughput or prove every historical
500 had this cause.

## Still required

Remaining endpoint/write/search/stream
workloads, resource/pool/headroom validation including blue-green overlap,
selected configuration/controller changes, regression/deploy checks and cleanup.
No final N/M/K choice is claimed here.

## Worker comparison with the candidate application pool

A fresh native worker container was started for each candidate, with two CPU
cores, a 1-GiB memory ceiling, application pool size 3 / zero overflow and
unchanged provider policy. Each batch submitted 32 distinct owned preparation
jobs over the same 16 already-populated senses. Selection was AUTO in all four
runs so the three benchmark senses reviewed by the study-contract check were
still included. This is comparable within this group, not identical to the
earlier NEW-selection warm-process measurements. Every job succeeded and every
fixture subtree was deleted after settlement; preferences were restored.

| M × K | Batch observed seconds | Execution median/max seconds | Queue median/max seconds |
| --- | --- | --- | --- |
| 1 × 4 | 5.313 | 0.290 / 0.640 | 1.116 / 2.200 |
| 1 × 8 | 5.154 | 0.535 / 0.910 | 1.034 / 1.958 |
| 1 × 16 | 5.036 | 1.100 / 1.730 | 0.811 / 1.738 |
| 2 × 4 | 3.190 | 0.285 / 0.640 | 0.576 / 1.006 |

Two-second HTTP polling quantizes the batch observation; native Taskiq execution
and queue labels provide the finer measurements. Increasing K on one Python
process lengthened execution rather than improving it. M=2/K=4 is the candidate
for mixed-load and draining validation; this does not claim paid provider calls
become faster. Worker Docker grace is 330 seconds, native task wait 310 seconds
and broker shutdown 10 seconds, covering the existing 300-second job deadline.

## Study, generation and checkpoint contract probes

On the original two-API routing with pool 3 / checkpoint maximum 2:

- A real three-sense cached preparation succeeded, three reviews were applied,
  the same idempotency key/body replayed the identical receipt, and progress
  reported three studied senses. Submit/replay took 249.37/117.31 ms from the
  independent edge client. Preferences were restored and the owned deck deleted.
- One native assistant turn finished in 3.95 seconds. Four concurrent turns
  then all completed in 2.64–4.91 seconds; first text arrived in 2.38–4.78
  seconds. Each stream had RUN_STARTED/text/RUN_FINISHED, persisted both roles
  in its checkpoint and was read back before its owned conversation was deleted.
  These are bounded real-provider checks, not high-percentile LLM capacity data.
- Generating an already-consumed reference exercised the real acceptance, native
  Taskiq execution and owner-only job result without paying to regenerate an
  existing word. Acceptance took 236.16 ms and the verified result was observed
  after 395.47 ms. Cold word generation remains a different provider workload.

Full backend regression after the overload handler: 587 passed, one previously
explicitly deferred Taskiq recovery test skipped, 15 upstream deprecation warnings.

## Dictionary search saturation and measured cause

The six-API search capacity run stopped in the first 50-RPS stage: 826 completed
requests, 188 HTTP failures, 223 interrupted iterations and 75 drops. p95/p99
were approximately 5,001 ms. Later stages did not start. All six API processes
used approximately 1.05–1.34 cores each while PostgreSQL remained nearly idle;
this was a search CPU bottleneck, not evidence for increasing the SQL pool.
The original two-upstream file hash and live Caddy admin routing were verified
restored after the test.

A bounded read-only profile of the production index found 1,149 unanchored
expression patterns checked for ordinary `hello`/`hel` queries. Validation and
regex compilation dominated Python CPU; native ordinary lexical queries took
approximately 1–3 ms. No content, checkpoint, or production index was modified.
The candidate indexes a required fixed-literal anchor, intersects postings with
query character n-grams, and still validates the full pattern. No candidate cap,
ranking relaxation or query-result cache was added. A separate temporary copy
of all stored lexical documents is used for equal-result/timing checks; this is
not yet a final deployed endpoint capacity result.

The final anchor candidate was checked against 223,369 copied production lexical
documents (the metadata document was excluded). All 19 queries returned exactly
the same ordered DTOs as the existing index. Three candidate timings per query:

| Query | Existing milliseconds | Candidate milliseconds |
| --- | --- | --- |
| hello | 313.11 | 5.21–6.78 |
| hel | 146.09 | 5.97–6.11 |
| book | 158.05 | 8.36–8.62 |
| a | 1,530.11 | 15.27–17.55 |
| b | 332.42 | 17.64–20.38 |
| the | 826.34 | 37.45–39.64 |
| a book | 1,732.71 | 8.75–10.88 |

The remaining equality cases covered misspelling/no hits, expression slots,
licensed inflections, Unicode accent normalization and dotless-i matching.
Copy construction took 25.8 seconds, inside a bounded existing container; the
temporary directory was automatically deleted. These are sequential native
query timings, not endpoint percentiles or proof of concurrent capacity.


## Search release validation and deployment gate

Search commit `dbaaea89cabe3f8a25a5429ddd29718ef1460df6` passed 594 backend
regressions with one previously deferred Taskiq recovery skip and 15 upstream
warnings. Ruff lint/format and focused search, integration and telemetry checks
passed. The clean-source immutable image is
`sha256:86a7910eaad0ce55e39bf99ca78cae0e64e103c67962866642b1f90e86b1efe4`;
Trivy's existing approved-exception gate passed, with both filtered and complete
findings retained privately. No vulnerability exception was added.

The first native blue-green deployment correctly aborted before switching traffic
because the existing operator smoke session expired. Its candidate APIs stopped;
the previous green release remained routed. The retry uses the existing dedicated
benchmark session through a temporary root-only `/run` session file, without
changing `/etc/pycil/smoke-session` or bypassing authenticated smoke. That durable
operator session still needs replacement before a future operator deployment.

Sixty host-memory samples during candidate index construction and rollout overlap
showed at least 57.86% available RAM. The container selector in that sampler
returned no series, so it provides host-memory evidence only, not per-container
memory evidence. Native Docker stats separately confirmed healthy API containers
and a two-process worker; final six-replica overlap validation remains pending.


The search release committed the native blue slot, recorded green as previous,
removed pending intent and stopped both old green APIs. The observing SSH
transport remained stale after the remote controller and wrapper exited; native
process/state inspection confirmed completion before terminating that owned local
SSH transport. No deployment retry was started from the transport timeout.
Four temporary additional APIs use the same new image for comparable N=6 load.

The first new search run did not start k6: the monitoring SSH tunnel had actually
terminated with connection reset. Its preflight failure is retained separately.
After confirming the old tunnel handle terminal and its port unbound, a new owned
keepalive tunnel was opened on the same port and a new run started. This is not
an HTTP capacity failure or evidence to relax monitoring guards.

A real grading probe on the dedicated benchmark account verified Free-plan
rejection, temporarily enabled the existing Pro plan through the native account
operation, and restored the plan plus original allowance values in a finally
block. Exact-answer calibration plus four concurrent requests all returned
correct diagnostics in 133–211 ms. One genuinely non-exact answer exercised
inference and dictionary search, returning 200 in 1,435 ms. No learning review
was submitted by this grading probe. These are branch/latency checks, not a
provider percentile benchmark. Native production OpenAPI was fetched internally
and compared with the ledger: all 36 operations match, none missing or obsolete.

GitHub run `39366334285` for the search commit completed successfully, including
backend, frontend, security, image and e2e jobs. VPS operational smoke/observation
tests also passed: 3 tests and 9 subtests; deployment shell syntax and diff
whitespace checks passed. Native inspection confirmed the temporary registry
credential directory was removed after deployment.

## Deployed anchor-filter HTTP capacity

The comparable six-API search run on `dbaaea89` retained the original three-query
fixture and all thresholds. Full two-minute plateaus:

| RPS | Requests | p95 ms | p99 ms | Non-200 |
| --- | --- | --- | --- | --- |
| 50 | 5,992 | 154.11 | 228.09 | 0 |
| 100 | 11,992 | 163.30 | 204.68 | 0 |
| 200 | 23,997 | 182.92 | 293.83 | 0 |

The 400-RPS plateau was truncated by native latency abort: p95 307.70 ms,
p99 443.92 ms across 36,883 plateau requests, eight genuine 503 responses,
zero drops and 86 interrupted iterations at abort. Recovery did not start.
The run remains failed (exit 99). All eight 503s coincide with native Uvicorn
`Exceeded concurrency limit.` warnings; there were no corresponding application
completion 5xx logs. This warrants a bounded native concurrency comparison,
not suppression of errors or removal of the protective limit. The current limit
is 64 and includes connections as well as active requests.

Routing was restored to the exact two-blue-upstream file
`d769de5d36181bad0a0e1fec64c9f47e41dbe173938dc4d59ce609f1cfed486f` and
confirmed in Caddy's live admin configuration. Public curl readiness returned 200.
A Python-default-user-agent request through Cloudflare returned 403; this is
retained separately from application readiness and does not justify changing WAF.
A fresh bounded six-API routing window now runs the independent short-query
fixture (`a`, `b`, `the`), with a distinct derived dataset hash.

### Short-query capacity and conservative length candidate

The v4 six-API short-query run (`20261020T041417Z-search`, fixed equal mix
`a`, `b`, `the`, unchanged native concurrency 64) completed the 50/100/200 RPS
plateaus. Their p95/p99 milliseconds were 171.17/284.17, 173.73/278.82 and
210.26/323.60. The 200-RPS plateau had one timeout in 23,997 requests; no drops
occurred through 200. At 400 RPS the test failed and aborted before completing
its plateau: 9,130 dropped iterations, 2,237 errors in that scenario, and
roughly seven API CPU cores. Recovery was not started. This is not a passing
400-RPS capacity result. Routing was restored and its exact original SHA-256
`d769de5d36181bad0a0e1fec64c9f47e41dbe173938dc4d59ce609f1cfed486f`
was checked after the native routing process exited 143.

Three focused regression tests demonstrate remaining unnecessary Python
pattern checks: `b` against `{sth} b`, `the` against `{sth} the`, and `book`
against `{sth} bookstore`. All three failed on v4 before the candidate edit.
The candidate stores a conservative minimum surface length in a Tantivy fast
field and adds a native numeric range clause; each slot contributes only one
character and shorter licensed head forms remain allowed. Full matching and
ranking are unchanged. The index directory changes to v5, retaining the old
v4 derived index for rollback. The existing pagination fixture now uses
same-length `home`/`hand` candidates so it continues exercising pagination,
rather than having its deliberately false candidates removed by length.
Unit search/text tests: 65 passed; search integration/telemetry/budget tests:
17 passed. Production-copy timing/equality and broader checks remain required
before accepting or deploying this candidate.

The v5 candidate was also built from the 223,369-document production v4
snapshot in a temporary directory (27.216 s), then compared with the unchanged
v4 runtime for 19 queries. Every ordered DTO list was equal. Illustrative
native timings: `give Jo a hand` 32.216 ms before, 11.882–12.200 ms after;
`book of my own` 19.159 vs 11.080–11.715 ms. One-character queries improved
only slightly (`a` 15.563 vs 14.383–14.781, `b` 19.265 vs 17.769–17.917).
These are native timings, not HTTP capacity. The temporary copy was removed
by TemporaryDirectory; the live index was not modified. Full backend suite:
600 passed, one existing deferred Taskiq compatibility skip, 15 upstream
warnings. Focused exact-match assertions were rerun after strengthening the
shorter-head test: 24 passed. Source committed as
`782aa9d5b9960c126aee72beffdbe4279d8f3e07`; production remains v4 during the
isolated concurrency comparison.

All six current v4 API containers were recreated sequentially with native
Uvicorn concurrency 128, verified by Docker command and internal readiness.
Other application configuration, image, worker, pool and resource limits are
unchanged. A fresh bounded six-API routing window now measures the original
hello/hel/book HTTP capacity workload for comparison with concurrency 64.

### Completed concurrency comparison

Run `20261020T042629Z-search` used the same v4 source, ordinary search fixture,
six API containers, pools and limits, with Uvicorn concurrency 128. It completed
all four plateaus and recovery: p95/p99 ms 127.66/170.24 at 50 RPS,
154.13/272.93 at 100, 166.72/277.88 at 200, and 295.98/452.04 at 400.
All 98,962 business requests returned 200. However 109 iterations were dropped
at 400 RPS, so the native test exited 99 and does not prove sustainable 400 RPS.
This removes the earlier native concurrency rejection, but does not create CPU
capacity. Deployment/config snapshots were equal before and after; original
2-blue routing was restored to SHA d769de5d36181bad0a0e1fec64c9f47e41dbe173938dc4d59ce609f1cfed486f.
CI run 39369566862 for source 782aa9d completed successfully, including E2E.
After session resumption, native Docker confirmed the same v4 six-container
experiment still running, no routing window marker, original 2-blue ingress,
4,338 MiB MemAvailable and zero swap used. No load generator or old monitoring
tunnel remained running; new ones are tracked separately.

### Application-read pool starvation and root-cause regression

Run `20261020T155257Z-app-read` kept the v4 source, six APIs, concurrency
128 and pool 3. At 50 RPS it completed 5,991 plateau requests with p95/p99
174.687/286.810 ms and no errors or drops. The 100-RPS scenario aborted:
51 errors in 7,061 requests; its truncated plateau p99 was 2,081.954 ms.
200/400 RPS and recovery did not run. Native logs identify checkout timeouts
across senses, schedule, conversations, discovery and usage, plus a search
owner failure. CPU was not exhausted; API usage around 50 RPS was 1.25 cores.
Original two-blue ingress was restored; the exact routing hash was checked
again after the run. Six-API application capacity is not yet accepted.

A real PostgreSQL regression with pool size 1, overflow 0 and checkout timeout
0.2 seconds failed for all three paths: sense summaries, summaries with
examples, and word previews. Each request already held a connection while
content hydration opened a second session against the same pool. Concurrent
requests can occupy all slots and then wait for one another. Hydration now
borrows the caller's session without closing or committing its transaction;
standalone content reads keep their existing session ownership. All three
regressions pass, as do the existing content-cache tests (17 total focused
checks). Library, search, preparation and assistant integration checks passed
71 tests before adding the final runtime search retry test.

Search reconciliation now treats SQLAlchemy pool checkout timeout as transient,
like its existing DBAPI retry path. A real one-connection saturation test
verifies the same owner survives and publishes the queued word after the
request releases the connection. Bootstrap retry checks cover both exception
types. These three focused checks pass. No pool increase or capacity claim
is substituted for fixing the nested checkout.

The complete backend regression suite passed: 605 tests, one existing Taskiq
compatibility skip and 15 upstream deprecation warnings. Ruff and formatting
checks passed for all changed files; content/session ownership and search
error paths were reviewed. Source `1ef3690fb5b0b738f65119b65bb6bbbabcc171d2`
was committed and pushed. A clean-archive image was built and published as
`sha256:29ea65bf00140cd5d3c4ecfe97afe35341f7755347ff6c5dd08793422c0c84d6`;
Trivy 0.75.0 passed with the existing exception policy and no added exceptions.
Unfiltered scan and CycloneDX SBOM are retained privately. Production has not
yet been switched to this image. The unhealthy blue-2 reader was restarted
with its unchanged source/configuration; internal readiness returned 200.

Before the pool-fix deployment, native monitoring preflight returned safe:
MemAvailable 51.88%, largest container memory ratio 52.68%, zero job/WAL
backlog and telemetry age 6.97 seconds. The candidate image was pulled to the
VPS by immutable digest using temporary registry credentials, removed after
the pull. The live two-replica controller received only the already-reviewed
480-second command deadline and native worker-process startup count check;
its original file is retained root-only at
`/srv/pycil/deploy/controller-before-pool.sh`. Replica topology and traffic
remain unchanged pending CI E2E and the subsequent isolated capacity run.

CI run `39454447082` completed successfully for source `1ef3690`: security,
frontend, backend, image and E2E all passed. The existing native two-replica
controller is now deploying the scanned pool-fix/v5 image with concurrency
128 and unchanged pool 3 / checkpoint 2 and worker M2/K4. Experimental extra
replicas still run the old source until the deployment completes; no capacity
load is valid during this mixed-source window. A separate bounded native
resource observer records this overlap; it is not the final 12-API rollout
headroom drill.

The native deployment completed successfully at approximately 16:28:55 UTC:
active green, source `1ef3690fb5b0b738f65119b65bb6bbbabcc171d2`, no pending
switch, retired blue APIs stopped cleanly. Both candidate APIs passed explicit
readiness and authenticated account/search smoke; both native worker processes
started. The new v5 index built in 27.848 seconds. All four observation gates
had zero errors; API-side mean time was 10.43–11.22 ms under smoke traffic.
This is not a capacity measurement. Maximum observed overlap was eight APIs
(two old blue, two new green, four experimental readers); minimum observed
MemAvailable at this point was 45.743%. Native PostgreSQL inspection during
overlap showed 33 idle client backends and one active administrative check.
The four experimental readers are now being replaced with the same candidate
image before any isolated capacity workload.

All six API readers and worker were then verified on source `1ef3690`; both
mounted configuration copies retained SHA-256 `6bdf9e9acfddd0241aa61e865fc3e0cd5aff4a5e0b0c6e45cd37321e3de652d8`.
The final deployment observer recorded 40 samples across 591.6 seconds, maximum
eight overlapping APIs and minimum host available memory 45.743%; this does not
replace the required twelve-API final rollout test.

The comparable six-API application-read repeat `20261020T163036Z-app-read`
exited 99 through native overload thresholds. Full 50/100-RPS plateaus had
5,992/11,991 requests, p95 168.50/176.11 ms, p99 217.79/402.71 ms, zero drops;
100 RPS included four HTTP 502 responses. The 200-RPS plateau was truncated:
10,716 plateau requests, p95 1,978.08 ms, p99 2,282.12 ms, 224 errors and
80 scenario drops. Neither 400 RPS nor recovery started. Preserve this failure;
the nested-checkout fix does not establish application-wide 200-RPS capacity.
Native API logs identify pool acquisition timeouts across endpoint families,
with Discovery contributing most errors. Late-load resource samples show API
CPU approaching one core each while PostgreSQL uses approximately 0.63 core
and more than 50% host memory remains available. This motivates isolated CPU /
query-construction diagnostics before changing connection budgets again.
After the generator completed, the owned route-window PID was verified by its
exact command and terminated. The SSH observer returned 255, but native Caddy
admin inspection independently confirmed the original two green upstreams;
the persisted upstream SHA-256 is `45734337dc5502cb816a55536f02fc8bd51af2816f04b888898e06adc20e3707`.

An isolated, read-only Discovery diagnostic used an extra short-lived Python
process inside the unchanged API container, outside any capacity workload.
Native cProfile attributed most CPU to rebuilding SQLAlchemy alias-column
proxies (20,500 proxies across 100 calls). A same-process comparison then
executed 100 original and 100 candidate reads, asserting complete result
equality on every call. Original: 3.836 seconds wall / 3.540 seconds process
CPU; candidate: 1.425 seconds wall / 0.966 seconds CPU. The candidate reuses
only authorization expression trees with typed request bind parameters;
PostgreSQL still checks current paths and permissions on every read. No result
or permission cache was introduced. This diagnostic is not HTTP capacity.
All 32 library integration tests passed, including alternating anonymous,
owner and stranger Discovery reads and immediate publication revocation.
The candidate is not yet deployed or accepted from this microbenchmark alone.

The Discovery expression-reuse change passed all 68 library, assistant and HTTP
integration checks plus Ruff/formatting/diff checks. Review confirmed unchanged
candidate batching, materialized scoped candidates, ordering, pagination and
live parent visibility; no caller signatures changed. Committed and pushed as
`5ec7b9eafbb5a51898e8161d01ae634454954f35`; CI run `39459861070` is in progress.
Production remains on `1ef3690` pending release validation. Full backend tests
are running separately; do not infer their result from the focused suite.

The complete backend suite on `5ec7b9e` passed: 605 tests, one existing Taskiq
compatibility skip, 15 upstream deprecation warnings, 117.82 seconds. The
clean-archive candidate image built successfully; scanning and remote CI
remain required before native deployment.

The native six-replica Compose topology is now installed for validation on the
unchanged `1ef3690` release. Each experimental reader was replaced one at a
time by its corresponding `api-green-3` through `api-green-6` service; all
passed explicit readiness before their experimental counterpart was stopped
and removed. Caddy validation passed and its live admin API confirms exactly
six green targets. Native operational files match the reviewed local candidate
hashes; originals and original two-target routing are retained root-only in
`/srv/pycil/deploy/operational-before-capacity`. This is a provisional topology,
not final acceptance of load, overlap, drain or rollback requirements.

Two bounded genuine cold word generations succeeded on the native M2/K4
worker: the first accepted in 445.08 ms and was observed successful after
18.42 seconds (native execution 16.04 s / queue 4.16 ms). The second accepted
in 124.55 ms and completed after 27.66 seconds (native execution 25.75 s /
queue 3.43 ms). Both returned readable generated senses and became visible
through the ordinary search API. No paid retry or fabricated provider was used.

The first manual worker restart happened after that job had already completed;
its 1.305-second restart is NOT an in-flight drain test. A separate second run
polled the native job to `running` before immediately requesting Docker restart
with its 330-second native stop budget. Restart took 26.384 seconds. Native
logs prove the task began at 16:51:47.130771 UTC; the idle sibling shut down
at 16:51:48, while the busy sibling finished real provider calls and published
the word at 16:52:12.875491. Only then did it log `No more tasks to wait for.
Shutting down.` at 16:52:12.884322 and close resources. The replacement's two
native worker processes began listening at 16:52:26.008915 / .189354.
The job succeeded once with retained native results and search visibility.
This proves in-flight graceful drain without a replacement worker framework.
It does not imply exactly-once handling after a crash or provider guarantees.

CI run `39459861070` completed successfully: backend, frontend, security,
image and E2E passed (live paid-provider CI and Sonar steps remained skipped
by the existing workflow conditions). The scanned Discovery image is
`ghcr.io/qninhdt/pycil-api@sha256:6feafa0c156272dd9f6c08614a217a693ba549d6707e5fb6ddf4e1efee9ec98d`.
The unchanged native six-replica controller began its production deployment.
All twelve APIs were observed running; all six candidate APIs passed readiness
and independently minted Clerk-authenticated account/search smoke before the
traffic switch. Observation and retirement are still in progress.

During twelve-API overlap, minimum observed MemAvailable so far is 36.90%
(approximately 2.86 GiB), above the 2-GiB headroom target. Five consecutive
`vmstat` samples showed no swap-in/out. Host swap contained 18,284 KiB of cold
pages, including 12,693,504 bytes charged to PostgreSQL; this is not zero swap
occupancy or evidence of active thrashing. Actual Docker memory/swap limits
for PostgreSQL, API and worker already match their equal no-additional-swap
ceilings; no further limit change or data-store restart was warranted.


## Interrupted six-replica switch and verified recovery

The initial discovery-release SSH transport disconnected after Caddy switched
to blue but before acceptance committed. Authoritative inspection found active
green, pending blue, twelve healthy APIs, the new worker, and an available
deployment lock with no remote controller. The observer's timeout alone was not
used as proof of termination. Its 38 samples retain the twelve-API overlap and
minimum 36.90% available memory; this was not an accepted deployment.

At 17:09 UTC the documented recovery ran under the deployment lock: all six
recorded green APIs passed readiness; the saved previous route was validated
and reloaded; the worker returned to the recorded green image and both native
processes logged Listening started. Authenticated account/search and public
readiness/search smoke passed before removing pending and stopping all six blue
APIs. Interrupted state and actual Caddy configuration are retained root-only
at `/srv/pycil/deploy/interrupted-20261020T170900Z`. No database restore or
downgrade occurred. A fresh native deployment is now observed over SSH with
keepalive; acceptance still requires the controller's successful terminal exit.


## Completed six-replica discovery deployment

The retry terminated successfully: `deploy completed; active=blue` at source
`5ec7b9eafbb5a51898e8161d01ae634454954f35`. Live inspection confirms no pending
marker, six healthy blue APIs on digest
`6feafa0c156272dd9f6c08614a217a693ba549d6707e5fb6ddf4e1efee9ec98d`,
and all six retired green APIs stopped. The native worker command is two
processes / four asynchronous tasks per process. The bounded retry observer
retained 73 samples; minimum available-memory ratio was 36.3937%.
Authenticated candidate checks and the full native public observation gate
passed. This proves deployment acceptance, not final capacity acceptance.

A fresh identical ten-route application-read capacity run starts against this
source with six APIs and idle M2/K4 worker. No routing, quota, pool or code
changes are permitted during this comparison.


## Remaining pattern candidate worst case

A local synthetic fixture (not the production corpus or VPS) explicitly
confirms linear fallback matching remains possible. Distinct entries with the
same `{sth} in {sth}` pattern all survive head/anchor/minimum-length filtering
for `alpha in beta gamma delta epsilon zeta eta theta`, but the seven-word
tail violates the five-word slot bound. At 100 / 1,000 / 5,000 documents the
matcher was called exactly 100 / 1,000 / 5,000 times, returned no hits, and took
14.466 / 121.495 / 615.468 ms on the local workstation. This is adversarial
algorithm evidence, not a claim that the production corpus has this distribution
or that its HTTP requests take those times. The existing result limit does not
bound candidate work. Production adversarial latency remains to be measured
separately after the unchanged application-read capacity run.


## Discovery-fix application capacity

`20261020T172314Z-app-read`, six native APIs / M2K4 idle worker,
source 5ec7b9e, completed the full 50/100/200-RPS plateaus with no errors
or drops: p95/p99 ms 150.71/186.37, 138.58/165.33 and 172.72/349.40.
The 200-RPS plateau completed 23,998 real requests. The 400-RPS stage
failed: truncated plateau 11,839 requests, p95 2,229.02 ms / p99
2,445.99 ms, 1,655 non-200; whole stage 1,745 failures and 10,248 dropped
iterations. Native abort exited 99; automatic recovery scenario never ran.
Public readiness subsequently returned 200. Keep this failed run.

Native API logs confirm database_pool_timeout during overload, while API
processes approach a CPU core each and PostgreSQL averages below one core.
This is not evidence that increasing PostgreSQL connections creates capacity.
The prior app mix failed already at 200 RPS; the new immutable expression
templates now sustain that full stage. Final mixed-load/recovery and a
comparable worker-container topology check remain open.


## Equal-budget worker container experiment

The accepted worker normally has one container / two execution processes /
four async tasks each, with 2 CPUs / 1 GiB total. A new same-release baseline
settled all 32 cached jobs in 3.143 s observed, median native execution
0.265 s and queue 0.724 s. An earlier attempt stopped at its initial profile
read with HTTP 401 after the operator's paused interval; it submitted no jobs.
A dedicated-session token refresh preceded the measured baseline.

A temporary native Compose overlay now compares two containers / one execution
process / four tasks each, with 1 CPU / 512 MiB per container: identical total
CPU, memory and task concurrency. Both logged native Listening started; no API
configuration changed. The first 32-job batch settled in 2.833 s (execution
median 0.250 s / queue 0.779 s). The warm batch settled in 2.812 s (execution
0.210 / queue 0.305 s). Each container used about 278 MiB after startup, with
zero restarts and no OOM. Repeated warm batches and restoration/repeat of the
one-container case are required before selecting the final layout. Polling
quantizes observed batch time; native execution/queue values remain separate.

The split-worker warm r2/r3 runs overlapped a bounded API workflow probe, so
they are contention evidence, not isolated topology comparisons. All 64 jobs
succeeded. The 32-cycle / concurrency-four workflow also passed every response
and cleanup assertion in 11.74 seconds. Route p95: membership 249.88 ms, copy
247.82, move 248.90, scoped search 189.92. One-request account/profile/vocabulary
checks remain smoke measurements. A separate isolated split-worker repeat follows
after both probes settle; neither overlapping run replaces the isolated baseline.


## Worker layout comparison completed

Isolated warm repeats: two containers / one process / four tasks each settled
32 cached preparations in 2.788 s (native execution median 0.230 s, queue 0.367 s).
After restoring one container / two processes / four tasks each, its first batch
settled in 2.853 s and its isolated warm repeat in 2.897 s (execution 0.245 s,
queue 0.328 s). All succeeded, fixture parents were deleted and learning settings
restored. These differences do not establish meaningful throughput superiority.
Select two containers for independent replacement, retaining the same combined
2 CPU / 1 GiB / eight-task ceiling. The native deployment controller now replaces
them sequentially and requires each replacement's startup log and unchanged live
container start time before proceeding. Native production acceptance follows.


Native split-worker installation completed with the deployment lock and no pending
switch; Redis pending/lag were both zero before replacement. The new second
container was started first, then the old container drained/replaced; both native
startup checks passed at 1 CPU / 512 MiB each, zero OOM/restarts. The first final
32-job batch settled successfully in 2.828 s (execution median 0.255 s, queue
0.737 s); this is a cold-start batch, not the isolated warm comparison above.
Operational rollback copies are private under
`/srv/pycil/deploy/worker-layout-20261020T203349Z/`. API routing was unchanged
until a separate four-API comparison window began.


## Final-source replica comparison

`20261020T203456Z-app-read`, four routed APIs on source 5ec7b9e, same
application/checkpoint pools, idle two worker containers. Full 50/100-RPS
plateaus passed: 5,992 / 11,993 requests, p95 149.87 / 153.45 ms and p99
173.47 / 177.64 ms, zero failures/drops. The 200-RPS stage aborted: 8,136
completed requests including its ramp, 1,387 errors and 194 dropped iterations;
truncated plateau p95/p99 2,254.01 / 2,521.29 ms. Neither 400 nor recovery ran.
Its route window was explicitly terminated; the restore trap returned all six
blue upstreams and readiness was 200. This supports six APIs over four for the
application mix: the six-API final-source run passed a full 200-RPS plateau.

## Actual-index adversarial diagnostic

The production v5 index contains 53,712 pattern documents, not fewer than
20,000 as an initial diagnostic guard assumed. That guard stopped two attempts
before query measurements; these are not search failures. A bounded read-only
process then evaluated 50 distinct actual-pattern/literal/long-query cases.
The slowest native call was 100.94 ms for twenty repeated `the` tokens (31
matcher calls, no hits); the adversarial `alpha in beta gamma delta epsilon
zeta eta theta` took 53.61 ms (39 matcher calls, no hits). A generated `out for`
case took 49.79 ms with 150 matcher calls. This is a sampled adversarial
diagnostic on the real index, not an exhaustive bound or an HTTP load result.
There is still no hard bound on candidates matching the indexed filters.


## Final mixed workload and split-worker drain

`20261020T204242Z-mixed` passed the native steady scenario: 15-second ramp,
three minutes at 200 reads/s and 75 seconds recovery at 10/s. Equal shares of
DB reads, dictionary search and ten application read routes; all 38,324
requests had correct responses, zero HTTP failures/drops/interrupted iterations.
Overall p95/p99 218.67 / 438.43 ms; steady-only 220.34 / 441.97 ms. Mounted
configuration and API/worker identities were unchanged; available RAM stayed
at least 46.94%, and each worker remained below 56% of its 512-MiB quota.

During the steady interval, all 32 cached preparations succeeded (observed
4.208 s, native execution median 0.325 s / queue 0.996 s). Four concurrent
real assistant streams completed in 3.43–3.99 s with persisted checkpoint
messages and owned conversation cleanup. Three fresh-sense reviews applied;
repeating the same body/idempotency key returned an identical receipt and
progress was three. Their temporary deck was deleted and learning settings
restored. The 32-cycle/concurrency-four library workflow also preserved every
contract/cleanup assertion, but mutation tail latency increased: PATCH p95
994.72 ms, membership 790.96, copy 762.53, move 568.84. These writes do not
pass the 300-ms latency target; read-only success does not erase that limit.
Trace diagnosis and separate final rare-route checks remain open.

After the mixed run was terminal, one real cold generation was observed running
before restarting its identified executing container `worker-1`, while
`worker-2` stayed available. Native Docker restart took 44.30 s including task
drain and replacement startup; the job subsequently returned succeeded, a
nonempty word and ordinary search publication. Total observed job interval
48.04 s, no OOM/restarts on either worker. This proves this graceful in-flight
case, not exactly-once behavior on crashes. No deployment ran during this drill.

### Per-route acceptance and checkpoint-pool comparison preparation

The final mixed run's aggregate latency pass does not pass every endpoint.
The endpoint ledger now records the actual per-route samples: senses p95
415.95 ms, activity 366.72 ms, discovery p99 919.42 ms and schedule p99
915.22 ms exceed the unchanged route latency targets. Shared k6 options now
apply native p95 <300 ms / p99 <800 ms thresholds separately to every bounded
business route. Native pinned k6 inspection resolved all 14 routes for mixed;
the preflight was corrected to visit all 30 mixed slots (all ten app routes),
rather than just its first ten slots. Six contract tests and four deployment
unit tests pass. These gates strengthen reporting; they do not change the load
or retroactively change the earlier native exit status.

The real PostgreSQL checkpoint pool checkout/exhaustion/recovery test now runs
with maximum sizes 1 and 2; both pass (2 passed, 8 deselected). This permits a
controlled application/checkpoint 4/1 comparison within the rollout connection
budget, but does not prove its throughput or concurrent streaming behavior.


## Wrap-up at the user's request — 21 October 2026

Further optimization is stopped. Keep six single-process API containers and two
single-process Taskiq worker containers, each accepting four async jobs. Keep
application/checkpoint pools 3/2, zero application overflow, Caddy CPU ceiling 1,
and native Tempo memory limiting. The 4/1 pool comparison and isolated senses
profile were prepared but never executed or activated; their unused drafts were
deleted. The temporary checkpoint-size test parameterization was also removed.
The existing reusable pool behavior test remains unchanged.

The original raw lesson-21 comparator, three repeated passing raw runs and
cached-production correctness fixes are retained. The capacity extension has
stronger mixed/job/stream/drain evidence, but not every route passes the latency
SLO. No additional tuning or benchmark run is scheduled after this wrap-up.
Local sanitized evidence is retained; S3 transport is deferred by the user.
Independent learner defense is not implied by assisted execution.


Final operational verification: native rollback to 1ef3690 and native redeploy to
5ec7b9e both completed successfully with the split-worker controller. Redeploy
passed six authenticated candidate smokes, thirty public observation smokes and
four Prometheus acceptance checks with zero observed errors. Active=blue, no
pending switch, six healthy blue APIs and two running workers; all retired green
APIs stopped. Twelve-API overlap was observed: available host RAM stayed above
30.79% during rollback and 35.21% during redeploy. Mounted configuration stayed
at SHA-256 6bdf9e9acfddd0241aa61e865fc3e0cd5aff4a5e0b0c6e45cd37321e3de652d8.

The dedicated benchmark Clerk session was revoked; reusable bearer values were
removed from its working fixture/auth files. Existing JWTs are not claimed
instantly invalidated by that session revocation. No load generator or route
window remains. The owned monitoring SSH tunnel and resource observers stopped;
unused remote capacity overlays, profiler and temporary deployment wrapper were
removed. Production data, retained immutable releases and operational recovery
records were preserved. No S3 upload was attempted.

Final narrow checks: four infrastructure unit tests, six performance contract
checks, two runner guard tests and Bash syntax passed. The runner tests were
first invoked with the machine's Python 3.10 and failed to import datetime.UTC;
rerunning with the project's Python 3.14 passed. This was a local interpreter
selection error, not a product failure. No new benchmark or profiling run was
started after the user's stop instruction. Production configuration/controller
changes remain in the working tree for publication; automatic trusted-branch
CD is still disabled, as recorded in the VPS delivery runbook.
